/*
 * Resolve where a link actually goes, before it is clicked.
 *
 * Everything else in the preflight lane reasons about the URL as written. This
 * is the only component that can answer where it ENDS UP, by walking the
 * redirect chain without credentials.
 *
 * Off by default, because following a link is not neutral observation:
 *   1. It confirms a live human to whoever operates the link.
 *   2. It can BURN A ONE-TIME TOKEN. Password resets, unsubscribe and OTP links
 *      are single-use; pre-fetching one breaks the user's real click.
 *   3. Some links act on GET.
 *
 * url_parse.js sets `skip_prefetch` on anything carrying an identifying or
 * high-entropy token, and this module refuses those regardless of settings.
 * With the setting off the hover card still shows the full local analysis and
 * reports the destination as unresolved.
 *
 * Sends the URL and nothing else: no cookies, no referrer, no cache
 * participation, headers only. fetchImpl is injectable so the hop logic is
 * tested with no network.
 */
"use strict";

(function (root, factory) {
  const api = factory(
    (typeof require !== "undefined") ? require("./url_parse.js") : root.PhishermanUrlParse
  );
  if (typeof module === "object" && module.exports) module.exports = api;
  root.PhishermanFetcher = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function (URLP) {

  const MAX_HOPS = 5;
  const HOP_TIMEOUT_MS = 3500;
  const TOTAL_BUDGET_MS = 8000;

  // Reasons a resolution never starts. Each is a refusal, not a failure.
  const REFUSE = {
    SINGLE_USE_TOKEN: "This link carries a one-time token. Opening it early would "
      + "use it up and break the link for you, so it was not contacted.",
    NOT_HTTP: "Only http and https links are resolved.",
    PRIVATE_HOST: "This address is on your own network or machine and was not contacted.",
    DISABLED: "Destination checking is off, so this link was not contacted.",
  };

  // url_parse reports the scheme WITH its colon ("https:"). Comparing against
  // "https" silently never matched, which disabled the downgrade check entirely.
  function _scheme(parsed) {
    return String((parsed && parsed.scheme) || "").replace(/:$/, "").toLowerCase();
  }

  function _isPrivate(parsed) {
    return !!(parsed && parsed.is_private_target);
  }

  /**
   * shouldResolve(parsed, opts) -> {ok:boolean, reason?:string}
   *
   * PURE. Every safety decision lives here so it can be tested without a
   * network, and so the answer is the same whoever asks.
   */
  function shouldResolve(parsed, opts) {
    const o = opts || {};
    const scheme = _scheme(parsed);
    if (scheme !== "http" && scheme !== "https") return { ok: false, reason: REFUSE.NOT_HTTP };

    // Hard stops, independent of settings. A user who switched resolution on did
    // not thereby ask us to consume their password-reset links.
    // Private/loopback is checked FIRST: url_parse sets skip_prefetch for it too,
    // and reporting "this carries a one-time token" about http://127.0.0.1 is
    // simply a false statement to the user.
    if (_isPrivate(parsed)) return { ok: false, reason: REFUSE.PRIVATE_HOST };
    if (parsed.skip_prefetch) return { ok: false, reason: REFUSE.SINGLE_USE_TOKEN };
    if (!o.enabled) return { ok: false, reason: REFUSE.DISABLED };
    return { ok: true };
  }

  /**
   * describeChain(hops) -> {signals:[], final, crossed_origin, downgraded}
   *
   * PURE. Turns a hop list into findings. Separated from the network so the
   * interpretation is testable against hand-written chains.
   */
  function describeChain(hops) {
    const signals = [];
    const list = hops || [];
    const first = list[0] || null;
    const final = list.length ? list[list.length - 1] : null;

    if (list.length > 1) {
      signals.push({
        label: "Redirects " + (list.length - 1) + " time"
          + (list.length > 2 ? "s" : "") + " before arriving",
        polarity: "context", severity: "none",
      });
    }

    let downgraded = false;
    let crossed = false;
    for (let i = 1; i < list.length; i++) {
      const prev = list[i - 1], cur = list[i];
      if (_scheme(prev) === "https" && _scheme(cur) === "http") downgraded = true;
      if (prev.registrable_domain && cur.registrable_domain
          && prev.registrable_domain !== cur.registrable_domain) crossed = true;
    }

    if (downgraded) {
      signals.push({
        label: "Drops from an encrypted connection to an unencrypted one mid-redirect",
        polarity: "risk", severity: "high",
      });
    }
    if (crossed && first && final && first.registrable_domain !== final.registrable_domain) {
      signals.push({
        label: "Ends on " + final.registrable_domain + ", a different site from the link shown",
        polarity: "risk", severity: "medium",
      });
    }
    return { signals: signals, final: final, crossed_origin: crossed, downgraded: downgraded };
  }

  function _withTimeout(ms, signal) {
    // AbortSignal.timeout is available in MV3 workers; fall back for older hosts.
    if (typeof AbortSignal !== "undefined" && AbortSignal.timeout && !signal) {
      return AbortSignal.timeout(ms);
    }
    return signal;
  }

  /**
   * resolve(url, opts) -> Promise<report>
   *
   * opts.enabled     boolean - the user setting. False means "do not contact".
   * opts.fetchImpl   injectable fetch, for tests.
   * opts.maxHops     default 5
   * opts.pageHost    passed through to url_parse for same-origin reasoning
   *
   * Never throws: a network failure is a reported outcome, not an exception. The
   * hover card must render something in every case.
   */
  async function resolve(url, opts) {
    const o = opts || {};
    const doFetch = o.fetchImpl || (typeof fetch !== "undefined" ? fetch : null);
    const maxHops = o.maxHops || MAX_HOPS;
    const started = o.now ? o.now() : 0;

    const parsed = URLP.parse(url, { pageHost: o.pageHost });
    const gate = shouldResolve(parsed, o);
    if (!gate.ok) {
      return {
        resolved: false, refused: true, reason: gate.reason,
        hops: [parsed], final: parsed, signals: [], network_used: false,
      };
    }
    if (!doFetch) {
      return { resolved: false, refused: false, reason: "No fetch available.",
               hops: [parsed], final: parsed, signals: [], network_used: false };
    }

    const hops = [parsed];
    let current = url;
    let truncated = false;
    let error = null;

    for (let i = 0; i < maxHops; i++) {
      let resp = null;
      try {
        resp = await doFetch(current, {
          method: "HEAD",
          redirect: "manual",
          credentials: "omit",       // no cookies — this is not the user's session
          referrerPolicy: "no-referrer",
          cache: "no-store",
          signal: _withTimeout(HOP_TIMEOUT_MS, o.signal),
        });
      } catch (e) {
        error = String((e && e.message) || e);
        break;
      }

      const status = resp && resp.status;
      const loc = resp && resp.headers && typeof resp.headers.get === "function"
        ? resp.headers.get("location") : null;

      // Not a redirect: this is the destination.
      if (!loc || !(status >= 300 && status < 400)) {
        hops[hops.length - 1].status = status;
        hops[hops.length - 1].content_type =
          (resp && resp.headers && resp.headers.get && resp.headers.get("content-type")) || null;
        break;
      }

      let next;
      try {
        next = new URL(loc, current).href;
      } catch (e) {
        error = "Redirect target could not be read.";
        break;
      }

      const nextParsed = URLP.parse(next, { pageHost: o.pageHost });
      hops[hops.length - 1].status = status;
      hops.push(nextParsed);
      current = next;

      // A redirect INTO a one-time-token URL stops the walk. We have learned the
      // destination host, which is what the user needs; consuming the token to
      // learn one hop more is not a trade we get to make on their behalf.
      if (nextParsed.skip_prefetch) { truncated = true; break; }
      if (o.now && (o.now() - started) > TOTAL_BUDGET_MS) { truncated = true; break; }
      if (i === maxHops - 1) truncated = true;
    }

    const described = describeChain(hops);
    return {
      resolved: !error,
      refused: false,
      network_used: true,
      truncated: truncated,
      error: error,
      hops: hops,
      final: described.final,
      crossed_origin: described.crossed_origin,
      downgraded: described.downgraded,
      signals: described.signals,
    };
  }

  return {
    resolve: resolve,
    shouldResolve: shouldResolve,
    describeChain: describeChain,
    REFUSE: REFUSE,
    MAX_HOPS: MAX_HOPS,
  };
}));
