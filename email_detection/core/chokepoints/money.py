"""CHOKEPOINT 2 -- MONEY. Where is the money actually going?

This is the strongest of the four checks and the hardest for a fraudster to
work around, because it does not care how convincing the front end is.

The reasoning
-------------
Since 1 October 2025 every SEBI-registered intermediary that collects money
from investors must do so through a validated UPI address on the "@valid"
handle, carrying a category suffix -- ".brk" for brokers, ".mf" for mutual
funds -- and that address is verifiable through SEBI Check.

The consequence is sharp: if investment money is being routed anywhere else --
a personal @ybl or @okhdfcbank address, an individual's bank account, a QR code
in a screenshot -- then whoever is asking is not a registered intermediary
collecting investor funds. A fake trading app can clone a broker's entire
interface, but it cannot obtain a validated @valid handle, because issuing one
requires the registration it does not have.

That is why this module catches fake trading apps, fake IPO allotments, fake
advisers, fake redemptions and digital-arrest payment demands with the same
few rules.

Nothing here is heuristic scoring. Each rule is a factual statement about
where money is going, compared against reference data on disk.
"""

from __future__ import annotations

import re
from typing import Any

from core.chokepoints.base import MONEY, CheckResult, Reason
from core.fields import ExtractedFields
from core.lexicon.identifiers import NON_ACCOUNT_KINDS, mask_identifiers
from core.reference import classify_upi_handle, is_valid_ifsc_format, resolve_ifsc
from core.textnorm import normalise_company_name, normalise_for_matching

# Wording that establishes the money is an INVESTMENT payment rather than, say,
# a utility bill. Chokepoint 2's severity-5 rules apply in that context.
INVESTMENT_CONTEXT = (
    "invest", "trading", "trade", "ipo", "allotment", "share", "stock", "equity",
    "mutual fund", "sip", "demat", "portfolio", "broker", "dividend", "nifty",
    "profit", "return", "margin", "f&o", "option", "commodity", "securities",
    "pre-ipo", "unlisted", "nse", "bse", "sebi",
)

PAYMENT_VERBS = (
    "pay", "transfer", "send", "deposit", "remit", "credit", "fund",
    "add money", "recharge", "top up", "topup", "upi", "scan", "qr",
)

# Payment-collection links. A registered intermediary collects funds inside its
# own app or through the validated handle, never via a consumer payment page.
PAYMENT_LINK_RE = re.compile(
    r"(?:razorpay\.com/paymentlink|rzp\.io|pages\.razorpay|paytm\.me|payu\.in|"
    r"instamojo\.com|pay\.google\.com|phonepe\.com/pay|bharatpe\.com|"
    r"cashfree\.com|billdesk\.com/pay|ccavenue\.com|paypal\.me|"
    r"buy\.stripe\.com|wise\.com/pay)",
    re.I,
)

UPI_LINK_RE = re.compile(r"upi://pay\?[^\s\"'<>]+", re.I)


# Window either side of a candidate account number when testing the three
# contextual conditions below.
ACCOUNT_WINDOW = 140

_PAYMENT_VERB_RE = re.compile(
    r"\b(?:transfer|remit|deposit|pay|paid|payment|send|sending|credit|fund|"
    r"neft|rtgs|imps|wire|top\s*-?\s*up)\b", re.I)
_SECOND_PERSON_RE = re.compile(
    r"\b(?:you|your|yours|kindly|please|must|need\s+to|required\s+to|immediately)\b"
    # An IMPERATIVE is second person even with no pronoun. "Transfer Rs 50,000
    # to A/c 123456789012" is addressed to the reader as plainly as "you must
    # transfer", and requiring an explicit pronoun let that instruction through.
    r"|(?:^|[.!?\n]\s*)(?:now\s+)?(?:transfer|pay|remit|deposit|send|credit)\b",
    re.I)
_ACCOUNT_CONTEXT_RE = re.compile(
    r"\b(?:a/c|a\.c|account|acct|beneficiary|ifsc|bank|branch|payee)\b", re.I)


def _near(text: str, needle: str, pattern: re.Pattern[str]) -> bool:
    """Does `pattern` occur within ACCOUNT_WINDOW characters of `needle`?"""
    index = text.find(needle)
    if index < 0:
        return False
    lo = max(0, index - ACCOUNT_WINDOW)
    hi = min(len(text), index + len(needle) + ACCOUNT_WINDOW)
    return bool(pattern.search(text[lo:hi]))


