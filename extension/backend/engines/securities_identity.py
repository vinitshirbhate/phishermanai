"""
backend/engines/securities_identity.py - F-B1 (registration identity) + F-B2
(payment namespace).  The flagship authentication capability (requirement.md §5.B).

Allowlist reasoning: instead of hunting for signs of badness (which adversaries
optimise against), we check for the presence/validity of a credential the law
now requires - a SEBI registration number, disclosed since 1 May 2026, that
resolves to the entity actually posting.

Design constraints honoured:
  * §4.1 (mandatory): the registration-number matcher is DERIVED FROM THE
    REGISTER DATA at load time, never hand-written from memory. A prefix present
    in the register but unmatched is a defect in the matcher.
  * Zero-tolerance: a genuinely registered entity's content must never produce
    `registration_invalid` / `registration_absent`. The website-match short
    circuit and the 70-84 `weak_match` band exist to protect that.
  * "Missing credentials are never proof of deception" - `absent` is bounded to
    securities content dated on/after the disclosure date.

No third-party fuzzy-matching dependency: token_set_ratio is implemented on
stdlib difflib, mirroring rapidfuzz's algorithm, to hold the <=10-dependency
budget (NFR-9).
"""
from __future__ import annotations

import difflib
import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "data"

DISCLOSURE_DATE = date(2026, 5, 1)  # SEBI circular HO/(79)2026-MIRSD-PODMMC

NAME_MATCH_VALID = 85
NAME_MATCH_WEAK = 70

# Trust deltas (todo.md §1.4). registration_valid is the ONLY state that raises trust.
SECURITIES_DELTA = {
    "valid": +25,
    "not_applicable": 0,
    "unverified": 0,     # bounded-subset miss: cannot verify != invalid. NEVER accusatory.
    "weak_match": -10,
    "absent": -20,
    "invalid": -40,
    "collision": -45,
}

# Worst-first precedence for the top-line verdict.
STATE_ORDER = ["collision", "invalid", "absent", "weak_match", "unverified",
               "not_applicable", "valid"]

_SUFFIX_RE = re.compile(r"\b(private|pvt|limited|ltd|llp|and|&)\b", re.IGNORECASE)
_SEC_LEXICON = [
    "sebi", "nse", "bse", "demat", "ipo", "trading", "portfolio", "mutual fund",
    "stock", "shares", "broker", "investment", "advisory", "research analyst",
    "securities", "fpi", "allotment", "pms", "block trade", "intraday",
]
# UPI id, e.g. name.brk@validhdfc
_UPI_RE = re.compile(r"\b([a-z0-9.\-_]{2,}@[a-z][a-z0-9.]{1,})\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Reference data (bundled snapshots, loaded once)
# --------------------------------------------------------------------------- #
class RegisterIntegrityError(RuntimeError):
    """Raised at load time when the derived matcher fails to cover the register.

    An unmatched row is ALWAYS a defect in the matcher generator, never a new
    fraud type - the register is SEBI's own published record of legitimate
    registrants. Failing loudly here is deliberate: a silently under-fitted
    matcher would stop extracting a real registrant's number, which downstream
    reads as `absent` against a legitimate firm (a G-2 violation).
    """


@lru_cache(maxsize=1)
def _register() -> dict:
    doc = json.loads((DATA / "sebi_register.json").read_text(encoding="utf-8"))
    by_number = {r["reg_number"].upper(): r for r in doc["intermediaries"]}
    return {
        "meta": doc["registry_meta"],
        "prefixes": doc["prefixes"],
        "shapes": doc.get("prefix_shapes", []),
        "by_number": by_number,
        "records": doc["intermediaries"],
    }


@lru_cache(maxsize=1)
def _upi_namespace() -> dict:
    doc = json.loads((DATA / "valid_upi_namespace.json").read_text(encoding="utf-8"))
    return {
        "meta": doc["registry_meta"],
        "suffixes": {s["suffix"].lower(): s for s in doc["namespace_suffixes"]},
        "category_map": doc.get("category_map", {}),
        "sebi_check_url": doc.get("sebi_check_url", "https://investor.sebi.gov.in/sebicheck"),
    }


def derive_prefix(reg_number: str) -> str:
    """Leading non-digit run of a registration number, taken from the value itself.

    'INH000004017' -> 'INH'   -   'INAIFSC10001' -> 'INAIFSC'
    'ARN-123456'   -> 'ARN'   -   'IN-DP-NSDL-321-2024' -> 'IN-DP'

    Mirrors scripts/fetch_sebi_register.py:derive_prefix so a claim's prefix can
    be resolved to a category without consulting the register.
    """
    rn = (reg_number or "").strip().upper()
    if rn.startswith("IN-DP-"):
        return "IN-DP"
    m = re.match(r"^([A-Z]+)-", rn)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z]+)", rn)
    return m.group(1) if m else rn


