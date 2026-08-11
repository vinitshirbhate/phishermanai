/*
 * Decide what a signal MEANS, from the signal itself.
 *
 * Signals cross the backend boundary as plain strings, so both display surfaces
 * used to guess severity from the page's overall score. On a page scored DANGER
 * that stamped every signal high-severity red, including "Domain is on trusted
 * whitelist" - a +30 TRUST signal in domain_intel.py. The UI showed evidence of
 * safety painted as evidence of danger.
 *
 * Polarity, not just severity:
 *   protective  reduces concern (whitelisted domain, legitimate pattern)
 *   risk        raises concern
 *   context     neither; describes the page
 *
 * Severity is meaningful only for `risk`. Protective and context signals never
 * take a risk icon or colour.
 */
"use strict";

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.PhishermanSignalPolarity = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {

  // Protective: the engine emitted this to LOWER concern. Matching one of these
  // and painting it red is the specific defect this module exists to stop.
  const PROTECTIVE = [
    /\bon\s+trusted\s+whitelist\b/i,
    /\blegitimate\s+notification\s+pattern\b/i,
    /\bknown\s+(?:good|legitimate)\s+(?:domain|sender)\b/i,
    /\bregistered\s+with\s+SEBI\b/i,
    /\bmatches\s+the\s+SEBI\s+register\b/i,
    /\bdomain\s+matches\s+the\s+registered\s+entity\b/i,
    /\bno\s+signals\s+found\b/i,
  ];

  // Context: describes the page without asserting risk. Rendering these as
  // threats is how a link count became "evidence".
  const CONTEXT = [
    /\bcontains?\s+links?\b/i,
    /\bnews\s+article\s+detected\b/i,
    /\bengine\s+error\b/i,
    /\bnot\s+scanning\b/i,
    /\bscan\s+(?:skipped|incomplete)\b/i,
  ];

  // Risk severity. Ordered most-severe-first; first match wins. Anything that
  // matches nothing here is 'low' - an unrecognised signal is not promoted to
  // an alarm just because the page scored badly.
  const HIGH = [
    /\bdigital\s+arrest\b/i,
    /\bknown\s+(?:phishing|malware|fraud)\b/i,
    /\bon\s+(?:a\s+)?blocklist\b/i,
    /\breported\s+\d+\s+times?\b/i,
    /\btyposquat\b/i,
    /\bIP\s+address\s+instead\s+of\s+domain\b/i,
    /\bcredential\s+harvest/i,
    /\bandroid\s+app\s+file\b/i,
    /\bunsigned\s+app\b/i,
    /\boutside\s+(?:an?\s+)?app\s+store\b/i,
  ];
  const MEDIUM = [
    /\bscam\b/i, /\bfraud\b/i, /\bphish/i,
    /\bimpersonat/i, /\bPII\b|\bpersonal\s+information\s+request\b/i,
    /\bUPI\s+(?:handle|ID|collect)/i,
    /\burgency\s+manipulation\b/i,
    /\bpressure\b/i, /\bthreat\b/i,
    /\bno\s+HTTPS\b/i,
    /\blink\s+shortener\b/i,
  ];

  function matches(list, label) {
    for (let i = 0; i < list.length; i++) if (list[i].test(label)) return true;
    return false;
  }

  /**
   * classify(label) -> { polarity, severity }
   *   polarity: "protective" | "risk" | "context"
   *   severity: "high" | "medium" | "low" | "none"
   */
  function classify(label) {
    const s = String(label == null ? "" : label);
    // Strip the lane tag the backend prefixes ("[scam] ...") before matching so
    // the tag itself never decides severity - "[scam]" appears on every signal
    // that lane emits, including protective ones.
    const bare = s.replace(/^\s*\[[a-z_]+\]\s*/i, "");

    if (matches(PROTECTIVE, bare)) return { polarity: "protective", severity: "none" };
    if (matches(CONTEXT, bare)) return { polarity: "context", severity: "none" };
    if (matches(HIGH, bare)) return { polarity: "risk", severity: "high" };
    if (matches(MEDIUM, bare)) return { polarity: "risk", severity: "medium" };
    return { polarity: "risk", severity: "low" };
  }

  /**
   * normalise(signal) -> { label, polarity, severity, ...original }
   *
   * Accepts a bare string or an object. An object that already carries an
   * explicit polarity is trusted - engines that know their own signal's meaning
   * should say so rather than have it re-derived from wording.
   */
  function normalise(signal) {
    if (signal && typeof signal === "object") {
      const label = signal.label || signal.message || signal.name || "Signal detected";
      if (signal.polarity) {
        return Object.assign({}, signal, {
          label: label,
          severity: signal.severity || (signal.polarity === "risk" ? "low" : "none"),
        });
      }
      const c = classify(label);
      return Object.assign({}, signal, {
        label: label,
        polarity: c.polarity,
        severity: signal.severity || c.severity,
      });
    }
    const label = String(signal == null ? "" : signal);
    const c = classify(label);
    return { label: label, polarity: c.polarity, severity: c.severity };
  }

  /** Split for display: risks first (most severe first), protective last. */
  function partition(signals) {
    const all = (signals || []).map(normalise);
    const rank = { high: 0, medium: 1, low: 2, none: 3 };
    const risk = all.filter((s) => s.polarity === "risk")
      .sort((a, b) => rank[a.severity] - rank[b.severity]);
    return {
      risk: risk,
      protective: all.filter((s) => s.polarity === "protective"),
      context: all.filter((s) => s.polarity === "context"),
      all: all,
    };
  }

  return { classify, normalise, partition };
}));
