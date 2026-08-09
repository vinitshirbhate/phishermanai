"""
Regression tests for the behavioural analysis lane.

WHAT BROKE, AND WHY THESE TESTS EXIST:

    A textbook WhatsApp task scam ("give positive ratings to the brands we work
    with... earn 1500 to 5000 rupees per day... 150 rupees joining bonus... reply
    with YES") scored 91/100 SAFE. Two independent defects produced that:

      1. DETECTION. Every keyword category in scam_signals.json is matched with
         `substring in text`, so ordinary grammatical variation escaped silently
         - "working from home" is not "work from home", "joining bonus" is not
         "joining fee". The message hit ZERO of 24 categories. The only signal
         raised was "Unverified domain: whatsapp.com", worth 8 risk points.

      2. CACHING. background.js consulted the hostname domain cache BEFORE the
         analysis chain. On web.whatsapp.com the hostname never changes, so the
         first cached verdict was replayed for every later conversation whatever
         its content.

    Both are covered below. The false-positive cases matter as much as the
    detections: a legitimate recruiter message must stay clean, or the lane is
    just a way to flag everything.

Standalone:  python tests/test_behavior_lane.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engines import behavior_lane, scamgate  # noqa: E402

BACKGROUND = ROOT / "extension" / "background.js"

# The exact message from the bug report, retyped from the screenshot.
SCREENSHOT_SCAM = """Hello, I am Nita Sharma from DigitalAdda.
We are hiring for a part time job. You have to give positive ratings to the brands we work with.
You can earn 1500 to 5000 rupees per day working from home.
We also give 150 rupees joining bonus to new members.
If you are interested reply with YES."""

MUST_FLAG = {
    "task_scam_screenshot": SCREENSHOT_SCAM,
    "withdrawal_trap": (
        "Congratulations, your balance is 48,500. Withdrawal is blocked until you "
        "complete 5 more tasks. Deposit 5000 to unlock your withdrawal."
    ),
    "otp_theft": (
        "This is HR from Amazon recruitment. Please share the OTP you just received "
        "to confirm your interview slot."
    ),
    "advance_fee_job": (
        "We are hiring for data entry work from home. Salary 35000 per month. "
        "A refundable security deposit of 2000 is required to activate your account."
    ),
}

MUST_NOT_FLAG = {
    "ordinary_chat": "Hey, are we still on for dinner at 8? I'll book the table.",
    "real_recruiter": (
        "Hi, I saw your profile on LinkedIn. We have a senior backend engineer opening "
        "at Acme Corp. Would you be open to a 30 minute call this week to discuss the "
        "role and compensation?"
    ),
    "bank_notification": (
        "Your account ending 4417 was debited Rs 2,340 on 04-Aug-26 at BigBazaar. "
        "Not you? Call the number on the back of your card."
    ),
    "order_update": (
        "Your order has been shipped and will arrive by Thursday. Track it in the app."
    ),
}


# --- Detection ------------------------------------------------------------

def test_screenshot_scam_is_no_longer_safe():
    """The reported bug: this exact message scored 91 SAFE."""
    verdict = scamgate.ScamGate().scan(SCREENSHOT_SCAM, "https://web.whatsapp.com/")
    assert verdict.trust_score <= 35, (
        f"regression: task scam scored {verdict.trust_score} "
        f"(was 91 SAFE at time of report); signals={verdict.signals}"
    )
    assert verdict.risk_level in ("WARNING", "DANGER"), verdict.risk_level


def test_screenshot_scam_produces_behavioural_reasons():
    """A score is not an explanation — the user must be told what the message DOES."""
    r = behavior_lane.analyze(SCREENSHOT_SCAM)
    ids = {t["id"] for t in r.tactics}
    for expected in ("reward_bait", "effort_reward_mismatch", "reciprocity_hook", "commitment_ladder"):
        assert expected in ids, f"missed tactic {expected}; got {sorted(ids)}"
    assert any(c["id"] == "task_scam_signature" for c in r.combos), \
        "payout-for-trivial-work combo did not fire"
    assert r.band == "severe", r.band
    assert r.narrative and "behaviourally" in r.narrative.lower()


def test_known_scams_all_reach_at_least_moderate():
    weak = {
        name: behavior_lane.analyze(txt).band
        for name, txt in MUST_FLAG.items()
        if behavior_lane.analyze(txt).band in ("none", "weak")
    }
    assert not weak, f"under-scored scam messages: {weak}"


def test_benign_messages_stay_clean():
    """The false-positive gate. A recruiter with a real role must not be accused."""
    noisy = {
        name: behavior_lane.analyze(txt).behavior_score
        for name, txt in MUST_NOT_FLAG.items()
        if behavior_lane.analyze(txt).behavior_score >= 40
    }
    assert not noisy, f"benign messages scored as manipulative: {noisy}"


def test_empty_and_garbage_input_is_safe():
    for bad in ("", "   ", "\n\n", "x" * 50000, "😀🙃" * 200):
        r = behavior_lane.analyze(bad)
        assert 0 <= r.behavior_score <= 100
        assert r.trust_penalty >= 0


def test_single_tactic_cannot_condemn_alone():
    """One tactic is weak evidence. Only co-occurrence should move a verdict far."""
    r = behavior_lane.analyze("Hurry, our sale ends today only!")
    assert r.trust_penalty <= 15, f"single weak tactic penalised {r.trust_penalty}"


def test_severe_band_requires_a_combo_to_promote_verdict():
    """Guards the promotion rule in scamgate._merge from firing on wordy copy."""
    r = behavior_lane.analyze(SCREENSHOT_SCAM)
    assert r.band == "severe" and len(r.combos) >= 1
    verdict = scamgate.ScamGate().scan(SCREENSHOT_SCAM, "")
    assert verdict.verdict == "scam", verdict.verdict


# --- Extension parity -----------------------------------------------------

def _js_eval(expr_body: str):
    """Run the offline behavioural lane out of background.js under node."""
    src = BACKGROUND.read_text(encoding="utf-8")
    blocks = []
    for name in ("LOCAL_BEHAVIOR_TACTICS", "LOCAL_BEHAVIOR_COMBOS", "LOCAL_BEHAVIOR_BANDS"):
        m = re.search(rf"const {name} = \[.*?\n\];", src, re.S)
        assert m, f"{name} not found in background.js"
        blocks.append(m.group(0))
    for name in ("localBehaviorCheck", "isMessagingSurface"):
        m = re.search(rf"function {name}\(.*?\n\}}", src, re.S)
        assert m, f"{name}() not found in background.js"
        blocks.append(m.group(0))
    m = re.search(r"const MESSAGING_HOSTS = /.*?/i;", src)
    assert m, "MESSAGING_HOSTS not found in background.js"
    blocks.append(m.group(0))

    script = "\n".join(blocks) + "\n" + expr_body
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, f"node failed: {out.stderr[:400]}"
    return json.loads(out.stdout)


def test_offline_js_lane_agrees_with_python_on_band():
    """
    The extension re-implements the lane in JS so it still works with the backend
    down. Two implementations means drift, exactly as with the ML features. Bands
    must agree - the offline pack is a deliberate subset, so raw scores may differ,
    but a message the backend calls severe must not read as clean offline.
    """
    cases = {**MUST_FLAG, **MUST_NOT_FLAG}
    names = list(cases)
    js = _js_eval(
        "console.log(JSON.stringify(" + json.dumps([cases[n] for n in names])
        + ".map(t => localBehaviorCheck(t))));"
    )
    rank = {"none": 0, "weak": 1, "moderate": 2, "strong": 3, "severe": 4}
    drift = []
    for name, jr in zip(names, js):
        py = behavior_lane.analyze(cases[name])
        pr, jrk = rank[py.band], rank[jr["band"]]
        if name in MUST_FLAG and jrk < 2:
            drift.append(f"{name}: python={py.band} but offline JS={jr['band']} (must be >= moderate)")
        if name in MUST_NOT_FLAG and jrk >= 2:
            drift.append(f"{name}: benign, but offline JS={jr['band']}")
        if abs(pr - jrk) > 1:
            drift.append(f"{name}: band drift python={py.band} js={jr['band']}")
    assert not drift, "offline/backend behavioural drift:\n  " + "\n  ".join(drift)


def test_offline_js_combo_ids_match_python():
    """Combo definitions are duplicated across the boundary; keep the ids aligned."""
    py_ids = {c["id"] for c in behavior_lane._pack()["combos"]}
    js_ids = set(_js_eval(
        "console.log(JSON.stringify(LOCAL_BEHAVIOR_COMBOS.map(c => c.id)));"
    ))
    unknown = js_ids - py_ids
    assert not unknown, f"background.js declares combos the backend does not know: {unknown}"


def test_messaging_surfaces_bypass_the_domain_cache():
    """
    The caching half of the bug. web.whatsapp.com must be recognised as a surface
    where the hostname says nothing about the content.
    """
    checks = _js_eval(
        "console.log(JSON.stringify({"
        "  whatsapp: isMessagingSurface({url:'https://web.whatsapp.com/'}),"
        "  telegram: isMessagingSurface({url:'https://web.telegram.org/k/'}),"
        "  hasMessaging: isMessagingSurface({url:'https://example.com/', messaging:{text:'x'}}),"
        "  ordinary: isMessagingSurface({url:'https://www.bbc.co.uk/news'}),"
        "  lookalike: isMessagingSurface({url:'https://web.whatsapp.com.evil.tk/'})"
        "}));"
    )
    assert checks["whatsapp"] is True
    assert checks["telegram"] is True
    assert checks["hasMessaging"] is True, "a snapshot carrying extracted messages is a messaging surface"
    assert checks["ordinary"] is False, "ordinary sites must keep using the domain cache"
    assert checks["lookalike"] is False, "a typosquat of a messaging host is NOT the messaging host"


def test_background_js_does_not_read_cache_before_analysis_on_messaging():
    """Structural guard: the cache read must sit behind the messaging check."""
    src = BACKGROUND.read_text(encoding="utf-8")
    m = re.search(r"const messagingSurface = isMessagingSurface\(snapshot\);(.*?)let result = cachedResult",
                  src, re.S)
    assert m, "scanTab no longer computes messagingSurface before the fallback chain"
    guarded = m.group(1)
    assert "if (!messagingSurface)" in guarded, \
        "getCachedDomain is no longer guarded by the messaging-surface check"


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}"); passed += 1
        except Exception as exc:
            print(f"FAIL  {name}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