def _tokenise_tail(tail: str) -> tuple[tuple, tuple]:
    """Split the post-prefix tail into typed runs: digits, letters, literals."""
    kinds, lengths = [], []
    for tok in re.findall(r"\d+|[A-Za-z]+|[^0-9A-Za-z]+", tail):
        if tok.isdigit():
            kinds.append("D")
        elif tok.isalpha():
            kinds.append("A")
        else:
            kinds.append("L:" + tok)
        lengths.append(len(tok))
    return tuple(kinds), tuple(lengths)


def _generate_family(reg_numbers) -> str:
    """
    DERIVE the registration-number regex family from the register's own values
    (§4.1 / task D3). Never hand-written from memory.

    Every number is decomposed into `prefix + typed token runs`, numbers sharing
    a token-kind sequence are merged, and each token's observed length range
    becomes a quantifier. That yields, from the real data:

        INA + 9 digits      -> INA\\d{9,9}
        INAIFSC + 5 digits  -> INAIFSC\\d{5,5}      <- GIFT City IFSC advisers.
                                                      A hand-written INA\\d{9}
                                                      silently fails this real
                                                      registrant. Both shapes
                                                      are 12 characters.
        ARN + '-' + digits  -> ARN\\-\\d{6,6}
        IN-DP + ...         -> IN\\-DP\\-[A-Za-z]{4,4}\\-\\d{3,3}\\-\\d{4,4}

    Alternatives are emitted longest-prefix-first so INAIFSC is tried before INA.
    """
    groups: dict[tuple, list[list[int]]] = {}
    for rn in reg_numbers:
        rn = (rn or "").strip().upper()
        if not rn:
            continue
        prefix = derive_prefix(rn)
        kinds, lengths = _tokenise_tail(rn[len(prefix):])
        key = (prefix, kinds)
        slot = groups.setdefault(key, [[l, l] for l in lengths])
        for i, ln in enumerate(lengths):
            slot[i][0] = min(slot[i][0], ln)
            slot[i][1] = max(slot[i][1], ln)

    alts = []
    for (prefix, kinds), bounds in sorted(
            groups.items(), key=lambda kv: (-len(kv[0][0]), kv[0][0], kv[0][1])):
        pat = re.escape(prefix)
        for kind, (lo, hi) in zip(kinds, bounds):
            if kind == "D":
                pat += r"\d{%d,%d}" % (lo, hi)
            elif kind == "A":
                pat += r"[A-Za-z]{%d,%d}" % (lo, hi)
            else:
                pat += re.escape(kind[2:])
        alts.append(pat)
    if not alts:
        raise RegisterIntegrityError("register contains no registration numbers")
    return r"\b(?:%s)\b" % "|".join(alts)


def _assert_family_covers_register(matcher: re.Pattern, records: list[dict]) -> None:
    """
    THE ASSERTION (task D3). Every row in the register must be matched IN FULL
    by the generated family. A partial match counts as a failure: extracting
    'INA000012' out of 'INAIFSC10001' would resolve the wrong entity.

    Loud by design - this raises rather than warns.
    """
    unmatched, partial = [], []
    for rec in records:
        rn = (rec.get("reg_number") or "").strip().upper()
        if not rn:
            continue
        m = matcher.search(rn)
        if m is None:
            unmatched.append(rn)
        elif m.group(0).upper() != rn:
            partial.append((rn, m.group(0)))
    if unmatched or partial:
        detail = []
        if unmatched:
            detail.append(f"{len(unmatched)} unmatched, e.g. {unmatched[:5]}")
        if partial:
            detail.append(f"{len(partial)} partially matched, e.g. {partial[:5]}")
        raise RegisterIntegrityError(
            "Derived registration-number family does not cover the SEBI register: "
            + "; ".join(detail)
            + f". Matcher pattern: {matcher.pattern!r}. "
              "This is a DEFECT IN THE MATCHER GENERATOR, not a new fraud type — "
              "every row here is a legitimate SEBI registrant. Fix "
              "_generate_family() in backend/engines/securities_identity.py."
        )


