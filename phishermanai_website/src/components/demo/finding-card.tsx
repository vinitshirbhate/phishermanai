import { chokepointMeta, findingTierMeta, type Finding } from "@/lib/analysis";
import { cn } from "@/lib/utils";

export function FindingCard({ finding }: { finding: Finding }) {
  const tier = findingTierMeta[finding.tier];

  return (
    <article className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("mono-label rounded-full border px-2 py-0.5", tier.className)}>
          {tier.label}
        </span>
        <span className="mono-label text-foreground/35">
          {chokepointMeta[finding.chokepoint].label}
        </span>
        <span className="ml-auto font-mono text-[0.6875rem] text-foreground/35">
          severity {finding.severity}
        </span>
      </div>

      <h4 className="mt-3 text-[0.9375rem] leading-snug font-medium">{finding.title}</h4>
      <p className="mt-2 font-serif text-sm leading-relaxed text-foreground/65">
        {finding.detail}
      </p>

      {finding.comparison ? (
        <div className="mt-4 overflow-hidden rounded-md border border-border">
          <p className="mono-label border-b border-border bg-muted/60 px-3 py-2 text-foreground/45">
            {finding.comparison.field}
          </p>
          <div className="grid grid-cols-2 gap-px bg-border">
            <div className="bg-card px-3 py-2.5">
              <p className="mono-label text-foreground/40">claimed</p>
              <p className="mt-1.5 font-mono text-sm break-words text-verdict-fraud">
                {finding.comparison.claimed}
              </p>
            </div>
            <div className="bg-card px-3 py-2.5">
              <p className="mono-label text-foreground/40">on record</p>
              <p className="mt-1.5 font-mono text-sm break-words text-verdict-verified">
                {finding.comparison.filed}
              </p>
            </div>
          </div>
          <p className="border-t border-border bg-muted/40 px-3 py-2 font-mono text-[0.6875rem] text-foreground/40">
            {finding.comparison.source} · as of {finding.comparison.asOf}
          </p>
        </div>
      ) : null}
    </article>
  );
}
