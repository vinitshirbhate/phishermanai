import { CornerFrame } from "@/components/site/corner-frame";
import { signals } from "@/lib/content";
import { cn } from "@/lib/utils";

interface ChannelDiagramProps {
  variant: "email" | "voice" | "video" | "social" | "web";
  className?: string;
}

const labels: Record<ChannelDiagramProps["variant"], string> = {
  email: "Email & messaging",
  voice: "Voice",
  video: "Video",
  social: "Social & web",
  web: "Web",
};

export function ChannelDiagram({ variant, className }: ChannelDiagramProps) {
  return (
    <div className={cn("rounded-3xl border border-border bg-card p-8 shadow-lg", className)}>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.3em] text-foreground/50">Channel</p>
          <h2 className="mt-2 text-2xl font-semibold">{labels[variant]}</h2>
        </div>
        <div className="rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary">
          {variant.toUpperCase()}
        </div>
      </div>
      <div className="grid gap-4">
        <div className="rounded-2xl border border-border bg-background px-5 py-6">
          <p className="font-medium">Detector path</p>
          <p className="mt-2 text-sm text-foreground/70">A simplified diagram for the selected channel.</p>
        </div>
        <div className="rounded-2xl border border-border bg-background p-6">
          <p className="font-medium">Live example</p>
          <p className="mt-2 text-sm text-foreground/70">The chosen channel highlights the relevant analysis stages.</p>
        </div>
      </div>
    </div>
  );
}

/**
 * The six fused signals as proportional weight bars. Bars are scaled against the
 * heaviest signal so the shortest one stays visible — the printed figure next to
 * each is the actual weight, and those are what sum to 1.00.
 */
export function FusionDiagram({ className }: { className?: string }) {
  const heaviest = Math.max(...signals.map((signal) => signal.weight));
  const total = signals.reduce((sum, signal) => sum + signal.weight, 0);

  return (
    <CornerFrame className={className} label="FUSION — WEIGHTED MEAN">
      <div className="border border-border bg-card p-6 sm:p-7">
        <div className="space-y-4">
          {signals.map((signal) => (
            <div key={signal.name}>
              <div className="flex items-baseline justify-between gap-4">
                <div className="flex items-center gap-2.5">
                  <signal.icon className="size-3.5 shrink-0 text-primary" aria-hidden />
                  <p className="font-mono text-[0.8125rem] text-foreground/85">{signal.name}</p>
                </div>
                <p className="font-mono text-[0.8125rem] tabular-nums text-foreground/45">
                  {signal.weight.toFixed(2)}
                </p>
              </div>
              <div className="mt-2 h-1 bg-border">
                <div
                  className="h-full bg-primary"
                  style={{ width: `${(signal.weight / heaviest) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 flex items-baseline justify-between gap-4 border-t border-border pt-4">
          <p className="mono-label text-foreground/35">fused score</p>
          <p className="font-mono text-[0.8125rem] tabular-nums text-foreground/45">
            {total.toFixed(2)}
          </p>
        </div>

        <p className="copy mt-3 text-[0.9375rem]">
          A detector that was skipped or failed drops out and the remaining weights are
          renormalised back to 1.00 — never scored as a zero.
        </p>

        <p className="mono-label mt-5 border-t border-border pt-4 text-foreground/35">
          override · registry-verified + signed → capped at Low
        </p>
      </div>
    </CornerFrame>
  );
}
