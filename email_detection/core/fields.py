"""Structured financial-field extraction from free text.

CRITICAL DESIGN POINT
---------------------
This module is used on BOTH sides of the tamper comparison:

  * when loading exchange filings into the database (ground truth), and
  * when parsing the message a user submits (the claim).

Using one parser for both is what makes the comparison meaningful. If the
filings loader read "Rs. 6.70" as 6.7 but the message parser read it as 670,
every comparison would be noise. Any change here changes both sides together.

Everything is deterministic regex plus dateutil. No LLM. Per the project rule:
models extract prose, Python compares numbers.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from dateutil import parser as dateparser

from core.textnorm import normalise_for_matching

# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------

# "Rs. 6.70 per share", "Rs 4/- per equity share", "INR 2.50 per share",
# "Rs.10/- per equity share of Re.1 each"
_DIVIDEND_RE = re.compile(
    r"(?:rs\.?|inr|₹|rupees)\s*\.?\s*"
    r"(?P<amount>\d{1,3}(?:,\d{2,3})*(?:\.\d{1,4})?|\d+(?:\.\d{1,4})?)"
    r"\s*(?:/\-|/=|/)?\s*"
    # \s* not \s+ throughout: OCR on a compressed screenshot loses spaces, so
    # the same sentence arrives as "Rs125perequityshare". Requiring whitespace
    # meant no dividend was extracted from any screenshot, which removed the
    # anchor the filings matcher needs and sent every image to UNVERIFIED.
    r"(?:per|a|each)\s*(?:equity\s*|ordinary\s*)?share",
    re.I,
)

# The reverse order: "dividend per share of Rs 4"
_DIVIDEND_RE_REVERSE = re.compile(
    r"dividend\s+(?:of\s+)?(?:rs\.?|inr|₹)?\s*"
    r"(?P<amount>\d{1,3}(?:,\d{2,3})*(?:\.\d{1,4})?|\d+(?:\.\d{1,4})?)"
    r"\s*(?:/\-)?\s*per\s*(?:equity\s*)?share",
    re.I,
)

# Percentage-of-face-value form, very common in Indian filings:
# "final dividend of 200% (Rs. 4 per equity share of face value Rs 2)"
_DIVIDEND_PCT_RE = re.compile(
    r"(?P<pct>\d{1,5}(?:\.\d{1,2})?)\s*%[^.]{0,80}?face\s+value[^.]{0,30}?"
    r"(?:rs\.?|inr|₹)\s*(?P<face>\d+(?:\.\d{1,2})?)",
    re.I,
)

_AMOUNT_ANY_RE = re.compile(
    r"(?:rs\.?|inr|₹|rupees)\s*\.?\s*"
    r"(?P<amount>\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"\s*(?P<scale>lakh|lakhs|lac|crore|crores|cr|k|thousand)?",
    re.I,
)

_SCALE = {
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5,
    "crore": 1e7, "crores": 1e7, "cr": 1e7,
    "k": 1e3, "thousand": 1e3,
}


def _to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def extract_dividend_per_share(text: str) -> float | None:
    """Rupees of dividend per equity share, or None if not stated.

    Returns None rather than guessing: an absent dividend must never be
    compared as if it were zero.
    """
    if not text:
        return None
    for rx in (_DIVIDEND_RE, _DIVIDEND_RE_REVERSE):
        m = rx.search(text)
        if m:
            val = _to_float(m.group("amount"))
            # Sanity bound: per-share dividends above Rs 10,000 are effectively
            # unheard of and almost always a misparse of a total payout figure.
            if val is not None and 0 < val <= 10_000:
                return val
    m = _DIVIDEND_PCT_RE.search(text)
    if m:
        pct, face = _to_float(m.group("pct")), _to_float(m.group("face"))
        if pct is not None and face is not None:
            val = round(pct / 100.0 * face, 4)
            if 0 < val <= 10_000:
                return val
    return None


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
)

# Textual: "Friday, July 10, 2026" / "10 July 2026" / "July 10, 2026"
# \s* rather than \s+ for the same OCR reason as the dividend pattern:
# "fixed asFriday,July24,2026" must still yield a date. The four-digit year
# requirement keeps this from matching stray number runs.
_DATE_TEXT_RE = re.compile(
    rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s*(?:{_MONTHS})\.?\s*,?\s*\d{{4}}"
    rf"|(?:{_MONTHS})\.?\s*\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s*\d{{4}})",
    re.I,
)
# Numeric: 10.07.2026 / 10-07-2026 / 10/07/2026 / 2026-07-10
#
# A FOUR-DIGIT YEAR IS MANDATORY. Allowing two-digit years made this pattern
# match clock times such as "5.00.00 P.M.", and dateutil then filled the missing
# components from today's date -- producing filings that appeared to have a
# record date of "today". Requiring the year removes that entire failure class,
# at the cost of missing the rare "10.07.26" filing, which is the right trade
# when the output feeds a tamper comparison.
_DATE_NUM_RE = re.compile(
    r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})"
)

# Sentinel whose fields are all implausible for a real filing, so anything
# dateutil silently defaults is detectable afterwards.
_DEFAULT_SENTINEL = datetime(1900, 1, 1)


def _parse_one(raw: str) -> date | None:
    raw = raw.strip().rstrip(".,;")
    # dayfirst=True suits Indian filings (DD/MM/YYYY) but corrupts ISO strings:
    # dateutil reads the tail of "2026-07-10" as day-month and returns 7 October.
    # Detect the unambiguous ISO shape and parse it day-last.
    dayfirst = not re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", raw)
    try:
        parsed = dateparser.parse(raw, dayfirst=dayfirst, fuzzy=False, default=_DEFAULT_SENTINEL)
    except (ValueError, OverflowError, TypeError):
        return None
    # Second guard: if the string carried no year of its own, the sentinel's
    # year survives and we reject rather than invent one.
    if parsed.year == _DEFAULT_SENTINEL.year:
        return None
    return parsed.date()


def find_dates(text: str) -> list[tuple[date, int, int]]:
    """Every parseable date with its character span, in order of appearance."""
    if not text:
        return []
    out: list[tuple[date, int, int]] = []
    for rx in (_DATE_TEXT_RE, _DATE_NUM_RE):
        for m in rx.finditer(text):
            parsed = _parse_one(m.group(0))
            if parsed and 1990 <= parsed.year <= 2100:
                out.append((parsed, m.start(), m.end()))
    out.sort(key=lambda t: t[1])
    # Drop overlapping duplicates (a textual match can contain a numeric one).
    deduped: list[tuple[date, int, int]] = []
    for item in out:
        if deduped and item[1] < deduped[-1][2]:
            continue
        deduped.append(item)
    return deduped


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Compile a keyword so intervening whitespace is optional.

    OCR output runs words together ("RecordDatefor determining"), so a literal
    search for "record date" finds nothing and the date beside it is lost.
    Matching /record\\s*date/ finds it either way.
    """
    return re.compile(r"\s*".join(re.escape(part) for part in keyword.split()), re.I)


