import type { EngineVerdictResponse } from "./engine-types";

/**
 * Turns a verdict into something the reader can keep, forward to a broker, or
 * attach to a complaint.
 *
 * The report states what was checked, what it was checked against, and what the
 * engine could not see — the same standard the rest of the product holds to. It
 * is generated in the browser from the response already on screen, so nothing is
 * re-sent anywhere to produce it.
 */

function value(input: unknown): string {
  if (input === null || input === undefined || input === "") return "—";
  if (typeof input === "boolean") return input ? "yes" : "no";
  if (typeof input === "object") return JSON.stringify(input);
  return String(input);
}

function severityLabel(severity: number): string {
  if (severity >= 4) return "disqualifying";
  if (severity >= 2) return "weak";
  return "context";
}

export function buildMarkdownReport(
  result: EngineVerdictResponse,
  context: { inputLabel: string; moneySent: boolean },
): string {
  const generated = new Date().toISOString();
  const lines: string[] = [];

  lines.push("# PhishermanAI verification report", "");
  lines.push(`**Verdict:** ${result.label || result.verdict}`, "");
  lines.push("| | |", "| --- | --- |");
  lines.push(`| Input | ${context.inputLabel} |`);
  lines.push(`| Source type | ${result.source_type} |`);
  lines.push(`| Evidence available | ${result.confidence}% |`);
  lines.push(`| Engine latency | ${result.latency_ms} ms |`);
  lines.push(`| Content fingerprint | \`${result.content_hash}\` |`);
  lines.push(`| Report generated | ${generated} |`);
  lines.push("");

  lines.push("> Evidence available measures how much the engine could see, not how");
  lines.push("> bad the message is. A low number means the evidence was thin, not");
  lines.push("> that the message is safe.");
  lines.push("");

  lines.push("## Summary", "", result.summary || "_No summary returned._", "");

  lines.push("## Why this was flagged", "");
  if (result.reasons.length === 0) {
    lines.push("No reason fired. That is the absence of a finding, not a clean bill of health.", "");
  } else {
    for (const reason of result.reasons) {
      lines.push(`### ${reason.code} — severity ${reason.severity} (${severityLabel(reason.severity)})`);
      lines.push("");
      lines.push(reason.message);
      lines.push("");
      const evidence = Object.entries(reason.evidence ?? {});
      if (evidence.length > 0) {
        lines.push("| Evidence | Value |", "| --- | --- |");
        for (const [key, item] of evidence) lines.push(`| ${key} | ${value(item)} |`);
        lines.push("");
      }
    }
  }

  if (result.field_comparisons.length > 0) {
    lines.push("## Field comparisons", "");
    lines.push("Values in the document, beside what was actually filed.", "");
    lines.push(
      "| Field | This document | On record | Read confidence | Result |",
      "| --- | --- | --- | --- | --- |",
    );
    for (const comparison of result.field_comparisons) {
      const outcome =
        comparison.read_confidence === "UNREADABLE"
          ? "not compared"
          : comparison.match
            ? "matches"
            : "differs";
      lines.push(
        `| ${comparison.field} | ${value(comparison.extracted_value)} | ${value(comparison.filed_value)} | ${comparison.read_confidence} | ${outcome} |`,
      );
    }
    lines.push("");
    lines.push(
      "A field read as UNREADABLE is never compared, and can never produce a tamper finding.",
      "",
    );
  }

  if (result.matched_filing && result.matched_filing.tier !== "NONE") {
    const filing = result.matched_filing;
    lines.push("## Matched filing", "");
    lines.push("| | |", "| --- | --- |");
    lines.push(`| Company | ${value(filing.company_name)} |`);
    lines.push(`| Filing type | ${value(filing.filing_type)} |`);
    lines.push(`| Filing date | ${value(filing.filing_date)} |`);
    lines.push(`| Exchange | ${value(filing.exchange)} |`);
    lines.push(`| Headline | ${value(filing.headline)} |`);
    lines.push(`| Match tier | ${filing.tier} (score ${filing.score.toFixed(2)}) |`);
    lines.push(`| Ranked by | ${filing.ranking_method}, from ${filing.candidates_considered} candidates |`);
    if (filing.pdf_url) lines.push(`| Source document | ${filing.pdf_url} |`);
    lines.push("");
    if (filing.notes?.length) {
      for (const note of filing.notes) lines.push(`- ${note}`);
      lines.push("");
    }
  }

  const checks = Object.entries(result.checks ?? {});
  if (checks.length > 0) {
    lines.push("## Checks run", "");
    lines.push("| Check | Result |", "| --- | --- |");
    for (const [name, outcome] of checks) lines.push(`| ${name} | ${value(outcome)} |`);
    lines.push("");
    lines.push(
      "A check that could not run is excluded from the verdict. It is never counted as evidence of innocence.",
      "",
    );
  }

  if (result.recommended_actions.length > 0) {
    lines.push("## What to do next", "");
    for (const action of result.recommended_actions) {
      lines.push(`### ${action.title}`);
      lines.push(`_${action.priority} · ${action.type}_`, "");
      lines.push(action.detail, "");
      const channel = action.channel as Record<string, unknown> | null;
      if (channel?.url) {
        lines.push(`- ${value(channel.name)}: ${value(channel.url)}`);
        if (channel.helpline) lines.push(`- Helpline: ${value(channel.helpline)}`);
        lines.push("");
      }
      const contact = action.contact as Record<string, unknown> | null;
      if (contact && Object.keys(contact).length > 0) {
        lines.push("Verified official contact:");
        for (const [key, item] of Object.entries(contact)) lines.push(`- ${key}: ${value(item)}`);
        lines.push("");
      }
    }
  }

  lines.push("## What this report does not establish", "");
  lines.push(
    "- The filings cross-check covers listed-company corporate actions. A message referencing anything else is judged on the four chokepoints alone.",
    "- Registrations are resolved against a dated snapshot of SEBI's public register. An entity registered after that snapshot would not resolve.",
    "- A verdict is evidence for a decision, not a legal finding.",
  );
  if (context.moneySent) {
    lines.push(
      "",
      "**You indicated money has already been sent.** Reporting within 24 hours gives the best chance of freezing the transfer.",
    );
  }
  lines.push("");
  lines.push(`_Generated by PhishermanAI from verification \`${result.content_hash.slice(0, 16)}\`._`);

  return lines.join("\n");
}

export function buildJsonReport(
  result: EngineVerdictResponse,
  context: { inputLabel: string; moneySent: boolean },
): string {
  return JSON.stringify(
    {
      report_generated: new Date().toISOString(),
      input: context.inputLabel,
      money_already_sent: context.moneySent,
      verdict: result,
    },
    null,
    2,
  );
}

/** Filenames carry the verdict and fingerprint so a folder of them stays legible. */
export function reportFilename(result: EngineVerdictResponse, extension: string): string {
  const stamp = new Date().toISOString().slice(0, 10);
  const hash = result.content_hash ? result.content_hash.slice(0, 8) : "no-hash";
  return `phishermanai-${result.verdict.toLowerCase()}-${hash}-${stamp}.${extension}`;
}

export function downloadText(filename: string, contents: string, mime: string): void {
  const blob = new Blob([contents], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoking immediately can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
