"use client";

import { useState } from "react";
import type { Reason } from "@/lib/types";

/**
 * Every verdict carries its reasons. A user who disagrees with us should be
 * able to see exactly what we looked at and decide for themselves -- a wrong
 * answer with visible reasoning is recoverable, a confident black box is not.
 */

function severityChip(severity: number) {
  if (severity >= 5) return { text: "Critical", cls: "bg-red-100 text-red-800" };
  if (severity === 4) return { text: "Serious", cls: "bg-orange-100 text-orange-800" };
  if (severity === 3) return { text: "Caution", cls: "bg-amber-100 text-amber-800" };
  if (severity > 0) return { text: "Minor", cls: "bg-slate-100 text-slate-700" };
  return { text: "Passed", cls: "bg-emerald-100 text-emerald-800" };
}

function ReasonRow({ reason }: { reason: Reason }) {
  const [open, setOpen] = useState(false);
  const chip = severityChip(reason.severity);
  const hasEvidence = reason.evidence && Object.keys(reason.evidence).length > 0;

  return (
    <li className="border-b border-slate-100 last:border-b-0">
      <div className="flex gap-3 px-5 py-3.5">
        <span className={`chip mt-0.5 shrink-0 ${chip.cls}`}>{chip.text}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-slate-800">{reason.message}</p>
          <div className="mt-1.5 flex items-center gap-3">
            <code className="text-[11px] text-slate-400">{reason.code}</code>
            {hasEvidence && (
              <button
                onClick={() => setOpen((v) => !v)}
                className="text-[11px] font-medium text-slate-500 underline underline-offset-2 hover:text-slate-900"
              >
                {open ? "hide evidence" : "show evidence"}
              </button>
            )}
          </div>
          {open && hasEvidence && (
            <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">
              {JSON.stringify(reason.evidence, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </li>
  );
}

export default function ReasonList({ reasons }: { reasons: Reason[] }) {
  const [showPassing, setShowPassing] = useState(false);
  const failing = reasons.filter((r) => r.severity > 0);
  const passing = reasons.filter((r) => r.severity === 0);
  const shown = showPassing ? [...failing, ...passing] : failing;

  return (
    <section className="card overflow-hidden">
      <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          Why we said this ({failing.length} finding{failing.length === 1 ? "" : "s"})
        </h2>
        {passing.length > 0 && (
          <button
            onClick={() => setShowPassing((v) => !v)}
            className="text-xs font-medium text-slate-500 underline underline-offset-2 hover:text-slate-900"
          >
            {showPassing ? "hide" : "show"} {passing.length} passing check
            {passing.length === 1 ? "" : "s"}
          </button>
        )}
      </header>
      {shown.length === 0 ? (
        <p className="px-5 py-6 text-sm text-slate-500">
          No findings were recorded for this message.
        </p>
      ) : (
        <ul>
          {shown.map((reason, i) => (
            <ReasonRow key={`${reason.code}-${i}`} reason={reason} />
          ))}
        </ul>
      )}
    </section>
  );
}
