"""
False-positive gate - legitimate pages must not be accused.

WHAT BROKE

    A Google results page for the query "sebi" scored 10/100 DANGER. So did a lot
    of other ordinary sites. The cause was not tuning; it was that presence of a
    TOPIC WORD was treated as evidence of fraud:

      * `authority_impersonation` contained bare entity names - "sebi", "rbi",
        "sbi", "police", "pnb", "lic", "ministry", "PAN", "KYC". Substring-matched,
        so MENTIONING the regulator scored as IMPERSONATING it (+25). SEBI's own
        website tripped this.
      * `financial_triggers` contained "kyc", "otp", "bank account", "investment",
        "suspended" (+30). Every bank site trips this.
      * `money_ask` contained "pay", "payment", "upi", "transfer", "deposit" (+20).
        Every checkout page on the internet trips this.
      * Each linked domain absent from a 26-entry whitelist added +8 - so
        link-rich legitimate pages (search results, news, Wikipedia) scored worse
        the more they linked out. The whitelist did not even contain sebi.gov.in.
      * "Contains link(s): N" added risk for the mere presence of a hyperlink.

    30 + 25 + 20 + link penalties reaches DANGER on a page that has done nothing.

THE RULE THIS ENFORCES

    An entity or topic is not evidence. An entity or topic PLUS an act is.
    See backend/engines/context_gate.py.

Both halves are tested here. A gate that suppresses false positives by suppressing
detection is worse than no gate, so MUST_CATCH runs alongside MUST_STAY_CLEAN and
both must hold.

Standalone:  python tests/test_false_positives.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engines import context_gate, scam_detector, scamgate, trust_engine  # noqa: E402

_gate = scamgate.ScamGate()

# Legitimate content. Every one of these was scored as risky before the fix.
MUST_STAY_CLEAN = {
    "google_serp_sebi": (
        """sebi - Google Search
        Securities and Exchange Board of India https://www.sebi.gov.in
        Welcome to website of Securities and Exchange Board of India.
        About SEBI - The Securities and Exchange Board of India was constituted ...
        Investor website. Vacancies. Circulars, Gazette Notification. Regulations.
        People also ask: What is SEBI and its work? Is SEBI owned by the government?
        How can I file a complaint with SEBI? Who is SEBI in India?
        https://en.wikipedia.org/wiki/Securities_and_Exchange_Board_of_India
        https://www.investopedia.com/terms/s/sebi.asp
        Investor grievance redressal - file a complaint online. Verify your KYC with your broker.""",
        "https://www.google.com/search?q=sebi",
    ),
    "sebi_official_site": (
        """Securities and Exchange Board of India. SEBI protects the interests of investors.
        Investor grievance redressal SCORES. Complete your KYC through a SEBI registered
        intermediary. Circulars, regulations, and press releases.""",
        "https://www.sebi.gov.in/",
    ),
    "bank_netbanking": (
        """HDFC Bank NetBanking. Login to your bank account securely. Update your KYC before
        the due date to keep your account active. Pay bills, transfer funds, and manage your
        investment portfolio.""",
        "https://www.hdfcbank.com/",
    ),
    "ecommerce_checkout": (
        """Order summary. Total 2,499. Pay with UPI, credit card or net banking. Payment is
        secured. Google Pay, PhonePe and Paytm accepted. Deposit refundable within 7 days.""",
        "https://www.flipkart.com/checkout",
    ),
    "wikipedia_article": (
        """The Securities and Exchange Board of India (SEBI) is the regulatory body for
        securities and commodity markets in India, owned by the Ministry of Finance. It was
        established in 1988 and given statutory powers in 1992.""",
        "https://en.wikipedia.org/wiki/SEBI",
    ),
    "news_about_fraud": (
        """RBI warns of rising digital payment fraud. The Reserve Bank of India said banks must
        strengthen KYC processes. Police registered a case against three men in Mumbai for an
        investment scam.""",
        "https://www.moneycontrol.com/news/x",
    ),
    "broker_site": (
        """Zerodha Kite. Open a free demat and trading account. Invest in stocks, mutual funds
        and IPOs. SEBI registration INZ000031633. Complete KYC online in 10 minutes.""",
        "https://zerodha.com/",
    ),
    "link_rich_page": (
        """Useful resources: https://www.rbi.org.in https://www.sebi.gov.in
        https://en.wikipedia.org/wiki/Finance https://www.investopedia.com
        https://www.moneycontrol.com https://github.com/example/repo
        https://stackoverflow.com/questions/1 https://www.bbc.co.uk/news""",
        "https://example.org/links",
    ),
}

