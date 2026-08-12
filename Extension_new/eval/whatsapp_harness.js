#!/usr/bin/env node
/*
 * eval/whatsapp_harness.js — runs the WhatsApp lane against REAL captured DOM.
 *
 *   node eval/whatsapp_harness.js
 *
 * REQUIRES eval/fixtures/whatsapp/*.html — five human-captured, sanitised
 * snapshots of `document.querySelector('#main').outerHTML`.
 *
 * IT WILL NOT SYNTHESISE THEM. Fixtures authored alongside the selectors would
 * match the selectors by construction and prove nothing about real WhatsApp —
 * the same self-consistency trap as the 17-entry fictional SEBI register. If the
 * directory is empty this exits non-zero and says exactly what is missing.
 *
 * No npm install: a minimal DOM shim is used when jsdom is unavailable, and the
 * shim's limitations are printed so results are not over-read.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const EXT = path.join(ROOT, "extension");
const FIX = path.join(ROOT, "eval", "fixtures", "whatsapp");
const OUT = path.join(ROOT, "eval", "whatsapp_summary.json");

const EXPECTED = [
  { file: "direct_1to1.html", covers: "ordinary one-to-one chat" },
  { file: "group_large.html", covers: "group with many members" },
  { file: "forwarded.html", covers: "chat containing a forwarded message" },
  { file: "image_message.html", covers: "chat containing an image" },
  { file: "system_added.html", covers: "chat with a 'You were added' system message" },
];

function fail(msg) {
  console.log("\n" + "=".repeat(78));
  console.log("WHATSAPP_HARNESS_BLOCKED");
  console.log("=".repeat(78));
  console.log(msg);
  process.exit(2);
}

if (!fs.existsSync(FIX) || !fs.readdirSync(FIX).filter((f) => f.endsWith(".html")).length) {
  fail(
    "eval/fixtures/whatsapp/ contains no *.html captures.\n\n"
    + "This harness needs FIVE real, human-captured, sanitised DOM snapshots:\n"
    + EXPECTED.map((e) => `  ${e.file.padEnd(22)} ${e.covers}`).join("\n")
    + "\n\nCapture each with, in the DevTools console on web.whatsapp.com:\n"
    + "    copy(document.querySelector('#main').outerHTML)\n"
    + "then replace real names, phone numbers, profile-photo URLs and message\n"
    + "text with placeholders. Leave STRUCTURE AND ATTRIBUTES untouched — the\n"
    + "structure is the entire point of the capture.\n\n"
    + "Fixtures are deliberately NOT generated here: fixtures written by the same\n"
    + "author as the selectors match those selectors by construction and prove\n"
    + "nothing about real WhatsApp."
  );
}

// --- DOM ------------------------------------------------------------------- #
let makeDoc, domNote;
try {
  const { JSDOM } = require("jsdom");
  makeDoc = (html) => new JSDOM(`<!doctype html><html><body>${html}</body></html>`).window.document;
  domNote = "jsdom";
} catch (e) {
  fail(
    "jsdom is not available and this harness needs a real DOM to resolve\n"
    + "selectors against captured markup. Options:\n"
    + "  * run `node --experimental-... ` with jsdom installed locally, or\n"
    + "  * run this harness from an environment that already has jsdom.\n\n"
    + "A hand-rolled DOM shim is deliberately NOT used here: selector resolution\n"
    + "is the exact thing under test, and a shim that implements only the\n"
    + "querySelector features our selectors happen to use would pass by\n"
    + "construction — the same trap as author-written fixtures."
  );
}

const SEL = require(path.join(EXT, "whatsapp/selectors.js"));
const HEALTH = require(path.join(EXT, "whatsapp/health.js"));
const EX = require(path.join(EXT, "whatsapp/extract.js"));
const CTX = require(path.join(EXT, "whatsapp/context.js"));
const V = require(path.join(EXT, "whatsapp/verdict.js"));
const SECURITIES = require(path.join(EXT, "securities_check.js"));
SECURITIES.load(JSON.parse(
  fs.readFileSync(path.join(EXT, "data/securities_snapshot.json"), "utf8")));

function runFixture(file) {
  const html = fs.readFileSync(path.join(FIX, file), "utf8");
  const doc = makeDoc(html);

  const health = HEALTH.check(doc);
  const main = SEL.resolve("conversation", doc).nodes[0] || doc.body;
  const scroll = SEL.resolve("scroll_container", doc, main).nodes[0] || main;
  const rows = SEL.resolve("message_row", doc, scroll).nodes;
  const titleNode = SEL.resolve("chat_title", doc, main).nodes[0];
  const title = titleNode
    ? (titleNode.getAttribute && titleNode.getAttribute("title")) || titleNode.textContent : null;
  const memberM = /(\d[\d,]*)\s+members?/i.exec(main.textContent || "");
  const memberCount = memberM ? Number(memberM[1].replace(/,/g, "")) : null;

  const timings = [];
  const records = [];
  for (const row of rows) {
    const t0 = process.hrtime.bigint();
    let rec = null;
    try { rec = EX.fromRow(row, { chatId: file }); } catch (e) { /* keep going */ }
    timings.push(Number(process.hrtime.bigint() - t0) / 1e6);
    if (rec) records.push(rec);
  }

  const channel = CTX.assess({ chat_id: file, title: title, member_count: memberCount },
                             records, {});
  const verdicts = records.map((rec) => {
    const q = rec.body_text ? SECURITIES.quickCheck(rec.body_text,
      (rec.sender && rec.sender.display_name) || "", rec.timestamp) : null;
    return V.assemble(rec, channel, { registration: q || {}, health: health.state });
  });

  const sorted = timings.slice().sort((a, b) => a - b);
  const p = (q) => sorted.length ? Number(sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))].toFixed(3)) : null;

  return {
    fixture: file,
    health: { state: health.state, score: health.score, tier_depth: health.tier_depth,
              resolved: health.resolved, expected: health.expected, targets: health.targets },
    chat: { title: title, member_count: memberCount, rows: rows.length },
    channel_signals: channel.signals,
    per_message_ms: { p50: p(0.5), p95: p(0.95), max: sorted.length ? Number(sorted[sorted.length - 1].toFixed(3)) : null,
                      over_8ms: timings.filter((t) => t > 8).length },
    verdict_counts: verdicts.reduce((a, v) => { a[v.verdict] = (a[v.verdict] || 0) + 1; return a; }, {}),
    badged: verdicts.filter((v) => v.badge).length,
    verdicts: verdicts.filter((v) => v.badge),
    records_sample: records.slice(0, 3).map((r) => ({
      message_id: r.message_id, direction: r.direction, timestamp: r.timestamp,
      sender: r.sender, entities: r.entities, flags: r.flags, partial: r.partial,
    })),
  };
}

