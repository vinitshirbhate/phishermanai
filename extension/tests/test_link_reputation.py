"""
Blocklist matching and hover provenance.

TWO FINDINGS ARE PINNED HERE.

1. THE BLOCKLIST CHECK NEVER FIRED.
   The three bundled feeds ship in three different formats:

       blocklistproject_phishing.txt   "0.0.0.0 www.sapl.com.hk"   hosts file
       phishing_domains_active.txt     "915856.buffalosouljah.com" bare domain
       scam_blocklist_domains.txt      "||falkewear.shop^"         AdBlock rule

   They were loaded verbatim and compared with `dom in self.phish_domains`, so a
   hostname could never match two of the three. scamgate's only hard evidence -
   "Known scam domain" (+40) and "Known phishing domain" (+50) - was dead against
   ~659,000 of ~819,000 entries.

   The tests below draw their subjects FROM THE FEEDS THEMSELVES, so they cannot
   pass by agreeing with a hand-written fixture.

2. A CLEAN RESULT MUST CARRY ITS PROVENANCE.
   "No signals" is true and useless. Every response reports which lists were
   consulted, how many entries each holds, and when they were refreshed - and
   says plainly what a clean result does not cover.

Standalone:  python tests/test_link_reputation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.engines import link_reputation as LR              # noqa: E402
from backend.engines.scamgate import (                          # noqa: E402
    load_domain_set, _load_lines, _normalise_blocklist_entry,
)

FEEDS = [name for name, _, _ in LR.DOMAIN_LISTS]


# ------------------------------------------------------- format normalisation --

def test_every_shipped_feed_format_normalises_to_a_bare_hostname():
    cases = [
        ("0.0.0.0 www.sapl.com.hk", "www.sapl.com.hk"),
        ("127.0.0.1\tevil.example.com", "evil.example.com"),
        ("||falkewear.shop^", "falkewear.shop"),
        ("||onlyfanstok.com^$third-party", "onlyfanstok.com"),
        ("915856.buffalosouljah.com", "915856.buffalosouljah.com"),
        ("  Mixed.Case.COM  ", "mixed.case.com"),
        ("# a comment", ""),
        ("! adblock comment", ""),
        ("@@||allowlisted.com^", ""),
        ("0.0.0.0 localhost", ""),
        ("", ""),
    ]
    for raw, expect in cases:
        got = _normalise_blocklist_entry(raw)
        assert got == expect, f"{raw!r} -> {got!r}, expected {expect!r}"


def test_normalisation_does_not_throw_away_the_feeds():
    """A normaliser that dropped most lines would 'fix' matching by going blind."""
    for name in FEEDS:
        raw = _load_lines(name)
        usable = load_domain_set(name)
        if not raw:
            continue
        assert len(usable) >= 0.95 * len(raw), (
            f"{name}: {len(raw)} raw lines collapsed to {len(usable)} usable "
            f"domains — the normaliser is discarding real entries")


# ------------------------------------------------- matching, drawn from feeds --

def _subjects(name: str, n: int = 5) -> list[str]:
    """Real entries from the feed itself, so the test cannot agree with itself."""
    entries = sorted(d for d in load_domain_set(name) if 6 < len(d) < 40 and "." in d)
    if not entries:
        return []
    step = max(1, len(entries) // (n + 1))
    return [entries[i * step] for i in range(1, n + 1)][:n]


def test_domains_listed_in_each_feed_are_detected():
    for name, label, _kind in LR.DOMAIN_LISTS:
        subjects = _subjects(name)
        if not subjects:
            continue                       # feed absent in this checkout
        for dom in subjects:
            r = LR.inspect(f"https://{dom}/login")
            hits = [l["list"] for l in r["listed"]]
            assert hits, (
                f"{dom!r} is IN {name} and was not detected. This is the bug that "
                f"made scamgate's blocklist signals dead code.")


def test_a_subdomain_of_a_listed_domain_is_detected():
    """Feeds list `evil.com`; links arrive as `login.evil.com`."""
    for name, _label, _kind in LR.DOMAIN_LISTS:
        subjects = [d for d in _subjects(name, 3) if d.count(".") == 1]
        for dom in subjects:
            r = LR.inspect(f"https://secure.login.{dom}/")
            assert r["listed"], f"subdomain of listed {dom!r} was not matched"
            assert r["listed"][0]["matched"] == dom
        if subjects:
            return


def test_ordinary_sites_are_not_listed():
    """The counterpart: matching must not have become indiscriminate."""
    for url in ["https://www.marxists.org/archive/marx/",
                "https://www.sebi.gov.in/", "https://en.wikipedia.org/wiki/Foo",
                "https://zerodha.com/products/kite"]:
        r = LR.inspect(url)
        assert r["listed"] == [], f"{url} was reported as blocklisted: {r['listed']}"


# ------------------------------------------------------------------ provenance --

def test_a_clean_result_reports_what_was_checked():
    r = LR.inspect("https://www.marxists.org/")
    assert r["lists_checked"] >= 1, "no lists were consulted at all"
    assert r["entries_checked"] > 100_000, \
        f"only {r['entries_checked']} entries checked — coverage collapsed"
    for c in r["checked"]:
        assert c["list"] and c["entries"] > 0
    assert r["as_of"], "no refresh date — an undated blocklist result is unfalsifiable"
    note = r["coverage_note"]
    assert note and "Not listed on" in note
    assert "would not appear" in note, \
        "the coverage note must state its limit, not just the clean result"


def test_reported_entry_counts_match_the_sets_actually_searched():
    """The count is a claim to the user; it must be the real number."""
    r = LR.inspect("https://example.com/")
    by_file = {label: name for name, label, _ in
               [(n, l, k) for n, l, k in LR.DOMAIN_LISTS]}
    for c in r["checked"]:
        name = by_file[c["list"]]
        assert c["entries"] == len(load_domain_set(name)), \
            f"{c['list']} reports {c['entries']} entries but holds {len(load_domain_set(name))}"


def test_a_listed_domain_reports_no_clean_coverage_note():
    subjects = _subjects(LR.DOMAIN_LISTS[0][0], 1)
    if not subjects:
        return
    r = LR.inspect(f"https://{subjects[0]}/")
    assert r["listed"], "precondition failed: subject is not listed"
    assert r["coverage_note"] is None, \
        "a listed domain must not also carry a 'not listed' reassurance"


def test_domain_intel_is_actually_attached():
    """A hasattr() guard silently returned {} and the card lost these findings."""
    r = LR.inspect("https://www.sebi.gov.in/")
    assert "error" not in r["intel"], r["intel"]
    assert r["intel"]["whitelisted"] is True
    assert any("whitelist" in s.lower() for s in r["intel"]["signals"])

    bad = LR.inspect("http://zerodha-verify.xyz/login")
    assert bad["intel"]["https"] is False
    assert bad["intel"]["tld_risk"] == "high"


def test_malformed_input_does_not_raise():
    for url in ["", "   ", "not a url", "http://", "javascript:alert(1)"]:
        r = LR.inspect(url)
        assert isinstance(r, dict)
        assert "listed" in r and "checked" in r


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
