#!/usr/bin/env node
/*
 * eval/preflight_harness.js — runs the PURE pre-flight pipeline under plain Node.
 *
 *   node eval/preflight_harness.js
 *
 * No npm install, no jsdom, no chrome.*. It loads the same UMD modules the
 * service worker loads, feeds them eval/fixtures/links/cases.json, and writes
 * real verdict JSON to eval/fixtures/links/expected/.
 *
 * WHAT THIS DOES NOT TEST, stated up front so the results are not over-read:
 * MV3 wiring, interstitial injection, hover timing and the webNavigation
 * triggers are in adapter_mv3.js and are NOT exercised here. They are verified
 * by hand in a browser; see docs/DEMO_SCRIPT.md. This harness proves the
 * decision logic, not the plumbing that delivers it.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const EXT = path.join(ROOT, "extension");

const urlParse = require(path.join(EXT, "preflight", "url_parse.js"));
const identity = require(path.join(EXT, "preflight", "identity.js"));
const verdictMod = require(path.join(EXT, "preflight", "verdict.js"));
const securities = require(path.join(EXT, "securities_check.js"));

// --- load the offline snapshots the extension bundles ----------------------- #
const snapshot = JSON.parse(
  fs.readFileSync(path.join(EXT, "data", "securities_snapshot.json"), "utf8"));
securities.load(snapshot);

const officialDoc = JSON.parse(
  fs.readFileSync(path.join(ROOT, "backend", "data", "official_domains.json"), "utf8"));
const OFFICIAL_DOMAINS = []
  .concat(officialDoc.regulator_and_mii || [])
  .concat(officialDoc.recovery_rails || []);

const CASES = JSON.parse(
  fs.readFileSync(path.join(ROOT, "eval", "fixtures", "links", "cases.json"), "utf8"));
const OUT_DIR = path.join(ROOT, "eval", "fixtures", "links", "expected");
fs.mkdirSync(OUT_DIR, { recursive: true });

// A local threat-feed stub. Real feeds live in backend/data/feeds/ and are a
// fast-negative pre-filter, never the detection thesis — so exactly one fixture
// exercises L5 and it is labelled as a feed hit, not as our own finding.
const FEED = {
  name: "openphish-sample",
  updated: "2026-08-06",
  hosts: new Set(["known-phish-example.top"]),
};

function runOne(c) {
  const t0 = process.hrtime.bigint();
  const parsed = urlParse.parse(c.url, {
    anchorText: c.anchor_text,
    pageHost: c.page_host,
    officialDomains: OFFICIAL_DOMAINS,
  });
  const ident = identity.resolve(parsed, {
    anchorText: c.anchor_text,
    surroundingText: c.surrounding_text || "",
    pageDate: c.page_date,
  });
  const host = parsed.registrable_domain || parsed.host_normalised;
  const feedHit = FEED.hosts.has(host)
    ? { listed: true, feed: FEED.name, updated: FEED.updated } : null;
  const v = verdictMod.assemble(parsed, ident, {
    feedHit: feedHit,
    pageDate: c.page_date,
    stagesRun: ["offline"],
  });
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;

  return {
    id: c.id,
    note: c.note,
    input: { url: c.url, anchor_text: c.anchor_text, page_host: c.page_host },
    expected_verdict: c.expected_verdict,
    verdict: v,
    parsed_summary: {
      scheme: parsed.scheme,
      host: parsed.host,
      host_decoded: parsed.host_decoded,
      registrable_domain: parsed.registrable_domain,
      public_suffix: parsed.public_suffix,
      psl_matched: parsed.psl_matched,
      is_payment_link: parsed.is_payment_link,
      payment: parsed.payment,
      is_ip_host: parsed.is_ip_host,
      ip_form: parsed.ip_form,
      is_private_target: parsed.is_private_target,
      is_punycode: parsed.is_punycode,
      userinfo_looks_like_host: parsed.userinfo_looks_like_host,
      subdomain_stuffing: parsed.subdomain_stuffing,
      anchor_mismatch: parsed.anchor_mismatch,
      is_shortener: parsed.is_shortener,
      expansion_required: parsed.expansion_required,
      skip_prefetch: parsed.skip_prefetch,
      obfuscation: parsed.obfuscation && parsed.obfuscation.obfuscated
        ? parsed.obfuscation : null,
      signals: parsed.signals,
    },
    identity_summary: {
      domain_status: ident.domain_status,
      official_entity: ident.official_entity,
      lookalike_of: ident.lookalike_of,
      registration_state: ident.registration ? ident.registration.state : null,
      upi: ident.upi,
    },
    elapsed_ms: Number(ms.toFixed(3)),
  };
}

// --- blocked-claims guard on generated copy (BL-5) -------------------------- #
const BLOCKED = ["safe", "verified safe", "guaranteed protection", "government affiliated",
                 "sebi-approved", "this is a deepfake", "ai-generated", "this voice is synthetic"];
function blockedClaimsIn(result) {
  const strings = [];
  (result.verdict.codes || []).forEach((c) => {
    strings.push(c.summary);
    if (c.disclaimer) strings.push(c.disclaimer);
  });
  Object.values(result.verdict.truths || {}).forEach((t) => {
    if (t && t.summary) strings.push(t.summary);
    (t && t.disclaimers || []).forEach((d) => strings.push(d));
  });
  const hits = [];
  strings.forEach((s) => {
    const low = String(s).toLowerCase();
    BLOCKED.forEach((b) => {
      if (low.indexOf(b) === -1) return;
      // "This is not a safety guarantee" contains "safe" only inside "safety",
      // which is a disclaimer, not a claim. Require a word boundary.
      const re = new RegExp("\\b" + b.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b");
      if (re.test(low)) hits.push({ claim: b, copy: s });
    });
  });
  return hits;
}

function main() {
  const results = [];
  let pass = 0, fail = 0, claimHits = 0;

  for (const c of CASES.cases) {
    let r;
    try {
      r = runOne(c);
    } catch (e) {
      console.log(`ERROR ${c.id}: ${e && e.stack ? e.stack.split("\n")[0] : e}`);
      fail++;
      continue;
    }
    const ok = r.verdict.verdict === r.expected_verdict;
    r.matches_expected = ok;
    ok ? pass++ : fail++;

    const hits = blockedClaimsIn(r);
    r.blocked_claim_hits = hits;
    claimHits += hits.length;

    results.push(r);
    fs.writeFileSync(path.join(OUT_DIR, c.id + ".json"),
                     JSON.stringify(r, null, 2) + "\n", "utf8");
  }

  // ---- report ------------------------------------------------------------- #
  console.log("=".repeat(78));
  console.log("PRE-FLIGHT HARNESS — pure logic modules, plain node, no network");
  console.log("=".repeat(78));
  for (const r of results) {
    console.log("\n" + "-".repeat(78));
    console.log(`${r.matches_expected ? "PASS" : "FAIL"}  ${r.id}`);
    console.log(`  expected ${r.expected_verdict}  ->  got ${r.verdict.verdict}`);
    console.log(JSON.stringify(r, null, 2));
  }

  const guards = results.filter((r) => (CASES.meta.false_positive_guards || []).indexOf(r.id) !== -1
                                    || r.expected_verdict === "L0_NO_SIGNALS");
  const accusedGuards = guards.filter((r) => r.verdict.verdict !== "L0_NO_SIGNALS");

  console.log("\n" + "=".repeat(78));
  console.log(`cases                : ${results.length}`);
  console.log(`verdict matches      : ${pass} pass / ${fail} fail`);
  console.log(`false-positive guards: ${guards.length} checked, ${accusedGuards.length} accused`);
  if (accusedGuards.length) {
    accusedGuards.forEach((r) => console.log(`   ACCUSED: ${r.id} -> ${r.verdict.verdict}`));
  }
  console.log(`BL-5 blocked claims  : ${claimHits}`);
  const slowest = results.reduce((m, r) => Math.max(m, r.elapsed_ms), 0);
  console.log(`slowest case         : ${slowest.toFixed(3)} ms`);
  console.log(`verdict JSON written : eval/fixtures/links/expected/`);
  console.log("=".repeat(78));

  // Machine-readable summary for eval/run_eval.py section C. Every figure in
  // REPORT.md section C is read from here; none is hand-entered.
  fs.writeFileSync(path.join(ROOT, "eval", "preflight_summary.json"), JSON.stringify({
    generated_by: "eval/preflight_harness.js",
    n_cases: results.length,
    n_match: pass,
    n_mismatch: fail,
    false_positive_guards: guards.length,
    false_positive_guards_accused: accusedGuards.length,
    blocked_claim_hits: claimHits,
    slowest_ms: Number(slowest.toFixed(3)),
    psl_rule_count: require(path.join(EXT, "preflight", "psl.js")).ruleCount,
    l0_copy: verdictMod.L0_COPY,
    rows: results.map((r) => ({
      id: r.id,
      url: r.input.url,
      expected: r.expected_verdict,
      got: r.verdict.verdict,
      match: r.matches_expected,
      codes_fired: r.verdict.codes_fired,
      confidence: r.verdict.confidence,
      skip_prefetch: r.parsed_summary.skip_prefetch,
      elapsed_ms: r.elapsed_ms,
    })),
  }, null, 2) + "\n", "utf8");

  const broken = fail > 0 || accusedGuards.length > 0 || claimHits > 0;
  console.log(broken ? "\nPREFLIGHT_HARNESS_FAIL" : "\nPREFLIGHT_HARNESS_PASS");
  process.exit(broken ? 1 : 0);
}

main();