# Must still be caught. A gate that mutes detection is worse than no gate.
MUST_CATCH = {
    "task_scam": (
        """Hello, I am Nita Sharma from DigitalAdda. We are hiring for a part time job. You have
        to give positive ratings to the brands we work with. You can earn 1500 to 5000 rupees per
        day working from home. We also give 150 rupees joining bonus. If you are interested reply
        with YES.""",
        "https://web.whatsapp.com/",
    ),
    "digital_arrest": (
        """This is Inspector Sharma calling from CBI. A case has been registered against you for
        money laundering. Your account will be blocked. You are under digital arrest. Do not tell
        anyone. Pay 250000 immediately to avoid arrest.""",
        "https://web.whatsapp.com/",
    ),
    "kyc_phish": (
        """Dear customer, your SBI account has been suspended. Update your KYC immediately to
        avoid closure. Click the link to verify: http://sbi-kyc-update.top/verify. Share your OTP
        to confirm.""",
        "http://sbi-kyc-update.top/verify",
    ),
    "otp_theft": (
        "This is HR from Amazon recruitment. Please share the OTP you just received to confirm "
        "your interview slot.",
        "https://web.whatsapp.com/",
    ),
    "withdrawal_trap": (
        "Your balance is 48,500. Withdrawal is blocked until you complete 5 more tasks. "
        "Deposit 5000 to unlock your withdrawal.",
        "https://web.whatsapp.com/",
    ),
    "lottery_scam": (
        "Congratulations! You have won KBC lottery prize of 25 lakh. Pay processing fee 8500 "
        "to claim. Call now.",
        "https://wa.me/919999999999",
    ),
}

CLEAN_FLOOR = 60   # legitimate content must not fall below this
CATCH_CEILING = 40  # known scams must not rise above this


def test_legitimate_pages_are_not_accused():
    bad = {}
    for name, (text, url) in MUST_STAY_CLEAN.items():
        r = _gate.scan(text, url)
        if r.trust_score < CLEAN_FLOOR:
            bad[name] = f"{r.trust_score} {r.risk_level} — {r.signals[:4]}"
    assert not bad, "false positives on legitimate content:\n  " + "\n  ".join(
        f"{k}: {v}" for k, v in bad.items()
    )


def test_known_scams_are_still_caught():
    """The other half. Suppressing false positives must not suppress detection."""
    missed = {}
    for name, (text, url) in MUST_CATCH.items():
        r = _gate.scan(text, url)
        if r.trust_score > CATCH_CEILING:
            missed[name] = f"{r.trust_score} {r.risk_level} {r.verdict}"
    assert not missed, "regression — scams no longer caught:\n  " + "\n  ".join(
        f"{k}: {v}" for k, v in missed.items()
    )


def test_legacy_scam_detector_agrees():
    """
    trust_engine runs BOTH scamgate and the legacy scam_detector, taking whichever
    is worse. Fixing only one left /api/analyze/page - the path ordinary web pages
    take - still producing false positives.
    """
    bad = {}
    for name, (text, _url) in MUST_STAY_CLEAN.items():
        res = scam_detector.detect(text)
        if res.risk_score >= 45:
            bad[name] = f"risk={res.risk_score} {res.risk_level} — {res.signals[:4]}"
    assert not bad, "legacy scam_detector still accusing legitimate content:\n  " + "\n  ".join(
        f"{k}: {v}" for k, v in bad.items()
    )