@functools.lru_cache(maxsize=256)
def _cached_keyword_pattern(keyword: str) -> re.Pattern[str]:
    return _keyword_pattern(keyword)


def _date_near(text: str, keywords: list[str], window: int = 160) -> date | None:
    """First date appearing within `window` chars after any keyword.

    Falls back to a date shortly BEFORE the keyword, which covers the very
    common Indian filing phrasing "fixed Friday, July 10, 2026 as the Record
    Date" where the date precedes its label.
    """
    if not text:
        return None
    low = text.lower()
    for kw in keywords:
        for m in _cached_keyword_pattern(kw).finditer(low):
            after = text[m.end(): m.end() + window]
            hits = find_dates(after)
            if hits:
                return hits[0][0]
            before = text[max(0, m.start() - window): m.start()]
            hits = find_dates(before)
            if hits:
                return hits[-1][0]
    return None


def extract_record_date(text: str) -> date | None:
    return _date_near(text, ["record date", "record-date"])


def extract_meeting_date(text: str) -> date | None:
    return _date_near(
        text,
        ["annual general meeting", "extra-ordinary general meeting",
         "extraordinary general meeting", "general meeting will be held",
         "meeting is scheduled", "agm", "egm"],
    )


def extract_evoting_window(text: str) -> tuple[date | None, date | None]:
    """(start, end) of the remote e-voting period.

    Typical phrasing: "remote e-voting period commences on Saturday, 8 August
    2026 at 9:00 A.M. and ends on Monday, 10 August 2026 at 5:00 P.M."
    """
    if not text:
        return None, None
    low = text.lower()
    anchor = None
    for kw in ("e-voting", "e voting", "evoting", "remote voting"):
        idx = low.find(kw)
        if idx >= 0:
            anchor = idx
            break
    if anchor is None:
        return None, None

    segment = text[anchor: anchor + 600]
    seg_low = segment.lower()

    start = end = None
    for kw in ("commenc", "begin", "start", "from"):
        i = seg_low.find(kw)
        if i >= 0:
            hits = find_dates(segment[i: i + 200])
            if hits:
                start = hits[0][0]
                break
    # NOTE: a bare "to" is deliberately absent. It matched ordinary prose such
    # as "to hold office ... with effect from January 1, 2027" and pulled an
    # unrelated date in as the e-voting end.
    for kw in ("ends on", "ends at", "end on", "conclude", "upto", "up to", "till"):
        i = seg_low.find(kw)
        if i >= 0:
            hits = find_dates(segment[i: i + 200])
            if hits:
                end = hits[0][0]
                break

    if start is None or end is None:
        hits = find_dates(segment)
        if len(hits) >= 2:
            start = start or hits[0][0]
            end = end or hits[1][0]
    if start and end and end < start:
        start, end = end, start

    # Sanity bound. A remote e-voting window is a few days -- three is typical
    # and the regulations do not contemplate months. A span outside this range
    # means we latched onto an unrelated date elsewhere in a long notice (an
    # appointment taking effect "from January 1, 2027", for instance), so we
    # discard the end rather than record a value the tamper comparator would
    # then treat as ground truth.
    if start and end and not (0 <= (end - start).days <= 45):
        end = None
    return start, end


