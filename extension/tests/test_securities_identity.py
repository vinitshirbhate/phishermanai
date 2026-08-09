"""
Acceptance tests for the v7.0 authentication core (F-B1, F-B2, F-A1).

Runs under pytest, or standalone:  python tests/test_securities_identity.py
(pytest is not a hard dependency of the repo; the __main__ runner mirrors it.)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engines import securities_identity as si          # noqa: E402
from engines import securities_typology as st           # noqa: E402
from store import Store                                 # noqa: E402

FIXTURES = json.loads((ROOT / "backend" / "data" / "securities_fixtures.json").read_text())["fixtures"]


# --- helpers ---------------------------------------------------------------- #
# The register is now REAL SEBI data (3,000+ live registrants), so these tests
# derive their subjects from it rather than hard-coding numbers. A hard-coded
# number would either name a real firm in a scam fixture or silently rot the
# moment SEBI's register changes.
def _active_records() -> list[dict]:
    return sorted((r for r in si._register()["records"] if r.get("status", "active") == "active"),
                  key=lambda r: r["reg_number"])


def _real_record(with_anchor: bool = False) -> dict:
    for rec in _active_records():
        if with_anchor and not rec.get("domain_anchor"):
            continue
        return rec
    raise AssertionError("register contains no suitable active record")


def _absent_number(prefix: str = "INA", width: int = 9) -> str:
    """A format-correct number in a COVERED family that is not in the register."""
    by_number = si._register()["by_number"]
    n = 10 ** width - 1
    while n > 0:
        candidate = f"{prefix}{n:0{width}d}"
        if candidate not in by_number:
            return candidate
        n -= 1
    raise AssertionError("no unallocated number found")


# --- F-B1: the five states ------------------------------------------------- #
def test_valid_on_own_domain():
    rec = _real_record(with_anchor=True)
    r = si.assess_registration(f"Advisory {rec['reg_number']}. demat trading portfolio",
                               poster_identity=rec["domain_anchor"])
    assert r["state"] == "valid", f"{rec['reg_number']} on its own domain -> {r['state']}"
    assert r["trust_delta"] == 25


def test_valid_by_name_match():
    rec = _real_record()
    r = si.assess_registration(
        f"{rec['registered_name']} {rec['reg_number']} broker demat",
        poster_identity=rec["registered_name"])
    assert r["state"] == "valid", f"{rec['reg_number']} by name -> {r['state']}"


def test_every_verdict_carries_as_on_date_and_verify_link():
    """Both valid and invalid verdicts must show the per-category as-on date and a
    live SEBI link, so a user can always check us against the source."""
    rec = _real_record()
    for text, poster in ((f"{rec['registered_name']} {rec['reg_number']} demat", rec["registered_name"]),
                         (f"Adviser {_absent_number()} securities demat trading", "Scammer")):
        r = si.assess_registration(text, poster_identity=poster)
        claim = r["claims"][0]
        assert claim["as_on_date"], f"no as-on date on a {r['state']} verdict"
        assert claim["verify_url"].startswith("https://www.sebi.gov.in"), claim["verify_url"]


def test_unresolvable_number_echoed_and_never_accusatory_on_subset():
    """While the register is a bounded subset, an unresolvable number yields the
    non-accusatory `unverified` state (G-2), with the number still echoed."""
    r = si.assess_registration("SEBI INA000999999 stock trading", poster_identity="FakeCo")
    expected = "invalid" if si.register_is_authoritative() else "unverified"
    assert r["state"] == expected
    assert "INA000999999" in r["reasons"][0]["text"]  # number echoed (F-B1 criterion)
    if expected == "unverified":
        assert r["trust_delta"] == 0, "a coverage gap must not reduce trust"


def test_g2_real_registration_numbers_are_never_accused():
    """G-2 zero-tolerance, the strict form: real SEBI numbers that fall outside our
    bounded subset must NEVER produce `invalid` or `absent`. Before the subset-aware
    fix these resolved to `invalid`, i.e. the tool falsely accused real intermediaries.

    Provenance: pairs quoted in remediation_plan.md §3.1 as public register facts.
    Not independently verified against sebi.gov.in - used here only as
    outside-the-subset probes, which does not depend on the pairing being correct.
    """
    probes = ["INH000000990", "INH100001666", "INH200000402", "INH300000211"]
    for number in probes:
        r = si.assess_registration(
            f"Research analyst {number} securities trading demat advisory",
            poster_identity="example-intermediary.in", page_date="2026-07-01")
        assert r["state"] not in ("invalid", "absent"), \
            f"{number} wrongly flagged {r['state']} — G-2 violation"
        assert r["trust_delta"] <= 0 or r["state"] == "valid"


def test_all_register_prefix_variants_are_matched():
    """The highest-value assertion in the codebase: the DERIVED family must match
    every row of the real register in full - all 3,000+ of them, every prefix
    shape, including the GIFT City IFSC advisers whose number is not numeric
    after the letters. A partial match counts as a failure."""
    m = si._reg_matcher()
    records = si._register()["records"]
    assert len(records) >= 3000, f"register unexpectedly small: {len(records)}"
    for rec in records:
        number = rec["reg_number"]
        hit = m.search(number)
        assert hit and hit.group(0).upper() == number.upper(), \
            f"generated matcher misses or partially matches {number}"


def test_inaifsc_gift_city_adviser_resolves():
    """INAIFSC10001 is a real registrant whose 5 trailing digits a hand-written
    INA\\d{9} silently fails. Both shapes are 12 characters."""
    reg = si._register()
    rec = reg["by_number"].get("INAIFSC10001")
    assert rec is not None, "INAIFSC10001 missing from the register"
    assert si.extract_claims("our registration is INAIFSC10001 here") == ["INAIFSC10001"]
    r = si.assess_registration(
        f"{rec['registered_name']} SEBI registration INAIFSC10001 advisory demat",
        poster_identity=rec["registered_name"])
    assert r["state"] == "valid", f"INAIFSC10001 -> {r['state']}"


def test_uncovered_category_is_unverified_never_invalid():
    """A Stock Broker's INZ number is genuine but outside the fetched categories.
    Calling it `invalid` would falsely accuse a real intermediary (G-2)."""
    r = si.assess_registration("Broker INZ000031633 securities demat trading stock",
                               poster_identity="somebroker.example")
    assert r["state"] == "unverified", f"uncovered prefix -> {r['state']}"
    assert r["trust_delta"] == 0, "a coverage gap must not reduce trust"


def test_fabricated_number_in_covered_category_is_invalid():
    number = _absent_number()
    r = si.assess_registration(f"SEBI registered {number} securities demat advisory",
                               poster_identity="ProfitGuruji Investments")
    assert r["state"] == "invalid"
    reason = r["claims"][0]["reason"]
    assert "Not found in the SEBI register as of" in reason, reason
    # Never assert fabrication: the register lists CURRENT registrants only, so a
    # lapsed registration disappears rather than showing as cancelled.
    assert "fake" not in reason.lower()


def test_collision_on_wrong_poster():
    rec = _real_record()
    r = si.assess_registration(
        f"VIP group {rec['reg_number']} guaranteed profit trading stock",
        poster_identity="ProfitGuruji")
    assert r["state"] == "collision", f"{rec['reg_number']} vs wrong poster -> {r['state']}"
    assert r["trust_delta"] == -45
    assert r["impersonation_alert"] is True


def test_absent_post_disclosure_date():
    r = si.assess_registration(
        "Guaranteed 30% monthly returns on stock trading! Join our demat IPO portfolio group",
        poster_identity="tipsguru", page_date="2026-07-01")
    assert r["state"] == "absent"


def test_not_applicable_for_non_securities():
    r = si.assess_registration("Buy fresh vegetables online, home delivery",
                               poster_identity="veggies.example")
    assert r["state"] == "not_applicable"


def test_zero_tolerance_registered_entity_never_invalid_or_absent():
    """F-B1 P0 / gate G-2: a genuinely registered entity's own content must never
    be flagged invalid or absent. Checks EVERY active row of the real register -
    every one of these is a named, identifiable firm."""
    for rec in _active_records():
        anchor = rec.get("domain_anchor") or rec["registered_name"]
        text = (f"{rec['registered_name']} registration {rec['reg_number']} "
                f"securities trading demat advisory")
        r = si.assess_registration(text, poster_identity=anchor, page_date="2026-07-01")
        assert r["state"] not in ("invalid", "absent", "collision"), \
            f"{rec['reg_number']} ({rec['registered_name']}) wrongly flagged {r['state']}"


# --- F-B1: derived matcher (§4.1) ------------------------------------------ #
def test_matcher_covers_every_register_prefix():
    """One sample per prefix, taken FROM the register rather than invented."""
    reg = si._register()
    matcher = si._reg_matcher()
    samples: dict[str, str] = {}
    for rec in reg["records"]:
        samples.setdefault(rec["reg_prefix"], rec["reg_number"])
    for prefix in reg["prefixes"]:
        assert prefix in samples, f"no register row for prefix {prefix}"
        assert matcher.search(samples[prefix]), f"matcher misses prefix {prefix}"


# --- F-B1: collision via store substrate ----------------------------------- #
def test_collision_across_two_handles_via_store():
    rec = _real_record()
    number = rec["reg_number"]
    dbp = Path(tempfile.gettempdir()) / "phisherman_collision_test.db"
    if dbp.exists():
        dbp.unlink()
    store = Store(dbp)
    store.load_reference_data(
        sebi_register=json.loads((ROOT / "backend/data/sebi_register.json").read_text()))
    # Two fabricated handles both claim the same real registrant's number. The
    # registrant is the victim of the simulated impersonation, not its subject.
    for handle in ("wa:+919111", "tg:@tipsx"):
        store.record_observation(
            {"channel": "whatsapp", "surface_id": handle, "content_sha256": handle * 4,
             "trust_score": 20, "tier": "HIGH", "layer": "1.7"},
            entities=[{"entity_type": "reg_number", "entity_value": number}])
    r = si.assess_registration(f"Join {number} VIP profit group trading stock",
                               poster_identity="scammer", store=store)
    assert r["state"] == "collision"
    assert r["collisions"] and r["collisions"][0]["number"] == number
    store.close()
    dbp.unlink()


# --- A.7b mitigation: widened disclosure-scope triggers --------------------- #
def test_t1_needs_both_payment_target_and_return_framing():
    """T1 must never fire on a payment target alone - a page with a UPI id and no
    investment framing is a shop, not a securities offering."""
    shop = "Pay for your order at shop99@ybl. Free delivery on all items."
    assert si.disclosure_scope(shop) == [], f"T1 fired on a shop: {si.disclosure_scope(shop)}"

    offering = "Send your capital to profitdesk99@ybl and receive monthly returns."
    codes = [t["code"] for t in si.disclosure_scope(offering)]
    assert "scope_payment_and_return_framing" in codes, codes


def test_t2_fires_on_unresolvable_registration_shaped_token():
    """A scheme we hold no data for (ARN) is still a disclosed credential: in
    scope via T2, and `unverified` rather than `absent` - never an accusation."""
    text = "Redeem your folio through our agent. ARN-123456."
    codes = [t["code"] for t in si.disclosure_scope(text)]
    assert "scope_registration_shaped_token" in codes, codes
    r = si.assess_registration(text, poster_identity="RedeemFast", page_date="2026-07-01")
    assert r["state"] == "unverified", r["state"]
    assert r["trust_delta"] == 0


def test_t3_is_inert_until_the_chat_capability_lands():
    ctx = {"chat_name": "W1001-VIP Wealth", "prior_in_scope_in_thread": True}
    text = "Good morning everyone, positions update shortly."
    assert si.CAPABILITIES["chat_context"] is False, "T3 must ship inert"
    assert si.disclosure_scope(text, channel_context=ctx) == []
    # ...and works the moment the capability is enabled.
    si.CAPABILITIES["chat_context"] = True
    try:
        codes = [t["code"] for t in si.disclosure_scope(text, channel_context=ctx)]
        assert "scope_channel_context" in codes, codes
    finally:
        si.CAPABILITIES["chat_context"] = False


def test_widened_triggers_do_not_lower_the_lexicon_threshold():
    assert si.is_securities_content("stock demat") is True
    assert si.is_securities_content("stock") is False, "lexicon threshold was lowered"


# --- F-B2: UPI namespace ---------------------------------------------------- #
def test_upi_valid_broker():
    r = si.upi_namespace_check("everest.brk@validhdfc")
    assert r["in_valid_namespace"] is True
    assert r["category"] == "broker"


def test_upi_outside_namespace():
    r = si.upi_namespace_check("investprofit99@ybl")
    assert r["in_valid_namespace"] is False
    assert r["reason"] == "outside_valid_namespace"


def test_upi_category_mismatch():
    r = si.upi_namespace_check("xyz.mf@validhdfc", claimed_category="broker")
    assert r["in_valid_namespace"] is True
    assert r["category_mismatch"] is True


# --- F-A1: typologies ------------------------------------------------------- #
def test_all_typology_fixtures_positive_and_negative():
    for f in FIXTURES:
        cls = f["class"]
        pos = {m["id"] for m in st.match_typologies(f["positive"])}
        neg = {m["id"] for m in st.match_typologies(f["negative"])}
        assert cls in pos, f"{cls} positive fixture did not match"
        assert cls not in neg, f"{cls} near-miss negative wrongly matched"


def test_combined_verdict_two_typologies():
    text = ("You have been added to our VIP premium trading group. Your withdrawal is "
            "blocked, pay a processing fee and margin top-up to release your funds.")
    ids = [m["id"] for m in st.match_typologies(text)]
    assert "withdrawal_trap" in ids and "vip_group_funnel" in ids


# --- standalone runner (no pytest needed) ---------------------------------- #
if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
