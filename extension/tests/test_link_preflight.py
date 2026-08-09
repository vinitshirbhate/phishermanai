"""
Link preflight: hover analysis and redirect resolution.

The safety properties here are not incidental - they are the reason the feature
is shippable at all. Following a link is not neutral observation: it contacts a
server the user did not choose to contact, confirms a live human to whoever
operates it, and CAN CONSUME A ONE-TIME TOKEN. A pre-fetch that burns a password
reset or unsubscribe link has broken the thing it claims to protect.

So the tests below assert, with no network anywhere:

  * a one-time-token link is refused even when the setting is on;
  * a private/loopback address is refused, with the RIGHT reason;
  * with the setting off, zero requests are made;
  * every request that IS made carries no cookies and no referrer;
  * the chain walk terminates (hop cap, token mid-chain, redirect loop).

Standalone:  python tests/test_link_preflight.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"


def _node(script: str):
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         cwd=str(ROOT), timeout=60)
    assert out.returncode == 0, out.stderr[:1200]
    return json.loads(out.stdout.strip().splitlines()[-1])


PRELUDE = """
  const F = require('./extension/preflight/fetcher.js');
  const P = require('./extension/preflight/url_parse.js');
  const mk = (u) => P.parse(u, {});
  const calls = [];
  function stub(chain) {
    return async (u, init) => {
      calls.push({ url: u, ...init });
      const h = chain[u] || { status: 200, loc: null };
      return { status: h.status,
               headers: { get: (k) => k.toLowerCase() === 'location' ? h.loc : null } };
    };
  }
