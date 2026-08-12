/*
 * extension/preflight/verdict.js - assembles L0-L5 from pure inputs.
 *
 * PURE. No chrome.*, no DOM, no network. Every product law that governs what the
 * user is told is enforced here, in one place, so a UI change cannot quietly
 * violate one:
 *
 *   BL-1  advisory only. Nothing here blocks: `action` is always "warn" or
 *         "inform", and every interstitial carries a working continue.
 *   BL-2  the four truths (channel / identity / content / interaction) are
 *         emitted SEPARATELY and never collapsed into one score.
 *   BL-3  any absent/missing state carries an explicit disclaimer line.
 *   BL-4  the producing layer and a confidence LABEL are always present.
 *   BL-5  no blocked claim appears in any copy string below. L0 in particular
 *         must never read "safe".
 *
 * Confidence is a LABEL - high / medium / low - never a percentage. A percentage
 * implies a calibration we have not demonstrated, and A.7/B.0 are exactly the
 * evidence that we should not imply one.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanPreflightVerdict = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const ORDER = ["L5_KNOWN_BAD", "L4_IDENTITY_MISMATCH", "L3_PAYMENT_RISK",
                 "L2_INFRASTRUCTURE_RISK", "L1_UNVERIFIED_SECURITIES", "L0_NO_SIGNALS"];

  // BL-5: this exact wording is required for L0. "No signals found" is a
  // statement about our coverage, not a claim about the destination.
  const L0_COPY = "No signals found. This is not a safety guarantee.";
  // BL-3: a missing credential is never proof of deception.
  const BL3_DISCLAIMER =
    "A missing registration disclosure is not proof of deception. It means the "
    + "disclosure required of securities-market content since 1 May 2026 was not "
    + "found on this link.";

  function _code(code, summary, evidence, truth) {
    return { code: code, summary: summary, evidence: evidence || {}, truth: truth };
  }

  /**
   * assemble(parsed, identity, opts)
   *   parsed    url_parse.parse() output
   *   identity  identity.resolve() output
   *   opts.feedHit   { feed, updated, listed } from a local threat-feed snapshot
   *   opts.pageDate  ISO date for the disclosure rule
   *   opts.stagesRun ["offline"] or ["offline","destination"]
   */
  function assemble(parsed, identity, opts) {
    const o = opts || {};
    const id = identity || {};
    const codes = [];

    // ---- L5 known bad ------------------------------------------------------
    if (o.feedHit && o.feedHit.listed) {
      codes.push(_code("L5_KNOWN_BAD",
        "Listed on a public threat feed (" + (o.feedHit.feed || "unknown feed")
          + ", updated " + (o.feedHit.updated || "unknown date") + ").",
        { feed: o.feedHit.feed, updated: o.feedHit.updated }, "channel"));
    }

    // ---- L4 identity mismatch ---------------------------------------------
    const reg = id.registration || {};
    if (reg.state === "collision") {
      codes.push(_code("L4_IDENTITY_MISMATCH",
        "A registration number used here is registered to a different entity.",
        { registration_state: reg.state, claims: reg.claims }, "identity"));
    }
    if (id.domain_status === "lookalike" && id.lookalike_of) {
      codes.push(_code("L4_IDENTITY_MISMATCH",
        "This domain resembles " + id.lookalike_of.official
          + " (" + (id.lookalike_of.entity || "official domain") + ") but is not it.",
        id.lookalike_of, "identity"));
    }

    // ---- L3 payment risk ---------------------------------------------------
    if (parsed.is_payment_link) {
      const p = parsed.payment || {};
      codes.push(_code("L3_PAYMENT_RISK",
        "This link opens a payment app" + (p.amount_prefilled
          ? " with the amount already filled in (" + p.amount + ")." : "."),
        { payee_vpa: p.payee_vpa, amount: p.amount, scheme: p.scheme }, "interaction"));
    }
    const badUpi = (id.upi || []).filter((u) => u && u.in_valid_namespace === false);
    if (badUpi.length) {
      codes.push(_code("L3_PAYMENT_RISK",
        "A payment identifier here is outside the SEBI @valid namespace used by "
          + "registered intermediaries.",
        { upi: badUpi.map((u) => u.upi_id) }, "interaction"));
    }
    if (/\.apk($|\?)/i.test(parsed.path || "")) {
      codes.push(_code("L3_PAYMENT_RISK",
        "This link distributes an Android package (.apk) outside an app store.",
        { path: parsed.path }, "interaction"));
    }

    // ---- L2 infrastructure risk -------------------------------------------
    const infra = [];
    if (parsed.is_punycode || (parsed.obfuscation && parsed.obfuscation.obfuscated)) {
      infra.push(parsed.is_punycode ? "punycode hostname" : "hidden characters in the hostname");
    }
    if (parsed.is_ip_host) {
      infra.push("the host is a raw IP address"
        + (parsed.ip_form && parsed.ip_form !== "ipv4" ? " written in " + parsed.ip_form + " form" : ""));
    }
    if (parsed.userinfo_looks_like_host) infra.push("the address shows one site before '@' but goes to another");
    if (parsed.subdomain_stuffing) infra.push("an official name appears in the subdomain of an unrelated domain");
    if (parsed.anchor_mismatch) infra.push("the visible link text names a different site than the link goes to");
    if ((o.redirectChain || []).length >= 3) infra.push((o.redirectChain || []).length + " cross-domain redirects");
    if (parsed.scheme_dangerous) infra.push("the link uses a " + String(parsed.scheme).replace(":", "") + ": scheme");
    // A shortener conceals the destination by design, so the offline stages
    // cannot see what they are judging. Say that rather than return L0 - an
    // unexpanded shortener is an absence of evidence, not evidence of absence.
    if (parsed.is_shortener) {
      infra.push("this is a link shortener, so the real destination is hidden until it is opened");
    }
    if (parsed.single_use_token) {
      infra.push("the address carries a one-time token that identifies the recipient");
    }
    if (infra.length) {
      codes.push(_code("L2_INFRASTRUCTURE_RISK", "Address-level signals: " + infra.join("; ") + ".",
        { details: infra, host: parsed.host, decoded: parsed.host_decoded }, "channel"));
    }

    // ---- L1 unverified securities -----------------------------------------
    if (reg.state === "absent") {
      const c = _code("L1_UNVERIFIED_SECURITIES",
        "This looks like securities-market content but shows no SEBI registration disclosure.",
        { registration_state: reg.state, register_as_of: reg.register_as_of }, "content");
      c.disclaimer = BL3_DISCLAIMER;      // BL-3, mandatory on this code
      codes.push(c);
    } else if (reg.state === "unverified") {
      const c = _code("L1_UNVERIFIED_SECURITIES",
        "A registration number is shown but could not be checked against the bundled register.",
        { registration_state: reg.state, register_as_of: reg.register_as_of }, "content");
      c.disclaimer = "This is a coverage limit of our offline snapshot, not a finding "
                   + "against this entity. Verify live on SEBI.";
      codes.push(c);
    }

    // ---- L0 ----------------------------------------------------------------
    if (!codes.length) {
      codes.push(_code("L0_NO_SIGNALS", L0_COPY, {}, "none"));
    }

    codes.sort((a, b) => ORDER.indexOf(a.code) - ORDER.indexOf(b.code));
    const top = codes[0].code;

    // ---- confidence: a LABEL, never a percentage --------------------------
    // High only for deterministic, offline-checkable facts. Anything resting on
    // a heuristic (brand-token similarity, an unmatched public suffix) is lower.
    let confidence = "medium";
    if (top === "L0_NO_SIGNALS") {
      confidence = (o.stagesRun || []).indexOf("destination") !== -1 ? "medium" : "low";
    } else if (top === "L5_KNOWN_BAD" || top === "L3_PAYMENT_RISK") {
      confidence = "high";
    } else if (top === "L4_IDENTITY_MISMATCH") {
      confidence = (reg.state === "collision"
        || (id.lookalike_of && id.lookalike_of.reason !== "brand_token_in_other_domain"))
        ? "high" : "medium";
    } else if (top === "L2_INFRASTRUCTURE_RISK") {
      confidence = (parsed.is_ip_host || parsed.userinfo_looks_like_host || parsed.is_punycode)
        ? "high" : "medium";
    } else if (top === "L1_UNVERIFIED_SECURITIES") {
      confidence = "medium";
    }
    if (parsed.psl_matched === false && !parsed.is_ip_host && confidence === "high") {
      confidence = "medium";   // eTLD+1 came from the fallback, not a known rule
    }

    return {
      verdict: top,
      codes_fired: codes.map((c) => c.code),
      codes: codes,
      // BL-2: four truths, separately, always. `null` means "not assessed",
      // which is not the same as "fine" and is rendered differently.
      truths: {
        channel: _truth(codes, "channel", parsed, id),
        identity: _truth(codes, "identity", parsed, id),
        content: _truth(codes, "content", parsed, id),
        interaction: _truth(codes, "interaction", parsed, id),
      },
      // BL-4: layer and confidence always visible.
      layer: "preflight",
      confidence: confidence,
      confidence_is_label: true,
      // BL-1: advisory only. Never "block".
      action: top === "L0_NO_SIGNALS" ? "inform" : "warn",
      dismissible: true,
      continue_allowed: true,
      stages_run: o.stagesRun || ["offline"],
      stages_note: (o.stagesRun || []).indexOf("destination") !== -1
        ? "Checked the destination."
        : "Checked offline only.",
      url: parsed.raw,
      host: parsed.host,
    };
  }

  function _truth(codes, truth, parsed, id) {
    const mine = codes.filter((c) => c.truth === truth);
    if (!mine.length) {
      return { state: "no_signals", summary: "No signals for this dimension.",
               codes: [], assessed: true };
    }
    return {
      state: "signals",
      summary: mine.map((c) => c.summary).join(" "),
      codes: mine.map((c) => c.code),
      disclaimers: mine.filter((c) => c.disclaimer).map((c) => c.disclaimer),
      assessed: true,
    };
  }

  return { assemble: assemble, L0_COPY: L0_COPY, BL3_DISCLAIMER: BL3_DISCLAIMER, ORDER: ORDER };
});