def _payment_verb_near(text: str, account: str) -> bool:
    return _near(text, account, _PAYMENT_VERB_RE)


def _second_person_near(text: str, account: str) -> bool:
    return _near(text, account, _SECOND_PERSON_RE)


def _account_context_near(text: str, account: str) -> bool:
    return _near(text, account, _ACCOUNT_CONTEXT_RE)


def _has_investment_context(text: str) -> bool:
    low = normalise_for_matching(text)
    return any(k in low for k in INVESTMENT_CONTEXT)


def _has_payment_request(text: str) -> bool:
    low = normalise_for_matching(text)
    return any(k in low for k in PAYMENT_VERBS)


def sebi_check_lookup(upi_id: str, *, allow_live: bool = False) -> dict[str, Any]:
    """Look up a UPI address in SEBI Check.

    SEBI Check is SEBI's facility for confirming that a UPI address belongs to a
    registered intermediary. The real request shape is documented here so the
    integration is a configuration change rather than a rewrite:

        POST https://www.sebi.gov.in/sebiweb/check/validateUpi
        body: {"upiId": "<handle>"}
        -> {"valid": bool, "entityName": str, "registrationNo": str,
            "category": "BROKER"|"MUTUAL_FUND"|..., "validatedOn": "<iso8601>"}

    THIS IS NEVER CALLED LIVE ON THE DEMO PATH. Two reasons, both deliberate:
    the demo must run with the network unplugged, and a per-verification call to
    a regulator's endpoint is not something to ship without an agreement in
    place. We answer from the structural rules in upi_handles.csv, which encode
    the same guarantee the lookup would confirm -- a handle that is not
    *.brk@valid or *.mf@valid cannot be a registered intermediary collecting
    investor funds, whatever a lookup would say.
    """
    rule = classify_upi_handle(upi_id)
    return {
        "upi_id": upi_id,
        "source": "local_structural_rules",
        "checked_live": False,
        "category": rule.category if rule else "UNKNOWN",
        "is_validated_intermediary": bool(rule and rule.category == "VALID_INTERMEDIARY"),
        "psp_or_entity": rule.psp_or_entity if rule else None,
        "note": "SEBI Check not called; see docstring for the live request shape.",
    }


def _entity_owns_destination(
    claimed_entity: str | None,
    destination: str,
    known_upi_handles: list[str] | None,
) -> bool | None:
    """Is this destination one the claimed entity is known to use?

    None means we hold no record either way -- the common case, and it must not
    be reported as a mismatch.
    """
    if not claimed_entity or not known_upi_handles:
        return None
    dest = destination.strip().lower()
    return any(dest == h.strip().lower() for h in known_upi_handles)


