/*
 * extension/preflight/identity.js - identity resolution for a pre-flight check.
 *
 * PURE. Delegates all registration reasoning to securities_check.js (the offline
 * F-B1 quick-check) rather than re-implementing it - the same single-definition
 * rule that governs ml/features.py and shared/normalise.js.
 *
 * THE RULE THAT MATTERS HERE: `domain_unknown` is NOT a risk signal. Most of the
 * web is not a registered intermediary, and a corner shop's website is not
 * suspicious for failing to appear in SEBI's register. Only a LOOKALIKE of an
 * official domain, or a registration claim that contradicts the domain, is
 * evidence. Getting this wrong would make the product warn on most of the web,
 * which is how users learn to dismiss warnings.
 *
 * No chrome.* APIs. Loads under Node and in the service worker.
 */
(function (root, factory) {
  const api = factory(
    (typeof require !== "undefined") ? require("../securities_check.js") : root.PhishermanSecurities
  );
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanPreflightIdentity = api;
})(typeof self !== "undefined" ? self : this, function (SEC) {
  "use strict";

  /**
   * resolve(parsed, ctx)
   *   parsed  output of url_parse.parse()
   *   ctx.anchorText / ctx.surroundingText  text to mine for a registration claim
   *   ctx.pageDate  ISO date, for the disclosure rule
   */
  function resolve(parsed, ctx) {
    const c = ctx || {};
    const out = {
      domain_status: "unknown",     // official | lookalike | unknown
      official_entity: null,
      lookalike_of: null,
      registration: null,
      upi: [],
      disclosure: null,
      layer: "preflight.identity",
      notes: [],
    };

    if (parsed.official_match) {
      out.domain_status = "official";
      out.official_entity = parsed.official_match.entity;
    } else if (parsed.homoglyph_target) {
      out.domain_status = "lookalike";
      out.lookalike_of = parsed.homoglyph_target;
    } else if (parsed.subdomain_stuffing) {
      out.domain_status = "lookalike";
      out.lookalike_of = { official: parsed.subdomain_stuffing.official,
                           entity: parsed.subdomain_stuffing.entity,
                           reason: "subdomain_stuffing" };
    } else {
      out.notes.push("Domain is not in the official list. That is the normal case "
                     + "for most of the web and is NOT scored as risk.");
    }

    // A upi: deep link carries its payee VPA directly - check the namespace.
    if (parsed.is_payment_link && parsed.payment && parsed.payment.payee_vpa) {
      const vpa = parsed.payment.payee_vpa;
      const handle = String(vpa).split("@")[1] || "";
      let inNamespace = false;
      try {
        const snap = SEC && SEC.snapshot && SEC.snapshot();
        inNamespace = !!(snap && (snap.upi_suffixes || []).indexOf(handle.toLowerCase()) !== -1);
      } catch (e) { /* snapshot not loaded; reported as unknown below */ }
      out.upi.push({ upi_id: vpa, in_valid_namespace: inNamespace,
                     amount: parsed.payment.amount || null });
    }

    // Registration claim from the anchor + the text around it.
    const text = [c.anchorText, c.surroundingText, c.title].filter(Boolean).join(" \n ");
    if (text.trim()) {
      try {
        const q = SEC.quickCheck(text, parsed.host_normalised || parsed.host, c.pageDate);
        if (q && q.state !== "unavailable") {
          out.registration = { state: q.state, claims: q.claims || [], reasons: q.reasons || [],
                               register_as_of: q.register_as_of || null };
          out.disclosure = { state: q.state, required: q.state === "absent" };
          (q.upi || []).forEach((u) => out.upi.push(u));
        } else if (q) {
          out.notes.push("Offline register snapshot not loaded; registration not checked.");
        }
      } catch (e) {
        out.notes.push("Registration check unavailable: " + (e && e.message));
      }
    }
    return out;
  }

  return { resolve: resolve };
});
