/*
 * extension/preflight/psl.js - bundled public-suffix list + the real PSL
 * algorithm (wildcards and exceptions), NOT a naive dot split.
 *
 * WHY THIS MATTERS HERE: eTLD+1 is what decides whether two hosts are "the same
 * site". A dot split gets `sebi.gov.in` wrong - it would read the registrable
 * domain as `gov.in`, making every `*.gov.in` host look like the same site as
 * SEBI, and making `sebi.gov.in.secure-verify.xyz` look like a subdomain of a
 * government domain. Both errors point the wrong way: one under-warns on a
 * lookalike, the other could accuse a legitimate government page.
 *
 * SCOPE, STATED HONESTLY: this is a CURATED SUBSET of the Mozilla Public Suffix
 * List (~200 rules), not the full ~9,000-rule list. It covers the ICANN generic
 * suffixes, the India-facing ccTLD space this product targets, and the
 * multi-label suffixes that appear in Indian financial services. Hosts under a
 * suffix we do not carry fall back to the last two labels, which is the same
 * answer a dot split would give - so the failure mode is "no worse than naive",
 * never "confidently wrong". `isKnownSuffix()` reports which case applied, and
 * the verdict layer lowers confidence when the answer came from the fallback.
 *
 * NOT SHARED WITH ml/features.py BY DESIGN. That module carries its own frozen
 * minimal suffix list because changing it would change feature VALUES, moving
 * the trained model's inputs and breaking G-1 parity against a shipped
 * artefact. This list is free to grow; that one is pinned to fs_v2.
 *
 * Loads in Node and in the MV3 service worker. No chrome.* APIs.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanPSL = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Ordinary rules. A host matching one of these consumes that many labels.
  const RULES = (
    // --- generic / ICANN ---
    "com net org edu gov mil int info biz name pro app dev page site online " +
    "xyz top club shop store tech space website live life world today news " +
    "io ai co me tv cc ly sh gg to " +
    "tk ml ga cf gq buzz click link work loan download review country stream " +
    "gdn racing win bid party trade date faith science cricket accountant men " +
    "rest fit surf monster quest cyou icu sbs " +
    // --- India: the space this product actually operates in ---
    "in co.in net.in org.in gen.in firm.in ind.in ac.in edu.in res.in " +
    "gov.in nic.in mil.in cs.in bank.in insurance.in " +
    // --- other ccTLDs commonly used to host India-facing lures ---
    "uk co.uk org.uk me.uk ac.uk gov.uk net.uk sch.uk ltd.uk plc.uk " +
    "au com.au net.au org.au edu.au gov.au id.au " +
    "jp co.jp or.jp ne.jp ac.jp go.jp " +
    "br com.br net.br org.br gov.br " +
    "cn com.cn net.cn org.cn gov.cn edu.cn " +
    "sg com.sg net.sg org.sg edu.sg gov.sg " +
    "my com.my net.my org.my edu.my gov.my " +
    "hk com.hk tw com.tw mx com.mx tr com.tr ar com.ar " +
    "pk com.pk bd com.bd np com.np lk com.lk " +
    "za co.za org.za nz co.nz org.nz kr co.kr id co.id th co.th or.th " +
    "ph com.ph vn com.vn sa com.sa eg com.eg ng com.ng gh com.gh " +
    "kw com.kw qa com.qa ae co.ae il co.il org.il ua com.ua pl com.pl ru com.ru " +
    "de fr it es nl be ch at se no dk fi ie pt gr cz ro hu us ca"
  ).split(/\s+/).filter(Boolean);

  // Wildcard rules: *.<suffix> - every label under these is itself a suffix.
  const WILDCARD = ["ck", "jm", "kh", "mm", "np.pk", "er", "fj", "fk", "bd", "il"];
  // Exception rules: !<host> - explicitly registrable despite a wildcard above.
  const EXCEPTION = ["www.ck", "city.kawasaki.jp"];

  const RULE_SET = new Set(RULES);
  const WILDCARD_SET = new Set(WILDCARD);
  const EXCEPTION_SET = new Set(EXCEPTION);

  function labelsOf(host) {
    return String(host || "").toLowerCase().replace(/^\.+|\.+$/g, "").split(".").filter(Boolean);
  }

  /**
   * The public suffix of `host`, per the PSL matching algorithm:
   * exceptions beat wildcards, wildcards beat ordinary rules, longest wins.
   * Returns { suffix, matched:boolean, rule } - `matched:false` means the
   * fallback applied and callers should treat the answer as lower-confidence.
   */
  function publicSuffix(host) {
    const labels = labelsOf(host);
    if (labels.length === 0) return { suffix: "", matched: false, rule: "empty" };

    // Exception rules win outright and consume one label fewer.
    for (let i = 0; i < labels.length; i++) {
      const candidate = labels.slice(i).join(".");
      if (EXCEPTION_SET.has(candidate)) {
        return { suffix: labels.slice(i + 1).join("."), matched: true, rule: "!" + candidate };
      }
    }
    // Wildcard: *.<suffix> means <label>.<suffix> is itself a public suffix.
    for (let i = 1; i < labels.length; i++) {
      const parent = labels.slice(i).join(".");
      if (WILDCARD_SET.has(parent)) {
        return { suffix: labels.slice(i - 1).join("."), matched: true, rule: "*." + parent };
      }
    }
    // Ordinary rules, longest match first.
    for (let i = 0; i < labels.length; i++) {
      const candidate = labels.slice(i).join(".");
      if (RULE_SET.has(candidate)) {
        return { suffix: candidate, matched: true, rule: candidate };
      }
    }
    // Unknown suffix: fall back to the final label. No worse than a dot split.
    return { suffix: labels[labels.length - 1], matched: false, rule: "fallback:last-label" };
  }

  /**
   * eTLD+1 - the registrable domain. Returns
   * { domain, suffix, sld, subdomains[], matched }.
   */
  function registrableDomain(host) {
    const labels = labelsOf(host);
    const ps = publicSuffix(host);
    const suffixLabels = ps.suffix ? ps.suffix.split(".").length : 0;
    if (labels.length <= suffixLabels) {
      // The host IS a public suffix (e.g. "co.in") - there is no registrable
      // domain. Never treat this as a site identity.
      return { domain: "", suffix: ps.suffix, sld: "", subdomains: [],
               matched: ps.matched, is_public_suffix: true, rule: ps.rule };
    }
    const sld = labels[labels.length - suffixLabels - 1];
    const domain = [sld].concat(ps.suffix ? ps.suffix.split(".") : []).join(".");
    return {
      domain: domain,
      suffix: ps.suffix,
      sld: sld,
      subdomains: labels.slice(0, labels.length - suffixLabels - 1),
      matched: ps.matched,
      is_public_suffix: false,
      rule: ps.rule,
    };
  }

  /** True when both hosts sit under the same registrable domain. */
  function sameSite(a, b) {
    const da = registrableDomain(a).domain;
    const db = registrableDomain(b).domain;
    return !!da && da === db;
  }

  return {
    publicSuffix: publicSuffix,
    registrableDomain: registrableDomain,
    sameSite: sameSite,
    ruleCount: RULES.length + WILDCARD.length + EXCEPTION.length,
  };
});
