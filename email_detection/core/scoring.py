"""Combine every signal into one verdict.

FOUR OUTCOMES, NEVER TWO
------------------------
    GENUINE     verified against authoritative data
    TAMPERED    matches a real filing BUT a field was altered
    UNVERIFIED  no match found; may be perfectly legitimate
    FRAUDULENT  active fraud indicators present

UNVERIFIED is the outcome that makes the rest trustworthy. Absence of evidence
is not evidence of fraud, and a system that only knows "safe" and "scam" has to
guess on everything it has not seen -- which means being confidently wrong to
users who can check. Saying "we could not verify this, and here is exactly what
we would have needed" is both more honest and more useful.

SEVERITY-DOMINANT, NOT AVERAGED
-------------------------------
Scores are not averaged. One severity-5 finding -- money going to a personal
UPI handle, say -- is decisive regardless of how many other checks passed.
Averaging would let four clean signals dilute one fatal one, which is precisely
backwards: fraud is designed to look clean everywhere except the one place it
cannot.

The 0-100 confidence figure is deliberately separate from the verdict. It says
how much evidence we actually had, so a GENUINE from five passing checks is
visibly different from a GENUINE from two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.chokepoints.base import CheckResult, Reason

GENUINE = "GENUINE"
TAMPERED = "TAMPERED"
UNVERIFIED = "UNVERIFIED"
FRAUDULENT = "FRAUDULENT"

# User-facing labels. The internal constants above are unchanged so that every
# existing test, eval manifest and gateway header keeps working; these are what
# a person actually reads.
#
# "NO RISK FOUND" replaces "UNVERIFIED" deliberately. Both mean the same thing --
# we could not confirm the sender -- but "unverified" reads as an accusation to
# somebody holding a perfectly genuine letter from a company we simply have no
# record of, and that is the single most common outcome for legitimate mail.
DISPLAY_LABELS = {
    GENUINE: "VERIFIED",
    UNVERIFIED: "NO RISK FOUND",
    TAMPERED: "TAMPERED",
    FRAUDULENT: "FRAUDULENT",
}

# --------------------------------------------------------------------------
# Two-tier findings
# --------------------------------------------------------------------------
#
# NOT ALL FAILURES ARE EQUAL, and treating them as equal is what produced every
# false positive this project has hit. Each of these was a SINGLE failure
# among many passes, and each was scored FRAUDULENT:
#
#     NSE investor awareness   toll-free number read as a bank account
#     CDSL holding statement   demat BO ID read as a bank account
#     malformed ISIN           check digit failed, nothing else wrong
#     forwarded genuine mail   freemail rule fired against the FORWARDER
#
# The dividing line is direction of harm:
#
#   DISQUALIFYING -- the SENDER is trying to take something from the reader.
#                    One is enough. These are assertions about what the message
#                    is doing, and they do not become less true in company.
#
#   WEAK          -- WE could not confirm something. An unrecognised domain, a
#                    missing filing, an unparseable identifier. These describe
#                    the limits of our knowledge, not the sender's conduct, and
#                    a single one must never convict.

DISQUALIFYING_CODES = {
    # Money leaving the reader
    "PERSONAL_UPI_FOR_INVESTMENT", "BANK_ACCOUNT_FOR_INVESTMENT",
    "DESTINATION_NOT_LINKED_TO_CLAIMED_ENTITY", "DESTINATION_BANK_MISMATCH",
    "QR_CONTAINS_PAYMENT_ADDRESS", "PERSONAL_ACCOUNT_INVESTMENT",
    "MULE_ACCOUNT_REQUEST", "PAY_TAX_TO_WITHDRAW", "WITHDRAWAL_BLOCKED_PAY",
    "ACCOUNT_REACTIVATION_FEE", "PAYMENT_INSTRUCTION_NOT_IN_FILING",
    # Credentials leaving the reader
    "OTP_SHARE_REQUEST", "REMOTE_ACCESS_APP", "APK_SIDELOAD",
    # Impersonation proven against a register or a signature
    "REG_NO_NAME_MISMATCH", "AUTHORITY_DEMANDS_PAYMENT", "DIGITAL_ARREST",
    "DMARC_FAIL", "DISPLAY_NAME_DOMAIN_MISMATCH", "LOOKALIKE_DOMAIN",
    "PUNYCODE_DOMAIN",
    # Promises that are illegal on their face
    "GUARANTEED_RETURNS", "FIXED_MONTHLY_INCOME", "DOUBLE_YOUR_MONEY",
    "ZERO_RISK_EQUITY", "IPO_GUARANTEED_ALLOTMENT", "FOREX_BINARY_SCHEME",
    "IMPLAUSIBLE_RETURN_RATE", "FRAUD_PATTERN_COMBINATION",
}


# Rule TYPES that describe a mechanism by their nature. Every rule of these
# types already requires an action verb and a FROM_USER direction to fire (see
# core/rules/engine.py), so one firing means the engine has confirmed the reader
# is being asked to hand over money, credentials or control -- not merely that
# hostile-sounding words appeared.
#
# Deliberately EXCLUDED: ILLEGAL_PROMISE, CONTRADICTION, IMPLAUSIBLE_RETURN,
# PRESSURE_TACTIC, SOCIAL_ENGINEERING, FALSE_AUTHORITY. Those describe how a
# message talks, not what it asks for, and a message that only talks cannot
# take anything from the reader.
MECHANISM_RULE_TYPES = {
    "MONEY_ROUTING", "FAKE_APP_SIGNATURE", "CREDENTIAL_THEFT", "COERCION",
    "IMPERSONATION", "PHISHING_LURE", "UNREGISTERED_OFFER",
    "UNREGULATED_PRODUCT", "MARKET_MANIPULATION",
}


def _is_disqualifying(reason: Reason) -> bool:
    """Is this finding about the SENDER taking something from the reader?

    Two ways to qualify. The explicit code list covers findings produced by the
    chokepoints and the auth layer. The rule-TYPE test covers the contextual
    rules, and is derived rather than hand-listed on purpose: every rule of a
    mechanism type already had to prove an action verb and a FROM_USER direction
    before firing, which is precisely the "sender is taking something" test.
    Hand-listing codes instead missed copy-trading, lottery fees and insider-tip
    solicitations -- 4 of 20 frauds -- simply because I had not enumerated them.
    """
    if reason.code in DISQUALIFYING_CODES:
        return True
    rule_type = (reason.evidence or {}).get("rule_type")
    return rule_type in MECHANISM_RULE_TYPES and reason.severity >= 4


def _classify_findings(reasons: list[Reason]) -> tuple[list[Reason], list[Reason]]:
    """Split findings into (disqualifying, weak)."""
    disqualifying = [r for r in reasons if _is_disqualifying(r)]
    weak = [
        r for r in reasons
        if not _is_disqualifying(r) and r.severity >= 3
    ]
    return disqualifying, weak


def has_ask(parsed, reasons: list[Reason]) -> bool:
    """Does this message ask the reader for anything?

    THE SAFETY RAIL. A message that requests nothing has no fraud mechanism:
    there is no action the reader can take that costs them. Every genuine
    communication that this system has ever misjudged -- NSE awareness, CDSL
    e-voting, SBI statements, demat updates -- asks for nothing, and all of them
    are resolved here before any finding list is consulted.

    Deliberately broad. A false "yes" only means the full failure logic runs; a
    false "no" would silence a real fraud, so anything resembling a request
    counts.
    """
    import re as _re

    fields = getattr(parsed, "structured", None)
    if fields is not None:
        if fields.upi_ids or fields.account_numbers:
            return True

    # An off-estate link is an ask: it is where the reader is being sent.
    if any(r.code in ("LOOKALIKE_DOMAIN", "PUNYCODE_DOMAIN", "APK_DOWNLOAD_LINK",
                      "URL_SHORTENER_IN_FINANCIAL_MESSAGE", "ELEVATED_RISK_TLD",
                      "DOMAIN_REGISTERED_RECENTLY", "CONSUMER_PAYMENT_LINK")
           for r in reasons):
        return True

    text = (getattr(parsed, "raw_text", "") or "")[:20000]
    # Strip anti-fraud advice first: "never share your OTP" is a warning, not a
    # request, and counting it made regulators' own education mail look like an
    # ask.
    text = _re.sub(
        r"\b(?:do\s+not|don'?t|never|will\s+never|no\s+one\s+(?:can|will)|"
        r"we\s+(?:do\s+not|never))\b[^.!?\n]{0,80}", " ", text, flags=_re.I)

    return bool(_re.search(
        r"\b(?:pay|transfer|remit|deposit|send)\b[^.!?\n]{0,50}"
        r"\b(?:rs\.?|inr|₹|amount|fee|charge|upi|account|a/c)\b"
        r"|\b(?:share|send|provide|confirm|enter|submit)\b[^.!?\n]{0,30}"
        r"\b(?:otp|pin|cvv|password|mpin|card\s*number)\b"
        r"|\b(?:download|install)\b[^.!?\n]{0,40}\b(?:apk|app|application)\b"
        r"|\bprocessing\s*fee\b|\bverification\s*(?:fee|charge)\b"
        r"|\bjoin\b[^.!?\n]{0,30}\b(?:group|channel)\b",
        text, _re.I,
    ))

# How much each chokepoint counts toward the confidence figure. MONEY and
# FILINGS lead because they are the hardest signals to fake: a fraudster
# controls their own copy and domain, but cannot control where a validated UPI
# handle points or what a company filed with the exchange.
CHOKEPOINT_WEIGHTS = {
    "MONEY": 1.5,
    "FILINGS": 1.5,
    "ENTITY": 1.2,
    "DELIVERY": 1.0,
    "CLAIM": 1.0,
    "EMAIL_AUTH": 1.2,
}


@dataclass
class Verdict:
    verdict: str
    confidence: int                              # 0-100, evidence available
    summary: str                                 # one plain sentence
    reasons: list[dict[str, Any]] = field(default_factory=list)
    field_comparisons: list[dict[str, Any]] = field(default_factory=list)
    matched_filing: dict[str, Any] | None = None
    recommended_actions: list[dict[str, Any]] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    # Set when the verdict came from the authorised-sender short-circuit rather
    # than from the chokepoints. Surfaced so the UI and the eval harness can
    # tell the two paths apart.
    short_circuit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "summary": self.summary,
            "reasons": self.reasons,
            "field_comparisons": self.field_comparisons,
            "matched_filing": self.matched_filing,
            "recommended_actions": self.recommended_actions,
            "checks": self.checks,
            "evidence_summary": self.evidence_summary,
            "short_circuit": self.short_circuit,
        }


# --------------------------------------------------------------------------
# Authorised-sender short-circuit
# --------------------------------------------------------------------------

def _solicits_value(parsed) -> bool:
    """Does this message ask the reader to pay, or to hand over a credential?

    Kept deliberately cheap and broad. It runs before the chokepoints, so it
    cannot use their output, and a false "yes" costs only a full pipeline run
    while a false "no" would skip every content check on a message asking for
    money.
    """
    import re as _re

    fields = getattr(parsed, "structured", None)
    if fields is not None and (fields.upi_ids or fields.account_numbers):
        return True

    text = (getattr(parsed, "raw_text", "") or "")[:20000]

    # Strip anti-fraud advice before testing. Institutions warn constantly --
    # "Do not share your OTP", "SEBI never asks investors for money" -- and
    # matching the noun made SEBI's own investor-education mail look like a
    # credential request, so none of it could short-circuit.
    text = _re.sub(
        r"\b(?:do\s+not|don'?t|never|will\s+never|no\s+one\s+(?:can|will)|"
        r"we\s+(?:do\s+not|never))\b[^.!?\n]{0,80}",
        " ", text, flags=_re.I,
    )

    if _re.search(
        r"\b(?:pay|transfer|remit|deposit|send)\b[^.!?\n]{0,50}"
        r"\b(?:rs\.?|inr|₹|amount|fee|charge|upi|account|a/c)\b"
        r"|\b(?:share|send|provide|confirm)\b[^.!?\n]{0,30}"
        r"\b(?:otp|pin|cvv|password|mpin)\b"
        r"|\bprocessing\s*fee\b|\bverification\s*(?:fee|charge)\b",
        text, _re.I,
    ):
        return True
    return False


def try_short_circuit(parsed, forward_info=None) -> "Verdict | None":
    """Return GENUINE without running any chokepoint, or None to continue.

    THE PRINCIPLE
    -------------
    DKIM signs the message body. A valid, ALIGNED DKIM signature from a domain
    we hold positive evidence is authorised proves two things at once: the
    content has not been altered since it left that domain, and that domain
    really sent it. Running content rules afterwards re-checks something already
    proven cryptographically, and can only manufacture false positives -- which
    is exactly what happened to a genuine NSE investor-awareness email whose
    text WARNED against guaranteed returns.

    THE BOUNDARY -- the part that must not be got wrong
    ---------------------------------------------------
    Every condition below is load-bearing. The short-circuit fires ONLY for a
    direct .eml carrying a valid aligned signature:

      screenshots / images   the sender is CLAIMED, never proven -- an image of
                             an NSE email is not an NSE email
      inline forwards        the original signature is destroyed by forwarding
      pasted text            no headers at all
      dkim absent/failed     nothing was proven
      dkim misaligned        somebody signed it, but not the claimed sender

    For any of those the claimed sender is an assertion, not evidence, and the
    full pipeline must run -- otherwise tamper detection is lost entirely, since
    a tampered screenshot of a real circular would sail through as GENUINE.
    """
    from core.authority import check_bimi, resolve_authority

    if getattr(parsed, "source_type", None) != "EMAIL":
        return None
    email = getattr(parsed, "email", None)
    if email is None:
        return None

    # Any forward -- inline or attached -- is excluded. An attached forward does
    # preserve the original headers, but the message WE received was signed by
    # the forwarder, so the outer signature proves nothing about the original.
    if forward_info is not None and getattr(forward_info, "is_forward", False):
        return None

    auth = email.auth
    if (auth.dkim or "").lower() != "pass":
        return None
    if not auth.dmarc_passed:
        return None
    if not auth.dkim_aligned_with(email.from_domain):
        return None

    authority = resolve_authority(email.from_domain)
    if authority is None:
        return None

    # FINAL EXCLUSION: the message must not be asking for money or credentials.
    #
    # DKIM proves the message left that domain unmodified. It does NOT prove the
    # sending account was not compromised, and it says nothing about intent. The
    # residual risk after every other check is a legitimate domain sending a
    # solicitation it should not be -- a hijacked broker mailbox, or an insider.
    #
    # Found by the test suite: a tampered dividend circular carrying a valid
    # aligned signature returned GENUINE and never reached tamper detection,
    # because the short-circuit had already answered. Anything that asks the
    # reader to pay or to hand over a credential therefore runs the full
    # pipeline, however impeccable its signature.
    if _solicits_value(parsed):
        return None

    reasons = [
        Reason(
            code="AUTHORISED_SENDER_DKIM_VALID",
            message=(
                f"This email was cryptographically signed by {email.from_domain} and the "
                f"signature is valid, so its contents have not been altered since "
                f"{authority.entity_name} sent it."
            ),
            evidence={
                "from_domain": email.from_domain,
                "dkim": auth.dkim, "dkim_signer": auth.dkim_domain,
                "dmarc": auth.dmarc, "spf": auth.spf,
                "aligned": True,
            },
            severity=0,
        ),
        Reason(
            code="SENDER_DOMAIN_AUTHORISED",
            message=(
                f"{email.from_domain} is a recognised domain of {authority.entity_name} "
                f"({authority.claim_type.replace('_', ' ').lower()})."
            ),
            evidence=authority.to_dict(),
            severity=0,
        ),
    ]

    # BIMI is a bonus signal only. Its ABSENCE is meaningless -- adoption is
    # under 1% -- so a missing record never appears as a finding.
    bimi = check_bimi(email.from_domain)
    if bimi.found and bimi.has_vmc:
        reasons.append(Reason(
            code="BIMI_VMC_VERIFIED",
            message=(
                f"{email.from_domain} publishes a BIMI record backed by a Verified Mark "
                "Certificate, which requires a registered trademark and an audited "
                "issuance process. This is the 'verified logo' your mail app shows."
            ),
            evidence=bimi.to_dict(),
            severity=0,
        ))

    return Verdict(
        verdict=GENUINE,
        confidence=95,
        summary=(
            f"Verified: sent by {email.from_domain}, an authorised domain of "
            f"{authority.entity_name}, with valid cryptographic signatures."
        ),
        reasons=[r.to_dict() for r in reasons],
        checks={},
        evidence_summary={
            "short_circuit": True,
            "authority": authority.to_dict(),
            "bimi_vmc": bool(bimi.found and bimi.has_vmc),
            "risk_level": "none",
            "verdict_confidence": 95,
            "evidence_available": 3 if (bimi.found and bimi.has_vmc) else 2,
            "evidence_total": 3,
        },
        short_circuit="AUTHORISED_SENDER_DKIM_VALID",
    )


def _confidence(checks: list[CheckResult], tamper_result, filing_match) -> int:
    """How much evidence did we actually gather? 0-100.

    Rises with the number and weight of checks that reached a conclusion, and
    with a confirmed filing match. A check returning None contributes nothing --
    it neither helps nor hurts, which is the honest treatment.
    """
    earned = 0.0
    possible = 0.0
    for check in checks:
        weight = CHOKEPOINT_WEIGHTS.get(check.chokepoint, 1.0)
        possible += weight
        if check.passed is not None:
            earned += weight * max(check.confidence, 0.35)

    filings_weight = CHOKEPOINT_WEIGHTS["FILINGS"]
    possible += filings_weight
    if filing_match is not None and getattr(filing_match, "found", False):
        strength = {"EXACT": 1.0, "VISUAL": 0.9, "STRUCTURED": 0.85, "SEMANTIC": 0.75}
        earned += filings_weight * strength.get(filing_match.tier, 0.6)

    if possible <= 0:
        return 0
    score = int(round(100 * earned / possible))
    return max(0, min(100, score))


# Minimum confidence for each verdict. Below this the verdict falls back to
# UNVERIFIED with an explanation.
MIN_CONFIDENCE = {
    FRAUDULENT: 70,
    TAMPERED: 65,
    GENUINE: 60,
}



def _mechanism_reasons(reasons: list[Reason]) -> list[Reason]:
    """Findings that establish a route by which the reader loses something.

    ONE definition, used by both the FRAUDULENT cap and the confidence
    calculation. They disagreed once -- the cap counted rule types while the
    confidence bonus counted reason codes -- so a lottery-fee demand passed the
    cap, scored 60 instead of 75, and was then blocked by the confidence gate
    it should have cleared.
    """
    out = []
    for reason in reasons:
        if reason.code in FRAUD_MECHANISM_CODES:
            out.append(reason)
        elif (reason.evidence or {}).get("rule_type") in MECHANISM_RULE_TYPES:
            # A contextual rule of a mechanism type has already proved the ask:
            # entity + action + FROM_USER direction + requires_ask all matched.
            out.append(reason)
    return out


def _has_fraud_mechanism(checks: list[CheckResult], reasons: list[Reason]) -> bool:
    """Is there any route by which acting on this message could cost the reader?"""
    # Without this, "pay Rs 45,000 or face a non-bailable warrant" was capped at
    # UNVERIFIED because the MONEY chokepoint only flags payment details in an
    # *investment* context, and a digital-arrest threat mentions no investment.
    if _mechanism_reasons(reasons):
        return True
    money_check = next((c for c in checks if c.chokepoint == "MONEY"), None)
    if money_check is not None and money_check.passed is False:
        return True
    delivery_check = next((c for c in checks if c.chokepoint == "DELIVERY"), None)
    if delivery_check is not None and any(r.severity >= 3 for r in delivery_check.reasons):
        return True
    return False


def _verdict_confidence(
    verdict: str,
    reasons: list[Reason],
    tamper_result,
    evidence_confidence: int,
) -> int:
    """How sure are we of THIS CONCLUSION -- a different question from how much
    evidence we gathered.

    These two must not be conflated, and conflating them broke both directions:

      * A four-line scam SMS concludes few checks, so its EVIDENCE score is low
        (~31). Gating the fraud verdict on that number downgraded obvious fraud
        -- money to a personal UPI handle with a guaranteed-return promise -- to
        UNVERIFIED, which is the recall failure the hardening was supposed to
        avoid.

      * Conversely a GENUINE verdict genuinely does depend on breadth: "every
        check passed" means little when only two checks ran.

    So confidence in a FRAUDULENT verdict comes from the strength and mechanism
    of the findings, while confidence in GENUINE comes from evidence breadth.
    The reported `confidence` figure stays as evidence availability (see E5).
    """
    if verdict == FRAUDULENT:
        severity_5 = [r for r in reasons if r.severity >= 5]
        severity_4 = [r for r in reasons if r.severity == 4]
        mechanism = _mechanism_reasons(reasons)
        score = 55 + 15 * min(len(severity_5), 2) + 5 * min(len(severity_4), 2)
        if mechanism:
            # A concrete route by which the reader loses money is the single
            # strongest confirmation that this is fraud rather than bad wording.
            score += 15
        return min(100, score)

    if verdict == TAMPERED:
        if tamper_result is None:
            return 60
        return 90 if tamper_result.confidence == "HIGH" else 70

    # GENUINE and UNVERIFIED are claims about how much we could check.
    return evidence_confidence


def _risk_level(verdict: str, reasons: list[Reason]) -> str:
    """What we concluded -- kept separate from how much we could inspect."""
    if verdict == FRAUDULENT:
        return "high"
    if verdict == TAMPERED:
        return "high"
    if any(r.severity >= 4 for r in reasons):
        return "elevated"
    if any(r.severity == 3 for r in reasons):
        return "low"
    return "none"


def _summary_line(verdict: str, top: list[Reason], tamper_result, filing_match,
                  confidence: int = 100) -> str:
    """One sentence a first-time investor can act on.

    LANGUAGE SCALES WITH CONFIDENCE. Categorical phrasing ("This IS a
    fraudulent message") is reserved for >= 85. Below that the sentence hedges
    in proportion to the evidence, because overclaiming on thin evidence is how
    a tool loses the user's trust the first time it is wrong.
    """
    if verdict == TAMPERED and tamper_result and tamper_result.altered_fields:
        comparison = tamper_result.altered_fields[0]
        pretty = comparison.field.replace("_", " ")
        company = (filing_match.company_name if filing_match else "the company") or "the company"
        return (
            f"This is a real {company} document, but the {pretty} has been changed: "
            f"it says {comparison.extracted_value} where {company} filed "
            f"{comparison.filed_value} with the exchange."
        )
    if verdict == FRAUDULENT:
        detail = f" {top[0].message}" if top else ""
        if confidence >= 85:
            return f"This is a fraudulent message.{detail}"
        if confidence >= 70:
            return f"This message shows strong signs of fraud.{detail}"
        # Below 70 a FRAUDULENT verdict cannot survive the confidence gate, so
        # this branch is defensive rather than expected.
        return f"Something here does not add up. Treat this with caution.{detail}"
    if verdict == GENUINE:
        company = (filing_match.company_name if filing_match and filing_match.found else None)
        if company:
            return (
                f"This matches a genuine announcement {company} filed with the exchange, "
                "and every check we ran passed."
            )
        return "Every check we ran on this message passed."
    return (
        # Leads with what we DID establish. The previous wording opened with
        # "We could not verify this message", which is the least reassuring true
        # sentence available and is what most legitimate mail receives.
        "No risk found. We could not match this to an authoritative record, so we "
        "cannot confirm it either way -- but nothing in it asks you for money or "
        "credentials, and we found no fraud indicators."
    )


# Reason codes that show the message is trying to extract something of value.
# These are what make a text-pattern hit actionable.
VALUE_EXTRACTION_CODES = {
    # money leaving the user
    "PERSONAL_UPI_FOR_INVESTMENT", "PERSONAL_UPI_PRESENT", "BANK_ACCOUNT_FOR_INVESTMENT",
    "CONSUMER_PAYMENT_LINK", "QR_CONTAINS_PAYMENT_ADDRESS", "DESTINATION_BANK_MISMATCH",
    "DESTINATION_NOT_LINKED_TO_CLAIMED_ENTITY", "UPI_HANDLE_UNRECOGNISED",
    "PAYMENT_INSTRUCTION_NOT_IN_FILING", "PAYMENT_DETAILS_IN_CORPORATE_NOTICE",
    # credentials leaving the user
    "OTP_SHARE_REQUEST", "REMOTE_ACCESS_APP", "APK_DOWNLOAD_LINK",
    # the user being redirected off the official estate
    "LOOKALIKE_DOMAIN", "PUNYCODE_DOMAIN", "DOMAIN_REGISTERED_RECENTLY",
    "ELEVATED_RISK_TLD", "URL_SHORTENER_IN_FINANCIAL_MESSAGE",
    "AUTHENTICATED_BUT_UNRECOGNISED_DOMAIN", "AUTHENTICATED_DOMAIN_WRONG_ENTITY",
    "INSTITUTIONAL_CLAIM_FROM_FREEMAIL", "DMARC_FAIL", "REPLY_TO_MISMATCH",
    "DISPLAY_NAME_DOMAIN_MISMATCH",
    # impersonation of an authority
    "AUTHORITY_DEMANDS_PAYMENT", "REG_NO_NAME_MISMATCH", "ISIN_CHECK_DIGIT_FAILED",
}


# Reason codes proving the message has a MECHANISM to defraud: it moves money,
# harvests credentials, or redirects the reader off the official estate.
FRAUD_MECHANISM_CODES = VALUE_EXTRACTION_CODES | {
    "AUTHORITY_DEMANDS_PAYMENT", "PAYMENT_INSTRUCTION_NOT_IN_FILING",
    "PAYMENT_DETAILS_IN_CORPORATE_NOTICE", "BANK_ACCOUNT_FOR_INVESTMENT",
}


def _apply_countervailing(
    verdict: str,
    checks: list[CheckResult],
    reasons: list[Reason],
    auth_verdict,
) -> tuple[str, Reason | None]:
    """Refuse to call something fraudulent when the evidence contradicts it.

    THE FAILURE THIS PREVENTS
    -------------------------
    A genuine CDSL e-voting notice was labelled FRAUDULENT on the strength of a
    single claim-rule hit, while every other signal said otherwise: the links
    all resolved to cdslindia.com, no payment was requested anywhere, and a real
    SEBI circular was cited. One text pattern outvoted five contradicting
    signals. That is an architecture problem, not a regex problem -- fixing the
    rule that happened to fire leaves the next direction-blind rule free to do
    the same thing.

    THE ARBITER IS MONEY
    --------------------
    Fraud that does not move value is not fraud. If a message asks for no
    payment, requests no credentials, and sends the user nowhere but the
    institution's own verified domains, then a text-pattern match alone must
    never reach FRAUDULENT. It can reach UNVERIFIED -- we still flag what we
    saw -- but we do not accuse.

    Note this can only ever DOWNGRADE a verdict, and only when the domains are
    positively verified against the domain map. A message from an unrecognised
    domain gets no protection from this rule.
    """
    by_code = {r.code for r in reasons}

    # Is anything of value being extracted?
    if by_code & VALUE_EXTRACTION_CODES:
        return verdict, None

    delivery = next((c for c in checks if c.chokepoint == "DELIVERY"), None)
    money = next((c for c in checks if c.chokepoint == "MONEY"), None)

    # Every domain referenced must be a known official domain. `passed is True`
    # on DELIVERY already means all domains resolved to the domain map.
    domains_verified = bool(
        delivery
        and delivery.passed is True
        and any(r.code == "KNOWN_OFFICIAL_DOMAIN" for r in delivery.reasons)
    )
    if not domains_verified:
        return verdict, None

    # No payment path at all. `passed is None` with NO_PAYMENT_DETAILS is the
    # strongest form: there were no payment details to judge.
    no_payment = bool(
        money
        and (money.passed is not False)
        and not any(r.severity >= 4 for r in money.reasons)
    )
    if not no_payment:
        return verdict, None

    # Authentication must not itself be a problem.
    if auth_verdict is not None and auth_verdict.status in ("FAIL", "SUSPICIOUS"):
        return verdict, None

    triggering = [r.code for r in reasons if r.severity >= 5]
    return UNVERIFIED, Reason(
        code="CLAIM_RULE_SUPPRESSED_BY_COUNTERVAILING_EVIDENCE",
        message=(
            "This message uses wording that often appears in fraud, but everything "
            "else about it checks out: every link goes to a verified official domain, "
            "it asks for no payment, and it requests no credentials. We have flagged "
            "the wording rather than calling the message fraudulent."
        ),
        evidence={
            "suppressed_findings": triggering,
            "domains_verified": True,
            "payment_requested": False,
            "credentials_requested": False,
            "rule": "value-extraction is required for a FRAUDULENT verdict",
        },
        severity=2,
    )


def score(
    checks: list[CheckResult],
    *,
    tamper_result=None,
    filing_match=None,
    auth_verdict=None,
    auth_anomalies=None,
    parsed_input=None,
) -> Verdict:
    """Combine chokepoint results, filing match and tamper analysis into a verdict."""
    reasons: list[Reason] = []
    for check in checks:
        for reason in check.reasons:
            if reason.severity > 0 or reason.code.startswith(("NO_", "KNOWN_", "ENTITY_RESOLVED",
                                                             "UPI_VALIDATED", "REG_NO_VERIFIED",
                                                             "ISIN_RESOLVED", "AUTHENTICATED")):
                reasons.append(reason)

    # Email authentication participates as a first-class signal.
    if auth_verdict is not None:
        reasons.append(Reason(
            code=auth_verdict.code, message=auth_verdict.message,
            evidence=auth_verdict.evidence, severity=auth_verdict.severity,
        ))
    for anomaly in auth_anomalies or []:
        reasons.append(Reason(
            code=anomaly.code, message=anomaly.message,
            evidence=anomaly.evidence, severity=anomaly.severity,
        ))

    # Tamper findings.
    field_comparisons: list[dict[str, Any]] = []
    if tamper_result is not None:
        field_comparisons = [c.to_dict() for c in tamper_result.comparisons]
        for comparison in tamper_result.altered_fields:
            reasons.append(Reason(
                code="FIELD_ALTERED",
                message=comparison.message,
                evidence={
                    "field": comparison.field,
                    "document_value": str(comparison.extracted_value),
                    "filed_value": str(comparison.filed_value),
                    "read_confidence": comparison.read_confidence,
                    "bbox": comparison.bbox,
                },
                severity=comparison.severity,
            ))
        for comparison in tamper_result.unreadable_fields:
            reasons.append(Reason(
                code="FIELD_UNREADABLE",
                message=comparison.message,
                evidence={"field": comparison.field, "filed_value": str(comparison.filed_value)},
                severity=0,
            ))
        for signal in tamper_result.extra_signals:
            reasons.append(Reason(
                code=signal["code"], message=signal["message"],
                evidence=signal.get("evidence", {}), severity=signal.get("severity", 3),
            ))

    reasons.sort(key=lambda r: -r.severity)
    severity_5 = [r for r in reasons if r.severity >= 5]

    tamper_high = bool(
        tamper_result is not None
        and tamper_result.tampered
        and tamper_result.confidence == "HIGH"
        and filing_match is not None
        and getattr(filing_match, "found", False)
    )
    tamper_medium = bool(
        tamper_result is not None and tamper_result.tampered and tamper_result.confidence == "MEDIUM"
    )

    # ------------------------------------------------------------ the decision
    #
    # TAMPERED is evaluated before FRAUDULENT, which reverses the order the
    # brief lists. The reason: a tampered circular almost always also trips a
    # severity-5 rule (an inserted payment demand), so checking FRAUDULENT
    # first would collapse every tampered document into the generic label and
    # discard the specific finding. TAMPERED is strictly more informative -- it
    # names the altered field and the filed value beside it -- and it is only
    # ever reached when a real filing was matched, so it cannot mislabel an
    # ordinary scam. Both verdicts tell the user not to act; only one tells
    # them what was changed.
    # ------------------------------------------------------ decision function
    #
    # Order matters and each step earns its place:
    #
    #   1. TAMPERED stays separate and first. "Real circular, altered account
    #      number, here is the red box" is a different message from "this is a
    #      scam", and it is the thing nothing else does.
    #   2. The has_ask rail. A message that requests nothing cannot defraud the
    #      reader, so it never reaches the failure lists at all.
    #   3. Disqualifying findings convict alone; weak findings need corroboration
    #      AND an ask.
    #   4. Passes are positive evidence. Counting only failures is why a fully
    #      authenticated SBI statement previously scored 12/100.

    disqualifying, weak = _classify_findings(reasons)
    passes = [c for c in checks if c.passed is True]
    asking = has_ask(parsed_input, reasons) if parsed_input is not None else True

    if tamper_high:
        verdict = TAMPERED
    elif tamper_medium:
        verdict = TAMPERED
    elif disqualifying:
        # DISQUALIFYING FINDINGS ARE CHECKED BEFORE THE has_ask RAIL, because a
        # disqualifying finding IS an ask -- proved more rigorously than the
        # rail's text search can manage.
        #
        # Every rule in this list requires an action verb AND a FROM_USER
        # direction before it fires (see core/rules/engine.py), so
        # MULE_ACCOUNT_REQUEST or REMOTE_ACCESS_APP firing already establishes
        # that the sender is soliciting. Running the rail first silenced six of
        # twenty frauds -- mule recruitment, remote-access, copy-trading,
        # lottery fees, VIP groups and insider tips -- because none of them
        # matches a "pay Rs X" pattern, which cost 25 points of recall.
        verdict = FRAUDULENT
    elif not asking:
        # THE SAFETY RAIL. Nothing is being requested, so there is no mechanism
        # by which acting on this message costs the reader anything.
        verdict = GENUINE if len(passes) >= 2 else UNVERIFIED
        if weak:
            reasons.insert(0, Reason(
                code="NO_REQUEST_MADE_OF_READER",
                message=(
                    "This message asks you for nothing -- no payment, no credentials, "
                    "and no link to an unrecognised site. Wording that can look "
                    "alarming was noted but not counted against it, because there is "
                    "no action here that could cost you anything."
                ),
                evidence={
                    "noted_findings": [r.code for r in weak][:6],
                    "checks_passed": len(passes),
                },
                severity=0,
            ))
    elif len(weak) >= 2:
        verdict = FRAUDULENT
    elif len(passes) > len(weak):
        verdict = GENUINE
    else:
        verdict = UNVERIFIED

    # ------------------------------------------------- countervailing evidence
    if verdict == FRAUDULENT:
        verdict, suppression = _apply_countervailing(verdict, checks, reasons, auth_verdict)
        if suppression:
            reasons.insert(0, suppression)

    # A message that asks for NOTHING has no fraud mechanism. No payment
    # request, no credential request, no off-site link means there is no way for
    # the reader to be defrauded by acting on it, whatever vocabulary it uses.
    # Cap at UNVERIFIED. Applied after countervailing because it is broader:
    # it does not require the domains to be positively verified.
    if verdict == FRAUDULENT and not _has_fraud_mechanism(checks, reasons):
        verdict = UNVERIFIED
        reasons.insert(0, Reason(
            code="NO_FRAUD_MECHANISM_PRESENT",
            message=(
                "This message uses wording associated with fraud, but it asks for no "
                "payment, requests no credentials, and sends you to no unrecognised "
                "website. We have flagged the wording rather than calling it fraud."
            ),
            evidence={"payment_requested": False, "credentials_requested": False,
                      "offsite_link": False},
            severity=2,
        ))

    confidence = _confidence(checks, tamper_result, filing_match)

    # --------------------------------------------------------- confidence gate
    # A verdict is a claim about evidence. Below these thresholds we do not have
    # enough to make it, so we say so instead of asserting it quietly.
    # A FRAUDULENT verdict at 44/100 previously produced the sentence
    # "This is a fraudulent message."
    verdict_confidence = _verdict_confidence(verdict, reasons, tamper_result, confidence)
    gate = MIN_CONFIDENCE.get(verdict)
    if gate is not None and verdict_confidence < gate:
        reasons.insert(0, Reason(
            code="INSUFFICIENT_CONFIDENCE_FOR_VERDICT",
            message=(
                f"Some signals pointed to {verdict.lower()}, but our confidence in that "
                f"conclusion is only {verdict_confidence}% ({gate}% is our threshold). "
                "We are reporting what we found rather than drawing a conclusion."
            ),
            evidence={"proposed_verdict": verdict, "verdict_confidence": verdict_confidence,
                      "evidence_confidence": confidence, "required": gate},
            severity=2,
        ))
        verdict = UNVERIFIED

    return Verdict(
        verdict=verdict,
        confidence=confidence,
        summary=_summary_line(verdict, reasons, tamper_result, filing_match, verdict_confidence),
        reasons=[r.to_dict() for r in reasons],
        field_comparisons=field_comparisons,
        matched_filing=filing_match.to_dict() if filing_match and filing_match.found else None,
        checks={c.chokepoint: c.to_dict() for c in checks},
        evidence_summary={
            "checks_concluded": len([c for c in checks if c.passed is not None]),
            "checks_run": len(checks),
            "severity_5_findings": len(severity_5),
            "severity_4_findings": len([r for r in reasons if r.severity == 4]),
            "filing_matched": bool(filing_match and getattr(filing_match, "found", False)),
            "filing_match_tier": filing_match.tier if filing_match else None,
            "tamper_confidence": tamper_result.confidence if tamper_result else None,
            # E5: risk and evidence are DIFFERENT axes and must not be shown as
            # one number. A high-evidence GENUINE and a low-evidence UNVERIFIED
            # both used to render as a single ambiguous score.
            "risk_level": _risk_level(verdict, reasons),
            "verdict_confidence": verdict_confidence,
            "evidence_available": len([c for c in checks if c.passed is not None]),
            "evidence_total": len(checks),
            "not_applicable_checks": [
                c.chokepoint for c in checks
                if c.passed is None and any(
                    r.code in ("NO_PAYMENT_DETAILS", "NOT_APPLICABLE") for r in c.reasons
                )
            ],
        },
    )