def test_full_page_pipeline_keeps_benign_pages_clean():
    """End-to-end through trust_engine, the aggregate the extension actually shows."""
    bad = {}
    for name, (text, url) in MUST_STAY_CLEAN.items():
        v = trust_engine.analyze_page(url=url, text=text)
        if v.trust_score < CLEAN_FLOOR:
            bad[name] = f"{v.trust_score} {v.risk_level} — {v.signals[:4]}"
    assert not bad, "aggregate pipeline accusing legitimate pages:\n  " + "\n  ".join(
        f"{k}: {v}" for k, v in bad.items()
    )


# --- The gate's own contract -------------------------------------------------

def test_bare_entity_mention_is_not_impersonation():
    """The specific defect: naming a regulator scored as impersonating it."""
    for token in ("sebi", "rbi", "police", "kyc", "pan"):
        assert not context_gate.should_score(
            "authority_impersonation", [token], f"An article discussing {token} policy."
        ), f"bare token {token!r} still scores as impersonation"


def test_entity_plus_act_does_score():
    """The gate must not simply disable the category."""
    text = ("This is Inspector Verma calling from CBI. A case has been registered against you. "
            "Pay 50000 immediately to avoid arrest.")
    assert context_gate.should_score("authority_impersonation", ["cbi", "police"], text)


def test_ungated_phrase_scores_even_without_an_act():
    """Multi-word phrases carry their own evidence and must never be gated."""
    assert context_gate.should_score(
        "financial_triggers", ["kyc", "account will be closed"], "your account will be closed"
    )


def test_corroboration_cap_only_hits_lone_categories():
    capped, note = context_gate.apply_corroboration_cap(80, ["money_ask"])
    assert capped == context_gate.single_category_cap() and note

    kept, note2 = context_gate.apply_corroboration_cap(80, ["money_ask", "urgency_triggers"])
    assert kept == 80 and note2 is None

    hard, note3 = context_gate.apply_corroboration_cap(80, ["money_ask", "phishing_domain"])
    assert hard == 80 and note3 is None, "hard evidence must never be capped"


def test_email_addresses_are_not_read_as_upi_handles():
    """UPI_RE matched the leading half of every email address."""
    out = scamgate.extract_all("Contact us at support@example.com or sales@example.co.in")
    assert out["upi"] == [], f"emails leaked into UPI extraction: {out['upi']}"
    out2 = scamgate.extract_all("Send payment to fraudster99@ybl now")
    assert "fraudster99@ybl" in out2["upi"], "genuine UPI handle no longer extracted"


def test_real_bank_domains_are_not_called_typosquats():
    """
    domain_intel's "brand embedded with <=4 extra characters" rule matched the
    brands' own domains: "hdfcbank" contains "hdfc" with a delta of exactly 4.
    hdfcbank.com, icicibank.com and axisbank.com were each reported as possible
    typosquats of themselves.
    """
    from engines import domain_intel

    for url in ("https://www.hdfcbank.com/", "https://www.icicibank.com/",
                "https://www.axisbank.com/", "https://www.sebi.gov.in/",
                "https://zerodha.com/", "https://www.google.com/"):
        r = domain_intel.analyze(url)
        assert not r.typosquat_suspect, f"{r.domain} called a typosquat of {r.typosquat_target!r}"
        assert r.trust_score >= CLEAN_FLOOR, f"{r.domain} scored {r.trust_score}"


def test_actual_typosquats_are_still_caught():
    from engines import domain_intel

    for url in ("https://hdfcbank-verify.top/", "https://www.icicibank-secure.xyz/",
                "https://gooogle.com/", "https://sbi-kyc-update.top/", "https://paytrn.com/"):
        r = domain_intel.analyze(url)
        assert r.typosquat_suspect or r.trust_score < 50, \
            f"typosquat missed: {r.domain} trust={r.trust_score}"


# --- Extension offline gate --------------------------------------------------