"""


# ------------------------------------------------------------- hard refusals --

def test_one_time_token_links_are_refused_even_when_enabled():
    """The refusal is in the module, not the caller, so it holds for everyone."""
    res = _node(PRELUDE + """
      const urls = [
        'https://mail.example.com/reset?token=abc123XYZ987longtoken',
        'https://news.example.com/unsub?u=a1b2c3d4e5f6g7h8',
        'https://x.example.com/confirm?code=ZZZZ1111YYYY2222',
      ];
      console.log(JSON.stringify(urls.map(u => {
        const g = F.shouldResolve(mk(u), { enabled: true });
        return { ok: g.ok, reason: g.reason };
      })));
    """)
    for r in res:
        assert r["ok"] is False, "a one-time-token link was cleared for pre-fetching"
        assert "one-time token" in r["reason"], r["reason"]


def test_a_refused_link_makes_no_network_request_at_all():
    """Refusing but fetching anyway would be the worst of both worlds."""
    res = _node(PRELUDE + """
      (async () => {
        const f = stub({});
        const r = await F.resolve('https://x.example.com/reset?token=abc123XYZ987long',
                                  { enabled: true, fetchImpl: f });
        console.log(JSON.stringify({ calls: calls.length, refused: r.refused,
                                     network_used: r.network_used }));
      })();
    """)
    assert res["calls"] == 0, "a refused link was still fetched"
    assert res["refused"] is True and res["network_used"] is False


def test_private_and_loopback_addresses_are_refused_with_the_right_reason():
    """
    url_parse sets skip_prefetch for private hosts too, so an order-of-checks
    slip made the extension tell users that http://127.0.0.1 "carries a one-time
    token" - a plainly false statement about their own machine.
    """
    res = _node(PRELUDE + """
      const urls = ['http://127.0.0.1:8080/x', 'http://192.168.1.1/admin',
                    'http://10.0.0.5/status'];
      console.log(JSON.stringify(urls.map(u => F.shouldResolve(mk(u), { enabled: true }))));
    """)
    for r in res:
        assert r["ok"] is False
        assert "your own network or machine" in r["reason"], r["reason"]


def test_non_http_schemes_are_never_fetched():
    res = _node(PRELUDE + """
      const urls = ['upi://pay?pa=x@ybl', 'javascript:alert(1)', 'file:///etc/passwd',
                    'data:text/html,<b>x'];
      console.log(JSON.stringify(urls.map(u => F.shouldResolve(mk(u), { enabled: true }).ok)));
    """)
    assert res == [False, False, False, False]


def test_setting_off_means_no_request():
    """BL-6: local by default. Off must mean off, not 'off but we peeked'."""
    res = _node(PRELUDE + """
      (async () => {
        const f = stub({ 'https://bit.ly/x': { status: 301, loc: 'https://evil.example/' } });
        const r = await F.resolve('https://bit.ly/x', { enabled: false, fetchImpl: f });
        console.log(JSON.stringify({ calls: calls.length, reason: r.reason }));
      })();
    """)
    assert res["calls"] == 0
    assert "off" in res["reason"]


# ---------------------------------------------------------- request hygiene --

def test_requests_carry_no_cookies_and_no_referrer():
    res = _node(PRELUDE + """
      (async () => {
        const f = stub({
          'https://bit.ly/x': { status: 301, loc: 'https://t.example/r' },
          'https://t.example/r': { status: 302, loc: 'https://final.example/p' },
        });
        await F.resolve('https://bit.ly/x', { enabled: true, fetchImpl: f });
        console.log(JSON.stringify(calls.map(c => ({
          method: c.method, credentials: c.credentials,
          referrerPolicy: c.referrerPolicy, redirect: c.redirect, cache: c.cache }))));
      })();
    """)
    assert res, "no requests were made at all"
    for c in res:
        assert c["credentials"] == "omit", "request would carry the user's cookies"
        assert c["referrerPolicy"] == "no-referrer", "request would leak the referring page"
        assert c["redirect"] == "manual", "redirects must be walked, not auto-followed"
        assert c["method"] == "HEAD", "a body fetch is more than we need"
        assert c["cache"] == "no-store"


# ------------------------------------------------------------ chain walking --

def test_chain_walk_terminates_on_hop_cap_and_on_a_loop():
    res = _node(PRELUDE + """
      (async () => {
        const loop = { 'https://a.example/': { status: 302, loc: 'https://b.example/' },
                       'https://b.example/': { status: 302, loc: 'https://a.example/' } };
        const r1 = await F.resolve('https://a.example/', { enabled: true, fetchImpl: stub(loop) });
        const n1 = calls.length; calls.length = 0;
        const deep = {};
        for (let i = 0; i < 20; i++) deep['https://h' + i + '.example/'] =
          { status: 302, loc: 'https://h' + (i + 1) + '.example/' };
        const r2 = await F.resolve('https://h0.example/', { enabled: true, fetchImpl: stub(deep) });
        console.log(JSON.stringify({ loopCalls: n1, loopHops: r1.hops.length,
          deepCalls: calls.length, deepHops: r2.hops.length,
          truncated: r2.truncated, max: F.MAX_HOPS }));
      })();
    """)
    assert res["loopCalls"] <= res["max"], "a redirect loop was not bounded"
    assert res["deepCalls"] <= res["max"], "the hop cap did not hold"
    assert res["truncated"] is True, "a truncated chain must say so, not look complete"


def test_a_redirect_into_a_token_url_stops_the_walk():
    """
    Learning the destination host is worth a request. Consuming the user's
    one-time token to learn one hop further is not ours to trade.
    """
    res = _node(PRELUDE + """
      (async () => {
        const f = stub({
          'https://bit.ly/x': { status: 301, loc: 'https://acct.example/verify?token=QQQQ1111WWWW2222' },
        });
        const r = await F.resolve('https://bit.ly/x', { enabled: true, fetchImpl: f });
        console.log(JSON.stringify({ calls: calls.length, hops: r.hops.length,
          truncated: r.truncated, finalHost: r.final.host_normalised }));
      })();
    """)
    assert res["calls"] == 1, "the token URL itself was requested"
    assert res["truncated"] is True
    assert res["finalHost"] == "acct.example", "the destination host should still be reported"


def test_network_failure_is_reported_not_thrown():
    """The hover card must render something in every case."""
    res = _node(PRELUDE + """
      (async () => {
        const f = async () => { throw new Error('net::ERR_NAME_NOT_RESOLVED'); };
        const r = await F.resolve('https://bit.ly/x', { enabled: true, fetchImpl: f });
        console.log(JSON.stringify({ resolved: r.resolved, error: r.error,
                                     hops: r.hops.length }));
      })();
    """)
    assert res["resolved"] is False
    assert "ERR_NAME_NOT_RESOLVED" in res["error"]
    assert res["hops"] == 1, "the originating link should still be reported"


# ----------------------------------------------------------- chain findings --

def test_downgrade_and_cross_domain_are_reported():
    """
    url_parse reports the scheme WITH its colon ("https:"). Comparing against
    "https" matched nothing, so the downgrade check was silently dead.
    """
    res = _node(PRELUDE + """
      const d = F.describeChain([mk('https://bit.ly/x'), mk('https://t.example/r'),
                                 mk('http://zerodha-verify.xyz/login')]);
      console.log(JSON.stringify(d));
    """)
    assert res["downgraded"] is True, "https -> http downgrade was not noticed"
    assert res["crossed_origin"] is True
    labels = [s["label"] for s in res["signals"]]
    assert any("unencrypted" in l for l in labels), labels
    assert any("zerodha-verify.xyz" in l for l in labels), labels


def test_a_direct_link_reports_no_redirect_findings():
    res = _node(PRELUDE + """
      console.log(JSON.stringify(F.describeChain([mk('https://www.sebi.gov.in/')])));
    """)
    assert res["signals"] == []
    assert res["downgraded"] is False and res["crossed_origin"] is False


# --------------------------------------------------------------- the wiring --

def test_hover_path_is_wired_end_to_end():
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert "'preflightLink'" in bg and "preflightLink(" in bg
    assert "action: 'preflightLink'" in cs, "the hover card never asks for an analysis"
    assert "attachShadow" in cs, "the hover card must render in a shadow root"
    # The old tooltip printed only a hostname and nothing else.
    assert "showLinkTooltip" not in cs, "the hostname-only tooltip is still installed"


def test_resolution_is_off_by_default():
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    opts = (EXT / "options/options.js").read_text(encoding="utf-8")
    for name, src in (("background.js", bg), ("options.js", opts)):
        assert "resolveRedirects: false" in src, \
            f"{name} does not default destination checking to OFF (BL-6)"
    assert "settings.resolveRedirects === true" in bg, \
        "resolution must require an explicit true, not merely a truthy default"


def test_fetcher_is_loaded_after_its_dependency():
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    block = bg[bg.index("importScripts("):bg.index(");", bg.index("importScripts("))]
    assert "preflight/fetcher.js" in block, "fetcher.js is never imported"
    assert block.index("preflight/url_parse.js") < block.index("preflight/fetcher.js"), \
        "fetcher.js resolves url_parse from the global; it must load after it"


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
