"""Authorised-sender short-circuit and numeric disambiguation (Phase 9 A+B).

THE BOUNDARY TESTS ARE THE POINT. The short-circuit skips every content check,
so a wrong boundary means tamper detection is silently lost -- a doctored
screenshot of a real NSE circular would return GENUINE. Each exclusion has its
own test, and they should be the last tests anyone deletes.
"""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

import pytest

from core.authority import resolve_authority
from core.fields import extract_all
from core.lexicon.identifiers import mask_identifiers
from core.pipeline import verify
from core.scoring import try_short_circuit

NSE_AWARENESS = """Dear Investor,

NSE cautions investors against fraudulent schemes. NO ONE can promise you
guaranteed or regular return on your investment in the securities market.
Any entity offering assured returns is violating SEBI regulations.

Call our toll free helpline 18002660050 or write to msm@nse.co.in
National Stock Exchange of India Limited
"""


def build_email(addr="msm@nse.co.in", *, name="NSE Investor Awareness",
                subject="Investor awareness", body=NSE_AWARENESS,
                signer=None, dkim="pass", dmarc="pass") -> bytes:
    from_domain = addr.split("@")[-1]
    signing_domain = signer or from_domain
    msg = EmailMessage()
    msg["Message-ID"] = make_msgid(domain=signing_domain)
    msg["Date"] = format_datetime(datetime.now())
    msg["From"] = f"{name} <{addr}>"
    msg["To"] = "investor@example.com"
    msg["Subject"] = subject
    msg["Authentication-Results"] = (
        f"mx.google.com; dkim={dkim} header.i=@{signing_domain} header.s=s1; "
        f"spf=pass smtp.mailfrom=noreply@{from_domain}; "
        f"dmarc={dmarc} (p=REJECT) header.from={from_domain}"
    )
    msg.set_content(body)
    return msg.as_bytes()


# ==========================================================================
# Acceptance: the two reported failures
# ==========================================================================

class TestReportedFailures:
    def test_nse_awareness_email_is_genuine(self):
        """Was FRAUDULENT: its own warning against guaranteed returns was read
        as a promise, its toll-free number as a bank account."""
        verdict, _parsed, _timings = verify(build_email(), filename="nse.eml")
        assert verdict.verdict == "GENUINE"
        assert verdict.short_circuit == "AUTHORISED_SENDER_DKIM_VALID"
        assert verdict.confidence >= 90

    def test_sbi_verified_email_is_genuine(self):
        """Was UNVERIFIED despite passing every authentication check."""
        verdict, _parsed, _timings = verify(
            build_email(addr="alerts@sbi.co.in", name="SBI Alerts",
                        body="Your statement is attached. The password is your PAN."),
            filename="sbi.eml",
        )
        assert verdict.verdict == "GENUINE"
        assert verdict.short_circuit == "AUTHORISED_SENDER_DKIM_VALID"


# ==========================================================================
# The boundary -- one explicit test per exclusion
# ==========================================================================

class TestShortCircuitBoundary:
    def test_screenshot_never_short_circuits(self):
        """An image of an NSE email is not an NSE email: the sender is claimed,
        never proven. Short-circuiting here would lose tamper detection."""
        class FakeParsed:
            source_type = "IMAGE"
            email = None
        assert try_short_circuit(FakeParsed()) is None

    def test_pasted_text_never_short_circuits(self):
        verdict, _parsed, _timings = verify(NSE_AWARENESS)
        assert verdict.short_circuit is None

    def test_inline_forward_never_short_circuits(self):
        """Inline forwarding destroys the original signature."""
        fwd = EmailMessage()
        fwd["From"] = "Investor <someone@gmail.com>"
        fwd["Subject"] = "Fwd: Investor awareness"
        fwd["Authentication-Results"] = (
            "mx.google.com; dkim=pass header.i=@gmail.com; dmarc=pass header.from=gmail.com"
        )
        fwd.set_content(
            "Is this real?\n\n---------- Forwarded message ----------\n"
            "From: NSE <msm@nse.co.in>\nSubject: Investor awareness\n\n" + NSE_AWARENESS
        )
        verdict, _parsed, _timings = verify(fwd.as_bytes(), filename="fwd.eml")
        assert verdict.short_circuit is None

    def test_attached_forward_never_short_circuits(self):
        """The outer signature is the forwarder's, so it proves nothing about
        the original."""
        import email
        import email.policy

        original = email.message_from_bytes(build_email(), policy=email.policy.default)
        fwd = EmailMessage()
        fwd["From"] = "Investor <someone@gmail.com>"
        fwd["Subject"] = "Fwd: check this"
        fwd["Authentication-Results"] = (
            "mx.google.com; dkim=pass header.i=@gmail.com; dmarc=pass header.from=gmail.com"
        )
        fwd.set_content("Attached.")
        fwd.add_attachment(original)
        verdict, _parsed, _timings = verify(fwd.as_bytes(), filename="fwd2.eml")
        assert verdict.short_circuit is None

    def test_dkim_fail_never_short_circuits(self):
        verdict, _p, _t = verify(build_email(dkim="fail"), filename="x.eml")
        assert verdict.short_circuit is None

    def test_dkim_absent_never_short_circuits(self):
        msg = EmailMessage()
        msg["From"] = "NSE <msm@nse.co.in>"
        msg["Subject"] = "no auth header"
        msg.set_content(NSE_AWARENESS)
        verdict, _p, _t = verify(msg.as_bytes(), filename="x.eml")
        assert verdict.short_circuit is None

    def test_dkim_misaligned_never_short_circuits(self):
        """Signed by evil.com while claiming to be nse.co.in. Anyone can sign
        their own mail; only an ALIGNED signature proves the sender."""
        verdict, _p, _t = verify(build_email(signer="evil.com"), filename="x.eml")
        assert verdict.short_circuit is None

    def test_dmarc_fail_never_short_circuits(self):
        verdict, _p, _t = verify(build_email(dmarc="fail"), filename="x.eml")
        assert verdict.short_circuit is None

    def test_unauthorised_domain_never_short_circuits(self):
        verdict, _p, _t = verify(
            build_email(addr="advisor@wealthmultiplier.xyz", name="Wealth"), filename="x.eml"
        )
        assert verdict.short_circuit is None

    def test_tampered_screenshot_still_reaches_tamper_detection(self):
        """The reason the boundary matters: content checks must still run."""
        from pathlib import Path

        fixture = Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "tampered_01.eml"
        if not fixture.exists():
            pytest.skip("tampered fixture not generated")
        verdict, _p, _t = verify(fixture.read_bytes(), filename="tampered_01.eml")
        assert verdict.short_circuit is None
        assert verdict.verdict in ("TAMPERED", "FRAUDULENT")


