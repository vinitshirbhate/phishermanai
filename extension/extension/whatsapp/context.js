/*
 * extension/whatsapp/context.js - CHANNEL-trust signals, scored independently.
 *
 * BL-2 in its sharpest form. Nothing in this module looks at whether a message
 * is fraudulent; it looks at the CHANNEL the message arrived through. The two
 * are computed separately and rendered separately, and neither is permitted to
 * overwrite the other.
 *
 * The case that defines the module: "Good morning" in a chat you were added to
 * unsolicited, in a group named W1001-VIP Wealth where 3 accounts post to 400
 * members, is ZERO content signal and a STRONG channel signal. Collapsing those
 * into one number destroys the only information the user actually needs - which
 * of the four truths is the problem.
 *
 * This module also supplies the object that activates T3 in
 * backend/engines/securities_identity.py (chat context -> disclosure scope).
 *
 * PURE: takes MessageRecords and chat metadata, returns signals. No DOM, no
 * chrome.*, no network, no clock (timestamps come from the records).
 */
(function (root, factory) {
  const api = factory(
    (typeof require !== "undefined") ? require("../shared/normalise.js") : root.PhishermanNormalise
  );
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanWaContext = api;
})(typeof self !== "undefined" ? self : this, function (N) {
  "use strict";

  // Mirrors the split in securities_identity.py: tokens that name a SUBJECT
  // MATTER, versus tokens that name a service TIER. "VIP" and "Premium" appear
  // in the documented funnel but also on gyms, airlines and support desks, and
  // A.7e measured what treating them as equivalent costs.
  const FUNNEL_SECURITIES_RE =
    /\b(signals?|wealth|profits?|trading|traders?|equity|equities|stocks?|investment|investing|portfolio|demat|ipo|nifty|sensex)\b|\bW\d{3,4}-/i;
  const FUNNEL_GENERIC_RE = /\b(vip|premium|elite|exclusive)\b/i;

  const OFF_PLATFORM_RE =
    /\b(join our app|download (?:our|the) app|install (?:our|the) app|private (?:app|link|group)|apk|telegram|move to|switch to)\b/i;

  function funnelName(name) {
    const n = name || "";
    const sec = FUNNEL_SECURITIES_RE.test(n);
    const gen = FUNNEL_GENERIC_RE.test(n);
    return { securities_adjacent: sec, generic_membership: gen, matched: sec || gen };
  }

  function _median(xs) {
    if (!xs.length) return null;
    const s = xs.slice().sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  /**
   * Near-uniform reply intervals across supposedly different people is a
   * scripted-room signal: real humans in a real group do not answer at a
   * metronome. Returns null when there is not enough data to say anything -
   * "unknown" and "fine" are different, and we do not conflate them.
   */
  function replyLatencyUniformity(records) {
    const stamps = records
      .filter((r) => r.timestamp)
      .map((r) => Date.parse(r.timestamp))
      .filter((t) => !isNaN(t))
      .sort((a, b) => a - b);
    if (stamps.length < 6) return null;
    const gaps = [];
    for (let i = 1; i < stamps.length; i++) gaps.push((stamps[i] - stamps[i - 1]) / 1000);
    const med = _median(gaps);
    if (!med || med <= 0) return null;
    const mean = gaps.reduce((a, b) => a + b, 0) / gaps.length;
    const varr = gaps.reduce((a, b) => a + (b - mean) * (b - mean), 0) / gaps.length;
    const cv = Math.sqrt(varr) / (mean || 1);      // coefficient of variation
    return { n_gaps: gaps.length, median_gap_s: Number(med.toFixed(1)),
             cv: Number(cv.toFixed(3)),
             near_uniform: cv < 0.35 && gaps.length >= 6 };
  }

  /**
   * Amounts rising monotonically over time - the withdrawal-trap ladder, where
   * each "release fee" is larger than the last.
   */
  function escalationLadder(records) {
    const points = [];
    for (const r of records) {
      if (r.direction === "outgoing") continue;
      for (const a of (r.entities && r.entities.amounts) || []) {
        points.push({ t: r.timestamp ? Date.parse(r.timestamp) : null, value: a.value, raw: a.raw });
      }
    }
    if (points.length < 3) return null;
    const ordered = points.filter((p) => p.t !== null && !isNaN(p.t)).sort((a, b) => a.t - b.t);
    const seq = (ordered.length >= 3 ? ordered : points).map((p) => p.value);
    let rising = 0;
    for (let i = 1; i < seq.length; i++) if (seq[i] > seq[i - 1]) rising++;
    const ratio = seq.length > 1 ? rising / (seq.length - 1) : 0;
    return {
      n_amounts: seq.length,
      first: seq[0], last: seq[seq.length - 1],
      monotonically_rising: ratio >= 0.8 && seq[seq.length - 1] > seq[0],
      rising_ratio: Number(ratio.toFixed(2)),
    };
  }

  /** Near-duplicate templates seen in OTHER chats. Hashes only — never text. */
  function duplicateTemplates(records, seenHashes) {
    if (!seenHashes || !seenHashes.size) return null;
    const hits = [];
    for (const r of records) {
      if (r.body_sha256 && seenHashes.has(r.body_sha256)) {
        hits.push({ hash: r.body_sha256, chats: seenHashes.get(r.body_sha256) });
      }
    }
    return hits.length ? { n: hits.length, hits: hits.slice(0, 5) } : null;
  }

  /**
   * assess(chat, records, opts) -> channel-trust report.
   *   chat  { chat_id, title, member_count, is_group }
   *   opts.seenHashes  Map<hash, [chat_id,...]> from other chats
   */
  function assess(chat, records, opts) {
    const o = opts || {};
    const ch = chat || {};
    const recs = records || [];
    const incoming = recs.filter((r) => r.direction === "incoming");
    const outgoing = recs.filter((r) => r.direction === "outgoing");
    const systems = recs.filter((r) => r.flags && r.flags.is_system);

    const addedByOther = systems.some((r) =>
      /added you|you were added|आपको जोड़ा/i.test(r.body_text || ""));
    // "Unsolicited" = a system add AND the user has never spoken here. Either
    // alone is ordinary; together they describe being put somewhere uninvited.
    const unsolicitedAdd = addedByOther && outgoing.length === 0;

    const senders = new Set(incoming.map((r) => r.sender && r.sender.display_name).filter(Boolean));
    const unknownSenders = incoming.filter((r) => r.sender && r.sender.is_contact === false);
    const senderNotInContacts = unknownSenders.length > 0
      && unknownSenders.length === incoming.filter((r) => r.sender && r.sender.is_contact !== null).length;

    const memberCount = typeof ch.member_count === "number" ? ch.member_count : null;
    const posterRatio = (memberCount && senders.size)
      ? Number((senders.size / memberCount).toFixed(4)) : null;
    // Few posters, many members - a broadcast wearing a group's clothes.
    const skewedPosterRatio = !!(memberCount && memberCount >= 50 && senders.size > 0
      && senders.size <= 5);

    const name = funnelName(ch.title);
    const forwardedMany = recs.some((r) => r.flags && r.flags.forwarded_many_times);
    const anyBusiness = recs.some((r) => r.sender && r.sender.is_business);
    const offPlatform = incoming.some((r) =>
      OFF_PLATFORM_RE.test(r.body_text || "")
      || ((r.entities && r.entities.apk_links) || []).length > 0);

    const signals = [];
    if (unsolicitedAdd) signals.push("unsolicited_add");
    if (senderNotInContacts) signals.push("sender_not_in_contacts");
    if (name.securities_adjacent) signals.push("group_name_securities_funnel_pattern");
    else if (name.generic_membership) signals.push("group_name_generic_membership_token");
    if (skewedPosterRatio) signals.push("skewed_poster_ratio");
    if (forwardedMany) signals.push("forwarded_many_times");
    if (offPlatform) signals.push("off_platform_move");

    const latency = replyLatencyUniformity(incoming);
    if (latency && latency.near_uniform) signals.push("near_uniform_reply_latency");
    const ladder = escalationLadder(recs);
    if (ladder && ladder.monotonically_rising) signals.push("escalation_ladder");
    const dupes = duplicateTemplates(recs, o.seenHashes);
    if (dupes) signals.push("near_duplicate_template_across_chats");

    return {
      chat_id: ch.chat_id || null,
      // CHANNEL trust only. Deliberately carries no content verdict (BL-2).
      truth: "channel",
      signals: signals,
      detail: {
        unsolicited_add: unsolicitedAdd,
        added_by_other: addedByOther,
        prior_outgoing_message_in_chat: outgoing.length > 0,
        sender_not_in_contacts: senderNotInContacts,
        distinct_posters_in_window: senders.size,
        group_member_count: memberCount,
        poster_to_member_ratio: posterRatio,
        skewed_poster_ratio: skewedPosterRatio,
        group_name: ch.title || null,
        group_name_match: name,
        forwarded_many_times: forwardedMany,
        business_account_present: anyBusiness,
        reply_latency: latency,
        escalation_ladder: ladder,
        duplicate_templates: dupes,
        off_platform_move: offPlatform,
      },
      // DELIVERABLE 8 - the object T3 consumes in securities_identity.py.
      // Field names match that engine's expectations exactly.
      disclosure_channel_context: {
        unsolicited_add: unsolicitedAdd,
        sender_in_contacts: !senderNotInContacts,
        is_business_account: anyBusiness,
        group_name: ch.title || null,
        group_member_count: memberCount,
        distinct_posters_in_window: senders.size,
        prior_outgoing_message_in_chat: outgoing.length > 0,
        prior_in_scope_in_thread: !!o.priorInScopeInThread,
      },
    };
  }

  return {
    assess: assess,
    funnelName: funnelName,
    replyLatencyUniformity: replyLatencyUniformity,
    escalationLadder: escalationLadder,
    duplicateTemplates: duplicateTemplates,
  };
});