def _generate_recognition_family(reg_numbers) -> tuple[str, frozenset]:
    """
    The RECOGNITION family - deliberately wider than the resolution family, and
    also derived from the data (its bounds are measured, not remembered).

    Why two families. The resolution family above is exact: it matches only the
    prefixes this snapshot actually contains (INA/INAIFSC/INH). If extraction
    used it, a genuine Stock Broker posting `INZ000031633` on post-1-May-2026
    securities content would have no claim extracted at all - and the disclosure
    rule would then report `absent` against a legitimate registrant. That is a
    false accusation and a G-2 violation, the exact failure this system exists
    to avoid.

    So recognition relaxes ONLY the letter sequence, keeping every measured
    bound: the shared 'IN' stem, the alpha-run and digit-run lengths, and the
    set of observed total lengths (all 12 in the current register). A token that
    is recognised but whose prefix is outside covered_prefixes resolves to
    `unverified` - trust-neutral, non-accusatory - never `invalid`.

    Returns (pattern, allowed_total_lengths); length is enforced after matching
    because a regex cannot express a total-length constraint across alternation.
    """
    stems, alpha_runs, digit_runs, lengths = set(), [], [], set()
    for rn in reg_numbers:
        rn = (rn or "").strip().upper()
        m = re.fullmatch(r"([A-Z]+)(\d+)", rn)
        if not m:
            continue                      # hyphenated schemes keep the exact family only
        alpha, digits = m.group(1), m.group(2)
        stems.add(alpha[:2])
        alpha_runs.append(len(alpha))
        digit_runs.append(len(digits))
        lengths.add(len(rn))
    if not alpha_runs:
        return _generate_family(reg_numbers), frozenset()

    stem = stems.pop() if len(stems) == 1 else ""
    lo_a, hi_a = min(alpha_runs) - len(stem), max(alpha_runs) - len(stem)
    lo_d, hi_d = min(digit_runs), max(digit_runs)
    pat = r"\b%s[A-Za-z]{%d,%d}\d{%d,%d}\b" % (re.escape(stem), max(lo_a, 1), hi_a, lo_d, hi_d)
    return pat, frozenset(lengths)


@lru_cache(maxsize=1)
def _reg_matcher() -> re.Pattern:
    """Exact, per-prefix family. Used for the load-time integrity assertion."""
    reg = _register()
    matcher = re.compile(_generate_family(r["reg_number"] for r in reg["records"]),
                         re.IGNORECASE)
    _assert_family_covers_register(matcher, reg["records"])
    return matcher


@lru_cache(maxsize=1)
def _recognition_matcher() -> tuple[re.Pattern, frozenset]:
    """Wider family used for claim EXTRACTION. Also asserted against the register."""
    reg = _register()
    pat, lengths = _generate_recognition_family(r["reg_number"] for r in reg["records"])
    matcher = re.compile(pat, re.IGNORECASE)
    _assert_family_covers_register(matcher, reg["records"])
    return matcher, lengths


def extract_claims(text: str) -> list[str]:
    """Registration-shaped tokens in `text`, uppercased and de-duplicated."""
    matcher, lengths = _recognition_matcher()
    out = []
    for m in matcher.finditer(text or ""):
        tok = m.group(0).upper()
        if lengths and len(tok) not in lengths:
            continue
        if tok not in out:
            out.append(tok)
    return out


SEBI_REGISTER_INDEX = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes"


def register_as_of() -> str:
    return _register()["meta"].get("fetched_at", "")


def category_for_prefix(prefix: str) -> Optional[str]:
    """'INH' -> 'RA'. Derived from the register, not hard-coded."""
    return (_register()["meta"].get("prefix_categories") or {}).get((prefix or "").upper())


def as_on_date_for(prefix: str) -> str:
    """
    The as-on date of the CATEGORY this prefix belongs to.

    Per-category, never global: SEBI refreshes each intermediary category on its
    own cadence and some are years staler than others. Quoting one global date
    would misreport the freshness of every other category.
    """
    meta = _register()["meta"]
    cat = category_for_prefix(prefix)
    per_cat = meta.get("per_category_as_on_dates") or {}
    return per_cat.get(cat) or meta.get("fetched_at", "")


def verify_url_for(prefix: str) -> str:
    """Live SEBI page for this prefix's category — shown on EVERY verdict."""
    meta = _register()["meta"]
    cat = category_for_prefix(prefix)
    return (meta.get("category_urls") or {}).get(cat) or SEBI_REGISTER_INDEX


def covered_categories() -> list[str]:
    return list(_register()["meta"].get("covered_categories") or [])


def register_is_authoritative_for(prefix: str) -> bool:
    """
    True only when this snapshot actually contains the prefix's whole category.

    G-2 (zero-tolerance), and the reason `invalid` is scoped rather than global:
    the register covers the categories we fetched (see covered_categories). A
    broker's INZ number is perfectly genuine but simply outside this snapshot -
    calling it `invalid` would falsely accuse a real intermediary, the worst
    defect class in this system. Outside a covered category we return the
    non-accusatory `unverified` instead.
    """
    meta = _register()["meta"]
    if meta.get("synthetic_subset", False):
        return False
    covered = {p.upper() for p in (meta.get("covered_prefixes") or [])}
    return (prefix or "").upper() in covered


def register_is_authoritative() -> bool:
    """Whole-snapshot authority: real data, not the old fictional subset."""
    meta = _register()["meta"]
    if meta.get("authoritative") is True:
        return True
    return not meta.get("synthetic_subset", False)


