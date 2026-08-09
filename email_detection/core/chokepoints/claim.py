"""CHOKEPOINT 3 -- CLAIM. Is what is promised legally possible in India?

Rules are CONTEXTUAL, not keyword lists. Each declares an entity (the noun), an
action (the verb that must accompany it), a direction (which way the thing is
travelling), and suppressors (contexts that negate it). See core/rules/engine.py
for why: "sending OTP on registered Mobile" and "share the OTP with me" contain
the same tokens and only direction separates them.

Text reaching this module has already been through the protected-identifier
pass, so a demat BO ID appears as <CDSL_BOID> and can never be mistaken for a
payment destination.

Three things beyond rule matching:

  1. NUMERIC PLAUSIBILITY. "40% in 3 months" and "2% daily" are normalised to a
     monthly rate and compared against a threshold, rather than pattern-matched
     as strings. The arithmetic is done in Python -- never ask a model whether
     one number exceeds another.

  2. COMBINATION SCORING. Urgency alone is weak. Urgency plus a payment request
     plus a guaranteed return is a different thing entirely, and scores as one.

  3. SUPPRESSION VISIBILITY. Everything that nearly fired is recorded, so a
     misfire is diagnosable rather than silent.

Every match carries character offsets so the UI can highlight the exact span.
"""

from __future__ import annotations

import csv
import functools
import re
from dataclasses import dataclass
from pathlib import Path

from core.chokepoints.base import CLAIM, CheckResult, Reason
from core.lexicon.identifiers import mask_identifiers
from core.rules.engine import Rule, compile_rule, evaluate
from core.textnorm import normalise_for_matching

# Words that invert the meaning of a following claim. Checked against the text
# immediately preceding a match.
NEGATION_CUES = (
    "no", "not", "never", "cannot", "can't", "cant", "don't", "dont", "does not",
    "doesn't", "doesnt", "without", "nor", "neither", "isn't", "isnt", "aren't",
    "arent", "won't", "wont", "avoid", "beware", "unlike", "rather than",
    "instead of", "subject to", "no assurance", "nahi", "nahin",
)
NEGATION_WINDOW = 42  # characters to look back

# Phrases that mark regulator-mandated risk disclosure. Their presence near a
# match is strong evidence the document is warning about risk, not promising
# returns -- the opposite of fraud.
DISCLAIMER_CUES = (
    "subject to market risk", "market risks", "read all scheme related",
    "past performance", "no assurance or guarantee", "does not guarantee",
    "not indicative of future", "carefully before investing",
    "scheme related documents",
)
DISCLAIMER_WINDOW = 220


@dataclass
class ClaimMatch:
    """One rule hit, with offsets already mapped back to the original text."""

    code: str
    rule_type: str
    severity: int
    matched_text: str
    start: int
    end: int
    explanation: str
    legal_basis: str | None


# --------------------------------------------------------------------------
# Investor-awareness detection
# --------------------------------------------------------------------------
#
# Exchanges, regulators and brokers publish material that DESCRIBES fraud in
# order to warn against it. It therefore contains every phrase a detector looks
# for, and a rule engine cannot tell "a Ponzi scheme promises to double your
# money" (education) from "we will double your money" (fraud) by pattern alone.
# Measured on the adversarial corpus: 4 genuine awareness emails produced
# severity-5 findings, three of them FRAUDULENT.
#
# This is a DOCUMENT-LEVEL heuristic, and a deliberately conservative stand-in
# for the semantic judgement an LLM adjudicator would make (Phase 9 Part C,
# unbuilt). It is not a general "trust this document" switch:
#
#   * it requires two independent awareness markers, and
#   * it requires the document to contain NO payment destination and NO
#     credential request aimed at the reader.
#
# So a fraudster cannot disarm the claim rules by pasting the word "beware" into
# their pitch: the moment they include a UPI handle or account number to pay,
# this stops applying -- and the MONEY and DELIVERY chokepoints are untouched by
# it in any case. Money remains the arbiter.

AWARENESS_MARKERS = (
    "beware", "caution", "cautioned", "cautions", "warning sign", "warning signs",
    "fraudster", "fraudsters", "investor education", "investor awareness",
    "advisory", "do not be misled", "no genuine broker", "will never ask",
    "never share", "do not share", "is a fraud", "such calls", "such messages",
    "such offers", "report such", "modus operandi", "red flag", "red flags",
    "ponzi", "we do not operate", "we do not promise", "in violation of",
    "criminal offence", "prohibited", "there is no procedure",
)

AWARENESS_MIN_MARKERS = 2


