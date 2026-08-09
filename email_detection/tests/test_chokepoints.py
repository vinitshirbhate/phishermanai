"""Unit tests for the four chokepoints.

Every module is tested three ways: a clear pass, a clear failure, and an
ambiguous input that must return passed=None rather than guessing. The
three-valued outcome is the point -- a chokepoint that answers False when it
has no evidence is a chokepoint that calls honest messages fraud.

The regression cases named in the build brief are marked REGRESSION.
"""

from __future__ import annotations

import pytest

from core.chokepoints import claim, delivery, entity, money
from core.chokepoints.base import CheckResult

# --------------------------------------------------------------------------
# Shared fixtures
# --------------------------------------------------------------------------

GENUINE_DIVIDEND = (
    "Dear Shareholder, the Board of Directors has recommended a final dividend "
    "of Rs 4 per equity share for the financial year 2025-26, subject to "
    "approval of the members at the Annual General Meeting. The record date "
    "for the purpose of the dividend has been fixed as Friday, 25 July 2026."
)

GENUINE_EVOTING = (
    "Notice is hereby given that the remote e-voting period commences on "
    "Saturday, 8 August 2026 at 9:00 A.M. and ends on Monday, 10 August 2026 "
    "at 5:00 P.M. Members may cast their vote at https://evoting.nsdl.com"
)

CLEAN_SET = [
    GENUINE_DIVIDEND,
    GENUINE_EVOTING,
    "Your quarterly portfolio statement for July 2026 is attached for your records.",
    "Mutual fund investments are subject to market risks. Read all scheme related "
    "documents carefully before investing.",
    "The 47th Annual General Meeting will be held on 12 August 2026 through video conferencing.",
    "We do not guarantee any returns. Past performance is not indicative of future results.",
    "Log in at https://kite.zerodha.com to view your holdings and download your contract note.",
    "Intimation of record date for payment of final dividend on equity shares for FY 2025-26.",
    "Please update your KYC details through the registrar portal at your convenience.",
    "The Board meeting to consider unaudited financial results is scheduled for 17 July 2026.",
]


def assert_result(result: CheckResult, chokepoint: str) -> None:
    """Every check must satisfy the shared contract."""
    assert result.chokepoint == chokepoint
    assert result.passed in (True, False, None)
    assert 0.0 <= result.confidence <= 1.0
    assert 0 <= result.severity <= 5
    for reason in result.reasons:
        assert reason.code and reason.message
        assert 0 <= reason.severity <= 5
        assert isinstance(reason.evidence, dict)


# ==========================================================================
# MONEY
# ==========================================================================

