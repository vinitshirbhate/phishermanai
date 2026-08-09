"use client";

import { VERDICT_STYLES, type VerdictResponse } from "@/lib/types";

/**
 * The verdict, its plain-English summary, and the evidence score.
 *
 * The evidence score is shown separately from the verdict on purpose. It says
 * how much we had to go on, not how bad the message is -- a GENUINE backed by
 * five passing checks and a filing match is a different statement from a
 * GENUINE backed by two, and hiding that difference would overstate what we
 * know.
 */
export default function VerdictCard({ result }: { result: VerdictResponse }) {
  const style = VERDICT_STYLES[result.verdict];
  const concluded = result.evidence_summary?.checks_concluded ?? 0;
  const run = result.evidence_summary?.checks_run ?? 0;

  return (
    <section className={`card ring-2 ${style.ring} overflow-hidden`}>
      <div className={`${style.bg} px-6 py-5`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className={`h-3.5 w-3.5 rounded-full ${style.dot}`} aria-hidden />
            <h2 className={`text-2xl font-bold tracking-tight ${style.text}`}>
              {style.label}
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Evidence score
              </div>
              <div className={`text-lg font-semibold ${style.text}`}>
                {result.confidence}
                <span className="text-sm font-normal text-slate-500">/100</span>
              </div>
            </div>
            <div className="h-10 w-px bg-slate-300" aria-hidden />
            <div className="text-right">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Checked in
              </div>
              <div className="text-lg font-semibold text-slate-700">
                {result.latency_ms}
                <span className="text-sm font-normal text-slate-500">ms</span>
              </div>
            </div>
          </div>
        </div>

        <p className={`mt-4 text-lg leading-relaxed ${style.text}`}>{result.summary}</p>

        <p className="mt-3 text-xs text-slate-600">
          Based on {concluded} of {run} checks that reached a conclusion
          {result.evidence_summary?.filing_matched
            ? ", plus a matched exchange filing"
            : ", with no matching exchange filing found"}
          .
        </p>
      </div>

      {/* Per-chokepoint strip: shows at a glance which checks concluded. */}
      <div className="grid grid-cols-2 divide-x divide-y divide-slate-200 border-t border-slate-200 sm:grid-cols-4 sm:divide-y-0">
        {["MONEY", "ENTITY", "CLAIM", "DELIVERY"].map((name) => {
          const check = result.checks?.[name];
          const passed = check?.passed;
          const tone =
            passed === true
              ? "text-emerald-700"
              : passed === false
              ? "text-red-700"
              : "text-slate-400";
          const label =
            passed === true ? "Passed" : passed === false ? "Failed" : "No evidence";
          return (
            <div key={name} className="px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                {name}
              </div>
              <div className={`mt-0.5 text-sm font-semibold ${tone}`}>{label}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
