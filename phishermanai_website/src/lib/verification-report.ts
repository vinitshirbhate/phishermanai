import type { EngineVerdictResponse } from "./engine-types";

/**
 * Keeping a verdict.
 *
 * The readable form is a PDF — see verification-pdf.ts. This file holds the raw
 * export and the shared filename convention. Both are produced in the browser
 * from the response already on screen, so nothing is re-sent to generate them.
 */

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
