"use client";

import { CircleAlert, CircleCheck, CircleSlash, FileText } from "lucide-react";

import { VerdictBadge } from "@/components/site/verdict-badge";
import { verdictMeta } from "@/lib/analysis";
import { warningCardUrl } from "@/lib/engine-client";
import {
  engineVerdictTone,
  severityTier,
  type EngineFieldComparison,
  type EngineVerdictResponse,
} from "@/lib/engine-types";
import { cn } from "@/lib/utils";

const tierClass = {
  disqualifying: "text-verdict-fraud border-verdict-fraud/35 bg-verdict-fraud/10",
  weak: "text-verdict-tampered border-verdict-tampered/35 bg-verdict-tampered/10",
  context: "text-verdict-quiet border-verdict-quiet/35 bg-verdict-quiet/10",
} as const;

function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ComparisonRow({ comparison }: { comparison: EngineFieldComparison }) {
  const unreadable = comparison.read_confidence === "UNREADABLE";

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <div className="flex items-center justify-between gap-3 border-b border-border bg-muted/60 px-3 py-2">
        <span className="mono-label text-foreground/45">{comparison.field}</span>
        <span
          className={cn(
            "mono-label",
            unreadable
              ? "text-verdict-quiet"
              : comparison.match
                ? "text-verdict-verified"
                : "text-verdict-fraud",
          )}
        >
          {unreadable ? "unreadable" : comparison.match ? "matches" : "differs"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-px bg-border">
        <div className="bg-card px-3 py-2.5">
          <p className="mono-label text-foreground/40">this document</p>
          <p
            className={cn(
              "mt-1.5 font-mono text-sm break-words",
              comparison.match === false ? "text-verdict-fraud" : "text-foreground/80",
            )}
          >
            {renderValue(comparison.extracted_value)}
          </p>
        </div>
        <div className="bg-card px-3 py-2.5">
          <p className="mono-label text-foreground/40">on record</p>
          <p className="mt-1.5 font-mono text-sm break-words text-verdict-verified">
            {renderValue(comparison.filed_value)}
          </p>
        </div>
      </div>

      {comparison.message ? (
        <p className="border-t border-border bg-muted/40 px-3 py-2 font-serif text-xs text-foreground/55">
          {comparison.message}
        </p>
      ) : null}

      {unreadable ? (
        <p className="border-t border-border bg-muted/40 px-3 py-2 font-serif text-xs text-foreground/45 italic">
          Read confidence is UNREADABLE, so this field cannot produce a tamper finding.
        </p>
      ) : null}
    </div>
  );
}