# ==========================================================================
# Authority resolution
# ==========================================================================

class TestAuthority:
    @pytest.mark.parametrize("domain,claim_type", [
        ("nse.co.in", "EXCHANGE"),
        ("cdslindia.com", "DEPOSITORY"),
        ("sebi.gov.in", "REGULATOR"),
        ("rbi.org.in", "REGULATOR"),
    ])
    def test_known_domains_resolve(self, domain, claim_type):
        authority = resolve_authority(domain)
        assert authority is not None and authority.claim_type == claim_type

    def test_restricted_tld_is_its_own_credential(self):
        """.bank.in is allotted only to RBI-licensed banks, so membership of the
        TLD is the evidence -- no per-domain listing needed."""
        for domain in ("sbi.bank.in", "somebank.bank.in"):
            authority = resolve_authority(domain)
            assert authority is not None
            assert authority.claim_type == "BANKING"
            assert authority.matched_via == "RESTRICTED_TLD"

    def test_fin_in_tld(self):
        authority = resolve_authority("anynbfc.fin.in")
        assert authority is not None and authority.claim_type == "NBFC"

    def test_subdomains_inherit_authority(self):
        authority = resolve_authority("alerts.sbi.co.in")
        assert authority is not None and authority.matched_via == "SUBDOMAIN"

    @pytest.mark.parametrize("domain", [
        "canarabank-dividends.co.in", "wealthmultiplier.xyz", "gmail.com", "",
    ])
    def test_unknown_domains_return_none(self, domain):
        """No evidence is not suspicion -- it is simply no evidence."""
        assert resolve_authority(domain) is None


# ==========================================================================
# Part B -- numeric disambiguation
# ==========================================================================

class TestNumericDisambiguation:
    @pytest.mark.parametrize("label,text,kind", [
        ("NSE toll-free", "call our toll free helpline 18002660050", "TOLL_FREE"),
        ("spaced toll-free", "dial 1800 266 0050 for support", "TOLL_FREE"),
        ("mobile", "contact us on 9876543210", "MOBILE_IN"),
        ("landline", "call 022 26598100 for assistance", "LANDLINE"),
        ("PIN code", "Bandra Kurla Complex, Mumbai 400051", "PIN_CODE"),
        ("SEBI circular", "as per SEBI/HO/MIRSD/DOP/CIR/P/2026/38", "SEBI_CIRCULAR"),
        ("NSE circular", "vide NSE/CML/2026/0042 dated 1 August", "EXCHANGE_CIRCULAR"),
        ("reference no", "Transaction ID TXN20260801994 refers", "REFERENCE_NO"),
    ])
    def test_recognised_as_protected_identifier(self, label, text, kind):
        kinds = {i.kind for i in mask_identifiers(text).identifiers}
        assert kind in kinds, f"{label}: got {kinds}"

    @pytest.mark.parametrize("text", [
        "call our toll free helpline 18002660050",
        "dial 1800 266 0050 for support",
        "contact us on 9876543210",
        "call 022 26598100 for assistance",
        "Bandra Kurla Complex, Mumbai 400051",
        "as per SEBI/HO/MIRSD/DOP/CIR/P/2026/38",
        "Transaction ID TXN20260801994 refers",
    ])
    def test_never_extracted_as_an_account_number(self, text):
        assert extract_all(text).account_numbers == []

    def test_genuine_payment_instruction_still_extracted(self):
        """The disambiguation must not blind us to a real payment destination."""
        fields = extract_all(
            "Please transfer the amount to your beneficiary A/c 123456789012 "
            "IFSC HDFC0001234 immediately."
        )
        assert "123456789012" in fields.account_numbers

    def test_genuine_payment_instruction_still_flagged(self):
        from core.chokepoints import money

        result = money.check(
            "Confirmed IPO allotment. Please transfer Rs 50,000 to beneficiary "
            "A/c 123456789012, IFSC HDFC0001234, immediately to secure your shares."
        )
        assert result.passed is False
        assert any(r.code == "BANK_ACCOUNT_FOR_INVESTMENT" for r in result.reasons)

    def test_helpline_in_investment_context_is_not_a_payment(self):
        """An investment newsletter quoting a helpline must not read as payment."""
        from core.chokepoints import money

        result = money.check(
            "For queries about your demat account and trading services, call our "
            "toll free helpline 18002660050."
        )
        assert not any(r.code == "BANK_ACCOUNT_FOR_INVESTMENT" for r in result.reasons)
