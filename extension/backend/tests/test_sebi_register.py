"""
Integrity tests for the real SEBI register and the identity engine that resolves
against it.

The highest-value test in this file is test_derived_family_covers_every_row: it
asserts that the registration-number matcher GENERATED FROM THE DATA matches
100% of the register. An unmatched row means the matcher stopped recognising a
real registrant's number, which downstream reads as `absent` against a
legitimate firm — a G-2 violation.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engines import securities_identity as si  # noqa: E402

REGISTER_PATH = ROOT / "backend" / "data" / "sebi_register.json"
SNAPSHOT_PATH = ROOT / "extension" / "data" / "securities_snapshot.json"

# A real GIFT City IFSC Investment Adviser. Its number is NOT numeric-after-the-
# category-letter, so a hand-written INA\d{9} silently fails it. Both shapes are
# 12 characters. This is the explicit regression case required by the task.
IFSC_ADVISER = "INAIFSC10001"


@pytest.fixture(scope="module")
def register() -> dict:
    return json.loads(REGISTER_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def test_register_is_real_not_synthetic(register):
    meta = register["registry_meta"]
    assert meta["synthetic_subset"] is False
    assert meta["authoritative"] is True
    assert meta["record_count"] >= 3000, "G-0 requires at least 3,000 real records"
    assert meta["record_count"] == len(register["intermediaries"])


def test_per_category_as_on_dates_present(register):
    """Per category, never one global date — SEBI refreshes each on its own cadence."""
    meta = register["registry_meta"]
    per_cat = meta["per_category_as_on_dates"]
    assert per_cat, "registry_meta.per_category_as_on_dates must not be empty"
    assert set(per_cat) == set(meta["covered_categories"])
    for cat, date in per_cat.items():
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""), f"{cat} has no as-on date"


def test_registration_numbers_are_unique(register):
    numbers = [r["reg_number"] for r in register["intermediaries"]]
    assert len(numbers) == len(set(numbers))


# --------------------------------------------------------------------------- #
# DPDPA field minimisation
# --------------------------------------------------------------------------- #
def test_no_personal_data_in_shipped_register(register):
    """No postal address, phone, fax or contact-person field may ship."""
    banned = ("address", "phone", "telephone", "fax", "contact", "mobile")
    keys = {k.lower() for rec in register["intermediaries"] for k in rec}
    leaked = [k for k in keys if any(b in k for b in banned)]
    assert leaked == [], f"personal-data fields present in shipped register: {leaked}"


def test_email_local_parts_are_not_shipped(register):
    """Only the e-mail DOMAIN is retained; the local part is PII."""
    for rec in register["intermediaries"]:
        for field in ("email_domain", "domain_anchor"):
            value = rec.get(field)
            assert value is None or "@" not in value, f"{field} retains a full address"


def test_free_mail_domains_are_never_identity_anchors(register):
    """Anchoring on gmail.com would let any consumer-mail sender reach `valid`."""
    for rec in register["intermediaries"]:
        anchor = rec.get("domain_anchor")
        assert anchor is None or anchor.lower() not in {
            "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com",
            "rediffmail.com", "icloud.com", "live.com",
        }, f"{rec['reg_number']} anchors identity on a free-mail domain"


# --------------------------------------------------------------------------- #
# The derived matcher — the assertion that matters
# --------------------------------------------------------------------------- #
def test_derived_family_covers_every_row(register):
    """100% of the register must be matched IN FULL by the generated family."""
    matcher = si._reg_matcher()          # raises RegisterIntegrityError if not
    unmatched = []
    for rec in register["intermediaries"]:
        rn = rec["reg_number"]
        m = matcher.search(rn)
        if m is None or m.group(0).upper() != rn.upper():
            unmatched.append(rn)
    assert unmatched == [], (
        f"{len(unmatched)} register rows unmatched, e.g. {unmatched[:5]}. "
        "This is a defect in the matcher generator, not a new fraud type."
    )


def test_recognition_family_also_covers_every_row(register):
    matcher, lengths = si._recognition_matcher()
    for rec in register["intermediaries"]:
        rn = rec["reg_number"]
        m = matcher.search(rn)
        assert m is not None and m.group(0).upper() == rn.upper(), rn
        assert not lengths or len(rn) in lengths


def test_matcher_generator_is_loud_when_it_under_fits():
    """A matcher that misses a row must raise, not warn."""
    bad = re.compile(r"\bINA\d{9,9}\b")           # the classic hand-written pattern
    rows = [{"reg_number": "INA000000037"}, {"reg_number": IFSC_ADVISER}]
    with pytest.raises(si.RegisterIntegrityError) as exc:
        si._assert_family_covers_register(bad, rows)
    assert IFSC_ADVISER in str(exc.value)


def test_derive_prefix_shapes():
    assert si.derive_prefix("INH000004017") == "INH"
    assert si.derive_prefix(IFSC_ADVISER) == "INAIFSC"
    assert si.derive_prefix("ARN-123456") == "ARN"
    assert si.derive_prefix("IN-DP-NSDL-321-2024") == "IN-DP"


# --------------------------------------------------------------------------- #
# INAIFSC10001 — the explicit regression case
# --------------------------------------------------------------------------- #
def test_ifsc_adviser_is_in_the_register(register):
    by_number = {r["reg_number"]: r for r in register["intermediaries"]}
    assert IFSC_ADVISER in by_number, f"{IFSC_ADVISER} missing from the register"
    assert by_number[IFSC_ADVISER]["reg_prefix"] == "INAIFSC"


def test_ifsc_adviser_is_extracted_from_text():
    claims = si.extract_claims(f"Our SEBI registration is {IFSC_ADVISER} for IFSC clients.")
    assert claims == [IFSC_ADVISER]


def test_ifsc_adviser_resolves_valid_for_its_own_holder(register):
    by_number = {r["reg_number"]: r for r in register["intermediaries"]}
    holder = by_number[IFSC_ADVISER]["registered_name"]
    result = si.assess_registration(
        f"{holder} SEBI registration {IFSC_ADVISER} securities investment advisory demat",
        holder)
    assert result["state"] == "valid"
    assert result["claims"][0]["resolved_name"] == holder


# --------------------------------------------------------------------------- #
# The re-enabled `invalid` state
# --------------------------------------------------------------------------- #
def _absent_number_in_covered_prefix(register) -> str:
    by_number = {r["reg_number"] for r in register["intermediaries"]}
    for n in range(999999999, 999999000, -1):
        candidate = f"INA{n:09d}"
        if candidate not in by_number:
            return candidate
    raise AssertionError("could not construct an unallocated INA number")


def test_unknown_number_in_covered_category_is_invalid(register):
    number = _absent_number_in_covered_prefix(register)
    result = si.assess_registration(
        f"SEBI registered {number} securities trading demat portfolio advisory", "ProfitGuruji")
    assert result["state"] == "invalid"


def test_invalid_reason_wording_is_exact(register):
    """Required wording, and the forbidden wording."""
    number = _absent_number_in_covered_prefix(register)
    result = si.assess_registration(f"Registered {number} securities demat trading", "Scammer")
    claim = result["claims"][0]
    as_on = si.as_on_date_for("INA")
    assert f"Not found in the SEBI register as of {as_on}" in claim["reason"]
    # The register lists current registrants only, so absence is not proof of
    # fabrication. Never accuse.
    lowered = claim["reason"].lower()
    for forbidden in ("is fake", "fabricated", "fraudulent", "does not exist"):
        assert forbidden not in lowered, f"accusatory wording {forbidden!r} in reason"


def test_uncovered_category_is_unverified_never_invalid():
    """G-2 guard: a genuine Stock Broker's INZ number is outside this snapshot."""
    for number in ("INZ000031633", "INP000005678", "INM000011234"):
        result = si.assess_registration(
            f"Broker {number} securities demat trading stock portfolio", "somefirm.example",
            page_date="2026-07-01")
        assert result["state"] == "unverified", f"{number} -> {result['state']}"
        assert result["claims"], f"{number} was not extracted at all"