# --------------------------------------------------------------------------
# Identifiers and payment details
# --------------------------------------------------------------------------

CIN_RE = re.compile(r"\b([LUlu]\d{5}[A-Za-z]{2}\d{4}[A-Za-z]{3}\d{6})\b")
ISIN_RE = re.compile(r"\b(IN[EFD][0-9A-Z]{9})\b")
# SEBI registration numbers, in the real formats seen in SEBI's own registers.
SEBI_REG_RE = re.compile(
    r"\b(IN[ZAHMRPB][A-Z]?\d{6,9}"          # INZ/INA/INH/INM/INR/INP/INBI...
    r"|IN-DP-\d{2,4}-\d{4}"                  # depository participants
    r"|IN/(?:CRA|KRA|AIF\d?|VCF|FVCI)/[\w\-/]+"  # slash-form registrations
    r"|MF/\d{2,4}/\d{2}/\d{1,3})\b",
    re.I,
)
# A UPI address never has a dot AFTER the '@' -- handles are @ybl, @okhdfcbank,
# @valid. The SEBI validated format puts its category suffix before the '@'
# (zerodha.brk@valid). E-mail addresses always do have a dot after the '@'.
# That single asymmetry separates the two cleanly, so the trailing lookahead
# rejects anything followed by a dot or further word characters.
# The two lookaheads are deliberately different. `(?!\w)` stops a partial match
# inside a longer token. `(?!\.[a-zA-Z0-9])` rejects an e-mail domain (@bank.com)
# while still accepting a handle that simply ends a sentence ("...@valid."),
# where the dot is punctuation rather than the start of a TLD.
UPI_RE = re.compile(r"\b([a-zA-Z0-9][a-zA-Z0-9._\-]{1,64}@[a-zA-Z][a-zA-Z0-9]{1,19})(?!\w)(?!\.[a-zA-Z0-9])")
IFSC_RE = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
# Indian bank accounts run 9-18 digits. The leading lookbehind also excludes
# letters, otherwise the digits inside an identifier such as INZ000031633 are
# harvested as an account number.
ACCOUNT_RE = re.compile(r"(?<![A-Za-z\d/-])(\d{9,18})(?![\d/-])")
PHONE_RE = re.compile(r"(?<!\d)((?:\+?91[\s\-]?)?[6-9]\d{9})(?!\d)")
PAN_RE = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b")
FOLIO_RE = re.compile(r"\b(?:folio\s*(?:no\.?|number)?\s*[:\-]?\s*)([A-Z0-9/\-]{4,20})\b", re.I)


def _trim_upi_local_part(upi_id: str) -> str:
    """Strip run-together prose from the front of a UPI address.

    OCR on a compressed screenshot loses spaces, so "pay Rs 250 processing fee
    to 9876543210@ybl" is read as one token and the regex captures
    "Rs250processingfeeto9876543210@ybl". The handle is still in there; the
    prefix is noise that would defeat any lookup.

    Two recoveries, both conservative:
      * a trailing run of 10+ digits is a phone-number UPI -- keep the last 10,
        which is the whole Indian mobile number;
      * otherwise keep the tail after the last capital-letter boundary, which
        is where a run-together word usually restarts.
    Anything we are not confident about is returned unchanged.
    """
    if "@" not in upi_id:
        return upi_id
    local, _, handle = upi_id.rpartition("@")
    if len(local) <= 24:
        return upi_id

    trailing_digits = re.search(r"(\d{10,})$", local)
    if trailing_digits:
        digits = trailing_digits.group(1)
        return f"{digits[-10:]}@{handle}"

    tail = re.search(r"([A-Z][a-zA-Z0-9._-]*)$", local)
    if tail and len(tail.group(1)) >= 3:
        return f"{tail.group(1).lower()}@{handle}"
    return upi_id


