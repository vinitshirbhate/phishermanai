/*
 * Read an Android package offer from its filename.
 *
 * `.apk` was matched only in link text and message bodies, so a document
 * ATTACHMENT - which carries neither - was invisible. The filename is the
 * evidence and has to be read off the attachment node.
 *
 * Financial brands score higher than entertainment ones: a sideloaded
 * "Zerodha Pro" or "Groww Premium" build is the fake-broker vector, the
 * app-shaped equivalent of the impostor domains preflight already resolves.
 *
 * Reports observable facts only - file type, delivery channel, what the
 * filename claims. Nothing here opens or inspects the package, so nothing here
 * calls it malware.
 *
 * Pure and Node-loadable. readAttachmentFrom() takes a DOM node as an argument
 * rather than reaching for `document`, so it runs under jsdom in tests.
 */
"use strict";

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.PhishermanApkCheck = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {

  const APK_EXT_RE = /\.(apk|xapk|apks|apkm|aab)(\s|$|\?)/i;

  // Claims of an unlocked paid product. These are what modded builds advertise;
  // no first-party Play Store listing uses them in a file name.
  const MOD_MARKERS = [
    { re: /\bmod(?:ded|s|\d+)?\b/i, term: "Mod" },
    { re: /\bcracked?\b/i, term: "Cracked" },
    { re: /\bpatched\b/i, term: "Patched" },
    { re: /\bpremium\b/i, term: "Premium" },
    { re: /\bpro[\s._-]*(?:unlocked|version|apk)\b/i, term: "Pro unlocked" },
    { re: /\bunlocked\b/i, term: "Unlocked" },
    { re: /\bfull[\s._-]*version\b/i, term: "Full version" },
    { re: /\bvip\b/i, term: "VIP" },
    { re: /\bplus\+|\bmega[\s._-]*mod\b/i, term: "Mega mod" },
    { re: /\bno[\s._-]*ads?\b/i, term: "No ads" },
    { re: /\bfree[\s._-]*(?:coins?|cash|money|recharge|subscription)\b/i, term: "Free currency" },
    { re: /\bunlimited[\s._-]*(?:money|coins?|gems?)\b/i, term: "Unlimited currency" },
  ];

  // Brands whose paid tiers are the usual bait for modded builds.
  const PAID_APP_BRANDS = [
    "spotify", "netflix", "youtube", "hotstar", "jiohotstar", "sonyliv", "zee5",
    "prime video", "primevideo", "amazon prime", "gaana", "wynk", "jiosaavn",
    "canva", "adobe", "photoshop", "lightroom", "picsart", "kinemaster",
    "capcut", "vpn", "nordvpn", "expressvpn", "minecraft", "pubg", "bgmi",
    "free fire", "freefire", "call of duty", "codm", "gta", "whatsapp",
    "gbwhatsapp", "instagram", "telegram", "tinder", "truecaller", "office",
    "microsoft 365",
  ];

  // Financial / securities brands. An APK carrying one of these, delivered
  // outside an app store, is the fake-broker vector and is scored highest.
  const FINANCIAL_BRANDS = [
    "zerodha", "kite", "groww", "upstox", "angel one", "angelone", "angel broking",
    "5paisa", "icici direct", "icicidirect", "hdfc securities", "hdfcsec",
    "kotak securities", "sharekhan", "motilal", "iifl", "dhan", "fyers",
    "aliceblue", "alice blue", "paytm money", "phonepe", "gpay", "google pay",
    "bhim", "sbi", "hdfc", "icici", "axis", "kotak", "paytm", "cred",
    "bajaj finserv", "mutual fund", "demat", "trading", "nse", "bse", "sebi",
    "stock", "invest", "portfolio", "ipo",
  ];

  // A file pretending to be a document but ending .apk.
  const DISGUISE_RE = /\.(pdf|doc|docx|xls|xlsx|jpg|jpeg|png|mp4|zip|txt)[\s._-]*\.(apk|xapk|apks)/i;

  function _has(list, hay) {
    for (let i = 0; i < list.length; i++) if (hay.indexOf(list[i]) !== -1) return list[i];
    return null;
  }

  /*
   * Filenames separate words with _ . - + rather than spaces, and `_` is a WORD
   * character in JS regex - so `\bunlocked\b` does not match "Pro_Unlocked" and
   * `\bmod\b` does not match "..._money_mod.apk". Every marker silently failed
   * on exactly the naming style modded builds actually use. Separators are
   * flattened to spaces before matching so \b means what it looks like it means.
   */
  function _tokens(name) {
    return String(name || "")
      .toLowerCase()
      .replace(/\.(apk|xapk|apks|apkm|aab)$/i, " ")
      .replace(/[._\-+()[\]{}]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function isAndroidPackage(filename, mime) {
    const n = String(filename || "");
    const m = String(mime || "").toLowerCase();
    return APK_EXT_RE.test(n)
      || m.indexOf("android.package-archive") !== -1
      || m === "application/vnd.android.package-archive";
  }

  /**
   * inspect({filename, mime, size_bytes, source}) -> report
   *
   * source: "chat" | "download" | "link" | "page" - the delivery channel. It is
   *         evidence in its own right: an APK arriving in a chat did not come
   *         from a store listing, whatever the filename says.
   *
   * Returns { is_apk, severity, signals[], claims[], brand, evidence } where
   * every signal carries its own polarity/severity for shared/signal_polarity.
   */
  function inspect(input) {
    const filename = String((input && input.filename) || "");
    const mime = (input && input.mime) || "";
    const source = (input && input.source) || "unknown";
    const sizeBytes = (input && input.size_bytes) || null;

    if (!isAndroidPackage(filename, mime)) {
      return { is_apk: false, severity: "none", signals: [], claims: [], brand: null, evidence: {} };
    }

    const lower = filename.toLowerCase();   // raw, for the disguised-extension test
    const words = _tokens(filename);        // separator-flattened, for \b markers
    const signals = [];
    const claims = [];

    // 1. The delivery fact. True of every APK that arrives this way, and it is
    //    the one thing we can state without reading the file.
    if (source === "chat" || source === "link" || source === "download") {
      signals.push({
        label: "Android app file received outside an app store",
        polarity: "risk",
        severity: "high",
      });
    }

    // 2. What the filename advertises.
    for (let i = 0; i < MOD_MARKERS.length; i++) {
      if (MOD_MARKERS[i].re.test(words)) claims.push(MOD_MARKERS[i].term);
    }
    if (claims.length) {
      signals.push({
        label: "Filename advertises a paid app unlocked for free (" + claims.join(", ") + ")",
        polarity: "risk",
        severity: "high",
      });
    }

    // 3. Whose app it claims to be.
    const finBrand = _has(FINANCIAL_BRANDS, words);
    const paidBrand = _has(PAID_APP_BRANDS, words);
    const brand = finBrand || paidBrand;

    if (finBrand) {
      signals.push({
        label: "Names a financial or trading brand (" + finBrand + ") but is not from its app store listing",
        polarity: "risk",
        severity: "high",
      });
    } else if (paidBrand && claims.length) {
      signals.push({
        label: "Names " + paidBrand + ", whose paid features this file claims to unlock",
        polarity: "risk",
        severity: "medium",
      });
    }

    // 4. Disguised extension.
    if (DISGUISE_RE.test(lower)) {
      signals.push({
        label: "Filename is shaped like a document but installs an app",
        polarity: "risk",
        severity: "high",
      });
    }

    // Severity. Anything that names a financial brand, advertises an unlock, or
    // hides its extension is the top band. A plain unbranded APK in a chat is
    // still worth surfacing - a developer sharing their own build looks exactly
    // like this - but it is not the same claim, so it stays a band lower.
    const severity = (finBrand || claims.length || DISGUISE_RE.test(lower))
      ? "high" : "medium";

    return {
      is_apk: true,
      severity: severity,
      signals: signals,
      claims: claims,
      brand: brand,
      evidence: {
        filename: filename,
        size_bytes: sizeBytes,
        source: source,
        mod_claims: claims,
        financial_brand: finBrand || null,
        paid_app_brand: paidBrand || null,
        disguised_extension: DISGUISE_RE.test(lower),
      },
    };
  }

  // A file bubble's visible label, e.g.
  //     "Spotify v9.1.36.1948 (Premium) Mod2.apk"   "APK - 129 MB"
  const FILE_EXT = "apk|xapk|apks|apkm|aab|pdf|docx?|xlsx?|pptx?|zip|rar|exe|msi";
  const FILENAME_RE = new RegExp("([^\\n\\r\\u2022|]+?\\.(?:" + FILE_EXT + "))\\b", "i");
  const SIZE_RE = /(\d[\d.,]*)\s*(KB|MB|GB)\b/i;

  const ATTACHMENT_NODE_SELECTOR =
    '[data-icon="document"], [data-icon*="document"], [data-testid*="document"], '
    + '[title$=".apk"], [title$=".pdf"], [aria-label*="ownload"]';

  /**
   * readAttachmentFrom(row, opts) -> {filename, size_text, source} | null
   *
   * Reads the file bubble's RENDERED LABEL. Nothing is clicked, expanded,
   * downloaded or fetched - this is the text already on the user's screen.
   *
   * Defined here rather than at each call site: the message lane and the page
   * lane both need it, and a duplicated definition is what let the UPI extractor
   * drift between two engines until it accused every email address of being a
   * payment handle. One definition, two callers.
   */
  function readAttachmentFrom(row, opts) {
    if (!row || typeof row.querySelector !== "function") return null;
    const o = opts || {};
    const node = row.querySelector(ATTACHMENT_NODE_SELECTOR);
    if (!node && !o.assumeDocument) return null;

    const scope = (node && node.closest && (node.closest("[role='button'], div") || row)) || row;
    const label = ((scope.innerText || scope.textContent || "") + "").trim();
    const titleAttr = (node && node.getAttribute && (node.getAttribute("title")
      || node.getAttribute("aria-label"))) || "";

    const m = FILENAME_RE.exec(label) || FILENAME_RE.exec(titleAttr);
    if (!m) return null;

    const size = SIZE_RE.exec(label);
    return {
      filename: m[1].trim(),
      size_text: size ? size[0] : null,
      source: o.source || "chat",
    };
  }

  /**
   * Plain-English explanation for the user. States the observable facts and the
   * consequence of installing, and stops there - nothing here has inspected the
   * package, so nothing here calls it malware.
   */
  function explain(report) {
    if (!report || !report.is_apk) return "";
    const parts = [];
    if (report.evidence.source === "chat") {
      parts.push("This is an Android app file sent in a chat, not a link to an app store listing.");
    } else {
      parts.push("This is an Android app file offered outside an app store.");
    }
    if (report.claims.length) {
      parts.push("Its filename advertises a paid app unlocked for free ("
        + report.claims.join(", ") + ").");
    }
    if (report.evidence.financial_brand) {
      parts.push("It carries the name of a financial or trading service. Apps handling "
        + "money or holdings should be installed only from that provider's official "
        + "app store listing — a sideloaded build can display balances and holdings "
        + "that are not real.");
    }
    parts.push("Installing it requires switching off Android's install-from-unknown-sources "
      + "protection, which is the step this kind of file needs and a store install does not.");
    return parts.join(" ");
  }

  return { inspect, explain, isAndroidPackage, readAttachmentFrom,
           ATTACHMENT_NODE_SELECTOR,
           MOD_MARKERS, FINANCIAL_BRANDS, PAID_APP_BRANDS };
}));
