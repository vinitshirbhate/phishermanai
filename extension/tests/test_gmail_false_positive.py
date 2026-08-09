"""
Regression tests for the Gmail false-positive class.

A legitimate internship email, opened in Gmail, was reported DANGER with:

    [scam] Lottery/prize scam
    [scam] Personal information request (Aadhaar/PAN/OTP)
    [scam] Contains UPI handle(s): 1
    [credibility] Excessive exclamation marks (9)
    [domain] Domain is on trusted whitelist        <- shown as a RED risk chip

The email contained no exclamation marks, requested no PII, mentioned no prize,
and quoted no payment handle. Four independent defects produced it:

  1. UPI_RE matched the front of every email address        -> entities.py
  2. Bare words ("congratulations", "winner") were evidence -> scam_signals.json
  3. Page-wide text extraction swept in the inbox thread list -> content_script
  4. Severity was inferred from the page verdict, painting a
     TRUST signal red                                       -> signal_polarity

Each test below fails against the code as it was.

Standalone:  python tests/test_gmail_false_positive.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.engines import entities, scam_detector, scamgate  # noqa: E402

EXT = ROOT / "extension"


# --------------------------------------------------------------- defect 1 ----
# Every email address in the world parsed as a payment handle.

ORDINARY_ADDRESSES = [
    "arhantanilbagde@gmail.com",
    "messages-noreply@linkedin.com",
    "support@sebi.gov.in",          # the regulator's own address
    "arhant.bagde23@vit.edu",
    "no-reply@accounts.google.com",
    "care@zerodha.com",
    "info@company.co.in",
]

REAL_VPAS = [
    "lucky.winner2025@paytm",
    "scammer123@ybl",
    "rahul@okhdfcbank",
    "merchant@newpspbank",          # unknown PSP — rule 3 must still accept it
]


def test_email_addresses_are_not_payment_handles():
    for addr in ORDINARY_ADDRESSES:
        assert entities.extract_upi(addr) == [], (
            f"{addr!r} was read as a UPI handle. Every mail page then reports "
            f"'Contains UPI handle(s): 1' and adds +12 risk."
        )


def test_real_vpas_are_still_extracted():
    """The fix must not buy precision by going blind."""
    for vpa in REAL_VPAS:
        assert entities.extract_upi(f"pay to {vpa} now") == [vpa], \
            f"{vpa!r} is a genuine VPA and must still be extracted"


def test_both_engines_share_one_upi_definition():
    """
    scam_detector and scamgate held separate copies of UPI_RE. scamgate learned
    about the email-prefix problem; scam_detector did not, and the bug shipped
    through /api/analyze/page. They must now resolve to the same function.
    """
    assert scam_detector.extract_upi is entities.extract_upi
    text = "reach us at a@b.com or pay ravi@ybl"
    assert scamgate.extract_all(text)["upi"] == entities.extract_upi(text)


# --------------------------------------------------------------- defect 2 ----
# Single ordinary words carried 55 points of "lottery scam".

def test_no_bare_single_word_scam_tokens():
    sig = json.loads((ROOT / "backend/data/scam_signals.json").read_text(encoding="utf-8"))
    for cat in ("lottery_scam", "pii_request"):
        bare = [k for k in sig[cat] if len(k.split()) == 1]
        assert not bare, (
            f"{cat} contains bare single words {bare}. 'congratulations' and "
            f"'winner' appear in ordinary promotional mail; at weight 55 one of "
            f"them is enough to reach CRITICAL."
        )


def test_ordinary_promotional_language_is_not_a_lottery_scam():
    benign = [
        "Congratulations on completing your KYC with us.",
        "Congratulations! Your order has been shipped.",
        "The winner of last week's hackathon will be announced Monday.",
        "Please verify your identity to continue.",
        "Confirm your details to complete the booking.",
    ]
    for text in benign:
        r = scam_detector.detect(text)
        assert "Lottery/prize scam" not in r.signals, f"false lottery hit on: {text!r}"
        assert "Personal information request (Aadhaar/PAN/OTP)" not in r.signals, \
            f"false PII hit on: {text!r}"


def test_actual_lottery_scam_still_detected():
    r = scam_detector.detect(
        "Congratulations you have won 25 lakh in the KBC lottery. "
        "Claim your prize now, share your Aadhaar and send OTP to claim.")
    assert "Lottery/prize scam" in r.signals, "genuine lottery scam text must still fire"
    assert "Personal information request (Aadhaar/PAN/OTP)" in r.signals


# --------------------------------------------------------------- defect 3 ----
# Scope: on a mail host the unit of judgement must be the open message, and if
# it cannot be isolated the scan must be suppressed rather than fall back to the
# whole SPA.

def _content_script() -> str:
    return (EXT / "content_script.js").read_text(encoding="utf-8")


def test_mail_hosts_do_not_fall_back_to_whole_page_text():
    src = _content_script()
    assert "extractMailMessage" in src, "no webmail extractor"
    assert "scannable" in src, "no scannable flag — the fail-closed path is missing"
    # The mail branch must not reach extractVisibleText().
    branch = src[src.index("const mailData = extractMailMessage()"):]
    branch = branch[:branch.index("return {")]
    assert "extractVisibleText()" in src, "sanity: page path still exists"
    assert branch.count("extractVisibleText()") == 1, (
        "the mail branch must not fall back to whole-page text; that fallback IS "
        "the bug — it scores the inbox list and attributes it to the open message")


def test_background_suppresses_a_verdict_it_cannot_scope():
    src = (EXT / "background.js").read_text(encoding="utf-8")
    assert "snapshot.scannable === false" in src, \
        "background does not honour scannable:false and will score an unscoped page"
    idx = src.index("snapshot.scannable === false")
    block = src[idx:idx + 900]
    assert "suppressed: true" in block
    assert "'UNKNOWN'" in block or '"UNKNOWN"' in block


# --------------------------------------------------------------- defect 4 ----
# A trust signal was rendered as a red high-severity threat.

def _node(script: str) -> dict:
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         cwd=str(ROOT), timeout=60)
    assert out.returncode == 0, out.stderr[:800]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_protective_signal_is_never_classified_as_risk():
    res = _node("""
      const P = require('./extension/shared/signal_polarity.js');
      const cases = [
        'Domain is on trusted whitelist',
        '[domain] Domain is on trusted whitelist',
        'Legitimate notification pattern detected',
      ];
      console.log(JSON.stringify(cases.map(c => P.classify(c))));
    """)
    for c in res:
        assert c["polarity"] == "protective", \
            f"a trust signal classified as {c}; it renders red beside real threats"
        assert c["severity"] == "none"


def test_risk_signals_keep_their_own_severity_regardless_of_page_score():
    res = _node("""
      const P = require('./extension/shared/signal_polarity.js');
      console.log(JSON.stringify({
        typo: P.classify('Possible typosquat of zerodha.com'),
        upi:  P.classify('[scam] Contains UPI handle(s): 1'),
        excl: P.classify('Excessive exclamation marks (9)'),
      }));
    """)
    assert res["typo"] == {"polarity": "risk", "severity": "high"}
    assert res["upi"]["polarity"] == "risk"
    # An unrecognised signal must NOT be promoted to high just because the page
    # scored badly - that promotion is the defect.
    assert res["excl"]["severity"] in ("low", "medium")


SIGNAL_SURFACES = ["background.js", "sidepanel/panel.js", "content_script.js"]


def test_no_display_surface_derives_severity_from_the_page_verdict():
    """
    This defect existed in THREE places independently - background.js,
    panel.js and content_script.js each had their own copy. Fixing two would
    have left the third shipping. All three are asserted together.
    """
    for rel in SIGNAL_SURFACES:
        src = (EXT / rel).read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith(("//", "*", "/*")))
        for pat, why in [
            (r"severity:\s*normalizedScore", "page score"),
            (r"severity:\s*assessment\?\.riskLevel", "page verdict"),
            (r"severity:\s*fallbackSeverity", "caller-supplied aggregate"),
            (r"getSeverityFromScore\s*\(", "score-to-severity helper"),
        ]:
            hit = re.search(pat, code)
            assert not hit, f"{rel} still derives signal severity from the {why}: {hit.group(0)!r}"
        assert "PhishermanSignalPolarity" in src, \
            f"{rel} does not use the shared classifier"


def test_every_signal_surface_can_reach_the_classifier():
    """A shared classifier that is not loaded is worse than no classifier: the
    call throws at render time, which is when the user needs the warning."""
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    worker = (EXT / "background.js").read_text(encoding="utf-8")
    assert "shared/signal_polarity.js" in worker, \
        "background.js does not importScripts the classifier it calls"

    bundles = [cs.get("js", []) for cs in manifest.get("content_scripts", [])]
    cs_bundle = next(b for b in bundles if "content_script.js" in b)
    assert "shared/signal_polarity.js" in cs_bundle, \
        "content_script.js calls the classifier but it is not in its bundle"
    assert cs_bundle.index("shared/signal_polarity.js") < cs_bundle.index("content_script.js"), \
        "content scripts share one global and run in array order — the dependency must be first"

    panel_html = (EXT / "sidepanel/panel.html").read_text(encoding="utf-8")
    # Compare actual <script src> order, not raw substring positions: prose in a
    # comment mentioning "panel.js" would otherwise decide the assertion.
    srcs = re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", panel_html)
    assert any("signal_polarity.js" in s for s in srcs), \
        "panel.html does not load the classifier"
    pol = next(i for i, s in enumerate(srcs) if "signal_polarity.js" in s)
    pan = next(i for i, s in enumerate(srcs) if s.endswith("panel.js"))
    assert pol < pan, f"signal_polarity.js must be loaded before panel.js (got {srcs})"


def test_trust_and_risk_scores_are_never_mixed():
    """
    Trust and risk run in OPPOSITE directions. `data.risk_score` used to sit in a
    ?? chain of trust scores, and the branch for "only risk_score was returned"
    used it unconverted - so risk 90 would have rendered as trust 90, i.e. SAFE,
    on a page the backend had just called dangerous. Both live endpoints return
    trust_score, so it never fired; it was a landmine for the next endpoint.
    """
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    assert "data.trustScore ?? data.trust_score ?? data.risk_score" not in bg, \
        "risk_score is still being treated as a trust score in a ?? chain"

    src = bg[bg.index("const clamp = (n) =>"):]
    src = src[:src.index("const backendSignals")]
    # Run the REAL normalisation block, lifted verbatim from background.js.
    res = _node("""
      const out = {};
      for (const [name, data] of Object.entries({
        trust_only: { trust_score: 12 },
        camel_only: { trustScore: 12 },
        risk_only:  { risk_score: 90 },
        neither:    {},
        garbage:    { trust_score: 'abc' },
      })) {
        %s
        out[name] = normalizedScore;
      }
      console.log(JSON.stringify(out));
    """ % src)
    assert res["trust_only"] == 12
    assert res["camel_only"] == 12
    assert res["risk_only"] == 10, \
        f"risk 90 became trust {res['risk_only']} — a dangerous page shown as safe"
    assert res["neither"] == 50
    assert res["garbage"] == 50, "a non-numeric score must fall back, not become NaN"


# --------------------------------------------------- the original screenshot --

EMAIL_BODY = """Hi Arhant,