class TestMoney:
    def test_pass_validated_broker_handle(self):
        r = money.check("Transfer your trading margin to zerodha.brk@valid as instructed.")
        assert_result(r, "MONEY")
        assert r.passed is True
        assert any(x.code == "UPI_VALIDATED_INTERMEDIARY" for x in r.reasons)

    def test_pass_validated_mutual_fund_handle(self):
        r = money.check("Your SIP will be debited to hdfcamc.mf@valid.")
        assert r.passed is True

    # REGRESSION: payment to a personal handle for an IPO -> severity 5
    def test_regression_personal_upi_for_ipo(self):
        r = money.check("Confirmed IPO allotment! Pay Rs 50,000 to 9876543210@ybl to book your shares.")
        assert_result(r, "MONEY")
        assert r.passed is False
        assert r.severity == 5
        assert any(x.code == "PERSONAL_UPI_FOR_INVESTMENT" for x in r.reasons)

    def test_fail_fake_app_withdrawal_fee(self):
        r = money.check("Your profit is ready. Pay 18% tax to 8887776665@paytm to withdraw your balance.")
        assert r.passed is False
        assert r.severity == 5

    def test_fail_destination_bank_mismatch(self):
        r = money.check(
            "Canara Bank unclaimed dividend: transfer Rs 500 to A/c 123456789012 "
            "IFSC HDFC0001234 to receive your investment payout.",
            claimed_entity="Canara Bank",
        )
        assert r.passed is False
        assert any(x.code == "DESTINATION_BANK_MISMATCH" for x in r.reasons)

    def test_fail_malformed_ifsc(self):
        r = money.check("Send your investment to A/c 123456789012 IFSC HDFCX001234")
        assert any(x.code in ("IFSC_MALFORMED", "BANK_ACCOUNT_FOR_INVESTMENT") for x in r.reasons)

    def test_ambiguous_no_payment_details(self):
        """A genuine dividend notice asks for no money: None, not False."""
        r = money.check(GENUINE_DIVIDEND)
        assert_result(r, "MONEY")
        assert r.passed is None
        assert any(x.code == "NO_PAYMENT_DETAILS" for x in r.reasons)

    def test_ambiguous_unrecognised_handle(self):
        r = money.check("Contact us regarding your account at someone@unknownpsp")
        assert r.passed is None

    def test_qr_payload_payment_address(self):
        r = money.check(
            "Scan to pay for your investment",
            qr_payloads=["upi://pay?pa=fraudster@ybl&pn=Broker&am=50000"],
        )
        assert any(x.code == "QR_CONTAINS_PAYMENT_ADDRESS" for x in r.reasons)
        assert r.severity == 5

    def test_consumer_payment_link(self):
        r = money.check("Complete your investment at https://rzp.io/l/abc123")
        assert any(x.code == "CONSUMER_PAYMENT_LINK" for x in r.reasons)

    def test_sebi_check_lookup_never_calls_live(self):
        out = money.sebi_check_lookup("zerodha.brk@valid")
        assert out["checked_live"] is False
        assert out["is_validated_intermediary"] is True


# ==========================================================================
# CLAIM
# ==========================================================================

class TestClaim:
    # REGRESSION: "guaranteed 30% monthly returns" -> severity 5
    def test_regression_guaranteed_monthly_returns(self):
        r = claim.check("Guaranteed 30% monthly returns from our expert trading desk.")
        assert_result(r, "CLAIM")
        assert r.passed is False
        assert r.severity == 5

    def test_fail_hinglish_guarantee(self):
        r = claim.check("Gauranteed profit har mahine, 100% safe investment!")
        assert r.passed is False
        assert r.severity == 5

    def test_fail_devanagari_guarantee(self):
        r = claim.check("पक्का रिटर्न मिलेगा, कोई जोखिम नहीं")
        assert r.passed is False

    def test_fail_homoglyph_evasion(self):
        """Cyrillic 'а' in 'guаranteed' must not defeat the rule."""
        r = claim.check("guаranteed returns of 25% monthly")
        assert r.passed is False

    def test_fail_zero_risk_equity(self):
        r = claim.check("Zero risk equity trading with assured payouts.")
        assert r.passed is False

    def test_fail_pay_tax_to_withdraw(self):
        r = claim.check("Pay the processing fee to withdraw your profit today.")
        assert r.passed is False
        assert r.severity == 5

    def test_combination_rule_escalates(self):
        r = claim.check(
            "Guaranteed 40% returns! Pay now to 9876543210@ybl. Hurry, only 2 slots left today!",
            has_payment_request=True,
        )
        assert any(x.code == "FRAUD_PATTERN_COMBINATION" for x in r.reasons)
        assert r.severity == 5

    def test_negation_guard_disclaimer_passes(self):
        """The compliance disclaimer must not read as an illegal promise."""
        r = claim.check("We do not guarantee any returns on your investment.")
        assert_result(r, "CLAIM")
        assert r.passed is True

    def test_negation_guard_market_risk_passes(self):
        r = claim.check("Mutual fund investments are subject to market risks.")
        assert r.passed is True

    def test_ambiguous_empty_text(self):
        r = claim.check("")
        assert r.passed is None

    @pytest.mark.parametrize("text,monthly", [
        ("Earn 2% daily returns", 60.0),
        ("40% in 3 months", 13.33),
        ("returns of 8% per month", 8.0),
        ("get 10% every week", 42.86),
    ])
    def test_return_rate_normalised_to_monthly(self, text, monthly):
        promises = claim.extract_return_promises(text.lower())
        assert promises and promises[0]["monthly_percent"] == pytest.approx(monthly, abs=0.01)

    def test_plausible_return_not_flagged(self):
        """12% a year is 1% a month -- an ordinary claim, not fraud."""
        r = claim.check("The fund targets 12% annual returns over the long term.")
        assert not any(x.code == "IMPLAUSIBLE_RETURN_RATE" for x in r.reasons)

    def test_matched_spans_returned_for_highlighting(self):
        r = claim.check("Guaranteed returns of 30% monthly!")
        spans = [x.evidence.get("span") for x in r.reasons if x.evidence.get("span")]
        assert spans and all(len(s) == 2 and s[0] < s[1] for s in spans)