# --------------------------------------------------------------------------- #
# Text utilities
# --------------------------------------------------------------------------- #
def normalise_name(name: str) -> str:
    n = _SUFFIX_RE.sub(" ", (name or "").lower())
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def token_set_ratio(a: str, b: str) -> int:
    """rapidfuzz-style token_set_ratio on stdlib difflib. Returns 0..100."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0
    inter = " ".join(sorted(ta & tb))
    rest_a = " ".join(sorted(ta - tb))
    rest_b = " ".join(sorted(tb - ta))
    s1 = inter
    s2 = (inter + " " + rest_a).strip()
    s3 = (inter + " " + rest_b).strip()
    return round(100 * max(_ratio(s1, s2), _ratio(s1, s3), _ratio(s2, s3)))


def is_securities_content(text: str, threshold: int = 2) -> bool:
    low = (text or "").lower()
    return sum(1 for term in _SEC_LEXICON if term in low) >= threshold


# --------------------------------------------------------------------------- #
# Disclosure SCOPE - widened evidence, NOT a widened threshold (A.7b mitigation)
# --------------------------------------------------------------------------- #
# A.7b measured that an attacker who strips the registration number AND avoids
# securities vocabulary escapes the authentication layer entirely. The obvious
# fix - lowering the 2-term lexicon threshold - is the WRONG one: it would demand
# a registration number from ordinary pages and manufacture false `absent`
# findings against legitimate sites, trading a bounded evasion for a G-2
# violation. The threshold below is therefore untouched.
#
# Instead we widen the EVIDENCE that puts content in scope. Any ONE trigger is
# sufficient. Each carries its own reason code and is never merged into a single
# boolean, so the report can attribute exactly which one fired.
DISCLOSURE_TRIGGERS_ALL = ("lexicon", "payment_framing", "reg_shaped_token", "channel_context")
DISCLOSURE_TRIGGERS_BASELINE = ("lexicon",)      # pre-mitigation, for A.7b's before/after

# T3 needs chat context, which only the WhatsApp lane supplies. The interface is
# implemented and gated here.
#
# IT SHIPS DISABLED, DELIBERATELY. extension/whatsapp/ now exists and produces a
# `disclosure_channel_context` object of the right shape, but its selectors have
# not been verified against real WhatsApp DOM - no captured fixtures exist yet.
# Enabling T3 on that basis would make eval/REPORT.md A.7d read as a production
# result when it is an interface demonstration. Flip it with enable_chat_context()
# once the lane is verified in-browser, and record who enabled it.
CAPABILITIES = {"chat_context": False}
CHAT_CONTEXT_PROVIDER: Optional[str] = None


def enable_chat_context(provider: str, verified: bool = False) -> dict:
    """
    Activate T3 (task D8). Explicit and auditable rather than a default.

    `verified` must be True to enable: it asserts the caller has confirmed the
    provider reads real chat context, not that the code merely exists.
    """
    global CHAT_CONTEXT_PROVIDER
    if not verified:
        raise ValueError(
            f"refusing to enable T3 for provider {provider!r} without verified=True. "
            "T3 changes verdicts on real user content; enabling it because the code "
            "exists — rather than because it was confirmed to read real chat DOM — "
            "is how an interface demonstration becomes a false production claim.")
    CAPABILITIES["chat_context"] = True
    CHAT_CONTEXT_PROVIDER = provider
    return {"chat_context": True, "provider": provider}


def chat_context_status() -> dict:
    return {"enabled": bool(CAPABILITIES.get("chat_context")),
            "provider": CHAT_CONTEXT_PROVIDER}

# --- T1 evidence: a payment target ----------------------------------------- #
# IFSC is a published, fixed-width Reserve Bank format: 4 letters, a literal 0,
# then 6 alphanumerics. Bank account numbers in India run 9-18 digits.
_IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_ACCOUNT_RE = re.compile(r"\b\d{9,18}\b")
_UPI_QR_RE = re.compile(r"upi://pay\?[^\s\"']+", re.IGNORECASE)

# --- T1 evidence: return / profit / investment framing ---------------------- #
# Deliberately narrow. A payment target ALONE must never fire T1 - a page with a
# UPI ID and no investment framing is a shop, not a securities offering. These
# terms describe a RETURN ON MONEY PLACED, not a purchase.
_RETURN_FRAMING_RE = re.compile(
    r"\b(returns?|profits?|payout|pay[\s-]?outs?|roi|yield|gains?|"
    r"guarantee(?:d)?|assured|risk[\s-]?free|"
    r"invest(?:ment|ing|or)?s?|capital|corpus|principal|"
    r"double|triple|multiply|compound(?:ing)?|"
    r"per\s?cent|percent|%\s*(?:monthly|weekly|daily|per)|"
    r"margin|lot\s?size|brokerage)\b",
    re.IGNORECASE,
)

# --- T2 evidence: a registration-SHAPED token ------------------------------- #
# Wider than the resolution family on purpose, and used ONLY for scope - never to
# resolve an entity. An attacker who fabricates a number in a shape our register
# does not cover is in scope by definition; so is a legitimate holder of a
# category we did not fetch. Neither is accused: see the `unverified` branch in
# assess_registration, which fires when a credential IS disclosed but cannot be
# checked. The bare-letters arm is derived from the register at runtime; the
# hyphenated arms cover schemes (ARN, IN-DP) for which we hold no data at all and
# therefore cannot derive a shape.
_REG_SHAPED_EXTRA_RE = re.compile(
    r"\bARN[-\s]?\d{4,8}\b|\bIN-DP-[A-Z]+-\d{2,}-\d{4}\b|\bIN[A-Z]{1,6}\d{4,10}\b",
    re.IGNORECASE,
)

# --- T3 evidence: channel context ------------------------------------------- #
# The documented funnel name pattern is VIP / Premium / Signal / Wealth / Profit
# / W####-. Measuring it against A.7e's legitimate controls showed those tokens
# are NOT equivalent, so they are split into two classes.
#
# SECURITIES-ADJACENT tokens name the subject matter. A group called "Wealth
# Signals" is about money markets whatever else it is.
_FUNNEL_SECURITIES_RE = re.compile(
    r"\b(signals?|wealth|profits?|trading|traders?|equity|equities|stocks?|"
    r"investment|investing|portfolio|demat|ipo|nifty|sensex)\b|\bW\d{3,4}-",
    re.IGNORECASE)
# GENERIC MEMBERSHIP tokens name a tier, not a subject. "VIP" and "Premium"
# appear in the documented funnel, but also in gyms, airlines, support desks and
# loyalty programmes. On their own they mark nothing securities-adjacent, and
# A.7e measures what treating them as if they did actually costs.
_FUNNEL_GENERIC_RE = re.compile(r"\b(vip|premium|elite|exclusive)\b", re.IGNORECASE)

# Which token classes put content in scope. "securities_adjacent" is the shipped
# behaviour; "any_token" is the original broad rule, retained so eval/run_eval.py
# can measure the tuning's before/after rather than asserting it.
T3_NAME_MODE = "securities_adjacent"


def funnel_name_match(name: str, mode: Optional[str] = None) -> dict:
    """Funnel tokens in a chat name, split by class. Evidence for T3."""
    name = name or ""
    sec = sorted({m.group(0).lower() for m in _FUNNEL_SECURITIES_RE.finditer(name)})
    gen = sorted({m.group(0).lower() for m in _FUNNEL_GENERIC_RE.finditer(name)})
    mode = mode or T3_NAME_MODE
    in_scope = bool(sec) if mode == "securities_adjacent" else bool(sec or gen)
    return {"securities_adjacent": sec, "generic_membership": gen,
            "in_scope": in_scope, "mode": mode}


def payment_targets(text: str, upi: Optional[list] = None) -> list[str]:
    """Concrete ways to send money found in `text`. Evidence for T1."""
    found: list[str] = []
    for u in (upi or []):
        if u.get("upi_id"):
            found.append(f"upi:{u['upi_id']}")
    if not found:
        for m in _UPI_RE.findall(text or ""):
            found.append(f"upi:{m}")
    for m in _UPI_QR_RE.findall(text or ""):
        found.append(f"qr:{m[:40]}")
    ifsc = _IFSC_RE.findall((text or "").upper())
    if ifsc and _ACCOUNT_RE.search(text or ""):
        # Account number alone is ambiguous (order ids, phone strings); an IFSC
        # alongside it is what makes it a bank transfer instruction.
        found.append(f"bank:{ifsc[0]}")
    return list(dict.fromkeys(found))


def registration_shaped_tokens(text: str) -> list[str]:
    """Registration-shaped tokens, resolvable or not. Evidence for T2."""
    toks = list(extract_claims(text))
    for m in _REG_SHAPED_EXTRA_RE.finditer(text or ""):
        tok = m.group(0).upper()
        if tok not in toks:
            toks.append(tok)
    return toks


def disclosure_scope(
    text: str,
    upi: Optional[list] = None,
    channel_context: Optional[dict] = None,
    enabled: tuple = DISCLOSURE_TRIGGERS_ALL,
) -> list[dict]:
    """
    Which triggers put this content in disclosure scope. Returns one entry per
    trigger that fired - never a merged boolean, so attribution survives.
    """
    fired: list[dict] = []
    text = text or ""

    if "lexicon" in enabled and is_securities_content(text):
        fired.append({
            "code": "scope_securities_lexicon",
            "trigger": "T0",
            "text": "Content uses securities-market vocabulary (>=2 lexicon terms).",
            "source_url": "https://www.sebi.gov.in",
        })

    if "payment_framing" in enabled:
        targets = payment_targets(text, upi)
        framing = _RETURN_FRAMING_RE.search(text)
        # BOTH required. A payment target on its own is commerce, not an offering.
        if targets and framing:
            fired.append({
                "code": "scope_payment_and_return_framing",
                "trigger": "T1",
                "text": (f"A payment target ({targets[0]}) appears alongside return/investment "
                         f"framing ('{framing.group(0)}'). Money is being solicited against a "
                         f"promised return, which no paraphrase removes."),
                "evidence": {"payment_targets": targets, "framing": framing.group(0)},
                "source_url": "https://www.sebi.gov.in",
            })

    if "reg_shaped_token" in enabled:
        toks = registration_shaped_tokens(text)
        if toks:
            fired.append({
                "code": "scope_registration_shaped_token",
                "trigger": "T2",
                "text": (f"A registration-shaped token ({toks[0]}) is present. Claiming a "
                         f"registration number places content in disclosure scope whether or "
                         f"not the number resolves."),
                "evidence": {"tokens": toks},
                "source_url": "https://www.sebi.gov.in/intmid.html",
            })

    if "channel_context" in enabled and CAPABILITIES.get("chat_context") and channel_context:
        why = []
        # `group_name` is the WhatsApp lane's field name; `chat_name` the generic one.
        name = channel_context.get("group_name") or channel_context.get("chat_name") or ""
        nm = funnel_name_match(name)
        if name and nm["in_scope"]:
            why.append(f"chat name '{name}' carries securities-adjacent funnel tokens "
                       f"({', '.join(nm['securities_adjacent'] or nm['generic_membership'])})")
        if channel_context.get("prior_in_scope_in_thread"):
            why.append("an earlier message in this thread was already in scope")
        if why:
            fired.append({
                "code": "scope_channel_context",
                "trigger": "T3",
                "text": "Channel context marks this securities-adjacent: " + "; ".join(why)
                        + ". Context is not paraphrasable.",
                "evidence": {"reasons": why,
                             "channel_trust_signals": channel_trust_signals(channel_context)},
                "source_url": "https://www.sebi.gov.in",
            })
    return fired


def channel_trust_signals(channel_context: Optional[dict]) -> list[str]:
    """
    Channel-trust evidence, reported SEPARATELY from content trust (BL-2).

    These describe the CHANNEL a message arrived through, not the message. They
    are deliberately NOT disclosure-scope triggers on their own: an unsolicited
    add is not a securities disclosure obligation, and treating it as one would
    demand a registration number from every unsolicited chat - a G-2 risk of
    exactly the kind the widened-evidence design exists to avoid. Only the
    funnel-name pattern and a prior in-scope message put content in scope (T3).
    """
    if not channel_context:
        return []
    c, out = channel_context, []
    if c.get("unsolicited_add"):
        out.append("added to this chat without prior contact")
    if c.get("sender_in_contacts") is False:
        out.append("sender is not in the user's contacts")
    if c.get("prior_outgoing_message_in_chat") is False:
        out.append("the user has never sent a message in this chat")
    name = c.get("group_name") or c.get("chat_name") or ""
    nm = funnel_name_match(name)
    if name and (nm["securities_adjacent"] or nm["generic_membership"]):
        out.append(f"group name '{name}' matches the documented funnel pattern")
    members = c.get("group_member_count")
    posters = c.get("distinct_posters_in_window")
    if isinstance(members, int) and isinstance(posters, int) and members >= 50 and posters <= 5:
        out.append(f"only {posters} accounts post to {members} members")
    return out


def _poster_host(poster_identity: str) -> str:
    p = poster_identity or ""
    if "://" in p or "." in p and " " not in p:
        host = (urlparse(p if "://" in p else f"http://{p}").hostname or p).lower()
        # Strip the www. PREFIX. Not str.lstrip("www."), which strips any leading
        # run of {w, .} characters: it turned "whiteoakinvestors.com" into
        # "hiteoakinvestors.com", so every registrant whose domain begins with a
        # 'w' failed the domain short-circuit, fell through to name matching and
        # was reported as a `collision` against itself. Caught by G-2 the moment
        # the fictional register was replaced with SEBI's real one.
        return host[4:] if host.startswith("www.") else host
    return p.lower()


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


# --------------------------------------------------------------------------- #
# F-B2 - UPI namespace verification
# --------------------------------------------------------------------------- #
def upi_namespace_check(upi_id: str, claimed_category: Optional[str] = None) -> dict:
    ns = _upi_namespace()
    sebi_check = ns["sebi_check_url"]
    upi_id = (upi_id or "").strip()
    m = re.match(r"^([a-z0-9.\-_]+)@([a-z0-9.]+)$", upi_id, re.IGNORECASE)
    if not m:
        return {"upi_id": upi_id, "in_valid_namespace": False, "category": None,
                "category_mismatch": False, "sebi_check_url": sebi_check,
                "reason": "malformed_upi_id"}
    local, handle = m.group(1).lower(), m.group(2).lower()
    suffix = ns["suffixes"].get(handle)
    if not suffix:
        return {"upi_id": upi_id, "in_valid_namespace": False, "category": None,
                "category_mismatch": False, "sebi_check_url": sebi_check,
                "reason": "outside_valid_namespace"}
    # category suffix embedded in the local part, e.g. name.brk@validhdfc
    cat_code = None
    cat_match = re.search(r"\.([a-z]{2,4})$", local)
    if cat_match and cat_match.group(1) in ns["category_map"]:
        cat_code = cat_match.group(1)
    category = ns["category_map"].get(cat_code) if cat_code else None
    mismatch = bool(claimed_category and category and category.lower() != claimed_category.lower())
    return {
        "upi_id": upi_id, "in_valid_namespace": True, "category": category,
        "category_mismatch": mismatch, "sebi_check_url": sebi_check,
        "reason": "category_mismatch" if mismatch else "in_valid_namespace",
    }


# --------------------------------------------------------------------------- #
# F-B1 - Registration identity verification
# --------------------------------------------------------------------------- #
def _resolve_one(claim: str, poster_identity: str, other_handles: list[str]) -> dict:
    reg = _register()
    rec = reg["by_number"].get(claim.upper())
    poster_host = _poster_host(poster_identity)
    poster_norm = normalise_name(poster_identity)

    prefix = derive_prefix(claim)
    as_on = as_on_date_for(prefix)
    verify_url = verify_url_for(prefix)
    # Every verdict - valid AND invalid - carries the per-category as-on date and
    # a live SEBI link, so the user can always check us against the source.
    base = {"number": claim, "register_category": category_for_prefix(prefix),
            "as_on_date": as_on, "verify_url": verify_url}

    if rec is None:
        if not register_is_authoritative_for(prefix):
            # Prefix outside the categories in this snapshot: absence is a
            # coverage limit, NOT evidence of fraud (G-2).
            covered = ", ".join(covered_categories()) or "none"
            return {**base, "state": "unverified", "resolved_name": None,
                    "category": None, "status": None, "name_match_score": None,
                    "reason": (f"Registration {claim} could not be checked — this snapshot "
                               f"covers only {covered}, and {claim} is outside those "
                               f"categories. This is a coverage limit, not a finding "
                               f"against this entity. Verify live on SEBI.")}
        # Authoritative for this category: unknown means invalid.
        # Wording is deliberate. The register lists CURRENT registrants only, so a
        # cancelled or lapsed registration disappears from it rather than showing a
        # cancelled status. "Not found" is therefore the strongest claim the data
        # supports - never "this number is fake".
        return {**base, "state": "invalid", "resolved_name": None,
                "category": None, "status": None, "name_match_score": 0,
                "reason": (f"Registration {claim} — Not found in the SEBI register as of "
                           f"{as_on}. The register lists current registrants only, so a "
                           f"lapsed or cancelled registration also appears this way.")}

    if rec.get("status", "active") != "active":
        return {**base, "state": "invalid", "resolved_name": rec["registered_name"],
                "category": rec["category"], "status": rec["status"], "name_match_score": None,
                "reason": (f"Registration {claim} is registered to {rec['registered_name']} "
                           f"but its status is {rec['status']} as of {as_on}")}

    # Domain short-circuit protects genuine holders posting on their own domain.
    # `domain_anchor` is the registrant's e-mail domain with free/consumer mail
    # providers removed - anchoring on gmail.com would let any consumer-mail
    # sender short-circuit to `valid`.
    anchor = (rec.get("domain_anchor") or rec.get("website") or "").lower()
    if anchor and poster_host and (poster_host == anchor
                                   or poster_host.endswith("." + anchor)
                                   or anchor.endswith("." + poster_host)):
        return {**base, "state": "valid", "resolved_name": rec["registered_name"],
                "category": rec["category"], "status": "active", "name_match_score": 100,
                "reason": (f"Registration {claim} resolves to {rec['registered_name']} on its "
                           f"own registered domain (SEBI register as of {as_on})")}

    score = token_set_ratio(poster_norm, rec["name_normalised"]) if poster_norm else 0
    if score >= NAME_MATCH_VALID:
        state = "valid"
        reason = (f"Registration {claim} resolves to {rec['registered_name']}, matching the "
                  f"poster (SEBI register as of {as_on})")
    elif score >= NAME_MATCH_WEAK:
        state = "weak_match"
        reason = (f"Registration {claim} resolves to {rec['registered_name']}; poster name is a "
                  f"partial match ({score}%). Flagged, not an accusation")
    else:
        state = "collision"
        holders = ", ".join(other_handles) if other_handles else "another identity"
        reason = (f"Registration {claim} is registered to {rec['registered_name']}, "
                  f"not to this sender (claimed by {holders})")
    return {**base, "state": state, "resolved_name": rec["registered_name"],
            "category": rec["category"], "status": "active", "name_match_score": score,
            "reason": reason}


def assess_registration(
    text: str,
    poster_identity: str = "",
    page_date: Optional[str] = None,
    store: Any = None,
    channel_context: Optional[dict] = None,
    disclosure_triggers: tuple = DISCLOSURE_TRIGGERS_ALL,
) -> dict:
    """
    Extract -> resolve -> state. Returns the /api/securities/identity payload shape.
    `store` (optional) supplies the collision substrate via handles_for_reg_number.
    `channel_context` (optional) feeds T3; inert unless CAPABILITIES["chat_context"].
    `disclosure_triggers` selects which scope triggers are live - eval/run_eval.py
    passes DISCLOSURE_TRIGGERS_BASELINE to measure A.7b's before/after honestly.
    """
    _reg_matcher()               # runs the load-time register-integrity assertion
    claims_raw = extract_claims(text)

    reasons: list[dict] = []
    upi_results = [upi_namespace_check(u) for u in dict.fromkeys(_UPI_RE.findall(text or ""))]

    # F-A1 typologies (worst-first). Reasons rendered with their SEBI source.
    try:
        from engines import securities_typology
        typologies = securities_typology.match_typologies(text or "")
    except Exception:
        typologies = []
    for ty in typologies:
        reasons.append({"code": f"typology_{ty['id']}", "text":
                        f"Matches SEBI-published typology '{ty['id']}' (weight {ty['weight']})",
                        "source_url": ty["source"]})

    # Disclosure check (§4.1): in scope, no resolvable reg claim, dated on/after
    # 1 May 2026. Scope is decided by the widened evidence set, not by a lowered
    # lexicon threshold - see disclosure_scope().
    if not claims_raw:
        pd = _parse_date(page_date)
        scope = disclosure_scope(text, upi=upi_results, channel_context=channel_context,
                                 enabled=disclosure_triggers)
        if scope and pd is not None and pd >= DISCLOSURE_DATE:
            reasons.extend(scope)
            shaped = next((t for t in scope if t["code"] == "scope_registration_shaped_token"), None)
            if shaped:
                # A credential IS disclosed - it simply does not resolve against
                # the categories in this snapshot. Disclosure is satisfied, so
                # `absent` would be a false finding. Non-accusatory `unverified`.
                toks = shaped["evidence"]["tokens"]
                reasons.append({
                    "code": "registration_unverified",
                    "text": (f"A registration number ({toks[0]}) is displayed but could not be "
                             f"resolved against this snapshot ({', '.join(covered_categories())} "
                             f"as of {register_as_of()}). This is a coverage limit, not a "
                             f"finding against this entity. Verify live on SEBI."),
                    "verify_label": "Verify live on SEBI",
                    "source_url": SEBI_REGISTER_INDEX,
                })
                return _result("unverified", [], [], upi_results, reasons, True, typologies)
            reasons.append({
                "code": "registration_absent",
                "text": "Securities-market content dated on/after 1 May 2026 must display a SEBI "
                        "registration number. None was found.",
                "disclaimer": "A missing registration number is not proof of deception. It means "
                              "the disclosure required since 1 May 2026 was not found here.",
                "scope_triggers": [t["trigger"] for t in scope],
                "source_url": "https://www.sebi.gov.in",
            })
            return _result("absent", [], [], upi_results, reasons, True, typologies)
        return _result("not_applicable", [], [], upi_results, reasons, False, typologies)

    claims_out: list[dict] = []
    collisions: list[dict] = []
    for claim in claims_raw:
        other_handles = []
        if store is not None:
            try:
                seen = store.handles_for_reg_number(claim)
                ph = _poster_host(poster_identity) or poster_identity
                other_handles = [h for h in seen if h and h != ph]
            except Exception:
                other_handles = []
        resolved = _resolve_one(claim, poster_identity, other_handles)
        claims_out.append(resolved)
        reasons.append({"code": f"registration_{resolved['state']}",
                        "text": resolved["reason"],
                        "as_on_date": resolved["as_on_date"],
                        "verify_label": "Verify live on SEBI",
                        "source_url": resolved["verify_url"]})
        if resolved["state"] == "collision":
            collisions.append({
                "number": claim,
                "legitimate_holder": resolved["resolved_name"],
                "other_handles": other_handles or [poster_identity],
            })

    # Worst state wins for the top-line verdict.
    worst = min((c["state"] for c in claims_out), key=lambda s: STATE_ORDER.index(s))
    return _result(worst, claims_out, collisions, upi_results, reasons, True, typologies)


def _result(state, claims, collisions, upi, reasons, disclosure_required, typologies=None) -> dict:
    typologies = typologies or []
    typology_penalty = sum(t["weight"] for t in typologies)
    meta = _register()["meta"]
    return {
        "state": state,
        "trust_delta": SECURITIES_DELTA.get(state, 0),
        "claims": claims,
        "collisions": collisions,
        "upi": upi,
        "typologies_matched": typologies,
        "typology_penalty": typology_penalty,
        "disclosure": {"required": disclosure_required, "present": bool(claims),
                       "effective_date": DISCLOSURE_DATE.isoformat()},
        "reasons": reasons,
        "register_as_of": register_as_of(),
        # Surfaced on every verdict (BL-4: the producing layer and its data
        # vintage are always visible; the user can always re-check the source).
        "register": {
            "per_category_as_on_dates": meta.get("per_category_as_on_dates", {}),
            "covered_categories": covered_categories(),
            "record_count": meta.get("record_count", 0),
            "verify_url": SEBI_REGISTER_INDEX,
            "verify_label": "Verify live on SEBI",
        },
        "impersonation_alert": bool(collisions),
    }