def is_awareness_material(text: str, fields=None) -> tuple[bool, list[str]]:
    """Is this document warning about fraud rather than committing it?

    Returns (verdict, matched markers) so the decision is auditable.
    """
    low = (text or "").lower()
    found = [m for m in AWARENESS_MARKERS if m in low]
    if len(found) < AWARENESS_MIN_MARKERS:
        return False, found

    # A payment destination present anywhere disqualifies the document: genuine
    # awareness copy never gives the reader somewhere to send money.
    if fields is not None and (fields.upi_ids or fields.account_numbers):
        return False, found

    # A credential request aimed at the reader likewise disqualifies it. The
    # negation strip means "never share your OTP" does not count.
    stripped = re.sub(
        r"\b(?:do\s+not|don'?t|never|will\s+never|no\s+one\s+(?:can|will))\b[^.!?\n]{0,80}",
        " ", low,
    )
    if re.search(r"\b(?:share|send|provide|tell)\b[^.!?\n]{0,25}"
                 r"\b(?:otp|pin|cvv|password|mpin)\b", stripped):
        return False, found

    return True, found


RULES_CSV = Path(__file__).resolve().parents[2] / "data" / "reference" / "contextual_rules.csv"


@functools.lru_cache(maxsize=1)
def _load_rules() -> list[Rule]:
    """Compile the contextual rule set once.

    Rules come from a CSV rather than the database because they are code-shaped
    (four regexes each) and must be reviewable in a diff. A rule that fails to
    compile disables itself; the rest keep working.
    """
    if not RULES_CSV.exists():
        return []
    compiled: list[Rule] = []
    with RULES_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rule = compile_rule(row)
            if rule is not None:
                compiled.append(rule)
    return compiled


def reset_rule_cache() -> None:
    """Drop the compiled-rule cache (used by tests that rewrite the rules)."""
    _load_rules.cache_clear()


def _is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - NEGATION_WINDOW): start].lower()
    return any(re.search(rf"\b{re.escape(cue)}\b", window) for cue in NEGATION_CUES)


def _in_disclaimer(text: str, start: int) -> bool:
    lo = max(0, start - DISCLAIMER_WINDOW)
    hi = min(len(text), start + DISCLAIMER_WINDOW)
    window = text[lo:hi].lower()
    return any(cue in window for cue in DISCLAIMER_CUES)


# --------------------------------------------------------------------------
# Numeric return promises
# --------------------------------------------------------------------------

_PERIOD_TO_MONTHS = {
    "day": 1 / 30.0, "daily": 1 / 30.0, "din": 1 / 30.0,
    "week": 7 / 30.0, "weekly": 7 / 30.0, "hafta": 7 / 30.0,
    "month": 1.0, "monthly": 1.0, "mahina": 1.0, "mahine": 1.0,
    "quarter": 3.0, "quarterly": 3.0,
    "year": 12.0, "yearly": 12.0, "annual": 12.0, "annually": 12.0, "saal": 12.0, "pa": 12.0,
}

# "40% in 3 months", "returns of 2% per day", "2% daily", "12% annual returns",
# "30% every week". The connector is OPTIONAL: fraud copy writes "2% daily",
# not "2% per day", and requiring "in|per|every" missed exactly those cases.
_RETURN_RE = re.compile(
    r"(?P<pct>\d{1,4}(?:\.\d{1,2})?)\s*%"
    r"[^.!?\n]{0,20}?"
    r"(?:(?:in|per|every|each|a|of|/)\s*)?"
    r"(?P<count>\d{1,3})?\s*"
    # The trailing `s?` matters: with a bare \b, "3 months" failed to match
    # because there is no word boundary between "month" and "s".
    r"(?P<period>daily|day|din|weekly|week|hafta|monthly|month|mahina|mahine|"
    r"quarterly|quarter|yearly|year|annually|annual|saal|p\.?a\.?)s?\b",
    re.I,
)

# Anything above this monthly rate is not a market return, it is a story.
# Indian equity indices have historically compounded around 1% a month.
IMPLAUSIBLE_MONTHLY_PCT = 5.0


def extract_return_promises(text: str) -> list[dict]:
    """Find promised returns and normalise each to a monthly percentage."""
    out: list[dict] = []
    for m in _RETURN_RE.finditer(text):
        try:
            pct = float(m.group("pct"))
        except (TypeError, ValueError):
            continue

        period = (m.group("period") or "").lower().rstrip(".")
        period = "pa" if period.replace(".", "") == "pa" else period
        months = _PERIOD_TO_MONTHS.get(period)
        if not months:
            continue

        count = m.group("count")
        span_months = months * (float(count) if count else 1.0)
        if span_months <= 0:
            continue

        out.append({
            "matched_text": m.group(0),
            "percent": pct,
            "period": period,
            "span_months": round(span_months, 3),
            "monthly_percent": round(pct / span_months, 2),
            "start": m.start(),
            "end": m.end(),
        })
    return out


# --------------------------------------------------------------------------
# Main check
# --------------------------------------------------------------------------

# Combination rule: these rule types together are worse than any one alone.
URGENCY_TYPES = {"PRESSURE_TACTIC"}
PAYMENT_TYPES = {"MONEY_ROUTING", "FAKE_APP_SIGNATURE"}
PROMISE_TYPES = {"ILLEGAL_PROMISE", "IMPLAUSIBLE_RETURN", "CONTRADICTION"}


