import type { EngineVerdictResponse } from "./engine-types";
import { engineVerdictTone } from "./engine-types";

/**
 * The verdict as a PDF someone can read, keep, or attach to a complaint.
 *
 * Built in the browser from the response already on screen, so nothing is
 * re-sent to produce it. jsPDF is imported dynamically: it is a large
 * dependency and only this one button needs it.
 */

type Context = { inputLabel: string; moneySent: boolean };

/** Verdict colours, matched to the site palette. */
const TONE_RGB: Record<string, [number, number, number]> = {
  VERIFIED: [28, 122, 74],
  NO_RISK_FOUND: [91, 106, 140],
  TAMPERED: [180, 92, 7],
  FRAUDULENT: [192, 38, 38],
};

const NAVY: [number, number, number] = [11, 21, 48];
const MUTED: [number, number, number] = [110, 118, 138];
const RULE: [number, number, number] = [214, 208, 200];

function text(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * A check is a chokepoint result, not a string: it arrives as
 * `{chokepoint, passed, confidence, severity, reasons[]}`. Printing it raw
 * fills a page with JSON, and the reasons are already set out above, so this
 * reduces each one to its outcome.
 */
function formatCheck(value: unknown): string {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const check = value as Record<string, unknown>;
    if (typeof check.passed === "boolean") {
      const parts = [check.passed ? "passed" : "failed"];
      if (typeof check.confidence === "number") {
        parts.push(`confidence ${check.confidence.toFixed(2)}`);
      }
      if (typeof check.severity === "number" && check.severity > 0) {
        parts.push(`severity ${check.severity}`);
      }
      if (Array.isArray(check.reasons) && check.reasons.length > 0) {
        parts.push(
          `${check.reasons.length} reason${check.reasons.length === 1 ? "" : "s"}, listed above`,
        );
      }
      return parts.join("   ·   ");
    }
  }
  return text(value);
}

function severityLabel(severity: number): string {
  if (severity >= 4) return "disqualifying";
  if (severity >= 2) return "weak";
  return "context";
}

/**
 * Lays the report out and returns the document. Separated from the download so
 * it can be rendered and inspected outside a browser.
 */
