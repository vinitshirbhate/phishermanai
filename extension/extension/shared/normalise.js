/*
 * extension/shared/normalise.js - THE single definition of text normalisation.
 *
 * Zero-width stripping and homoglyph folding are needed in at least three
 * places: pre-flight URL comparison (preflight/url_parse.js), WhatsApp message
 * matching, and any future page-text lane. Defining them once is the same
 * single-source-of-truth rule that governs ml/features.py - a second normaliser
 * is how two layers silently disagree about whether "аpple" is "apple".
 *
 * NOTE ON SCOPE: this module normalises for COMPARISON only. It never mutates
 * anything the user sees. The original string is always carried alongside, and
 * the fact that obfuscation was present is itself a signal (see detect()).
 *
 * Loads in Node and in the MV3 service worker. No chrome.* APIs.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanNormalise = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Zero-width and bidi-control characters. These are invisible: they exist in a
  // hostname or a message purely to break string comparison.
  //   200B ZWSP - 200C ZWNJ - 200D ZWJ - 200E/200F LRM/RLM - 2060 word joiner
  //   FEFF BOM - 00AD soft hyphen - 202A-202E bidi overrides
  const ZERO_WIDTH_RE = /[​-‏‪-‮⁠-⁤﻿­]/g;

  // Homoglyph folding table: confusable -> ASCII. Only characters that are
  // VISUALLY IDENTICAL (or near enough at UI sizes) in common fonts are folded.
  // Folding merely-similar characters would create false lookalike matches.
  const HOMOGLYPHS = {
    // Cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "і": "i", "ј": "j", "һ": "h",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C",
    "Х": "X", "У": "Y", "М": "M", "Н": "H", "К": "K",
    "В": "B", "Т": "T", "Ѕ": "S",
    // Greek
    "ο": "o", "α": "a", "ε": "e", "ρ": "p", "ν": "v",
    "υ": "u", "ι": "i", "κ": "k", "χ": "x",
    "Ο": "O", "Α": "A", "Ε": "E", "Ρ": "P", "Β": "B",
    "Η": "H", "Κ": "K", "Μ": "M", "Τ": "T", "Χ": "X",
    // Latin lookalikes and dotless forms
    "ı": "i", "ł": "l", "ǀ": "l",
    // Armenian / Georgian confusables seen in real campaigns
    "օ": "o", "ո": "n", "ӏ": "l",
  };

  // Fullwidth forms FF01-FF5E map linearly onto ASCII 21-7E.
  function foldFullwidth(s) {
    let out = "";
    for (const ch of s) {
      const cp = ch.codePointAt(0);
      out += (cp >= 0xFF01 && cp <= 0xFF5E) ? String.fromCharCode(cp - 0xFEE0) : ch;
    }
    return out;
  }

  /** Remove invisible characters. Always run BEFORE any comparison. */
  function stripZeroWidth(s) {
    return (s || "").replace(ZERO_WIDTH_RE, "");
  }

  /** Fold confusable scripts onto ASCII. Does not lowercase. */
  function foldHomoglyphs(s) {
    let out = "";
    for (const ch of foldFullwidth(s || "")) {
      out += Object.prototype.hasOwnProperty.call(HOMOGLYPHS, ch) ? HOMOGLYPHS[ch] : ch;
    }
    return out;
  }

  /**
   * Full comparison form: strip invisibles, fold confusables, NFKC, lowercase,
   * collapse separator runs. Use this on BOTH sides of any equality test.
   */
  function normalise(s, opts) {
    const o = opts || {};
    let t = stripZeroWidth(s || "");
    if (o.foldHomoglyphs !== false) t = foldHomoglyphs(t);
    try { t = t.normalize("NFKC"); } catch (e) { /* older runtimes: skip */ }
    t = t.toLowerCase();
    if (o.collapseSeparators !== false) t = t.replace(/[\s._\-]+/g, o.separator || "");
    return t.trim();
  }

  /**
   * Domain IDENTITY form. Strips invisibles and case, and NOTHING ELSE.
   *
   * Homoglyphs are deliberately NOT folded here. Folding them would make
   * `nsеindia.com` (Cyrillic е) normalise to `nseindia.com` and compare EQUAL to
   * the genuine NSE domain - classifying a homograph impostor as the official
   * site. That failure is worse than missing the attack: it actively vouches for
   * it. Resemblance is `foldConfusable`'s job, and the two must never be the
   * same function.
   */
  function normaliseHost(host) {
    return normalise(host, { collapseSeparators: false, foldHomoglyphs: false })
      .replace(/[․。．｡]/g, ".")   // one-dot-leader & ideographic full stops
      .replace(/\.+/g, ".")
      .replace(/^\.|\.$/g, "");
  }

  /** Drop combining marks: "sébi" -> "sebi". */
  function stripDiacritics(s) {
    try { return (s || "").normalize("NFD").replace(/[̀-ͯ]/g, ""); }
    catch (e) { return s || ""; }
  }

  /**
   * The LOOKALIKE comparison form - strictly more aggressive than normaliseHost.
   *
   * Kept separate on purpose. `normaliseHost` decides IDENTITY ("is this host
   * sebi.gov.in?") and must not fold `sébi.gov.in` onto `sebi.gov.in`, or an
   * impostor would be classified as the regulator itself. `foldConfusable`
   * decides RESEMBLANCE ("does this host look like sebi.gov.in?"). Two hosts
   * that differ under the first and agree under the second are exactly the
   * homograph-attack case.
   */
  function foldConfusable(s) {
    return stripDiacritics(foldHomoglyphs(normaliseHost(s)))
      .toLowerCase()
      .replace(/[^a-z0-9.]/g, "");
  }

  /**
   * Report obfuscation as EVIDENCE, not just clean it away.
   * A hostname containing a zero-width space is not an accident.
   */
  function detect(s) {
    const raw = s || "";
    const zw = raw.match(ZERO_WIDTH_RE) || [];
    const glyphs = [];
    for (const ch of foldFullwidth(raw)) {
      if (Object.prototype.hasOwnProperty.call(HOMOGLYPHS, ch)) glyphs.push(ch);
    }
    const fullwidth = /[！-～]/.test(raw);
    return {
      has_zero_width: zw.length > 0,
      zero_width_count: zw.length,
      zero_width_codepoints: zw.map((c) => "U+" + c.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")),
      has_homoglyphs: glyphs.length > 0,
      homoglyphs: glyphs,
      has_fullwidth: fullwidth,
      // Mixed-script is the general case the explicit table cannot cover.
      mixed_script: /[a-z]/i.test(raw) && /[Ѐ-ӿͰ-Ͽ԰-֏]/.test(raw),
      obfuscated: zw.length > 0 || glyphs.length > 0 || fullwidth,
    };
  }

  return {
    stripZeroWidth: stripZeroWidth,
    foldHomoglyphs: foldHomoglyphs,
    foldFullwidth: foldFullwidth,
    normalise: normalise,
    normaliseHost: normaliseHost,
    stripDiacritics: stripDiacritics,
    foldConfusable: foldConfusable,
    detect: detect,
    ZERO_WIDTH_RE: ZERO_WIDTH_RE,
  };
});
