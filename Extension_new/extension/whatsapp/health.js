/*
 * extension/whatsapp/health.js - selector health check. MANDATORY.
 *
 * WhatsApp's DOM will change. When it does, the honest failure is to STOP and
 * SAY SO. The dishonest failure - the one this module exists to prevent - is to
 * keep running, find nothing, show no badges, and let the user believe they are
 * protected. That is strictly worse than being switched off, because it
 * manufactures false confidence.
 *
 * This is BL-4 (no certainty theatre) applied to the DOM layer: the producing
 * layer's ability to see is itself surfaced, not assumed.
 *
 *   health = resolved_required_targets / expected_required_targets
 *     >= 0.8   HEALTHY   normal operation
 *     0.4-0.8  DEGRADED  scan what resolves, and say coverage is partial
 *     <  0.4   BLIND     STOP scanning. Badge reads "Not scanning".
 *
 * Tier depth is tracked separately: a registry resolving everything at tier 3 is
 * one change away from blindness and should be visible before it gets there.
 *
 * PURE MODULE: takes a document, returns a report. No chrome.*, no network.
 */
(function (root, factory) {
  const api = factory(
    (typeof require !== "undefined") ? require("./selectors.js") : root.PhishermanWaSelectors
  );
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanWaHealth = api;
})(typeof self !== "undefined" ? self : this, function (SEL) {
  "use strict";

  const HEALTHY_MIN = 0.8;
  const DEGRADED_MIN = 0.4;
  const RECHECK_MS = 5 * 60 * 1000;      // every 5 minutes, plus on chat open

  const COPY = {
    HEALTHY: { badge: "Scanning", panel: "Scanning this chat." },
    DEGRADED: {
      badge: "Partial",
      panel: "Partial coverage — WhatsApp's page structure changed. Some messages "
           + "in this chat may not be checked.",
    },
    BLIND: {
      badge: "Not scanning",
      panel: "Not scanning. WhatsApp's page structure changed and this extension can "
           + "no longer read messages reliably. Nothing in this chat is being checked. "
           + "This is a limitation of the extension, not a judgement about this chat.",
    },
    OFF: { badge: "Off", panel: "Scanning is switched off for this chat." },
  };

  /** Detect the logged-out / QR screen. Nothing is readable there. */
  function isLoggedOut(doc) {
    if (!doc || !doc.querySelector) return true;
    if (doc.querySelector("canvas[aria-label], [data-ref]")) {
      // QR canvas present and no conversation pane -> not logged in.
      if (!doc.querySelector("#main")) return true;
    }
    const t = (doc.body && doc.body.textContent || "").toLowerCase();
    return /to use whatsapp on your computer|log into whatsapp|scan the qr code/.test(t);
  }

  /**
   * check(doc) -> {
   *   state, score, ratio, logged_out, targets[], tier_depth, copy, registry_version
   * }
   */
  function check(doc) {
    const t0 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
    const loggedOut = isLoggedOut(doc);

    const main = SEL.resolve("conversation", doc).nodes[0] || null;
    const scroll = main ? SEL.resolve("scroll_container", doc, main).nodes[0] : null;

    const required = SEL.requiredTargetNames();
    const rows = [];
    let resolved = 0, tierSum = 0;

    for (const name of required) {
      const scope = (name === "message_row" || name === "message_meta" || name === "outgoing")
        ? (scroll || main) : (name === "chat_title" || name === "scroll_container") ? main : null;
      const r = SEL.resolve(name, doc, scope);
      rows.push({ target: name, resolved: r.resolved, tier: r.tier,
                  tier_name: r.tier_name, count: r.nodes.length });
      if (r.resolved) { resolved += 1; tierSum += r.tier; }
    }

    const ratio = required.length ? resolved / required.length : 0;
    let state = ratio >= HEALTHY_MIN ? "HEALTHY" : (ratio >= DEGRADED_MIN ? "DEGRADED" : "BLIND");
    // A logged-out tab cannot be scanned at all, whatever the selectors say.
    if (loggedOut) state = "BLIND";

    const t1 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
    return {
      state: state,
      // Never scan when BLIND. The adapter reads this flag, not the string.
      may_scan: state === "HEALTHY" || state === "DEGRADED",
      score: Number(ratio.toFixed(3)),
      resolved: resolved,
      expected: required.length,
      logged_out: loggedOut,
      // Mean tier depth of what DID resolve. 1.0 is ideal; approaching 3 means
      // we are surviving on fallbacks and one change from BLIND.
      tier_depth: resolved ? Number((tierSum / resolved).toFixed(2)) : null,
      targets: rows,
      copy: COPY[state],
      registry_version: SEL.REGISTRY_VERSION,
      elapsed_ms: Number((t1 - t0).toFixed(3)),
      checked_at: null,     // stamped by the adapter; pure module takes no clock
    };
  }

  return {
    check: check,
    isLoggedOut: isLoggedOut,
    COPY: COPY,
    HEALTHY_MIN: HEALTHY_MIN,
    DEGRADED_MIN: DEGRADED_MIN,
    RECHECK_MS: RECHECK_MS,
  };
});