# ==========================================================================
# DELIVERY
# ==========================================================================

class TestDelivery:
    # REGRESSION: canarabank-dividends.co.in -> LOOKALIKE_DOMAIN
    def test_regression_lookalike_domain(self):
        r = delivery.check("Claim your dividend at https://canarabank-dividends.co.in/claim")
        assert_result(r, "DELIVERY")
        assert r.passed is False
        assert any(x.code == "LOOKALIKE_DOMAIN" for x in r.reasons)
        assert r.severity == 5

    # REGRESSION: a genuine broker domain passes with no false positives
    def test_regression_genuine_broker_domain_clean(self):
        r = delivery.check("View your holdings at https://kite.zerodha.com")
        assert_result(r, "DELIVERY")
        assert r.passed is True
        assert r.severity == 0

    def test_pass_official_evoting_domain(self):
        r = delivery.check("Cast your vote at https://evoting.nsdl.com")
        assert r.passed is True

    def test_fail_edit_distance_typosquat(self):
        r = delivery.check("Login at https://canarabankk.com")
        assert any(x.code == "LOOKALIKE_DOMAIN" for x in r.reasons)

    def test_fail_apk_download(self):
        r = delivery.check("Install our trading app: https://fast-profit.top/app.apk")
        assert any(x.code == "APK_DOWNLOAD_LINK" for x in r.reasons)
        assert r.severity == 5

    def test_fail_elevated_risk_tld(self):
        r = delivery.check("Register at http://sebi-refund.xyz/form")
        assert r.passed is False

    def test_shortener_flagged(self):
        r = delivery.check("Details here https://bit.ly/3xY9kLm")
        assert any(x.code == "URL_SHORTENER_IN_FINANCIAL_MESSAGE" for x in r.reasons)

    def test_ambiguous_no_urls(self):
        r = delivery.check("Please call our office during business hours.")
        assert_result(r, "DELIVERY")
        assert r.passed is None

    def test_unknown_domain_is_not_fraud(self):
        """An unmapped domain is unknown, not guilty."""
        r = delivery.check("See https://some-small-company-blog.com/post")
        assert r.passed is not False or all(
            x.code != "LOOKALIKE_DOMAIN" for x in r.reasons
        )

    def test_registrable_domain_extraction(self):
        assert delivery.registrable_domain("https://kite.zerodha.com/orders") == "zerodha.com"
        assert delivery.registrable_domain("canarabank-dividends.co.in") == "canarabank-dividends.co.in"


# ==========================================================================
# ENTITY
# ==========================================================================