def check(text: str, *, has_payment_request: bool = False, fields=None) -> CheckResult:
    result = CheckResult(chokepoint=CLAIM, passed=None, confidence=0.0)

    if not text or not text.strip():
        return CheckResult.undetermined(CLAIM, "No text content to check.")

    # Protected identifiers are masked BEFORE any rule sees the text, so a
    # demat BO ID or folio can never be read as a payment destination.
    if fields is None:
        from core.fields import extract_all
        fields = extract_all(text)

    masked = mask_identifiers(text)

    # Normalise but keep the original case for display.
    norm = normalise_for_matching(masked.masked, lower=False)

    evaluation = evaluate(_load_rules(), norm)

    # Document-level suppression for investor-awareness material. Applied to
    # claim rules only -- MONEY and DELIVERY are untouched.
    awareness, markers = is_awareness_material(text, fields)
    if awareness and evaluation.hits:
        suppressed_ids = [h.rule_id for h in evaluation.hits]
        evaluation.hits = []
        result.add(Reason(
            code="AWARENESS_MATERIAL_SUPPRESSED",
            message=(
                "This message describes fraud in order to warn against it, rather than "
                "committing it: it names no payment destination and asks for no "
                "credentials. The matched wording was not counted against it."
            ),
            evidence={"markers": markers[:6], "suppressed_rules": suppressed_ids,
                      "basis": "document-level awareness heuristic"},
            severity=0,
        ))

    matches = [
        ClaimMatch(
            code=hit.rule_id, rule_type=hit.rule_type, severity=hit.severity,
            matched_text=hit.matched_text,
            # Offsets are mapped back through the mask so highlight spans
            # resolve against the text the user actually submitted.
            start=masked.to_original_offset(hit.start),
            end=masked.to_original_offset(hit.end),
            explanation=hit.explanation, legal_basis=hit.legal_basis,
        )
        for hit in evaluation.hits
    ]
    suppressed = len(evaluation.suppressions)
    low = norm.lower()

    for match in matches:
        result.add(Reason(
            code=match.code,
            message=match.explanation,
            evidence={
                "matched_text": match.matched_text,
                "span": [match.start, match.end],
                "rule_type": match.rule_type,
                "legal_basis": match.legal_basis,
            },
            severity=match.severity,
        ))

    # ------------------------------------------------------------ numeric check
    for promise in extract_return_promises(low):
        if _is_negated(low, promise["start"]) or _in_disclaimer(low, promise["start"]):
            suppressed += 1
            continue
        monthly = promise["monthly_percent"]
        if monthly <= IMPLAUSIBLE_MONTHLY_PCT:
            continue
        severity = 5 if monthly >= 20 else 4
        result.add(Reason(
            code="IMPLAUSIBLE_RETURN_RATE",
            message=(
                f"This promises {promise['percent']}% over "
                f"{promise['span_months']:g} month(s), which works out to about "
                f"{monthly:g}% a month. Indian equity markets have historically "
                "returned in the region of 1% a month. A rate like this is not "
                "an investment return."
            ),
            evidence={
                "matched_text": promise["matched_text"],
                "span": [promise["start"], promise["end"]],
                "monthly_percent": monthly,
                "threshold_monthly_percent": IMPLAUSIBLE_MONTHLY_PCT,
            },
            severity=severity,
        ))

    # -------------------------------------------------------- combination rule
    present_types = {m.rule_type for m in matches}
    has_urgency = bool(present_types & URGENCY_TYPES)
    has_payment = bool(present_types & PAYMENT_TYPES) or has_payment_request
    has_promise = bool(present_types & PROMISE_TYPES)

    if sum([has_urgency, has_payment, has_promise]) >= 3:
        result.add(Reason(
            code="FRAUD_PATTERN_COMBINATION",
            message=(
                "This message combines three things that belong together only in a "
                "scam: a promise of returns, a demand for payment, and pressure to "
                "act immediately. Any one alone might be innocent; together they are "
                "the standard structure of investment fraud."
            ),
            evidence={
                "urgency": has_urgency,
                "payment_request": has_payment,
                "return_promise": has_promise,
                "rule_types": sorted(present_types),
            },
            severity=5,
        ))

    # ------------------------------------------------------------------ verdict
    max_sev = result.max_severity
    if max_sev >= 4:
        result.passed = False
        result.confidence = min(1.0, 0.65 + 0.08 * len([r for r in result.reasons if r.severity >= 4]))
    elif max_sev == 3:
        result.passed = False
        result.confidence = 0.5
    elif not _load_rules():
        result.passed = None
        result.confidence = 0.0
        result.add(Reason(
            code="CLAIM_RULES_UNAVAILABLE",
            message="Claim rules could not be loaded, so promises in this message were not checked.",
            evidence={},
            severity=0,
        ))
    else:
        result.passed = True
        result.confidence = 0.75
        result.add(Reason(
            code="NO_ILLEGAL_CLAIMS",
            message="Nothing in this message promises a return that would be illegal or implausible.",
            evidence={"rules_checked": len(_load_rules()), "suppressed_by_negation": suppressed},
            severity=0,
        ))

    return result
