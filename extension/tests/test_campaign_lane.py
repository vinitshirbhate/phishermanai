"""
Acceptance tests for F-A7 cross-channel campaign correlation.

Runs under pytest, or standalone:  python tests/test_campaign_lane.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from store import Store                                        # noqa: E402
from engines.campaign_lane import (                            # noqa: E402
    CampaignLane, extract_entities, campaign_id_for,
    MIN_SHARED_ENTITIES, DORMANCY_DAYS,
)

BASE = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _fresh():
    p = Path(tempfile.gettempdir()) / "phisherman_campaign_test.db"
    if p.exists():
        p.unlink()
    s = Store(p)
    return s, CampaignLane(s), p


def _obs(store, lane, channel, surface, text, day):
    at = (BASE + timedelta(days=day)).isoformat()
    ents = extract_entities(text=text)
    oid = store.record_observation(
        {"channel": channel, "surface_id": surface, "content_sha256": f"h{day}{surface}",
         "trust_score": 15, "tier": "HIGH", "layer": "4.1", "observed_at": at},
        entities=ents)
    return lane.ingest(oid, ents, channel, at)


def test_multichannel_campaign_forms_one_object():
    store, lane, p = _fresh()
    try:
        _obs(store, lane, "whatsapp", "wa:+919812345670",
             "Join VIP group. Pay investprofit99@ybl or call 9812345670. Visit fakebroker.xyz", 0)
        r2 = _obs(store, lane, "web", "fakebroker.xyz",
                  "Deposit to investprofit99@ybl for allotment. More at fakebroker.xyz", 2)
        r3 = _obs(store, lane, "payment", "upi-form",
                  "Final call 9812345670 send to investprofit99@ybl", 3)
        assert r2["campaign_id"] is not None
        assert r3["campaign_id"] == r2["campaign_id"], "same campaign across channels"
        detail = lane.get(r3["campaign_id"])
        assert set(detail["campaign"]["channels"]) >= {"whatsapp", "web", "payment"}
        assert detail["campaign"]["event_count"] >= 3
    finally:
        store.close(); p.unlink()


def test_single_shared_entity_does_not_link():
    """The >=2 threshold prevents linking everything through one common host."""
    store, lane, p = _fresh()
    try:
        _obs(store, lane, "whatsapp", "wa:+91981",
             "Pay investprofit99@ybl or call 9812345670 at fakebroker.xyz", 0)
        r = _obs(store, lane, "web", "unrelated.example",
                 "An unrelated page that merely mentions fakebroker.xyz", 5)
        assert r["campaign_id"] is None
        assert str(MIN_SHARED_ENTITIES) in r["reason"]
    finally:
        store.close(); p.unlink()


def test_resurfacing_after_dormancy():
    store, lane, p = _fresh()
    try:
        _obs(store, lane, "whatsapp", "wa:+91981",
             "VIP group investprofit99@ybl 9812345670 fakebroker.xyz", 0)
        _obs(store, lane, "web", "fakebroker.xyz",
             "Deposit investprofit99@ybl 9812345670", 2)
        r = _obs(store, lane, "telegram", "tg:@newhandle",
                 "Back again investprofit99@ybl and 9812345670", 2 + DORMANCY_DAYS + 5)
        assert r["resurfaced"] is True
        assert r["dormant_days"] >= DORMANCY_DAYS
    finally:
        store.close(); p.unlink()


def test_no_resurfacing_inside_dormancy_window():
    store, lane, p = _fresh()
    try:
        _obs(store, lane, "whatsapp", "wa:+91981",
             "VIP investprofit99@ybl 9812345670 fakebroker.xyz", 0)
        _obs(store, lane, "web", "fakebroker.xyz", "Deposit investprofit99@ybl 9812345670", 1)
        r = _obs(store, lane, "telegram", "tg:@x", "More investprofit99@ybl 9812345670", 5)
        assert r["resurfaced"] is False
    finally:
        store.close(); p.unlink()


def test_campaign_id_is_deterministic():
    ents = extract_entities(text="pay investprofit99@ybl call 9812345670 at fakebroker.xyz")
    assert campaign_id_for(ents) == campaign_id_for(list(reversed(ents)))


def test_entity_extraction_types():
    ents = extract_entities(
        text="pay investprofit99@ybl call 9812345670 visit fakebroker.xyz join @tipschannel",
        reg_numbers=["INZ000031633"], phash="abc123", group="VIP Traders")
    types = {e["entity_type"] for e in ents}
    assert {"upi", "phone", "domain", "reg_number", "phash", "group"} <= types


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}"); passed += 1
        except Exception as exc:
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