Thank you for your interest in the AI TECH Systems & Product Management Intern
role at Omysha Foundation-VONG & A4G. As the next step in our selection process,
shortlisted candidates are requested to complete the Stage-1 Screening Google
Form within 24 hours of receiving this message.

Your responses will help us understand your AI, product, and technical alignment
with the role. Based on the evaluation, selected candidates will be invited for
an online interaction.
Best regards,
"""

GMAIL_SURROUNDINGS = """
arhant bagde <arhantanilbagde@gmail.com> to me Reply Forward Inbox 1,784
Swiggy Congratulations! You've unlocked 60% OFF your next order!!
Cred Congratulations, you've won a scratch card worth up to 1000 cashback!
Netflix Please verify your identity to continue your subscription
Zomato Winner announcement: this week's lucky draw results are out!
LinkedIn 12 new jobs for you! Apply now!!
"""


def test_the_reported_email_is_not_called_a_lottery_or_pii_scam():
    """The message itself, which is what the fixed scope actually submits."""
    r = scam_detector.detect(EMAIL_BODY)
    for bad in ("Lottery/prize scam",
                "Personal information request (Aadhaar/PAN/OTP)"):
        assert bad not in r.signals, f"{bad!r} still fires on a genuine internship email"
    assert not any("UPI handle" in s for s in r.signals), \
        "the sender's own email address is still being read as a payment handle"
    assert r.risk_score < 50, f"risk {r.risk_score} on an ordinary recruiting email"


def test_inbox_contamination_no_longer_manufactures_pii_or_upi_signals():
    """
    Belt and braces: even if scope regressed, the pattern and extractor fixes
    must stop the PII and UPI accusations. Lottery phrases genuinely present in
    the surrounding promos are a scope problem, and scope is asserted above.
    """
    r = scam_detector.detect(GMAIL_SURROUNDINGS + EMAIL_BODY)
    assert "Personal information request (Aadhaar/PAN/OTP)" not in r.signals
    assert not any("UPI handle" in s for s in r.signals)


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}"); passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
