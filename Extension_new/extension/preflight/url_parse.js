/*
 * extension/preflight/url_parse.js - Layer 0 of pre-flight. PURE, ~1 ms, offline.
 *
 * Parses with `new URL()`, never with a regex. This is not a style preference:
 * every classic URL trick below (userinfo, backslash paths, encoded hosts) works
 * precisely because hand-written regexes disagree with the browser's own parser
 * about where the host ends. If we parse differently from the navigator, we
 * report on a URL the user is not actually visiting.
 *
 * Comparison is done on the NORMALISED form from extension/shared/normalise.js -
 * the single normaliser - and the obfuscation itself is reported as evidence
 * rather than quietly cleaned away.
 *
 * PURE MODULE: no chrome.* APIs, no network, no DOM. Loads under Node and in the
 * service worker. All browser interaction lives in adapter_mv3.js.
 */
(function (root, factory) {
  const api = factory(
    (typeof require !== "undefined") ? require("../shared/normalise.js") : root.PhishermanNormalise,
    (typeof require !== "undefined") ? require("./psl.js") : root.PhishermanPSL
  );
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanUrlParse = api;
})(typeof self !== "undefined" ? self : this, function (N, PSL) {
  "use strict";

  const SAFE_SCHEMES = ["http:", "https:"];
  const DANGEROUS_SCHEMES = ["data:", "javascript:", "blob:", "file:", "vbscript:"];

  // Payment deep links. A `upi:` href is a PAYMENT INSTRUCTION wearing the
  // costume of a hyperlink - the user taps what looks like a link and their
  // payment app opens pre-filled. Primary vector; never treated as "not a URL".
  const PAYMENT_SCHEMES = ["upi:", "tez:", "phonepe:", "paytmmp:", "bharatpe:", "gpay:"];

  const SHORTENERS = new Set([
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "rebrand.ly", "cutt.ly", "shorturl.at", "rb.gy", "tiny.cc", "bl.ink",
    "t.ly", "short.io", "s.id", "linktr.ee", "wa.me", "chat.whatsapp.com",
    "surl.li", "clck.ru", "vk.cc", "shrtco.de", "qrco.de", "bitly.com",
  ]);

  // Query parameters whose presence means the URL identifies a PERSON. Fetching
  // one tells the operator the message reached a live human, and can burn a
  // one-time token. See skip_prefetch below.
  const TRACKING_PARAMS = new Set([
    "token", "t", "id", "key", "u", "unsub", "uid", "sid", "auth", "session",
    "code", "otp", "ref", "rcpt", "recipient", "email", "e", "confirm", "verify",
  ]);

  const IPV4_RE = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
  const DECIMAL_HOST_RE = /^\d{6,10}$/;              // 2130706433 -> 127.0.0.1
  const OCTAL_HOST_RE = /^0\d+(\.0\d+){0,3}$/;       // 0177.0.0.1
  const HEX_HOST_RE = /^0x[0-9a-f]+(\.0x[0-9a-f]+){0,3}$/i;

  function _entropy(s) {
    if (!s) return 0;
    const counts = {};
    for (const ch of s) counts[ch] = (counts[ch] || 0) + 1;
    let h = 0;
    for (const k in counts) { const p = counts[k] / s.length; h -= p * Math.log2(p); }
    return h;
  }

  function _isPrivateIPv4(host) {
    const m = IPV4_RE.exec(host);
    if (!m) return false;
    const o = m.slice(1).map(Number);
    if (o.some((x) => x > 255)) return false;
    return o[0] === 127 || o[0] === 10 || o[0] === 0
      || (o[0] === 192 && o[1] === 168)
      || (o[0] === 172 && o[1] >= 16 && o[1] <= 31)
      || (o[0] === 169 && o[1] === 254);
  }

  /** Decode the non-dotted IP encodings browsers still accept. */
  function _decodeNumericHost(host) {
    if (IPV4_RE.test(host)) return { form: "ipv4", ip: host };
    if (DECIMAL_HOST_RE.test(host)) {
      const n = Number(host);
      if (n <= 4294967295) {
        return { form: "decimal",
                 ip: [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join(".") };
      }
    }
    if (OCTAL_HOST_RE.test(host)) {
      const parts = host.split(".").map((p) => parseInt(p, 8));
      if (parts.every((p) => !isNaN(p) && p <= 255)) return { form: "octal", ip: parts.join(".") };
    }
    if (HEX_HOST_RE.test(host)) {
      const parts = host.split(".").map((p) => parseInt(p, 16));
      if (parts.length === 1 && parts[0] <= 4294967295) {
        const n = parts[0];
        return { form: "hex",
                 ip: [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join(".") };
      }
      if (parts.every((p) => !isNaN(p) && p <= 255)) return { form: "hex", ip: parts.join(".") };
    }
    return null;
  }

  /** Decode xn-- labels to their Unicode form so they can be compared as read. */
  function _decodePunycode(host) {
    if (!/(^|\.)xn--/i.test(host)) return { decoded: host, is_punycode: false };
    // URL.prototype.hostname gives us the ASCII form; Node/browsers expose the
    // Unicode form through the URL parser when we round-trip a punycode host.
    let decoded = host;
    try {
      // `new URL` keeps punycode, so decode label-wise via toUnicode when present.
      if (typeof globalThis !== "undefined" && globalThis.URL) {
        decoded = host.split(".").map((label) => {
          if (!/^xn--/i.test(label)) return label;
          try { return _punyDecode(label.slice(4)); } catch (e) { return label; }
        }).join(".");
      }
    } catch (e) { /* keep ASCII form */ }
    return { decoded: decoded, is_punycode: true };
  }

  // Minimal RFC 3492 decoder - stdlib `punycode` is deprecated in Node and
  // unavailable in the service worker, so the ~30 lines live here.
  function _punyDecode(input) {
    const base = 36, tMin = 1, tMax = 26, skew = 38, damp = 700, initialBias = 72, initialN = 128;
    let n = initialN, i = 0, bias = initialBias;
    const output = [];
    let basic = input.lastIndexOf("-");
    if (basic < 0) basic = 0;
    for (let j = 0; j < basic; j++) output.push(input.charCodeAt(j));
    for (let index = basic > 0 ? basic + 1 : 0; index < input.length;) {
      const oldi = i;
      for (let w = 1, k = base; ; k += base) {
        const c = input.charCodeAt(index++);
        let digit;
        if (c - 48 < 10) digit = c - 22;
        else if (c - 65 < 26) digit = c - 65;
        else if (c - 97 < 26) digit = c - 97;
        else throw new Error("bad punycode");
        i += digit * w;
        const t = k <= bias ? tMin : (k >= bias + tMax ? tMax : k - bias);
        if (digit < t) break;
        w *= base - t;
      }
      const out = output.length + 1;
      let delta = i - oldi;
      delta = oldi === 0 ? Math.floor(delta / damp) : delta >> 1;
      delta += Math.floor(delta / out);
      let k = 0;
      for (; delta > ((base - tMin) * tMax) >> 1; k += base) delta = Math.floor(delta / (base - tMin));
      bias = Math.floor(k + ((base - tMin + 1) * delta) / (delta + skew));
      n += Math.floor(i / out);
      i %= out;
      output.splice(i++, 0, n);
    }
    return String.fromCodePoint.apply(String, output);
  }

  /**
   * parse(rawUrl, opts)
   *   opts.anchorText     visible link text, for the mismatch check
   *   opts.pageHost       host of the page the link sits on (same-origin test)
   *   opts.officialDomains [{domain, entity, entity_type}] for lookalike checks
   */
  function parse(rawUrl, opts) {
    const o = opts || {};
    const raw = String(rawUrl == null ? "" : rawUrl);
    const signals = [];
    const out = {
      raw: raw,
      valid: false,
      scheme: null,
      scheme_safe: false,
      scheme_dangerous: false,
      is_payment_link: false,
      payment: null,
      host: "",
      host_normalised: "",
      host_decoded: "",
      registrable_domain: "",
      public_suffix: "",
      subdomains: [],
      psl_matched: false,
      path: "",
      query: "",
      userinfo_present: false,
      userinfo_looks_like_host: false,
      is_ip_host: false,
      ip_form: null,
      ip_address: null,
      is_private_target: false,
      is_punycode: false,
      obfuscation: null,
      homoglyph_target: null,
      subdomain_stuffing: null,
      anchor_mismatch: null,
      is_shortener: false,
      expansion_required: false,
      single_use_token: null,
      skip_prefetch: false,
      same_origin_as_page: false,
      signals: signals,
      layer: "preflight.url_parse",
    };

    if (!raw.trim()) { signals.push("empty_url"); return out; }

    // --- scheme -------------------------------------------------------------
    let u;
    try { u = new URL(raw); } catch (e) { /* handled below */ }
    if (!u) {
      // Relative or malformed. Try to resolve against the page for a real answer.
      if (o.pageUrl) { try { u = new URL(raw, o.pageUrl); } catch (e2) { /* ignore */ } }
      if (!u) { signals.push("unparseable_url"); return out; }
    }
    out.valid = true;
    out.scheme = u.protocol;
    out.scheme_safe = SAFE_SCHEMES.indexOf(u.protocol) !== -1;
    out.scheme_dangerous = DANGEROUS_SCHEMES.indexOf(u.protocol) !== -1;
    if (out.scheme_dangerous) signals.push("dangerous_scheme:" + u.protocol.replace(":", ""));

    // --- upi: and friends - a payment instruction, not a page ----------------
    if (PAYMENT_SCHEMES.indexOf(u.protocol) !== -1) {
      out.is_payment_link = true;
      // upi://pay?pa=x@bank&am=500 and upi:pay?... both occur in the wild.
      const qs = raw.slice(raw.indexOf("?") + 1);
      const params = new URLSearchParams(raw.indexOf("?") === -1 ? "" : qs);
      out.payment = {
        scheme: u.protocol.replace(":", ""),
        payee_vpa: params.get("pa") || null,      // pa = payee address (the UPI id)
        payee_name: params.get("pn") || null,
        amount: params.get("am") || null,
        currency: params.get("cu") || null,
        note: params.get("tn") || null,
        // A pre-filled amount removes the user's last decision point.
        amount_prefilled: !!params.get("am"),
      };
      signals.push("payment_deep_link");
      if (out.payment.payee_vpa) signals.push("payment_payee:" + out.payment.payee_vpa);
      if (out.payment.amount_prefilled) signals.push("payment_amount_prefilled");
      out.skip_prefetch = true;             // never fetch a payment intent
      return out;                            // no host semantics to compute
    }

    // --- userinfo trick -----------------------------------------------------
    // https://icicidirect.com@evil.tld/ - everything before @ is a credential,
    // not a host. The user reads the brand; the browser goes to evil.tld.
    if (u.username || u.password) {
      out.userinfo_present = true;
      const ui = decodeURIComponent(u.username || "");
      // Only alarming when the userinfo is SHAPED like a hostname or brand.
      if (/\.[a-z]{2,}$/i.test(ui) || (o.officialDomains || []).some(
            (d) => N.normaliseHost(ui).indexOf(N.normaliseHost(d.domain)) !== -1)) {
        out.userinfo_looks_like_host = true;
        signals.push("userinfo_trick:" + ui);
      } else {
        signals.push("userinfo_present");
      }
    }

    // --- host ---------------------------------------------------------------
    const hostRaw = u.hostname || "";
    out.host = hostRaw;
    out.obfuscation = N.detect(hostRaw);
    if (out.obfuscation.obfuscated) {
      signals.push("host_obfuscation");
      if (out.obfuscation.has_zero_width) signals.push("zero_width_in_host");
    }

    const puny = _decodePunycode(hostRaw);
    out.is_punycode = puny.is_punycode;
    out.host_decoded = puny.decoded;
    if (puny.is_punycode) signals.push("punycode_host");
    // Normalise the DECODED form: xn--pple-43d decodes to "аpple" (Cyrillic а),
    // which only folds to "apple" after decoding. Comparing the ASCII punycode
    // form would miss it entirely.
    out.host_normalised = N.normaliseHost(puny.decoded);

    const numeric = _decodeNumericHost(hostRaw.replace(/^\[|\]$/g, ""));
    if (numeric) {
      out.is_ip_host = true;
      out.ip_form = numeric.form;
      out.ip_address = numeric.ip;
      signals.push("ip_literal_host:" + numeric.form);
      if (numeric.form !== "ipv4") signals.push("obfuscated_ip_encoding");
      out.is_private_target = _isPrivateIPv4(numeric.ip);
    } else if (/^\[?[0-9a-f:]+\]?$/i.test(hostRaw) && hostRaw.indexOf(":") !== -1) {
      out.is_ip_host = true;
      out.ip_form = "ipv6";
      out.ip_address = hostRaw.replace(/^\[|\]$/g, "");
      signals.push("ip_literal_host:ipv6");
      out.is_private_target = /^(::1|fe80:|fc|fd)/i.test(out.ip_address);
    }

    if (/^(localhost|.*\.local|.*\.internal|.*\.localhost)$/i.test(hostRaw)) {
      out.is_private_target = true;
    }
    if (out.is_private_target) {
      signals.push("private_or_loopback_target");
      out.skip_prefetch = true;             // never pre-fetch inside the network
    }

    // --- eTLD+1 via the PSL, not a dot split --------------------------------
    if (!out.is_ip_host) {
      const rd = PSL.registrableDomain(out.host_normalised);
      out.registrable_domain = rd.domain;
      out.public_suffix = rd.suffix;
      out.subdomains = rd.subdomains;
      out.psl_matched = rd.matched;
      if (!rd.matched) signals.push("unknown_public_suffix");
    }

    out.path = u.pathname || "";
    out.query = u.search || "";

    // --- official-domain comparison: exact, lookalike, or unknown -----------
    const officials = o.officialDomains || [];
    if (!out.is_ip_host && officials.length) {
      const normHost = out.host_normalised;
      const normReg = out.registrable_domain;
      let exact = null, look = null, stuffed = null;
      for (const d of officials) {
        const od = N.normaliseHost(d.domain);
        const odReg = PSL.registrableDomain(od).domain || od;
        if (normHost === od || normReg === odReg) { exact = d; break; }
        // Subdomain stuffing: sebi.gov.in.secure-verify.xyz - the brand appears
        // in the LABELS but the registrable domain belongs to someone else.
        if (normHost.indexOf(od + ".") === 0 || normHost.indexOf("." + od + ".") !== -1) {
          stuffed = { official: d.domain, entity: d.entity, observed_host: out.host };
          continue;
        }
        // Homoglyph / punycode lookalike: differs before folding, matches after.
        // foldConfusable is deliberately more aggressive than normaliseHost -
        // see the note in shared/normalise.js on identity vs resemblance.
        const foldedHost = N.foldConfusable(normReg);
        const foldedOfficial = N.foldConfusable(odReg);
        if (foldedHost === foldedOfficial && normReg !== odReg) {
          look = { official: d.domain, entity: d.entity, observed: out.host,
                   decoded: out.host_decoded, reason: "homoglyph_or_punycode" };
          continue;
        }
        // Brand token inside a different registrable domain, e.g. sebi-verify.xyz
        const brand = odReg.split(".")[0];
        if (brand.length >= 4 && normReg !== odReg
            && normReg.replace(/[^a-z0-9]/g, "").indexOf(brand) !== -1) {
          look = { official: d.domain, entity: d.entity, observed: out.host,
                   decoded: out.host_decoded, reason: "brand_token_in_other_domain" };
        }
      }
      if (exact) {
        out.official_match = { domain: exact.domain, entity: exact.entity,
                               entity_type: exact.entity_type };
        signals.push("official_domain:" + exact.domain);
      } else if (stuffed) {
        out.subdomain_stuffing = stuffed;
        signals.push("subdomain_stuffing:" + stuffed.official);
      } else if (look) {
        out.homoglyph_target = look;
        signals.push("lookalike_of:" + look.official);
      }
      // NOTE: no signal is emitted when the domain matches nothing. Most of the
      // web is not a registered intermediary; "unknown" is not evidence.
    }

    // --- anchor text vs href ------------------------------------------------
    if (o.anchorText) {
      const at = String(o.anchorText).trim();
      // Only meaningful when the anchor text is itself URL- or domain-shaped.
      const looksLikeUrl = /^(https?:\/\/)?[a-z0-9¡-￿.-]+\.[a-z¡-￿]{2,}(\/|$)/i.test(at);
      if (looksLikeUrl) {
        let claimed = at.replace(/^https?:\/\//i, "").split("/")[0];
        claimed = N.normaliseHost(claimed);
        const claimedReg = PSL.registrableDomain(claimed).domain || claimed;
        const actualReg = out.registrable_domain || out.host_normalised;
        if (claimedReg && actualReg && claimedReg !== actualReg) {
          out.anchor_mismatch = { claimed: at, claimed_domain: claimedReg,
                                  actual_domain: actualReg };
          signals.push("anchor_text_mismatch");
        }
      }
    }

    // --- shorteners ---------------------------------------------------------
    if (SHORTENERS.has(out.registrable_domain) || SHORTENERS.has(out.host_normalised)) {
      out.is_shortener = true;
      out.expansion_required = true;
      signals.push("known_shortener:" + out.host_normalised);
    }

    // --- single-use / identifying tokens ------------------------------------
    const params = new URLSearchParams(out.query);
    const namedToken = [];
    for (const [k] of params) if (TRACKING_PARAMS.has(k.toLowerCase())) namedToken.push(k);
    let highEntropy = null;
    const candidates = out.path.split("/").filter(Boolean);
    for (const [, v] of params) candidates.push(v);
    for (const c of candidates) {
      if (c.length >= 16 && /^[A-Za-z0-9_\-.=]+$/.test(c) && _entropy(c) >= 3.2) {
        highEntropy = c;
        break;
      }
    }
    if (namedToken.length || highEntropy) {
      out.single_use_token = { named_params: namedToken, high_entropy_token: highEntropy };
      out.skip_prefetch = true;
      signals.push("single_use_token");
    }

    // --- same-origin (never interstitial an internal link) -------------------
    if (o.pageHost) {
      out.same_origin_as_page =
        N.normaliseHost(o.pageHost) === out.host_normalised
        || PSL.sameSite(N.normaliseHost(o.pageHost), out.host_normalised);
    }

    return out;
  }

  return { parse: parse, SHORTENERS: SHORTENERS, PAYMENT_SCHEMES: PAYMENT_SCHEMES };
});