@dataclass
class ExtractedFields:
    """Everything structured we could pull out of a document.

    A field is None when it was not stated. It is never defaulted to zero or
    today's date -- absence and a value are different things to the comparator.
    """

    doc_type: str | None = None
    company_name: str | None = None
    cin: str | None = None
    isin: str | None = None
    sebi_reg_no: str | None = None
    dividend_per_share: float | None = None
    record_date: date | None = None
    meeting_date: date | None = None
    evoting_start: date | None = None
    evoting_end: date | None = None
    evoting_url: str | None = None
    upi_ids: list[str] = field(default_factory=list)
    account_numbers: list[str] = field(default_factory=list)
    ifsc_codes: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    folio_present: bool = False
    rta_name: str | None = None
    sender_claimed: str | None = None
    field_confidence: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        def enc(v):
            if isinstance(v, (date, datetime)):
                return v.isoformat()
            return v
        return {k: enc(v) for k, v in self.__dict__.items()}


DOC_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("EVOTING", ("e-voting", "evoting", "remote voting", "instavote")),
    ("DIVIDEND", ("dividend", "record date", "book closure")),
    ("EGM_NOTICE", ("extra-ordinary general meeting", "extraordinary general meeting", "egm", "postal ballot")),
    ("AGM_NOTICE", ("annual general meeting", "agm")),
    ("BOARD_MEETING", ("board meeting", "meeting of the board")),
    ("RESULTS", ("financial results", "quarterly results", "unaudited results")),
]


def classify_doc_type(text: str) -> str:
    low = (text or "").lower()
    for doc_type, keywords in DOC_TYPE_KEYWORDS:
        if any(k in low for k in keywords):
            return doc_type
    return "OTHER"


def extract_all(text: str, *, urls: list[str] | None = None) -> ExtractedFields:
    """Run every extractor over a block of text."""
    text = text or ""
    norm = normalise_for_matching(text, lower=False)

    start, end = extract_evoting_window(norm)
    cin = CIN_RE.search(norm)
    isin = ISIN_RE.search(norm)
    reg = SEBI_REG_RE.search(norm)

    upi_candidates = [_trim_upi_local_part(u) for u in UPI_RE.findall(norm)]

    # A 10-digit number beginning 6-9 is a mobile number, and mobile numbers are
    # not bank accounts. Without this, every message quoting a helpline number
    # would appear to contain payment details.
    phones = sorted(set(PHONE_RE.findall(norm)))
    phone_digits = {re.sub(r"\D", "", p) for p in phones}

    # Securities identifiers that merely LOOK like account numbers are excluded
    # here, at extraction, so NO downstream consumer can mistake one for a
    # payment destination. Filtering in money.py alone was not enough: the
    # tamper detector read a CDSL BO ID out of `account_numbers` and reported
    # "payment details in a corporate notice" on a genuine holdings statement.
    from core.lexicon.identifiers import NON_ACCOUNT_KINDS, mask_identifiers
    protected = {
        i.value for i in mask_identifiers(text).identifiers
        if i.kind in NON_ACCOUNT_KINDS
    }
    accounts = sorted({
        a for a in ACCOUNT_RE.findall(norm)
        if a not in phone_digits and a not in protected
    })

    return ExtractedFields(
        doc_type=classify_doc_type(norm),
        cin=cin.group(1).upper() if cin else None,
        isin=isin.group(1).upper() if isin else None,
        sebi_reg_no=reg.group(1).upper() if reg else None,
        dividend_per_share=extract_dividend_per_share(norm),
        record_date=extract_record_date(norm),
        meeting_date=extract_meeting_date(norm),
        evoting_start=start,
        evoting_end=end,
        upi_ids=sorted(set(upi_candidates)),
        account_numbers=accounts,
        ifsc_codes=sorted(set(IFSC_RE.findall(norm.upper()))),
        urls=urls or [],
        phones=phones,
        folio_present=bool(FOLIO_RE.search(norm)),
    )
