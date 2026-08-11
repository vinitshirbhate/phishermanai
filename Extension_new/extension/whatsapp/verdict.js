/*
 * extension/whatsapp/verdict.js - W0-W6 assembly. PURE.
 *
 * BADGE ONLY AT W1 AND ABOVE. W0 renders nothing at all - not a green tick, not
 * a quiet "checked" marker, nothing. A wall of reassurances is noise, and noise
 * is how people learn to ignore warnings. The absence of a badge is the signal
 * for an ordinary message.
 *
 * OUTGOING MESSAGES ARE NEVER SCORED FOR RISK. The user's own words are not
 * evidence against them. They feed the escalation ladder and the "no prior
 * outgoing" unsolicited-add check in context.js, and nothing else.
 *
 * THE CLAIM IS ALWAYS ABOUT THE CREDENTIAL, NEVER THE PERSON. W5 says "this
 * number is registered to someone else" - it never says the sender is a
 * criminal. We do not know that, and asserting it about an identifiable person
 * on the basis of a DOM scrape would be indefensible.
 *
 * W6 is the outcome that matters most: it is the only one that demonstrates
 * detection of a CAMPAIGN spanning channels rather than a message in isolation.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanWaVerdict = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // W4_UNSAFE_APP_OFFER sits at the W4 tier alongside payment solicitation: both
  // are "this message asks you to take an irreversible action", which is what
  // the tier means. It outranks payment because sideloading a financial-brand
  // app compromises the device itself, not just one transfer.
  const ORDER = ["W6_CAMPAIGN_LINKED", "W5_IDENTITY_MISMATCH", "W4_UNSAFE_APP_OFFER",
                 "W4_PAYMENT_SOLICITATION",
                 "W3_TYPOLOGY_MATCH", "W2_UNVERIFIED_ADVISORY", "W1_UNSOLICITED_CONTEXT",
                 "W0_NO_SIGNALS"];

  const BL3_DISCLAIMER =
    "A missing registration disclosure is not proof of deception. It means the "
    + "disclosure required of securities-market content since 1 May 2026 was not "
    + "found in this message.";

  const DISCLOSURE_DATE = Date.UTC(2026, 4, 1);   // 1 May 2026

  function _code(code, summary, evidence, truth) {
    return { code: code, summary: summary, evidence: evidence || {}, truth: truth };
  }

  /**
   * assemble(record, channel, opts)
   *   record   MessageRecord from extract.js
   *   channel  context.assess() output
   *   opts.registration  securities_check.quickCheck() result for this body
   *   opts.typologies    [{id, weight, source}] from the typology matcher
   *   opts.campaign      {shared_entities:[], prior:{chat_id|url, seen_at}, within_days}
   *   opts.health        health.check() state string
   */
  function assemble(record, channel, opts) {
    const o = opts || {};
    const r = record || {};
    const ch = channel || { signals: [], detail: {} };
    const codes = [];

    // The user's own messages are never scored. Return early and explicitly.
    if (r.direction === "outgoing") {
      return _result("W0_NO_SIGNALS", [_code("W0_NO_SIGNALS",
        "Outgoing message — never scored for risk.", {}, "none")], r, ch, o, false);
    }

    // ---- W6 campaign linkage (the demo outcome) --------------------------
    const camp = o.campaign;
    if (camp && (camp.shared_entities || []).length >= 2) {
      codes.push(_code("W6_CAMPAIGN_LINKED",
        "This message shares " + camp.shared_entities.length
          + " identifiers with activity seen elsewhere"
          + (camp.prior && camp.prior.where ? " (" + camp.prior.where + ")" : "")
          + (camp.within_days ? " within the last " + camp.within_days + " days." : "."),
        { shared_entities: camp.shared_entities, prior: camp.prior,
          within_days: camp.within_days }, "channel"));
    }

    // ---- W5 identity mismatch -------------------------------------------
    const reg = o.registration || {};
    if (reg.state === "collision") {
      const num = (reg.claims && reg.claims[0] && reg.claims[0].number) || "the number quoted";
      const who = (reg.claims && reg.claims[0] && reg.claims[0].resolved_name) || "another entity";
      codes.push(_code("W5_IDENTITY_MISMATCH",
        // About the CREDENTIAL. Never about the person.
        "Registration " + num + " is registered to " + who + ", not to this sender.",
        { registration_state: reg.state, claims: reg.claims,
          register_as_of: reg.register_as_of }, "identity"));
    }

    // ---- W4 payment solicitation ----------------------------------------
    const ent = r.entities || {};
    const payEvidence = [];
    const badUpi = (reg.upi || []).filter((u) => u && u.in_valid_namespace === false);
    if (badUpi.length) payEvidence.push("a UPI id outside the @valid namespace used by registered intermediaries");
    if ((ent.upi_deeplinks || []).length) payEvidence.push("a upi:// payment link");
    if ((ent.ifsc || []).length) payEvidence.push("bank account details with an IFSC code");
    if (ch.detail && ch.detail.escalation_ladder && ch.detail.escalation_ladder.monotonically_rising) {
      payEvidence.push("amounts requested in this chat that rise over time");
    }
    if (payEvidence.length) {
      codes.push(_code("W4_PAYMENT_SOLICITATION",
        "This message asks for money: " + payEvidence.join("; ") + ".",
        { upi_ids: ent.upi_ids, upi_deeplinks: ent.upi_deeplinks, ifsc: ent.ifsc,
          amounts: ent.amounts,
          escalation: ch.detail && ch.detail.escalation_ladder }, "interaction"));
    }

    // ---- W4 unsafe app offer ---------------------------------------------
    // An APK offer used to be appended to payEvidence, which produced the
    // sentence "This message asks for money: an Android app distributed outside
    // an app store." It does not ask for money. It asks the user to sideload an
    // app, which is a different action with a different consequence, and saying
    // the wrong one teaches the user to discount the warning.
    //
    // Evidence is the filename and the delivery channel. Nothing here has read
    // the package, so nothing here calls it malware - see shared/apk_check.js.
    const apk = r.apk && r.apk.is_apk ? r.apk : null;
    const apkLinks = (ent.apk_links || []);
    if (apk || apkLinks.length) {
      const what = apk
        ? (apk.claims.length
          ? "an Android app file whose name advertises a paid app unlocked for free ("
            + apk.claims.join(", ") + ")"
          : "an Android app file")
        : "a link to an Android app file";
      const extra = apk && apk.evidence.financial_brand
        ? " It carries the name of a financial or trading service; a sideloaded build "
          + "can display holdings and balances that are not real."
        : "";
      codes.push(_code("W4_UNSAFE_APP_OFFER",
        "This message delivers " + what + ", outside any app store." + extra,
        { attachment: r.attachment || null,
          apk_links: apkLinks,
          filename: apk ? apk.evidence.filename : null,
          mod_claims: apk ? apk.claims : [],
          financial_brand: apk ? apk.evidence.financial_brand : null,
          disguised_extension: apk ? apk.evidence.disguised_extension : false,
          severity: apk ? apk.severity : "medium" }, "interaction"));
    }

    // ---- W3 typology match ----------------------------------------------
    for (const t of (o.typologies || [])) {
      codes.push(_code("W3_TYPOLOGY_MATCH",
        "Matches a SEBI-published fraud typology: " + (t.label || t.id) + ".",
        { typology_id: t.id, weight: t.weight, source_url: t.source }, "content"));
    }

    // ---- W2 unverified advisory -----------------------------------------
    const ts = r.timestamp ? Date.parse(r.timestamp) : null;
    const postDisclosure = ts === null || isNaN(ts) ? true : ts >= DISCLOSURE_DATE;
    if (reg.state === "absent" && postDisclosure) {
      const c = _code("W2_UNVERIFIED_ADVISORY",
        "This reads as securities-market advice but shows no SEBI registration disclosure.",
        { registration_state: reg.state, register_as_of: reg.register_as_of }, "content");
      c.disclaimer = BL3_DISCLAIMER;      // BL-3, mandatory on this code
      codes.push(c);
    } else if (reg.state === "unverified") {
      const c = _code("W2_UNVERIFIED_ADVISORY",
        "A registration number is quoted but could not be checked against the bundled register.",
        { registration_state: reg.state, register_as_of: reg.register_as_of }, "content");
      c.disclaimer = "This is a coverage limit of the offline snapshot, not a finding "
                   + "against this entity. Verify live on SEBI.";
      codes.push(c);
    }

    // ---- W1 unsolicited context ------------------------------------------
    // Requires >=2 channel properties. One alone is ordinary: plenty of
    // legitimate groups are large, and plenty add you without asking.
    const w1Signals = ["unsolicited_add", "sender_not_in_contacts",
                       "group_name_securities_funnel_pattern", "skewed_poster_ratio"]
      .filter((s) => (ch.signals || []).indexOf(s) !== -1);
    if (w1Signals.length >= 2) {
      codes.push(_code("W1_UNSOLICITED_CONTEXT",
        "This chat has " + w1Signals.length + " properties of the documented scam funnel: "
          + w1Signals.join(", ") + ".",
        { signals: w1Signals, detail: ch.detail }, "channel"));
    }

    if (!codes.length) codes.push(_code("W0_NO_SIGNALS", "", {}, "none"));
    codes.sort((a, b) => ORDER.indexOf(a.code) - ORDER.indexOf(b.code));
    return _result(codes[0].code, codes, r, ch, o, true);
  }

  function _truth(codes, truth) {
    const mine = codes.filter((c) => c.truth === truth && c.code !== "W0_NO_SIGNALS");
    if (!mine.length) {
      return { state: "no_signals", summary: "No signals for this dimension.", codes: [] };
    }
    return {
      state: "signals",
      summary: mine.map((c) => c.summary).join(" "),
      codes: mine.map((c) => c.code),
      disclaimers: mine.filter((c) => c.disclaimer).map((c) => c.disclaimer),
    };
  }

  function _result(top, codes, r, ch, o, scored) {
    // Confidence is a LABEL, never a percentage - no calibration has been
    // demonstrated for this lane and a number would imply one (BL-4).
    let confidence = "medium";
    if (top === "W0_NO_SIGNALS") confidence = "low";
    else if (top === "W5_IDENTITY_MISMATCH" || top === "W4_PAYMENT_SOLICITATION") confidence = "high";
    else if (top === "W6_CAMPAIGN_LINKED") {
      confidence = ((o.campaign && o.campaign.shared_entities) || []).length >= 3 ? "high" : "medium";
    } else if (top === "W1_UNSOLICITED_CONTEXT") confidence = "low";
    // A DEGRADED DOM means we may simply not have seen the rest of the chat.
    if (o.health === "DEGRADED" && confidence === "high") confidence = "medium";

    const flags = r.flags || {};
    const unscannable = [];
    if (flags.view_once_unscannable) unscannable.push("view_once_not_opened");
    if (flags.text_in_image_unscanned) unscannable.push("text_in_image_unscanned");
    if (r.partial) unscannable.push("sender_and_timestamp_unreadable");

    return {
      verdict: top,
      codes_fired: codes.map((c) => c.code),
      codes: codes,
      // W0 renders nothing at all. Badges start at W1.
      badge: top !== "W0_NO_SIGNALS",
      scored: scored,
      truths: {
        channel: _truth(codes, "channel"),
        identity: _truth(codes, "identity"),
        content: _truth(codes, "content"),
        interaction: _truth(codes, "interaction"),
      },
      layer: "whatsapp",
      confidence: confidence,
      confidence_is_label: true,
      // BL-1: advisory only. Nothing here acts on the user's behalf.
      action: top === "W0_NO_SIGNALS" ? "none" : "warn",
      dismissible: true,
      // Reported, never silently dropped.
      unscannable: unscannable,
      message_id: r.message_id || null,
      chat_id: r.chat_id || null,
      health: o.health || null,
      // Persistence contract: hashes and codes only, never body text.
      persist: {
        allowed: r.persist !== false,
        body_sha256: r.body_sha256 || null,
        codes: codes.map((c) => c.code),
      },
    };
  }

  return { assemble: assemble, ORDER: ORDER, BL3_DISCLAIMER: BL3_DISCLAIMER };
});
