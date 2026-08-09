r"""Engine unit tests. Zero-dependency by design -- run with:

    .\.venv\Scripts\python tests/test_engines.py

These cover the pure logic (fusion arithmetic, snowflake decoding, lookalike detection)
that must never regress. Anything requiring a model or network lives in the manual
verification steps instead.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apif.engines import trust_registry  # noqa: E402
from apif.engines.coordination import parse_status_url  # noqa: E402
from apif.engines.fusion import OVERRIDE_VERIFIED_OFFICIAL, fuse  # noqa: E402
from apif.schemas import Signal  # noqa: E402

_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        _failures.append(label)


def test_fusion() -> None:
    print("\nfusion")

    # Every detector failed: must not divide by zero, must not read as "safe".
    v = fuse([Signal.unavailable("text_phishing", "service down")])
    check("all-unavailable does not crash", v.risk_score == 0.0)
    check("all-unavailable headline is inconclusive", "Inconclusive" in v.headline,
          f"got {v.headline!r}")

    # No signals at all.
    v = fuse([])
    check("empty signal list does not crash", v.risk_score == 0.0)

    # Renormalisation: a lone high signal must not be diluted by absent detectors.
    v = fuse([
        Signal(name="text_phishing", score=0.9),
        Signal.unavailable("video_deepfake", "Space down"),
        Signal.unavailable("market_anomaly", "no tickers"),
    ])
    check("unavailable signals are excluded, not counted as 0",
          abs(v.risk_score - 0.9) < 1e-6, f"got {v.risk_score}")
    check("renormalised score bands as Critical", v.band == "Critical")

    # Weighted combination across two present signals.
    v = fuse([
        Signal(name="text_phishing", score=1.0),   # weight .25
        Signal(name="coordination", score=0.0),    # weight .10
    ])
    expected = 0.25 / 0.35
    check("weighted mean over available signals",
          abs(v.risk_score - expected) < 1e-3, f"got {v.risk_score}, want {expected:.4f}")

    # A clean voice signal must not escalate anything.
    v = fuse([Signal(name="voice_spoof", score=0.05, evidence={"is_spoof": False})])
    check("authentic voice does not escalate", v.override_applied is None)
    check("authentic voice bands Low", v.band == "Low")

    # A high spoof score stands on its own weight -- no override involved.
    v = fuse([Signal(name="voice_spoof", score=0.95, evidence={"is_spoof": True})])
    check("synthetic voice scores on weight alone", v.override_applied is None)
    check("synthetic voice bands Critical", v.band == "Critical", f"got {v.band}")

    # Override: verified official source caps a high text score at Low.
    v = fuse([
        Signal(name="text_phishing", score=0.95),
        Signal(name="source_untrusted", score=0.0,
               evidence={"registry_matched": True, "signature_valid": True}),
    ])
    check("official override fires", v.override_applied == OVERRIDE_VERIFIED_OFFICIAL)
    check("official override caps at Low", v.band == "Low", f"got {v.band}")

    # The cap applies to the fused score, so even a strong spoof finding from a
    # registry-verified signed source is held at Low. With speaker verification gone
    # there is no clone rule to outrank it -- worth knowing when reading a verdict.
    v = fuse([
        Signal(name="voice_spoof", score=0.9, evidence={"is_spoof": True}),
        Signal(name="source_untrusted", score=0.0,
               evidence={"registry_matched": True, "signature_valid": True}),
    ])
    check("official cap now applies even to spoofed audio",
          v.override_applied == OVERRIDE_VERIFIED_OFFICIAL and v.band == "Low",
          f"got {v.override_applied} / {v.band}")


def test_snowflake() -> None:
    print("\ncoordination / snowflake decoding")

    # Real status ID posted 2022-10-31/11-01 UTC.
    parsed = parse_status_url("https://x.com/elonmusk/status/1587498907336118274")
    check("status URL parses", parsed is not None)
    if parsed:
        check("handle recovered from URL path", parsed["handle"] == "elonmusk",
              f"got {parsed['handle']!r}")
        check("timestamp decoded to 2022", parsed["posted_at"].year == 2022,
              f"got {parsed['posted_at'].isoformat()}")
        check("timestamp is timezone-aware",
              parsed["posted_at"].tzinfo is not None)

    check("twitter.com host also parses",
          parse_status_url("https://twitter.com/SEBI_India/status/1587498907336118274")
          is not None)
    check("profile URL rejected", parse_status_url("https://x.com/elonmusk") is None)
    check("non-twitter URL rejected",
          parse_status_url("https://moneycontrol.com/news/123") is None)
    check("garbage rejected", parse_status_url("") is None)
    check("implausible ID rejected", parse_status_url("https://x.com/a/status/1") is None)
    check("pre-snowflake sequential ID rejected",
          parse_status_url("https://x.com/a/status/12345678") is None)


def test_registry() -> None:
    print("\ntrust registry")

    r = trust_registry.lookup("https://www.sebi.gov.in/legal/circulars/x.html")
    check("official SEBI URL matches", r.matched and r.organisation.startswith("Securities"),
          f"got matched={r.matched} org={r.organisation!r}")

    r = trust_registry.lookup("@NSEIndia")
    check("official X handle matches", r.matched and r.match_type == "handle",
          f"got {r.match_type!r}")

    r = trust_registry.lookup("alerts@sebi.gov.in")
    check("official email domain matches", r.matched and r.match_type == "email_domain",
          f"got {r.match_type!r}")

    # The check that actually catches phishing: near-miss domains.
    r = trust_registry.lookup("https://sebi-gov.in/verify")
    check("hyphen lookalike flagged", r.lookalike_of == "sebi.gov.in" and not r.matched,
          f"got lookalike_of={r.lookalike_of!r}")

    r = trust_registry.lookup("http://nseindla.com")
    check("typo lookalike flagged", r.lookalike_of == "nseindia.com",
          f"got lookalike_of={r.lookalike_of!r}")

    r = trust_registry.lookup("https://totally-unrelated-blog.example")
    check("unrelated domain is unknown, not lookalike",
          not r.matched and r.lookalike_of is None,
          f"got lookalike_of={r.lookalike_of!r}")

    org = trust_registry.find_organisation("SEBI")
    check("issuer resolves by short name", org is not None and org["short_name"] == "SEBI")
    check("unknown issuer resolves to None",
          trust_registry.find_organisation("Definitely Not A Real Org") is None)


def test_registry_signal() -> None:
    print("\ntrust registry -> Signal")

    # Content claiming SEBI, arriving from a lookalike domain: the classic fake.
    s = trust_registry.analyze(source="https://sebi-gov.in/notice", claimed_issuer="SEBI")
    check("impersonation scores high", s.available and s.score >= 0.9, f"got {s.score}")
    check("impersonation is not registry-matched",
          s.evidence.get("registry_matched") is False)

    # Genuine SEBI URL.
    s = trust_registry.analyze(source="https://www.sebi.gov.in/x", claimed_issuer="SEBI")
    check("genuine source scores low", s.score <= 0.1, f"got {s.score}")
    check("genuine source sets registry_matched",
          s.evidence.get("registry_matched") is True)

    s = trust_registry.analyze()
    check("no source and no issuer is unavailable", not s.available)


if __name__ == "__main__":
    test_fusion()
    test_snowflake()
    test_registry()
    test_registry_signal()

    print()
    if _failures:
        print(f"{len(_failures)} FAILED: {', '.join(_failures)}")
        sys.exit(1)
    print("all engine tests passed")