class TestEntity:
    # REGRESSION: real SEBI reg number + wrong entity name -> REG_NO_NAME_MISMATCH
    def test_regression_reg_no_name_mismatch(self):
        r = entity.check(
            "Alpha Wealth Advisory Services, SEBI Registration No. INA000017523.",
            claimed_entity="Alpha Wealth Advisory Services",
        )
        assert_result(r, "ENTITY")
        assert r.passed is False
        assert r.severity == 5
        assert any(x.code == "REG_NO_NAME_MISMATCH" for x in r.reasons)

    def test_pass_reg_no_matches_holder(self):
        r = entity.check(
            "1 Finance Private Limited, SEBI Reg INA000017523",
            claimed_entity="1 Finance Private Limited",
        )
        assert r.passed is True
        assert any(x.code == "REG_NO_VERIFIED" for x in r.reasons)

    def test_fail_authority_demands_payment(self):
        r = entity.check("SEBI NOTICE: your demat account is frozen. Pay Rs 5,000 penalty now.")
        assert r.passed is False
        assert any(x.code == "AUTHORITY_DEMANDS_PAYMENT" for x in r.reasons)
        assert r.severity == 5

    def test_pass_known_listed_company(self):
        r = entity.check("Canara Bank has declared a final dividend of Rs 4 per equity share.")
        assert r.passed is True

    def test_ambiguous_no_identifiers(self):
        r = entity.check("Thanks for your message, we will get back to you shortly.")
        assert_result(r, "ENTITY")
        assert r.passed is None

    def test_isin_check_digit_valid(self):
        assert entity.is_valid_isin("INE002A01018") is True

    def test_isin_check_digit_rejects_tampered(self):
        assert entity.is_valid_isin("INE002A01019") is False

    def test_isin_check_digit_computation(self):
        assert entity.isin_check_digit("INE002A01018") == 8

    def test_fail_invalid_isin_in_message(self):
        r = entity.check("Buy shares of ISIN INE002A01019 at a discount today.")
        assert any(x.code == "ISIN_CHECK_DIGIT_FAILED" for x in r.reasons)

    @pytest.mark.parametrize("cin,valid", [
        ("L65110KA1906PLC001983", True),
        ("U74999MH2015PTC266499", True),
        ("X65110KA1906PLC001983", False),   # bad first character
        ("L65110KA1906PLC00198", False),    # too short
    ])
    def test_cin_validation(self, cin, valid):
        assert entity.is_valid_cin(cin) is valid

    def test_reg_no_not_in_register(self):
        r = entity.check("Trust Advisory, SEBI Reg INA999999999", claimed_entity="Trust Advisory")
        assert any(x.code == "REG_NO_NOT_FOUND" for x in r.reasons)

    def test_entity_resolution_handles_suffix_variants(self):
        a = entity.resolve_entity("Canara Bank Ltd")
        b = entity.resolve_entity("CANARA BANK LIMITED")
        assert a and b and a["normalised_name"] == b["normalised_name"]


# ==========================================================================
# False-positive suite: the clean set must stay clean
# ==========================================================================

class TestNoFalsePositives:
    @pytest.mark.parametrize("text", CLEAN_SET)
    def test_claim_no_false_positive(self, text):
        r = claim.check(text)
        assert r.passed is not False, f"CLAIM false positive: {[x.code for x in r.reasons]}"

    @pytest.mark.parametrize("text", CLEAN_SET)
    def test_money_no_false_positive(self, text):
        r = money.check(text)
        assert r.passed is not False, f"MONEY false positive: {[x.code for x in r.reasons]}"

    @pytest.mark.parametrize("text", CLEAN_SET)
    def test_delivery_no_false_positive(self, text):
        r = delivery.check(text)
        assert r.severity < 4, f"DELIVERY false positive: {[x.code for x in r.reasons]}"

    @pytest.mark.parametrize("text", CLEAN_SET)
    def test_entity_no_false_positive(self, text):
        r = entity.check(text)
        assert r.passed is not False, f"ENTITY false positive: {[x.code for x in r.reasons]}"


# ==========================================================================
# Contract conformance
# ==========================================================================

class TestContract:
    @pytest.mark.parametrize("module,name", [
        (money, "MONEY"), (claim, "CLAIM"), (delivery, "DELIVERY"), (entity, "ENTITY"),
    ])
    def test_all_modules_satisfy_contract(self, module, name):
        for text in ("", "Guaranteed 50% monthly returns, pay 98765@ybl now!", GENUINE_DIVIDEND):
            assert_result(module.check(text), name)

    @pytest.mark.parametrize("module,name", [
        (money, "MONEY"), (claim, "CLAIM"), (delivery, "DELIVERY"), (entity, "ENTITY"),
    ])
    def test_result_is_json_serialisable(self, module, name):
        import json
        payload = module.check("Guaranteed returns, pay 98765@ybl").to_dict()
        json.loads(json.dumps(payload))
        assert payload["chokepoint"] == name