export async function buildPdf(result: EngineVerdictResponse, context: Context) {
  const [{ jsPDF }, autoTableModule] = await Promise.all([
    import("jspdf"),
    import("jspdf-autotable"),
  ]);
  const autoTable = autoTableModule.default;

  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 48;
  const contentWidth = pageWidth - margin * 2;
  const tone = engineVerdictTone[result.verdict];
  const accent = TONE_RGB[tone] ?? MUTED;

  let y = 0;

  const ensureRoom = (needed: number) => {
    if (y + needed > pageHeight - 64) {
      doc.addPage();
      y = margin;
    }
  };

  const heading = (label: string) => {
    ensureRoom(46);
    y += 20;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.setTextColor(...NAVY);
    doc.text(label.toUpperCase(), margin, y);
    y += 8;
    doc.setDrawColor(...RULE);
    doc.setLineWidth(0.7);
    doc.line(margin, y, pageWidth - margin, y);
    y += 16;
  };

  const body = (value: string, options: { size?: number; muted?: boolean } = {}) => {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(options.size ?? 10);
    doc.setTextColor(...(options.muted ? MUTED : NAVY));
    const lines = doc.splitTextToSize(value, contentWidth) as string[];
    for (const line of lines) {
      ensureRoom(16);
      doc.text(line, margin, y);
      y += 14;
    }
  };

  // ---- Header band, carrying the verdict colour -------------------------
  doc.setFillColor(...accent);
  doc.rect(0, 0, pageWidth, 128, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  doc.text("PhishermanAI — verification report", margin, 46);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(30);
  doc.text(result.label || result.verdict, margin, 86);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9.5);
  doc.text(
    `Evidence available ${result.confidence}/100   ·   ${result.latency_ms} ms   ·   generated ${new Date().toLocaleString()}`,
    margin,
    108,
  );

  y = 128 + 30;

  // ---- Summary ----------------------------------------------------------
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12.5);
  doc.setTextColor(...NAVY);
  const summaryLines = doc.splitTextToSize(result.summary || "", contentWidth) as string[];
  for (const line of summaryLines) {
    ensureRoom(20);
    doc.text(line, margin, y);
    y += 18;
  }

  y += 4;
  body(
    "Evidence available measures how much the engine could see, not how bad the message is. A low number means the evidence was thin, not that the message is safe.",
    { size: 9, muted: true },
  );

  // ---- What was checked -------------------------------------------------
  heading("What was checked");
  autoTable(doc, {
    startY: y,
    margin: { left: margin, right: margin },
    theme: "plain",
    styles: { font: "helvetica", fontSize: 9.5, cellPadding: 5, textColor: NAVY },
    columnStyles: { 0: { cellWidth: 150, textColor: MUTED }, 1: { cellWidth: "auto" } },
    body: [
      ["Input", context.inputLabel],
      ["Read as", result.source_type],
      ["Content fingerprint", result.content_hash || "—"],
      ["Money already sent", context.moneySent ? "yes" : "no"],
    ],
  });
  y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 6;

  body(
    "The fingerprint is a SHA-256 of the normalised content. The engine stores it and the verdict — never the message itself.",
    { size: 8.5, muted: true },
  );

  // ---- Why it was flagged ----------------------------------------------
  heading("Why this was flagged");
  if (result.reasons.length === 0) {
    body("No reason fired. That is the absence of a finding, not a clean bill of health.");
  } else {
    for (const reason of result.reasons) {
      ensureRoom(50);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10);
      doc.setTextColor(...NAVY);
      const titleLines = doc.splitTextToSize(reason.message, contentWidth) as string[];
      for (const line of titleLines) {
        ensureRoom(16);
        doc.text(line, margin, y);
        y += 14;
      }
      doc.setFont("helvetica", "normal");
      doc.setFontSize(8.5);
      doc.setTextColor(...MUTED);
      ensureRoom(14);
      doc.text(
        `${reason.code}   ·   severity ${reason.severity} (${severityLabel(reason.severity)})`,
        margin,
        y,
      );
      y += 12;

      const evidence = Object.entries(reason.evidence ?? {}).filter(([, value]) => {
        // Fields the register had nothing for add length without adding meaning.
        if (value === null || value === undefined || value === "") return false;
        if (Array.isArray(value)) return value.length > 0;
        if (typeof value === "object") return Object.keys(value).length > 0;
        return true;
      });
      for (const [key, value] of evidence) {
        const line = `${key}: ${text(value)}`;
        const wrapped = doc.splitTextToSize(line, contentWidth - 14) as string[];
        for (const part of wrapped) {
          ensureRoom(13);
          doc.text(part, margin + 14, y);
          y += 11;
        }
      }
      y += 8;
    }
  }

  // ---- Field comparisons — the tamper evidence --------------------------
  if (result.field_comparisons.length > 0) {
    heading("Field comparisons");
    body("What the document says, beside what was actually filed.", { size: 9, muted: true });
    y += 4;
    autoTable(doc, {
      startY: y,
      margin: { left: margin, right: margin },
      theme: "grid",
      headStyles: { fillColor: NAVY, textColor: [255, 255, 255], fontSize: 9 },
      styles: { font: "helvetica", fontSize: 9, cellPadding: 5, textColor: NAVY },
      head: [["Field", "This document", "On record", "Read", "Result"]],
      body: result.field_comparisons.map((comparison) => [
        comparison.field,
        text(comparison.extracted_value),
        text(comparison.filed_value),
        comparison.read_confidence,
        comparison.read_confidence === "UNREADABLE"
          ? "not compared"
          : comparison.match
            ? "matches"
            : "differs",
      ]),
      didParseCell: (data) => {
        if (data.section !== "body" || data.column.index !== 4) return;
        const value = String(data.cell.raw);
        if (value === "differs") data.cell.styles.textColor = TONE_RGB.FRAUDULENT;
        if (value === "matches") data.cell.styles.textColor = TONE_RGB.VERIFIED;
      },
    });
    y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 6;
    body("A field read as UNREADABLE is never compared, and can never produce a tamper finding.", {
      size: 8.5,
      muted: true,
    });
  }

  // ---- Matched filing ---------------------------------------------------
  if (result.matched_filing && result.matched_filing.tier !== "NONE") {
    const filing = result.matched_filing;
    heading("Matched filing");
    autoTable(doc, {
      startY: y,
      margin: { left: margin, right: margin },
      theme: "plain",
      styles: { font: "helvetica", fontSize: 9.5, cellPadding: 5, textColor: NAVY },
      columnStyles: { 0: { cellWidth: 150, textColor: MUTED }, 1: { cellWidth: "auto" } },
      body: [
        ["Company", text(filing.company_name)],
        ["Filing type", text(filing.filing_type)],
        ["Filing date", text(filing.filing_date)],
        ["Exchange", text(filing.exchange)],
        ["Headline", text(filing.headline)],
        ["Match tier", `${filing.tier} (score ${filing.score.toFixed(2)})`],
        ["Ranked by", `${filing.ranking_method}, from ${filing.candidates_considered} candidates`],
        ...(filing.pdf_url ? [["Source document", filing.pdf_url]] : []),
      ],
    });
    y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;
  }

  // ---- Checks -----------------------------------------------------------
  const checks = Object.entries(result.checks ?? {});
  if (checks.length > 0) {
    heading("Checks run");
    autoTable(doc, {
      startY: y,
      margin: { left: margin, right: margin },
      theme: "plain",
      styles: { font: "helvetica", fontSize: 9.5, cellPadding: 5, textColor: NAVY },
      columnStyles: { 0: { cellWidth: 220, textColor: MUTED }, 1: { cellWidth: "auto" } },
      body: checks.map(([name, value]) => [name, formatCheck(value)]),
      didParseCell: (data) => {
        if (data.section !== "body" || data.column.index !== 1) return;
        const value = String(data.cell.raw);
        if (value.startsWith("failed")) data.cell.styles.textColor = TONE_RGB.FRAUDULENT;
        if (value.startsWith("passed")) data.cell.styles.textColor = TONE_RGB.VERIFIED;
      },
    });
    y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 6;
    body(
      "A check that could not run is excluded from the verdict. It is never counted as evidence of innocence.",
      { size: 8.5, muted: true },
    );
  }

  // ---- What to do next --------------------------------------------------
  if (result.recommended_actions.length > 0) {
    heading("What to do next");
    for (const action of result.recommended_actions) {
      ensureRoom(48);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10);
      doc.setTextColor(...NAVY);
      doc.text(`${action.priority} — ${action.title}`, margin, y);
      y += 14;
      body(action.detail, { size: 9 });

      const channel = action.channel as Record<string, unknown> | null;
      if (channel?.url) {
        const label = `${text(channel.name)}: ${text(channel.url)}${
          channel.helpline ? `  ·  helpline ${text(channel.helpline)}` : ""
        }`;
        doc.setTextColor(...accent);
        doc.setFontSize(9);
        for (const line of doc.splitTextToSize(label, contentWidth) as string[]) {
          ensureRoom(14);
          doc.text(line, margin, y);
          y += 12;
        }
      }

      const contact = action.contact as Record<string, unknown> | null;
      if (contact) {
        for (const [key, value] of Object.entries(contact)) {
          // Skip anything the register had no value for, and the caution
          // string, which is the same sentence already printed as the detail.
          if (value === null || value === undefined || value === "") continue;
          if (Array.isArray(value) && value.length === 0) continue;
          if (typeof value === "object" && Object.keys(value).length === 0) continue;
          if (key === "caution") continue;
          body(`${key.replace(/_/g, " ")}: ${text(value)}`, { size: 8.5, muted: true });
        }
      }
      y += 8;
    }
  }

  // ---- Bounds -----------------------------------------------------------
  heading("What this report does not establish");
  body(
    "The filings cross-check covers listed-company corporate actions. A message referencing anything else is judged on the four chokepoints alone.",
    { size: 9 },
  );
  body(
    "Registrations are resolved against a dated snapshot of SEBI's public register. An entity registered after that snapshot would not resolve.",
    { size: 9 },
  );
  body("A verdict is evidence for a decision, not a legal finding.", { size: 9 });
  if (context.moneySent) {
    y += 6;
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...TONE_RGB.FRAUDULENT);
    body(
      "You indicated money has already been sent. Reporting within 24 hours gives the best chance of freezing the transfer.",
      { size: 9 },
    );
  }

  // ---- Page numbers -----------------------------------------------------
  const pages = doc.getNumberOfPages();
  for (let page = 1; page <= pages; page += 1) {
    doc.setPage(page);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(...MUTED);
    doc.text(
      `PhishermanAI · ${result.content_hash.slice(0, 16)}`,
      margin,
      pageHeight - 28,
    );
    doc.text(`${page} of ${pages}`, pageWidth - margin, pageHeight - 28, { align: "right" });
  }

  return doc;
}

export async function downloadPdfReport(
  result: EngineVerdictResponse,
  context: Context,
  filename: string,
): Promise<void> {
  const doc = await buildPdf(result, context);
  doc.save(filename);
}