def _run_offline_gate(cases: dict) -> dict:
    """Execute background.js's offline gate under node against the given cases."""
    import json as _json
    import re as _re
    import subprocess

    src = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

    def grab(pattern: str) -> str:
        m = _re.search(pattern, src, _re.S)
        assert m, f"not found in background.js: {pattern}"
        return m.group(0)

    blocks = [
        grab(r"const LOCAL_GATE_RULES = \[.*?\n\];"),
        grab(r"const TRUSTED_HOSTS = \[.*?\n\];"),
        grab(r"function isTrustedHost\(.*?\n\}"),
        grab(r"const LOCAL_BEHAVIOR_TACTICS = \[.*?\n\];"),
        grab(r"const LOCAL_BEHAVIOR_COMBOS = \[.*?\n\];"),
        grab(r"const LOCAL_BEHAVIOR_BANDS = \[.*?\n\];"),
        grab(r"function localBehaviorCheck\(.*?\n\}"),
        grab(r"function localGateCheck\(payload\) \{.*?\n\}"),
        grab(r"function getRiskLevel\(score\) \{.*?\n\}"),
    ]
    script = "\n".join(blocks) + (
        f"\nconst cases = {_json.dumps(cases)};"
        "\nconst out = {};"
        "\nfor (const k of Object.keys(cases)) { const r = localGateCheck(cases[k]);"
        "  out[k] = {trust: r.trustScore, level: r.riskLevel, signals: r.signals}; }"
        "\nconsole.log(JSON.stringify(out));"
    )
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"node failed: {res.stderr[:400]}"
    return _json.loads(res.stdout)


def test_offline_gate_keeps_legitimate_pages_clean():
    """
    The offline gate had an unconditional false positive: its baseline was 72
    while getRiskLevel() calls anything under 80 CAUTION, so EVERY page scanned
    with the backend down was flagged even with zero signals.
    """
    out = _run_offline_gate({
        "serp": {"url": "https://www.google.com/search?q=sebi", "title": "sebi",
                 "visibleText": "Securities and Exchange Board of India. How can I file a "
                                "complaint with SEBI? Verify your KYC with your broker. "
                                "Expand the company panel to claim results."},
        "bank": {"url": "https://netbanking.hdfcbank.com/", "title": "HDFC",
                 "visibleText": "Login to your bank account. Update your KYC. Pay bills and "
                                "transfer funds. Claim your reward points."},
        "wiki": {"url": "https://en.wikipedia.org/wiki/SEBI", "title": "SEBI",
                 "visibleText": "The Securities and Exchange Board of India is the regulatory "
                                "body for securities markets."},
        "shop": {"url": "https://www.flipkart.com/checkout", "title": "Checkout",
                 "visibleText": "Total 2499. Pay with UPI, credit card or net banking. "
                                "PhonePe and Paytm accepted."},
    })
    bad = {k: v for k, v in out.items() if v["trust"] < CLEAN_FLOOR}
    assert not bad, f"offline gate false positives: {bad}"


def test_offline_gate_still_catches_scams():
    out = _run_offline_gate({
        "task_scam": {"url": "https://web.whatsapp.com/", "title": "WA",
                      "visibleText": "I am Nita Sharma from DigitalAdda. We are hiring for a "
                                     "part time job. Give positive ratings to the brands we "
                                     "work with. Earn 1500 to 5000 rupees per day. 150 rupees "
                                     "joining bonus. Reply with YES."},
        "digital_arrest": {"url": "https://web.whatsapp.com/", "title": "WA",
                           "visibleText": "This is Inspector Sharma from CBI. Digital arrest "
                                          "warrant issued. Pay 250000 immediately to avoid "
                                          "arrest. Do not tell anyone."},
        "otp_phish": {"url": "http://sbi-kyc.top/v", "title": "Verify",
                      "visibleText": "Your SBI account is suspended. Update your KYC "
                                     "immediately. Share your OTP to confirm and unlock."},
    })
    missed = {k: v for k, v in out.items() if v["trust"] > CATCH_CEILING}
    assert not missed, f"offline gate no longer catching: {missed}"


def test_trusted_host_suppression_is_not_a_typosquat_bypass():
    """`hdfcbank.com.evil.tk` must NOT inherit hdfcbank.com's trust."""
    out = _run_offline_gate({
        "typosquat": {"url": "https://hdfcbank.com.evil.tk/login", "title": "HDFC",
                      "visibleText": "Update your KYC immediately. Share your OTP to verify "
                                     "and unlock your account."},
    })
    assert out["typosquat"]["trust"] <= CATCH_CEILING, \
        f"typosquat treated as trusted: {out['typosquat']}"


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
