/*
 * securities_check.js - Layer 1.6, the in-extension registration quick-check (F-B1 task 1.7).
 *
 * Runs entirely offline in the service worker: the SEBI register subset and the
 * @valid UPI suffixes are bundled (data/securities_snapshot.json). No backend,
 * no network. When the FastAPI backend IS reachable, background.js prefers its
 * richer result (which adds cross-handle collision detection); this is the
 * always-available floor.
 *
 * Mirrors backend/engines/securities_identity.py: derived matcher, five states,
 * website short-circuit, 85/70 name bands. Kept deliberately simple - the
 * authoritative engine is the Python one; parity is on the states, not scores.
 *
 * Exposes (both worker and node/test):  quickCheck(text, posterIdentity, pageDate)
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api; // node tests
  root.PhishermanSecurities = api;                                          // service worker
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const DISCLOSURE_DATE = Date.UTC(2026, 4, 1); // 1 May 2026
  const SECURITIES_DELTA = {
    valid: 25, not_applicable: 0, unverified: 0, weak_match: -10,
    absent: -20, invalid: -40, collision: -45,
  };
  // Worst-first precedence. `unverified` sits below weak_match: it is a coverage
  // limit of the bundled subset, never an accusation (G-2).
  const STATE_ORDER = ["collision", "invalid", "absent", "weak_match", "unverified",
    "not_applicable", "valid"];
  const SEC_LEXICON = [
    "sebi", "nse", "bse", "demat", "ipo", "trading", "portfolio", "mutual fund",
    "stock", "shares", "broker", "investment", "advisory", "research analyst",
    "securities", "fpi", "allotment", "pms",
  ];
  const SUFFIX_RE = /\b(private|pvt|limited|ltd|llp|and|&)\b/gi;
  const UPI_RE = /\b([a-z0-9.\-_]{2,}@[a-z][a-z0-9.]{1,})\b/gi;

  let SNAPSHOT = null;         // loaded lazily
  let MATCHER = null;          // recognition family (extraction)
  let LENGTHS = null;          // observed total lengths, enforced after matching
  let BY_NUMBER = null;

  function _loadSnapshot(snapshot) {
    SNAPSHOT = snapshot;
    BY_NUMBER = {};
    (snapshot.intermediaries || []).forEach((r) => { BY_NUMBER[r.reg_number.toUpperCase()] = r; });
    const built = _buildMatcher(snapshot.intermediaries || []);
    MATCHER = built.matcher;
    LENGTHS = built.lengths;
  }

  // Derived RECOGNITION matcher - mirrors securities_identity._generate_recognition_family.
  // Built from the register's own values, never hand-written, and deliberately
  // wider than the covered prefixes: a genuine Stock Broker's INZ number must
  // still be EXTRACTED (so disclosure is satisfied) even though this snapshot
  // cannot resolve it. It then reports `unverified`, never `invalid`.
  function _buildMatcher(records) {
    const stems = new Set(); const alphaRuns = []; const digitRuns = [];
    const lengths = new Set();
    records.forEach((r) => {
      const rn = String(r.reg_number || "").toUpperCase();
      const m = /^([A-Z]+)(\d+)$/.exec(rn);
      if (!m) return;
      stems.add(m[1].slice(0, 2));
      alphaRuns.push(m[1].length);
      digitRuns.push(m[2].length);
      lengths.add(rn.length);
    });
    if (!alphaRuns.length) return { matcher: /(?!)/g, lengths: new Set() };
    const stem = stems.size === 1 ? Array.from(stems)[0] : "";
    const loA = Math.max(Math.min.apply(null, alphaRuns) - stem.length, 1);
    const hiA = Math.max.apply(null, alphaRuns) - stem.length;
    const loD = Math.min.apply(null, digitRuns);
    const hiD = Math.max.apply(null, digitRuns);
    const pat = "\\b" + stem + "[A-Za-z]{" + loA + "," + hiA + "}\\d{" + loD + "," + hiD + "}\\b";
    return { matcher: new RegExp(pat, "gi"), lengths: lengths };
  }

  // Mirrors securities_identity.derive_prefix.
  function _derivePrefix(regNumber) {
    const rn = String(regNumber || "").trim().toUpperCase();
    if (rn.indexOf("IN-DP-") === 0) return "IN-DP";
    let m = /^([A-Z]+)-/.exec(rn);
    if (m) return m[1];
    m = /^([A-Z]+)/.exec(rn);
    return m ? m[1] : rn;
  }

  function _meta() { return (SNAPSHOT && SNAPSHOT.meta) || {}; }

  function _categoryForPrefix(prefix) {
    return (_meta().prefix_categories || {})[String(prefix || "").toUpperCase()] || null;
  }

  // Per-category as-on date - never one global date. SEBI refreshes each
  // intermediary category on its own cadence.
  function _asOnDateFor(prefix) {
    const cat = _categoryForPrefix(prefix);
    const perCat = _meta().per_category_as_on_dates || {};
    return (cat && perCat[cat]) || _meta().register_as_of || "";
  }

  function _verifyUrlFor(prefix) {
    const cat = _categoryForPrefix(prefix);
    return ((_meta().category_urls || {})[cat])
      || "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes";
  }

  function _normaliseName(name) {
    return (name || "").toLowerCase().replace(SUFFIX_RE, " ")
      .replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  }

  function _posterHost(poster) {
    const p = (poster || "").toLowerCase();
    if (p.includes("://") || (p.includes(".") && !p.includes(" "))) {
      try {
        const u = new URL(p.includes("://") ? p : "http://" + p);
        return (u.hostname || p).replace(/^www\./, "");
      } catch (e) { return p; }
    }
    return p;
  }

  // Dice-coefficient bigram similarity, scaled 0..100 (stands in for token_set_ratio).
  function _nameScore(a, b) {
    a = a || ""; b = b || "";
    if (!a || !b) return 0;
    if (a === b) return 100;
    const bigrams = (s) => {
      const m = new Map();
      for (let i = 0; i < s.length - 1; i++) { const g = s.substr(i, 2); m.set(g, (m.get(g) || 0) + 1); }
      return m;
    };
    const ma = bigrams(a), mb = bigrams(b);
    let inter = 0, total = 0;
    ma.forEach((c) => (total += c));
    mb.forEach((c, g) => { total += c; if (ma.has(g)) inter += Math.min(c, ma.get(g)); });
    return Math.round((2 * inter / total) * 100);
  }

  function _isSecurities(text) {
    const low = (text || "").toLowerCase();
    return SEC_LEXICON.filter((t) => low.includes(t)).length >= 2;
  }

  function _parseDate(v) {
    if (!v) return null;
    const t = Date.parse(v);
    return isNaN(t) ? null : t;
  }

  // Authority is PER CATEGORY, not global (mirrors register_is_authoritative_for).
  // A number whose prefix is outside covered_prefixes may be perfectly genuine and
  // simply outside the fetched categories - it must never be called `invalid` (G-2).
  function _authoritativeFor(prefix) {
    const meta = _meta();
    if (meta.synthetic_subset) return false;
    return (meta.covered_prefixes || []).indexOf(String(prefix || "").toUpperCase()) !== -1;
  }

  function _resolveOne(claim, poster) {
    const rec = BY_NUMBER[claim.toUpperCase()];
    const prefix = _derivePrefix(claim);
    const asOn = _asOnDateFor(prefix);
    // Every verdict - valid AND invalid - carries the per-category as-on date and
    // a live SEBI link (BL-4: the data vintage is always visible).
    const base = { number: claim, register_category: _categoryForPrefix(prefix),
      as_on_date: asOn, verify_url: _verifyUrlFor(prefix), verify_label: "Verify live on SEBI" };

    if (!rec) {
      if (!_authoritativeFor(prefix)) {
        const covered = (_meta().covered_categories || []).join(", ") || "none";
        return Object.assign({}, base, { state: "unverified", resolved_name: null,
          name_match_score: null,
          reason: "Registration " + claim + " could not be checked — this snapshot covers only "
            + covered + ", and " + claim + " is outside those categories. This is a coverage "
            + "limit, not a finding against this entity. Verify live on SEBI." });
      }
      // The register lists CURRENT registrants only, so a lapsed or cancelled
      // registration disappears rather than showing a cancelled status. "Not
      // found" is the strongest claim the data supports - never "this is fake".
      return Object.assign({}, base, { state: "invalid", resolved_name: null, name_match_score: 0,
        reason: "Registration " + claim + " — Not found in the SEBI register as of " + asOn
          + ". The register lists current registrants only, so a lapsed or cancelled "
          + "registration also appears this way." });
    }
    if (rec.status && rec.status !== "active") {
      return Object.assign({}, base, { state: "invalid", resolved_name: rec.registered_name,
        name_match_score: null,
        reason: "Registration " + claim + " is registered to " + rec.registered_name
          + " but its status is " + rec.status + " as of " + asOn });
    }
    const host = _posterHost(poster);
    // domain_anchor is the registrant's e-mail domain with free/consumer mail
    // providers removed - anchoring on gmail.com would let any consumer-mail
    // sender short-circuit to `valid`.
    const site = (rec.domain_anchor || rec.website || "").toLowerCase();
    if (site && host && (host === site || host.endsWith("." + site) || site.endsWith("." + host))) {
      return Object.assign({}, base, { state: "valid", resolved_name: rec.registered_name,
        name_match_score: 100,
        reason: "Registration " + claim + " resolves to " + rec.registered_name
          + " on its own registered domain (SEBI register as of " + asOn + ")" });
    }
    const score = _nameScore(_normaliseName(poster), rec.name_normalised);
    if (score >= 85) {
      return Object.assign({}, base, { state: "valid", resolved_name: rec.registered_name,
        name_match_score: score,
        reason: "Registration " + claim + " resolves to " + rec.registered_name
          + ", matching the poster (SEBI register as of " + asOn + ")" });
    }
    if (score >= 70) {
      return Object.assign({}, base, { state: "weak_match", resolved_name: rec.registered_name,
        name_match_score: score,
        reason: "Registration " + claim + " resolves to " + rec.registered_name
          + "; poster name is a partial match (" + score + "%). Flagged, not an accusation" });
    }
    return Object.assign({}, base, { state: "collision", resolved_name: rec.registered_name,
      name_match_score: score,
      reason: "Registration " + claim + " is registered to " + rec.registered_name
        + ", not to this sender" });
  }

  function quickCheck(text, posterIdentity, pageDate) {
    if (!SNAPSHOT) return { state: "unavailable", reason: "snapshot not loaded", layer: "1.6" };
    text = text || "";
    const claims = [];
    let m;
    MATCHER.lastIndex = 0;
    while ((m = MATCHER.exec(text)) !== null) {
      const c = m[0].toUpperCase();
      // Enforce the observed total-length envelope; a regex cannot express a
      // total-length constraint across alternation.
      if (LENGTHS && LENGTHS.size && !LENGTHS.has(c.length)) continue;
      if (!claims.includes(c)) claims.push(c);
    }

    // UPI namespace membership (offline)
    const upi = [];
    let u;
    UPI_RE.lastIndex = 0;
    while ((u = UPI_RE.exec(text)) !== null) {
      const id = u[1].toLowerCase();
      const handle = id.split("@")[1] || "";
      upi.push({ upi_id: id, in_valid_namespace: (SNAPSHOT.upi_suffixes || []).includes(handle),
        sebi_check_url: SNAPSHOT.sebi_check_url });
    }

    const reasons = [];
    if (claims.length === 0) {
      const pd = _parseDate(pageDate);
      if (_isSecurities(text) && pd !== null && pd >= DISCLOSURE_DATE) {
        reasons.push({ code: "registration_absent",
          text: "Securities content dated on/after 1 May 2026 must display a SEBI registration number. None was found.",
          source_url: "https://www.sebi.gov.in" });
        return _result("absent", [], upi, reasons);
      }
      return _result("not_applicable", [], upi, reasons);
    }

    const resolved = claims.map((c) => _resolveOne(c, posterIdentity));
    resolved.forEach((r) => reasons.push({ code: "registration_" + r.state, text: r.reason,
      as_on_date: r.as_on_date, verify_label: "Verify live on SEBI", source_url: r.verify_url }));
    const worst = resolved.map((r) => r.state)
      .sort((a, b) => STATE_ORDER.indexOf(a) - STATE_ORDER.indexOf(b))[0];
    return _result(worst, resolved, upi, reasons);
  }

  function _result(state, claims, upi, reasons) {
    return {
      state: state,
      trust_delta: SECURITIES_DELTA[state] || 0,
      claims: claims,
      upi: upi,
      reasons: reasons,
      register_as_of: SNAPSHOT ? SNAPSHOT.meta.register_as_of : null,
      register: {
        per_category_as_on_dates: _meta().per_category_as_on_dates || {},
        covered_categories: _meta().covered_categories || [],
        record_count: _meta().record_count || 0,
        verify_url: "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes",
        verify_label: "Verify live on SEBI",
      },
      layer: "1.6",
    };
  }

  // Read-only accessor so other lanes (preflight/identity.js) can consult the
  // bundled UPI namespace and register metadata without reaching into internals
  // or loading a second copy of the snapshot.
  function snapshot() { return SNAPSHOT; }

  return { load: _loadSnapshot, quickCheck: quickCheck, snapshot: snapshot,
           _nameScore: _nameScore, SECURITIES_DELTA: SECURITIES_DELTA };
});