def check(
    text: str,
    fields: ExtractedFields | None = None,
    *,
    claimed_entity: str | None = None,
    entity_upi_handles: list[str] | None = None,
    entity_bank_accounts: list[str] | None = None,
    qr_payloads: list[str] | None = None,
) -> CheckResult:
    """Run the MONEY chokepoint.

    `qr_payloads` are decoded QR contents from an image (pyzbar), passed in by
    the image pipeline so a payment QR inside a screenshot is checked exactly
    like a typed UPI address.
    """
    result = CheckResult(chokepoint=MONEY, passed=None, confidence=0.0)

    text = text or ""
    if fields is None:
        from core.fields import extract_all
        fields = extract_all(text)

    investment_context = _has_investment_context(text)
    payment_request = _has_payment_request(text)

    # QR payloads are payment instructions too -- fold any upi:// target in.
    upi_ids = list(fields.upi_ids)
    for payload in qr_payloads or []:
        for match in UPI_LINK_RE.finditer(payload):
            pa = re.search(r"[?&]pa=([^&\s]+)", match.group(0))
            if pa:
                decoded = pa.group(1).strip().lower()
                if decoded not in upi_ids:
                    upi_ids.append(decoded)
                    result.add(Reason(
                        code="QR_CONTAINS_PAYMENT_ADDRESS",
                        message=(
                            f"The QR code in this image is a payment request to {decoded}. "
                            "A QR code hides the destination until you scan it, which is "
                            "exactly why it is used."
                        ),
                        evidence={"qr_payload": match.group(0)[:200], "upi_id": decoded},
                        severity=3,
                    ))

    findings = 0

    # ---------------------------------------------------------------- Rule A/B
    # UPI destinations, classified against the validated-handle rules.
    for upi_id in upi_ids:
        findings += 1
        rule = classify_upi_handle(upi_id)

        if rule is None:
            result.add(Reason(
                code="UPI_HANDLE_UNRECOGNISED",
                message=(
                    f"We do not recognise the UPI address {upi_id}. Registered "
                    "intermediaries collect investor money on a validated address "
                    "ending in .brk@valid or .mf@valid."
                ),
                evidence={"upi_id": upi_id, "sebi_check": sebi_check_lookup(upi_id)},
                severity=3 if investment_context else 2,
            ))
            continue

        if rule.category == "VALID_INTERMEDIARY":
            result.add(Reason(
                code="UPI_VALIDATED_INTERMEDIARY",
                message=(
                    f"{upi_id} is a SEBI-validated intermediary address. "
                    "Handles on @valid are issued only to registered intermediaries."
                ),
                evidence={"upi_id": upi_id, "category": rule.category, "basis": rule.source},
                severity=0,
            ))
            continue

        if rule.category == "VALID_NO_CATEGORY":
            result.add(Reason(
                code="UPI_VALID_MISSING_CATEGORY",
                message=(
                    f"{upi_id} uses the @valid handle but without the .brk or .mf "
                    "suffix a registered intermediary collecting investor money must "
                    "carry. Verify it on SEBI Check before paying."
                ),
                evidence={"upi_id": upi_id, "category": rule.category},
                severity=rule.severity or 3,
            ))
            continue

        # PERSONAL_PSP -- the severity-5 case, when money is being requested for
        # an investment purpose.
        if investment_context and payment_request:
            severity, code = 5, "PERSONAL_UPI_FOR_INVESTMENT"
            message = (
                f"The money is going to {upi_id}, a personal {rule.psp_or_entity} "
                "address. Since 1 October 2025 every SEBI-registered intermediary "
                "must collect investor money on a validated .brk@valid or .mf@valid "
                "address. A personal handle means this is not a registered "
                "intermediary, however genuine the message looks."
            )
        else:
            severity, code = 3, "PERSONAL_UPI_PRESENT"
            message = (
                f"This message contains a personal {rule.psp_or_entity} UPI address "
                f"({upi_id}). Never send investment money to a personal handle."
            )

        result.add(Reason(
            code=code,
            message=message,
            evidence={
                "upi_id": upi_id,
                "psp": rule.psp_or_entity,
                "category": rule.category,
                "investment_context": investment_context,
                "payment_request": payment_request,
                "legal_basis": rule.source,
            },
            severity=severity,
        ))

        # -------------------------------------------------------------- Rule D
        owned = _entity_owns_destination(claimed_entity, upi_id, entity_upi_handles)
        if owned is False:
            result.add(Reason(
                code="DESTINATION_NOT_LINKED_TO_CLAIMED_ENTITY",
                message=(
                    f"This message says it is from {claimed_entity}, but the money goes "
                    f"to {upi_id}, which is not an address {claimed_entity} uses."
                ),
                evidence={
                    "claimed_entity": claimed_entity,
                    "destination": upi_id,
                    "known_handles": entity_upi_handles,
                },
                severity=5,
            ))

    # ------------------------------------------------------------------ Rule C
    # IFSC codes: validate the format, resolve the bank, and compare against the
    # institution the message claims to be.
    for ifsc in fields.ifsc_codes:
        findings += 1
        if not is_valid_ifsc_format(ifsc):
            result.add(Reason(
                code="IFSC_MALFORMED",
                message=(
                    f"The IFSC code {ifsc} is not a valid format. A real IFSC is four "
                    "letters, then a zero, then six characters."
                ),
                evidence={"ifsc": ifsc},
                severity=4,
            ))
            continue

        bank = resolve_ifsc(ifsc)
        if bank is None:
            result.add(Reason(
                code="IFSC_BANK_UNKNOWN",
                message=(
                    f"The IFSC code {ifsc} is correctly formatted but we cannot match it "
                    "to a bank in our reference list."
                ),
                evidence={"ifsc": ifsc},
                severity=2,
            ))
            continue

        result.add(Reason(
            code="PAYMENT_DESTINATION_BANK",
            message=f"The account given belongs to {bank.name} (from IFSC {ifsc}).",
            evidence={"ifsc": ifsc, "bank": bank.name, "bank_type": bank.bank_type},
            severity=0,
        ))

        if claimed_entity:
            claimed_norm = normalise_company_name(claimed_entity)
            bank_norm = normalise_company_name(bank.name)
            # Only meaningful when the claimed sender is itself a bank; a company
            # legitimately banks anywhere, so a mismatch is only evidence when
            # the message claims to BE the institution.
            claimed_is_bank = "bank" in claimed_norm
            if claimed_is_bank and bank_norm and bank_norm not in claimed_norm and claimed_norm not in bank_norm:
                result.add(Reason(
                    code="DESTINATION_BANK_MISMATCH",
                    message=(
                        f"This message claims to be from {claimed_entity}, but the account "
                        f"it asks you to pay is held at {bank.name}."
                    ),
                    evidence={"claimed_entity": claimed_entity, "destination_bank": bank.name, "ifsc": ifsc},
                    severity=5,
                ))

    # Bank account numbers with an investment payment request.
    #
    # Identifiers that merely LOOK like account numbers are filtered out first.
    # A CDSL BO ID is 16 digits and a genuine holding statement is full of them;
    # one was read as a payment destination and scored a real CDSL statement
    # FRAUDULENT with no payment verb anywhere in the message.
    protected = {
        i.value for i in mask_identifiers(text).identifiers
        if i.kind in NON_ACCOUNT_KINDS
    }
    for account in fields.account_numbers:
        if account in protected:
            continue
        findings += 1
        # FOUR conditions must ALL hold before a number is called a payment
        # destination. Each rules out a class of genuine number that was
        # previously misread:
        #
        #   not protected      -- toll-free, mobile, PIN, demat, circular refs
        #   payment verb       -- somebody is actually moving money
        #   second person      -- YOU are being asked to move it, not told that
        #                         a refund was credited to you
        #   account context    -- an A/C, account or IFSC token sits nearby, so
        #                         the digits are being presented AS an account
        if (investment_context and payment_request
                and _payment_verb_near(text, account)
                and _second_person_near(text, account)
                and _account_context_near(text, account)):
            owned = _entity_owns_destination(claimed_entity, account, entity_bank_accounts)
            result.add(Reason(
                code="BANK_ACCOUNT_FOR_INVESTMENT",
                message=(
                    f"This message asks you to transfer investment money to account "
                    f"{account[:4]}...{account[-4:]}. Registered intermediaries collect "
                    "client funds only in a designated client bank account, and they do "
                    "not ask for transfers over chat or e-mail."
                ),
                evidence={"account_number": account, "owned_by_claimed_entity": owned},
                severity=5 if owned is False else 4,
            ))

    # Consumer payment-collection links.
    haystack = f"{text} {' '.join(fields.urls)}"
    for match in PAYMENT_LINK_RE.finditer(haystack):
        findings += 1
        result.add(Reason(
            code="CONSUMER_PAYMENT_LINK",
            message=(
                f"This message contains a payment-collection link ({match.group(0)}). "
                "Registered intermediaries take money inside their own app or through "
                "their validated UPI address, not through a payment page sent to you."
            ),
            evidence={"link": match.group(0)},
            severity=4 if investment_context else 3,
        ))

    # ------------------------------------------------------------------ Verdict
    failures = [r for r in result.reasons if r.severity >= 4]
    positives = [r for r in result.reasons if r.code in
                 ("UPI_VALIDATED_INTERMEDIARY", "PAYMENT_DESTINATION_BANK")]

    if failures:
        result.passed = False
        result.confidence = min(1.0, 0.6 + 0.1 * len(failures))
    elif positives and not failures:
        result.passed = True
        result.confidence = 0.8
    elif findings == 0:
        # No payment details at all. That is not a pass and not a failure --
        # there was simply nothing for this chokepoint to judge.
        result.passed = None
        result.confidence = 0.0
        result.add(Reason(
            code="NO_PAYMENT_DETAILS",
            message="This message does not ask for money or contain payment details.",
            evidence={},
            severity=0,
        ))
    else:
        result.passed = None
        result.confidence = 0.4

    return result