export function LiveResult({ result }: { result: EngineVerdictResponse }) {
  const tone = engineVerdictTone[result.verdict];
  const meta = verdictMeta[tone];
  const checks = Object.entries(result.checks ?? {});

  return (
    <div className="space-y-5">
      <div className={cn("rounded-xl border p-5 sm:p-6", meta.border, meta.bg)}>
        <div className="flex flex-wrap items-center gap-3">
          {/* Colour comes from the tone map; the wording is always the API's. */}
          <VerdictBadge verdict={tone} size="lg" className="hidden" />
          <span
            className={cn(
              "mono-label inline-flex items-center gap-2.5 rounded-full border px-3.5 py-1.5 text-sm",
              meta.border,
              meta.bg,
              meta.text,
            )}
          >
            <span className={cn("size-1.5 rounded-full", meta.dot)} aria-hidden />
            {result.label || result.verdict}
          </span>
          <span className="ml-auto font-mono text-xs text-foreground/40">
            {result.latency_ms} ms · live engine
          </span>
        </div>

        <p className="mt-4 font-serif text-lg leading-snug">{result.summary}</p>

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-current/10 pt-4">
          <span className="font-mono text-[0.6875rem] text-foreground/45">
            evidence available {result.confidence}%
          </span>
          <span className="font-mono text-[0.6875rem] text-foreground/45">
            {result.source_type.toLowerCase()}
          </span>
          <span className="font-mono text-[0.6875rem] text-foreground/45">
            {result.content_hash.slice(0, 16)}
          </span>
        </div>
        <p className="mt-2 font-serif text-xs text-foreground/45 italic">
          Confidence is how much the engine could see, not how bad the message is. A low
          number means evidence was thin.
        </p>
      </div>

      {result.matched_filing && result.matched_filing.tier !== "NONE" ? (
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2.5">
            <FileText className="size-4 text-primary" aria-hidden />
            <h3 className="mono-label text-foreground/45">matched filing</h3>
            <span className="mono-label ml-auto text-foreground/35">
              tier {result.matched_filing.tier} · {result.matched_filing.score.toFixed(2)}
            </span>
          </div>
          <p className="mt-3 text-[0.9375rem] font-medium">
            {result.matched_filing.headline ?? result.matched_filing.filing_type ?? "Filing"}
          </p>
          <p className="mt-1.5 font-mono text-xs text-foreground/50">
            {[
              result.matched_filing.company_name,
              result.matched_filing.exchange,
              result.matched_filing.filing_date,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p className="mt-2 font-serif text-xs text-foreground/45 italic">
            Ranked by {result.matched_filing.ranking_method} from{" "}
            {result.matched_filing.candidates_considered} candidates.
          </p>
          {result.matched_filing.notes?.length ? (
            <ul className="mt-2 space-y-1">
              {result.matched_filing.notes.map((note) => (
                <li key={note} className="font-mono text-[0.6875rem] text-foreground/40">
                  · {note}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {result.field_comparisons.length > 0 ? (
        <div>
          <h3 className="mono-label text-foreground/45">
            field comparisons · {result.field_comparisons.length}
          </h3>
          <div className="mt-3 space-y-3">
            {result.field_comparisons.map((comparison) => (
              <ComparisonRow key={comparison.field} comparison={comparison} />
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <h3 className="mono-label text-foreground/45">reasons · {result.reasons.length}</h3>
        <div className="mt-3 space-y-3">
          {result.reasons.length > 0 ? (
            result.reasons.map((reason) => {
              const tier = severityTier(reason.severity);
              return (
                <article key={reason.code} className="rounded-lg border border-border bg-card p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn("mono-label rounded-full border px-2 py-0.5", tierClass[tier])}
                    >
                      {tier}
                    </span>
                    <span className="font-mono text-[0.6875rem] text-foreground/35">
                      {reason.code}
                    </span>
                    <span className="ml-auto font-mono text-[0.6875rem] text-foreground/35">
                      severity {reason.severity}
                    </span>
                  </div>
                  <p className="mt-3 font-serif text-[0.9375rem] leading-relaxed text-foreground/75">
                    {reason.message}
                  </p>
                  {Object.keys(reason.evidence ?? {}).length > 0 ? (
                    <dl className="mt-3 space-y-1 border-t border-border pt-3">
                      {Object.entries(reason.evidence).map(([key, value]) => (
                        <div key={key} className="flex gap-3">
                          <dt className="mono-label shrink-0 text-foreground/35">{key}</dt>
                          <dd className="font-mono text-[0.6875rem] break-all text-foreground/55">
                            {renderValue(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                </article>
              );
            })
          ) : (
            <p className="rounded-lg border border-border bg-card p-4 font-serif text-sm text-foreground/55">
              No reason fired. That is the absence of a finding, not a clean bill of health.
            </p>
          )}
        </div>
      </div>

      {result.recommended_actions.length > 0 ? (
        <div>
          <h3 className="mono-label text-foreground/45">what to do next</h3>
          <ul className="mt-3 space-y-2">
            {result.recommended_actions.map((action) => (
              <li key={action.title} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2">
                  <span className="mono-label text-primary">{action.priority}</span>
                  <span className="mono-label text-foreground/35">{action.type}</span>
                </div>
                <p className="mt-2 text-[0.9375rem] font-medium">{action.title}</p>
                <p className="mt-1.5 font-serif text-sm leading-relaxed text-foreground/65">
                  {action.detail}
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {checks.length > 0 ? (
        <div>
          <h3 className="mono-label text-foreground/45">checks</h3>
          <ul className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
            {checks.map(([name, value]) => {
              const passed = value === true || value === "pass" || value === "PASS";
              const skipped = value === null || value === "unavailable";
              return (
                <li
                  key={name}
                  className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0"
                >
                  {skipped ? (
                    <CircleSlash className="size-4 shrink-0 text-foreground/25" aria-hidden />
                  ) : passed ? (
                    <CircleCheck className="size-4 shrink-0 text-verdict-verified" aria-hidden />
                  ) : (
                    <CircleAlert className="size-4 shrink-0 text-verdict-fraud" aria-hidden />
                  )}
                  <span className="font-mono text-xs">{name}</span>
                  <span className="ml-auto text-right font-mono text-[0.6875rem] text-foreground/45">
                    {renderValue(value)}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 font-serif text-xs text-foreground/45 italic">
            A check that could not run is excluded from the verdict. It is never counted as
            evidence of innocence.
          </p>
        </div>
      ) : null}

      {result.content_hash ? (
        <a
          href={warningCardUrl(result.content_hash)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 text-sm text-primary underline-offset-4 hover:underline"
        >
          Open the shareable warning card
        </a>
      ) : null}
    </div>
  );
}