function main() {
  const files = fs.readdirSync(FIX).filter((f) => f.endsWith(".html")).sort();
  const missing = EXPECTED.filter((e) => files.indexOf(e.file) === -1);
  const results = files.map(runFixture);

  console.log("=".repeat(78));
  console.log(`WHATSAPP HARNESS — ${files.length} real fixture(s), DOM: ${domNote}, network not used`);
  console.log("=".repeat(78));
  for (const r of results) {
    console.log("\n" + "-".repeat(78));
    console.log(`${r.fixture}   health=${r.health.state} (${r.health.score}, tier depth ${r.health.tier_depth})`);
    console.log(JSON.stringify(r, null, 2));
  }

  const degraded = results.filter((r) => r.health.state !== "HEALTHY");
  const overBudget = results.filter((r) => r.per_message_ms.over_8ms > 0);

  console.log("\n" + "=".repeat(78));
  console.log(`fixtures            : ${results.length}`);
  console.log(`health HEALTHY      : ${results.length - degraded.length}/${results.length}`);
  degraded.forEach((r) => console.log(`   ${r.health.state}: ${r.fixture} (score ${r.health.score})`));
  if (degraded.length) {
    console.log("   ^ A DEGRADED/BLIND fixture is a finding about the selector registry,");
    console.log("     not a harness bug. Report it as such.");
  }
  console.log(`over 8ms/message    : ${overBudget.length} fixture(s)`);
  if (missing.length) {
    console.log(`MISSING captures    : ${missing.map((m) => m.file).join(", ")}`);
  }
  fs.writeFileSync(OUT, JSON.stringify({
    generated_by: "eval/whatsapp_harness.js", dom: domNote,
    n_fixtures: results.length, missing: missing.map((m) => m.file),
    registry_version: SEL.REGISTRY_VERSION, results: results,
  }, null, 2) + "\n", "utf8");
  console.log(`summary written     : eval/whatsapp_summary.json`);
  console.log("=".repeat(78));
  process.exit(missing.length ? 1 : 0);
}

main();