def test_uncovered_number_still_satisfies_disclosure():
    """
    An uncovered-category number must still be EXTRACTED, otherwise the
    disclosure rule reports `absent` against a legitimate broker.
    """
    result = si.assess_registration(
        "Broker INZ000031633 securities demat trading stock portfolio investment advisory",
        "somebroker.example", page_date="2026-07-01")
    assert result["state"] != "absent"
    assert result["disclosure"]["present"] is True


# --------------------------------------------------------------------------- #
# Every verdict shows its provenance
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("number_kind", ["valid", "invalid", "unverified"])
def test_every_verdict_carries_as_on_date_and_verify_link(register, number_kind):
    if number_kind == "valid":
        rec = register["intermediaries"][0]
        text, poster = (f"{rec['registered_name']} registration {rec['reg_number']} securities "
                        f"demat advisory"), rec["registered_name"]
    elif number_kind == "invalid":
        text, poster = (f"Registered {_absent_number_in_covered_prefix(register)} securities "
                        f"demat trading"), "Scammer"
    else:
        text, poster = "Broker INZ000031633 securities demat trading", "somebroker.example"

    result = si.assess_registration(text, poster)
    assert result["state"] == number_kind
    claim = result["claims"][0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", claim["as_on_date"] or "")
    assert claim["verify_url"].startswith("https://www.sebi.gov.in/")
    reason = result["reasons"][0]
    assert reason["verify_label"] == "Verify live on SEBI"
    assert reason["source_url"].startswith("https://www.sebi.gov.in/")


# --------------------------------------------------------------------------- #
# Regression: the www-prefix bug that G-2 caught
# --------------------------------------------------------------------------- #
def test_poster_host_strips_www_prefix_not_leading_w_characters():
    """
    str.lstrip("www.") strips any leading run of {w, .}, so "whiteoakinvestors.com"
    became "hiteoakinvestors.com" and every registrant whose domain starts with a
    'w' failed the domain short-circuit and was reported as a collision against
    itself. Real register data surfaced this immediately.
    """
    assert si._poster_host("whiteoakinvestors.com") == "whiteoakinvestors.com"
    assert si._poster_host("www.whiteoakinvestors.com") == "whiteoakinvestors.com"
    assert si._poster_host("https://www.wavesstrategy.com/page") == "wavesstrategy.com"
    assert si._poster_host("wealthdiscovery.in") == "wealthdiscovery.in"


def test_registrants_with_w_domains_resolve_valid(register):
    """The cohort-level version of the bug above."""
    w_records = [r for r in register["intermediaries"]
                 if (r.get("domain_anchor") or "").startswith("w")][:25]
    assert w_records, "expected at least one registrant with a w-initial domain"
    for rec in w_records:
        result = si.assess_registration(
            f"{rec['registered_name']} SEBI registration {rec['reg_number']} securities advisory",
            rec["domain_anchor"], page_date="2026-07-01")
        assert result["state"] == "valid", f"{rec['reg_number']} -> {result['state']}"


# --------------------------------------------------------------------------- #
# Offline behaviour (C4) and extension parity (D6)
# --------------------------------------------------------------------------- #
def test_engine_returns_a_verdict_with_no_store_and_cold_caches():
    si._register.cache_clear()
    si._reg_matcher.cache_clear()
    si._recognition_matcher.cache_clear()
    result = si.assess_registration(
        "Research analyst INH000000016 securities trading demat", "SomeFirm", store=None)
    assert result["state"] in si.SECURITIES_DELTA


def test_extension_snapshot_agrees_with_backend_register(register):
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    meta_b, meta_x = register["registry_meta"], snapshot["meta"]
    assert meta_x["sha256"] == meta_b["sha256"], "snapshot built from a different register"
    assert meta_x["record_count"] == meta_b["record_count"]
    assert meta_x["covered_prefixes"] == meta_b["covered_prefixes"]
    assert meta_x["per_category_as_on_dates"] == meta_b["per_category_as_on_dates"]
    assert meta_x["synthetic_subset"] is False

    backend_numbers = {r["reg_number"] for r in register["intermediaries"]}
    snapshot_numbers = {r["reg_number"] for r in snapshot["intermediaries"]}
    assert backend_numbers == snapshot_numbers


def test_extension_snapshot_carries_no_personal_data():
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    banned = ("address", "phone", "telephone", "fax", "contact", "mobile", "email_domain")
    keys = {k.lower() for rec in snapshot["intermediaries"] for k in rec}
    assert [k for k in keys if any(b in k for b in banned)] == []


def test_extension_snapshot_within_bundle_budget():
    assert SNAPSHOT_PATH.stat().st_size <= 2 * 1024 * 1024
