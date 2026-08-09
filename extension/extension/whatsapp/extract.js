/*
 * extension/whatsapp/extract.js - DOM row -> MessageRecord.
 *
 * Split deliberately into two halves:
 *   PURE      parsePrePlainText, extractEntities, normaliseBody, classify -
 *             no DOM, unit-testable, and the half that carries the logic.
 *   DOM READ  fromRow() - reads a row through the selector registry.
 *
 * THE ONE RULE THAT OVERRIDES EVERY OTHER: this module never opens, expands,
 * downloads or clicks anything. It reads what is already rendered. View-once
 * media is flagged and left alone - opening it CONSUMES it for the user, which
 * is an irreversible action taken on their behalf and a BL-1 violation. There is
 * no configuration that turns that on.
 *
 * PRIVACY: body_text is returned for scoring in-memory and is NEVER persisted.
 * The caller persists `body_sha256` and reason codes only. Disappearing and
 * view-once content sets `persist: false` and is not stored at all.
 */
(function (root, factory) {
  const api = factory(
    (typeof require !== "undefined") ? require("./selectors.js") : root.PhishermanWaSelectors,
    (typeof require !== "undefined") ? require("../shared/normalise.js") : root.PhishermanNormalise,
    (typeof require !== "undefined") ? require("../shared/apk_check.js") : root.PhishermanApkCheck
  );
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanWaExtract = api;
})(typeof self !== "undefined" ? self : this, function (SEL, N, APK) {
  "use strict";

  const MAX_BODY_FOR_LLM = 4096;         // truncate for the LLM; regex sees it all

  // Devanagari, Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi.
  const INDIC_RE = /[ऀ-ॿঀ-৿஀-௿ఀ-౿ಀ-೿ഀ-ൿ઀-૿਀-੿]/;

  const URL_RE = /\b(?:https?:\/\/|www\.)[^\s<>"']+/gi;
  const UPI_RE = /\b([a-z0-9.\-_]{2,}@[a-z][a-z0-9.]{1,})\b/gi;
  const UPI_DEEPLINK_RE = /\bupi:\/\/pay\?[^\s<>"']+/gi;
  const APK_RE = /\b(?:https?:\/\/)?[^\s<>"']+\.apk\b/gi;
  const PHONE_RE = /(?:\+91[\s-]?|\b0)?[6-9]\d{9}\b/g;
  const IFSC_RE = /\b[A-Z]{4}0[A-Z0-9]{6}\b/g;
  // Amounts: Rs 45,000 / ₹45000 / 45k / 2 lakh / 1.5 crore.
  // Two alternatives with DIFFERENT digit rules, deliberately:
  //   1. currency-prefixed - any digit count, the ₹/Rs/INR marker disambiguates.
  //   2. bare number + REQUIRED unit word - also any digit count, because "2
  //      lakh" is the ordinary Indian phrasing and a 4-digit floor would drop
  //      every lakh/crore figure below 1000, i.e. most of them. The mandatory
  //      unit is what stops this matching "Class 7B" or "row 12".
  const AMOUNT_RE = /(?:₹|\brs\.?\s*|\binr\s*)\s?([\d,]+(?:\.\d+)?)\s*(k|lakh|lakhs|lac|crore|cr)?\b|\b([\d,]+(?:\.\d+)?)\s*(k|lakh|lakhs|lac|crore|cr)\b/gi;
  // Registration-shaped tokens. Scope evidence only - resolution happens in
  // securities_check.js against the real register.
  const REG_RE = /\b(?:IN[A-Z]{1,6}\d{4,10}|ARN[-\s]?\d{4,8}|IN-DP-[A-Z]+-\d{2,}-\d{4})\b/gi;

  const MEDIA_KINDS = ["image", "video", "audio", "ptt", "document", "sticker",
                       "contact", "location", "poll", "gif"];

  // ---------------------------------------------------------------- PURE ----
  /**
   * "[14:32, 07/08/2026] Ramesh Kumar: " -> {time, date, sender, iso}
   * Also accepts "[7/8/2026, 14:32]" ordering, which some locales emit.
   * Returns null when the string does not parse - never a guessed value.
   */
  function parsePrePlainText(value) {
    if (!value) return null;
    const m = /^\s*\[([^\]]+)\]\s*([\s\S]*?):\s*$/.exec(value);
    if (!m) return null;
    const inner = m[1].trim();
    const sender = m[2].trim();

    const timeM = /(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?/i.exec(inner);
    const dateM = /(\d{1,4})[\/.-](\d{1,2})[\/.-](\d{2,4})/.exec(inner);
    let iso = null;
    if (dateM) {
      let a = Number(dateM[1]), b = Number(dateM[2]), c = Number(dateM[3]);
      let day, month, year;
      if (dateM[1].length === 4) { year = a; month = b; day = c; }      // YYYY-MM-DD
      else { day = a; month = b; year = c < 100 ? 2000 + c : c; }       // DD/MM/YYYY
      // Day/month ambiguity is real. WhatsApp uses the locale order; when the
      // first field cannot be a day we swap rather than silently mis-date.
      if (day > 31 && month <= 31) { const t = day; day = month; month = t; }
      let hh = 0, mm = 0;
      if (timeM) {
        hh = Number(timeM[1]); mm = Number(timeM[2]);
        const ap = (timeM[4] || "").toLowerCase();
        if (ap === "pm" && hh < 12) hh += 12;
        if (ap === "am" && hh === 12) hh = 0;
      }
      if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
        iso = year + "-" + String(month).padStart(2, "0") + "-" + String(day).padStart(2, "0")
            + "T" + String(hh).padStart(2, "0") + ":" + String(mm).padStart(2, "0") + ":00";
      }
    }
    return { sender: sender || null, time: timeM ? timeM[0] : null,
             date: dateM ? dateM[0] : null, iso: iso, raw: value };
  }

  /** A display name that is only digits/punctuation is an unsaved number. */
  function senderIsPhoneNumber(name) {
    if (!name) return false;
    return /^[+\d][\d\s\-()]{6,}$/.test(String(name).trim());
  }

  function _amountToNumber(raw, unit) {
    let n = Number(String(raw).replace(/,/g, ""));
    if (!isFinite(n)) return null;
    const u = (unit || "").toLowerCase();
    if (u === "k") n *= 1e3;
    else if (u === "lakh" || u === "lakhs" || u === "lac") n *= 1e5;
    else if (u === "crore" || u === "cr") n *= 1e7;
    return n;
  }

  /**
   * Entities from body text. Matching runs on the NORMALISED string (zero-width
   * stripped, homoglyphs folded) so obfuscation cannot hide a UPI id - and the
   * obfuscation is itself returned as a signal rather than silently cleaned.
   */
  function extractEntities(bodyText) {
    const raw = bodyText || "";
    const obf = N.detect(raw);
    const norm = N.stripZeroWidth(raw);          // fold-free: keeps ids intact
    const folded = N.foldHomoglyphs(norm);       // for pattern matching

    const uniq = (arr) => Array.from(new Set(arr.filter(Boolean)));
    const urls = uniq((folded.match(URL_RE) || []).map((u) => u.replace(/[.,;)]+$/, "")));
    const apk = uniq(folded.match(APK_RE) || []);
    const upiDeep = uniq(folded.match(UPI_DEEPLINK_RE) || []);
    // A UPI id looks like an email; exclude anything that is part of a URL.
    const upi = uniq((folded.match(UPI_RE) || [])
      .filter((v) => !urls.some((u) => u.indexOf(v) !== -1))
      .map((v) => v.toLowerCase()));
    const regs = uniq((folded.match(REG_RE) || []).map((v) => v.toUpperCase().replace(/\s/g, "")));
    const phones = uniq(folded.match(PHONE_RE) || []);
    const ifsc = uniq(folded.match(IFSC_RE) || []);

    const amounts = [];
    let m;
    AMOUNT_RE.lastIndex = 0;
    while ((m = AMOUNT_RE.exec(folded)) !== null) {
      const val = _amountToNumber(m[1] || m[3], m[2] || m[4]);
      if (val !== null) amounts.push({ raw: m[0].trim(), value: val });
    }

    return {
      urls: urls, upi_ids: upi, upi_deeplinks: upiDeep, reg_numbers: regs,
      phones: phones, ifsc: ifsc, amounts: amounts, apk_links: apk,
      // Obfuscation is EVIDENCE, not noise to be scrubbed.
      obfuscation: obf.obfuscated ? obf : null,
      script: INDIC_RE.test(raw) ? "indic_or_mixed" : "latin",
    };
  }

  /** FNV-1a — enough to dedupe near-identical templates. Never reversible to text. */
  function bodyHash(text) {
    const s = N.normalise(text || "", { collapseSeparators: true });
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return ("00000000" + h.toString(16)).slice(-8);
  }

  // ------------------------------------------------------------- DOM READ ----
  function _attr(node, name) {
    return (node && node.getAttribute) ? node.getAttribute(name) : null;
  }

  function _textOf(node) {
    return node && node.textContent ? node.textContent : "";
  }

  /**
   * fromRow(row, ctx) -> MessageRecord
   *
   * `ctx` supplies chat_id and the tier-resolved helpers. Returns a record even
   * for rows it cannot fully read - a partial record with explicit flags beats a
   * dropped message, because a dropped message is invisible.
   */
  function fromRow(row, ctx) {
    const c = ctx || {};
    const dataId = _attr(row, "data-id") || null;
    const metaNode = row.querySelector ? row.querySelector("[data-pre-plain-text]") : null;
    const pre = metaNode ? parsePrePlainText(_attr(metaNode, "data-pre-plain-text")) : null;

    // --- direction -------------------------------------------------------
    // data-id is "true_..." for messages the user sent. Outgoing messages are
    // NEVER scored for risk (see verdict.js); they feed the escalation ladder
    // and the "no prior outgoing" unsolicited-add check only.
    let direction = "unknown";
    if (dataId && /^true_/.test(dataId)) direction = "outgoing";
    else if (dataId && /^false_/.test(dataId)) direction = "incoming";
    else if (c.outgoingSet && dataId && c.outgoingSet.has(dataId)) direction = "outgoing";
    else if (pre) direction = "incoming";

    // --- system row ------------------------------------------------------
    const isSystem = !metaNode && SEL.SYSTEM_PHRASES.some(
      (p) => _textOf(row).trim().toLowerCase().indexOf(p) !== -1);

    // --- media, WITHOUT opening anything ---------------------------------
    let mediaKind = null, hasMedia = false, viewOnce = false;
    if (row.querySelector) {
      for (const k of MEDIA_KINDS) {
        if (row.querySelector('[data-icon*="' + k + '"], [data-testid*="' + k + '"]')) {
          mediaKind = k; hasMedia = true; break;
        }
      }
      if (row.querySelector("img, video, canvas")) hasMedia = true;
      // View-once: detected by marker only. We never click, expand or fetch it.
      viewOnce = !!row.querySelector(
        '[data-icon*="view-once"], [data-testid*="view-once"], [aria-label*="iew once"]');
    }

    // --- document attachment ---------------------------------------------
    // A file bubble carries no URL and no `.apk` token in any message text, so
    // APK_RE over the body could never see it. The filename lives on the
    // attachment node and has to be read from there. Nothing is opened,
    // downloaded or fetched - this is the visible label, exactly as rendered.
    const attachment = APK.readAttachmentFrom(row, {
      source: "chat",
      assumeDocument: mediaKind === "document",
    });

    // --- flags -----------------------------------------------------------
    const rowText = _textOf(row);
    const lowText = rowText.trim().toLowerCase();
    const isForwarded = !!(row.querySelector && (
      row.querySelector('[data-icon="forward"]')
      || SEL.FORWARDED_LABELS.some((l) => lowText.indexOf(l) !== -1)));
    const manyTimes = /many times|कई बार|अनेक वेळा/.test(lowText);
    const isDeleted = /this message was deleted|you deleted this message|यह संदेश हटा/.test(lowText);
    const isEdited = /<this message was edited>|\bedited\b|संपादित/.test(lowText);
    const isReply = !!(row.querySelector && row.querySelector('[data-testid="quoted-message"], blockquote'));

    // --- body ------------------------------------------------------------
    // For a reply, exclude the quoted block: the quoted text belongs to the
    // ORIGINAL message and scoring it here would double-count it.
    let body = "";
    if (metaNode) {
      const clone = metaNode.cloneNode ? metaNode.cloneNode(true) : metaNode;
      if (clone.querySelectorAll) {
        for (const q of clone.querySelectorAll('[data-testid="quoted-message"], blockquote')) {
          if (q.parentNode) q.parentNode.removeChild(q);
        }
      }
      body = _textOf(clone).trim();
    } else if (!isSystem) {
      body = rowText.trim();
    }

    // Media whose only text is inside the image: report it, do not stay silent.
    const textInImageUnscanned = hasMedia && !body
      && (mediaKind === "image" || mediaKind === "sticker" || mediaKind === "video");

    const entities = extractEntities(body);
    const senderName = pre ? pre.sender : null;

    return {
      message_id: dataId || (pre && pre.raw ? "pre:" + bodyHash(pre.raw) : null),
      chat_id: c.chatId || null,
      direction: direction,
      timestamp: pre ? pre.iso : null,
      timestamp_raw: pre ? (pre.date || "") + " " + (pre.time || "") : null,
      sender: {
        display_name: senderName,
        // Only a HINT. We never resolve or store a full number.
        phone_hint: senderIsPhoneNumber(senderName)
          ? String(senderName).replace(/\d(?=\d{4})/g, "•") : null,
        is_contact: senderName ? !senderIsPhoneNumber(senderName) : null,
        is_business: !!(row.querySelector && row.querySelector('[data-icon*="business"], [aria-label*="usiness account"]')),
        is_admin: !!(row.querySelector && row.querySelector('[data-testid*="admin"], [aria-label*="dmin"]')),
      },
      body_text: body,                       // in-memory only, never persisted
      body_sha256: body ? bodyHash(body) : null,
      body_truncated_for_llm: body.length > MAX_BODY_FOR_LLM
        ? body.slice(0, MAX_BODY_FOR_LLM) : body,
      body_was_truncated: body.length > MAX_BODY_FOR_LLM,
      entities: entities,
      // Filename-only reading of a file bubble. The package is never opened,
      // downloaded or hashed - see shared/apk_check.js for what may be claimed.
      attachment: attachment,
      apk: attachment ? APK.inspect(attachment) : null,
      flags: {
        is_forwarded: isForwarded,
        forwarded_many_times: manyTimes,
        is_system: isSystem,
        has_media: hasMedia,
        media_kind: mediaKind,
        is_reply: isReply,
        is_deleted: isDeleted,
        is_edited: isEdited,
        // Flagged, never opened. Opening consumes it for the user (BL-1).
        view_once_unscannable: viewOnce,
        text_in_image_unscanned: textInImageUnscanned,
        obfuscation_detected: !!entities.obfuscation,
      },
      // Disappearing and view-once content is never written to disk at all.
      persist: !(viewOnce || c.disappearing === true),
      partial: !pre && !isSystem,            // read, but without sender/timestamp
      registry_version: SEL.REGISTRY_VERSION,
    };
  }

  return {
    parsePrePlainText: parsePrePlainText,
    senderIsPhoneNumber: senderIsPhoneNumber,
    extractEntities: extractEntities,
    bodyHash: bodyHash,
    fromRow: fromRow,
    MAX_BODY_FOR_LLM: MAX_BODY_FOR_LLM,
  };
});
