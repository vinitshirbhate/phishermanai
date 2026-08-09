"""Protected identifier pass -- runs BEFORE every chokepoint.

WHY THIS EXISTS
---------------
Indian securities communications are dense with identifiers that look exactly
like payment destinations to a naive regex:

    CDSL BO ID      1209870000018454     16 digits -- reads as a bank account
    NSDL BO ID      IN30021412345678
    Folio No.       ANR0001234
    PAN             ABCDE1234F
    Scrip line      ANANT RAJ -EQ RS 2   -- "RS 2" reads as an amount

A genuine CDSL holding statement was scored FRAUDULENT because its BO ID was
read as a bank account being solicited for investment, with no payment verb
anywhere in the message.

So every recognised identifier is replaced with a typed placeholder before any
rule runs. `1209870000018454` becomes `<CDSL_BOID>`, which no money rule can
mistake for an account number, while remaining visible to rules that legitimately
care about demat identifiers.

An offset map is retained so highlight spans and OCR bounding boxes still
resolve to positions in the ORIGINAL text.

Correctly formed identifiers are also POSITIVE evidence. A structurally valid,
check-digit-correct ISIN is weak evidence of legitimacy: fraudsters routinely
get the structure wrong because they are inventing plausible-looking strings
rather than quoting real ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# Identifier patterns
# --------------------------------------------------------------------------
#
# Order matters: longer / more specific patterns must be tried first, otherwise
# a generic digit run swallows the front of a structured identifier.

IDENTIFIER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # SEBI circular numbers: SEBI/HO/MIRSD/DOP/CIR/P/2026/38
    ("SEBI_CIRCULAR", re.compile(r"\bSEBI/[A-Z0-9]{1,10}(?:/[A-Z0-9\-]{1,20}){1,6}/\d{2,4}/\d{1,4}\b", re.I)),
    # SEBI registration numbers
    ("SEBI_REG", re.compile(r"\bIN[ZAHMRPB][A-Z]?\d{6,9}\b|\bIN-DP-\d{2,4}-\d{4}\b"
                            r"|\bIN/(?:CRA|KRA|AIF\d?|VCF|FVCI)/[\w\-/]+\b|\bMF/\d{2,4}/\d{2}/\d{1,3}\b", re.I)),
    # NSDL BO ID: "IN" + 6-digit DP + 8-digit client = IN + 14 digits
    ("NSDL_BOID", re.compile(r"\bIN\d{14}\b")),
    # ISIN: INE/INF/IND + 9 alphanumeric. Check digit validated separately.
    ("ISIN", re.compile(r"\bIN[EFD][0-9A-Z]{9}\b")),
    # CIN: 21 characters, structure-validated separately.
    ("CIN", re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", re.I)),
    # GSTIN: 15 chars -- 2 digit state + PAN + 3
    ("GSTIN", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]{3}\b")),
    # IFSC: 4 alpha + '0' + 6 alnum. Kept visible to money.py, which validates it.
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    # PAN: 5 alpha + 4 digits + 1 alpha
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    # CDSL BO ID: 16 digits beginning with the "12" DP prefix
    ("CDSL_BOID", re.compile(r"\b12\d{14}\b")),
    # Explicitly labelled DP ID / Client ID / BO ID
    ("DP_CLIENT_ID", re.compile(
        r"\b(?:DP\s*ID|Client\s*ID|BO\s*ID|Beneficiary\s*(?:Owner\s*)?ID)\s*[:\-]?\s*([A-Z0-9]{6,20})\b", re.I)),
    # Folio numbers are context-driven: only with an explicit label.
    ("FOLIO", re.compile(r"\b(?:Folio\s*(?:No\.?|Number)?)\s*[:\-]?\s*([A-Z0-9/\-]{4,20})\b", re.I)),
    # Scrip descriptor: "ANANT RAJ -EQ RS 2", "RELIANCE -EQ RS 10"
    ("SCRIP_DESCRIPTOR", re.compile(r"\b[A-Z][A-Z&.\s]{2,40}\s*-\s*(?:EQ|BE|BZ|SM|ST|GC|IL)\b(?:\s*RS\s*\d+(?:\.\d+)?)?", re.I)),

    # --- Numbers that are NOT payment destinations --------------------------
    #
    # NSE's helpline 1800 266 0050 was extracted as a bank account number and
    # contributed to a FRAUDULENT verdict on an NSE investor-awareness email.
    # Every pattern below exists because some genuine institutional message
    # carries the number and no rule may read it as somewhere to send money.

    # Indian toll-free: 1800 / 1860 / 1900 prefixes, spaced or unspaced.
    ("TOLL_FREE", re.compile(r"\b(?:1800|1860|1900)[\s\-]?\d{2,4}[\s\-]?\d{3,5}\b")),
    # Exchange and regulator circular references.
    ("EXCHANGE_CIRCULAR", re.compile(
        r"\b(?:NSE|BSE|NSCCL|ICCL)[/\-][A-Z0-9]{1,12}(?:[/\-][A-Z0-9\-]{1,20}){1,5}\b", re.I)),
    # Transaction / reference numbers, recognised by their label.
    ("REFERENCE_NO", re.compile(
        r"(?:\b(?:ref(?:erence)?|transaction\s*id|txn\s*id|UTR|ARN|RRN|order\s*(?:id|no))\b"
        r"\s*(?:no\.?|number|:|-)?\s*)([A-Z0-9][A-Z0-9\-/]{5,24})", re.I)),
    # Landline with STD code.
    ("LANDLINE", re.compile(r"\b0\d{2,4}[\s\-]\d{6,8}\b")),
    # Indian mobile, with or without country code.
    ("MOBILE_IN", re.compile(r"\b(?:\+?91[\s\-]?)?[6-9]\d{9}\b")),
    # Postal PIN: six digits, but only when labelled or after a place name.
    ("PIN_CODE", re.compile(
        r"(?:\b(?:PIN|PIN\s*code|Pincode|Postal\s*code)\b\s*[:\-]?\s*|"
        r"\b(?:Mumbai|Delhi|New\s+Delhi|Bengaluru|Bangalore|Chennai|Kolkata|Hyderabad|Pune|"
        r"Ahmedabad|Jaipur|Lucknow|Chandigarh|Noida|Gurugram|Gurgaon|Thane|Navi\s+Mumbai|"
        r"Maharashtra|Karnataka|Tamil\s*Nadu|Gujarat|Telangana|Haryana|Kerala|Rajasthan|"
        r"West\s+Bengal|Uttar\s+Pradesh|Andhra\s+Pradesh)\b[^\d\n]{0,20})(\d{6})\b", re.I)),
    # Eight digits that parse as a date (DDMMYYYY) near the present.
    ("DATE_COMPACT", re.compile(r"\b(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])(?:20[12]\d)\b")),
]

# Rupee amounts are money being DESCRIBED, not an account to send it to. Handled
# separately from the table because the match must keep the currency prefix out
# of the placeholder.
AMOUNT_RE = re.compile(r"(?:\brs\.?|\binr|₹)\s*([\d,]+(?:\.\d{1,2})?)\s*(?:lakh|crore|cr)?\b", re.I)

# Identifier kinds that must never be treated as a payment destination.
# Consumed by core/fields.py and core/chokepoints/money.py.
NON_ACCOUNT_KINDS = frozenset({
    "CDSL_BOID", "NSDL_BOID", "DP_CLIENT_ID", "FOLIO", "PAN", "GSTIN",
    "TOLL_FREE", "LANDLINE", "MOBILE_IN", "PIN_CODE", "EXCHANGE_CIRCULAR",
    "SEBI_CIRCULAR", "SEBI_REG", "REFERENCE_NO", "DATE_COMPACT", "ISIN", "CIN",
})

# Placeholder form. Deliberately unlike anything a rule pattern matches:
# no digits, no '@', no '.'.
PLACEHOLDER = "<{kind}>"

# Types that count as weak positive evidence when structurally valid.
STRUCTURAL_EVIDENCE_TYPES = {"ISIN", "CIN", "SEBI_REG", "GSTIN", "SEBI_CIRCULAR"}


@dataclass
class FoundIdentifier:
    kind: str
    value: str
    start: int          # offset in the ORIGINAL text
    end: int
    valid: bool | None = None   # None when the type has no checkable structure

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value,
                "span": [self.start, self.end], "valid": self.valid}


@dataclass
class MaskedText:
    """Text with identifiers replaced, plus the map back to the original."""

    masked: str
    original: str
    identifiers: list[FoundIdentifier] = field(default_factory=list)
    # (masked_start, masked_end, original_start, original_end) per replacement
    _spans: list[tuple[int, int, int, int]] = field(default_factory=list)

    def to_original_offset(self, masked_offset: int) -> int:
        """Map an offset in the masked text back to the original text.

        Highlight spans and OCR bounding boxes are computed against the original,
        so every offset a rule reports has to be translated before it reaches
        the UI.
        """
        shift = 0
        for m_start, m_end, o_start, o_end in self._spans:
            if masked_offset >= m_end:
                shift += (o_end - o_start) - (m_end - m_start)
            elif masked_offset >= m_start:
                # Inside a placeholder: anchor to the start of the original token.
                return o_start
            else:
                break
        return masked_offset + shift

    def to_original_span(self, start: int, end: int) -> tuple[int, int]:
        return self.to_original_offset(start), self.to_original_offset(end)

    def by_kind(self, kind: str) -> list[FoundIdentifier]:
        return [i for i in self.identifiers if i.kind == kind]

    @property
    def structural_evidence_count(self) -> int:
        """Structurally VALID identifiers, as weak evidence of legitimacy."""
        return sum(
            1 for i in self.identifiers
            if i.kind in STRUCTURAL_EVIDENCE_TYPES and i.valid is not False
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifiers": [i.to_dict() for i in self.identifiers],
            "structural_evidence_count": self.structural_evidence_count,
            "counts": {k: len(self.by_kind(k)) for k in {i.kind for i in self.identifiers}},
        }


# --------------------------------------------------------------------------
# Structural validators
# --------------------------------------------------------------------------

def _valid_isin(value: str) -> bool:
    from core.chokepoints.entity import is_valid_isin
    return is_valid_isin(value)


def _valid_cin(value: str) -> bool:
    from core.chokepoints.entity import is_valid_cin
    return is_valid_cin(value)


def _valid_pan(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", value.upper()))


def _valid_gstin(value: str) -> bool:
    # State code 01-38, then a PAN, then 3 more characters.
    if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]{3}", value.upper()):
        return False
    return 1 <= int(value[:2]) <= 38


VALIDATORS = {
    "ISIN": _valid_isin,
    "CIN": _valid_cin,
    "PAN": _valid_pan,
    "GSTIN": _valid_gstin,
}


def mask_identifiers(text: str) -> MaskedText:
    """Replace recognised identifiers with typed placeholders.

    Runs before claim.py, money.py, entity.py and delivery.py. No downstream
    rule should ever see a raw demat number, folio or PAN.
    """
    if not text:
        return MaskedText(masked="", original="")

    # Collect all matches first, then resolve overlaps by preferring the
    # earliest and, at equal start, the longest match.
    found: list[FoundIdentifier] = []
    for kind, pattern in IDENTIFIER_PATTERNS:
        for match in pattern.finditer(text):
            # Patterns with a capture group mask only the captured identifier,
            # so the human-readable label ("Folio No.") survives for rules that
            # legitimately key on it.
            if match.groups():
                start, end = match.start(1), match.end(1)
                value = match.group(1)
            else:
                start, end = match.start(), match.end()
                value = match.group()
            validator = VALIDATORS.get(kind)
            valid = validator(value) if validator else None
            found.append(FoundIdentifier(kind=kind, value=value, start=start, end=end, valid=valid))

    found.sort(key=lambda i: (i.start, -(i.end - i.start)))

    accepted: list[FoundIdentifier] = []
    cursor = -1
    for item in found:
        if item.start < cursor:
            continue          # overlaps an already-accepted identifier
        accepted.append(item)
        cursor = item.end

    out: list[str] = []
    spans: list[tuple[int, int, int, int]] = []
    position = 0
    for item in accepted:
        out.append(text[position:item.start])
        placeholder = PLACEHOLDER.format(kind=item.kind)
        masked_start = sum(len(chunk) for chunk in out)
        out.append(placeholder)
        spans.append((masked_start, masked_start + len(placeholder), item.start, item.end))
        position = item.end
    out.append(text[position:])

    return MaskedText(
        masked="".join(out),
        original=text,
        identifiers=accepted,
        _spans=spans,
    )
