import type { ComponentType, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Shared chrome for the two APIF consoles.
 *
 * Both forms render the same shapes — a titled header with its endpoint, a
 * labelled field, a verdict band, a scored signal — so those live here rather
 * than being written twice and drifting apart.
 *
 * Everything is sharp-cornered on purpose: --radius is 0rem across the theme,
 * so any `rounded-*` here would be a no-op that only misleads the next reader.
 */

/** Band → palette. Written out in full because Tailwind cannot see through
 *  an interpolated class name. */
const BAND_STYLE: Record<string, { chip: string; bar: string }> = {
  low: {
    chip: "border-verdict-verified/35 bg-verdict-verified/10 text-verdict-verified",
    bar: "bg-verdict-verified",
  },
  medium: {
    chip: "border-verdict-tampered/35 bg-verdict-tampered/10 text-verdict-tampered",
    bar: "bg-verdict-tampered",
  },
  high: {
    chip: "border-primary/35 bg-primary/10 text-primary",
    bar: "bg-primary",
  },
  critical: {
    chip: "border-verdict-fraud/35 bg-verdict-fraud/10 text-verdict-fraud",
    bar: "bg-verdict-fraud",
  },
};

const FALLBACK_STYLE = {
  chip: "border-border bg-muted text-muted-foreground",
  bar: "bg-muted-foreground",
};

export function bandStyle(band: string | undefined) {
  return BAND_STYLE[(band ?? "").toLowerCase()] ?? FALLBACK_STYLE;
}

/** Icon, title, and the endpoint the panel actually calls. */
export function ConsoleHeader({
  icon: Icon,
  title,
  endpoint,
  children,
}: {
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  endpoint: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-border pb-5">
      <span className="grid size-10 shrink-0 place-items-center border border-primary/25 bg-primary/10 text-primary">
        <Icon className="size-[1.15rem]" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        {children ? (
          <p className="mt-0.5 text-sm text-foreground/55">{children}</p>
        ) : null}
      </div>
      <code className="mono-label shrink-0 border border-border bg-muted px-2.5 py-1.5 text-foreground/60">
        {endpoint}
      </code>
    </div>
  );
}

/** A labelled form control with an optional hint underneath. */
export function Field({
  htmlFor,
  label,
  hint,
  className,
  children,
}: {
  htmlFor?: string;
  label: string;
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <label htmlFor={htmlFor} className="mono-label text-foreground/50">
        {label}
      </label>
      {children}
      {hint ? <p className="text-sm text-foreground/45">{hint}</p> : null}
    </div>
  );
}

/** The verdict chip. Colour carries the meaning, the word repeats it. */
export function BandPill({ band }: { band: string }) {
  return (
    <span
      className={cn(
        "mono-label shrink-0 border px-3 py-1.5",
        bandStyle(band).chip,
      )}
    >
      {band}
    </span>
  );
}

/** One scored detector signal, with a bar so the number reads at a glance. */
export function SignalCard({
  label,
  score,
  detail,
  available = true,
}: {
  label: string;
  score: number;
  detail: string;
  available?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  const band =
    score >= 0.75 ? "critical" : score >= 0.5 ? "high" : score >= 0.25 ? "medium" : "low";

  return (
    <div
      className={cn(
        "border border-border bg-background p-4",
        !available && "opacity-55",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium">{label}</p>
        <span className="stat-figure text-base text-foreground/70">
          {score.toFixed(2)}
        </span>
      </div>
      <div className="mt-3 h-1 w-full bg-border">
        <div
          className={cn("h-full transition-[width] duration-500", bandStyle(band).bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-3 text-sm leading-6 text-foreground/60">{detail}</p>
    </div>
  );
}

/**
 * The pre-submit state. A hairline strip rather than a tall empty card — the
 * previous version reserved a full column for a sentence, which is most of the
 * dead space this page had.
 */
export function AwaitingResult({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 border border-dashed border-border bg-background/60 px-4 py-3.5">
      <span className="size-1.5 shrink-0 animate-pulse-node bg-primary" aria-hidden />
      <p className="text-sm text-foreground/55">{children}</p>
    </div>
  );
}

/** Section rule inside a result panel. */
export function ResultRule({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-4">
      <span className="mono-label text-foreground/40">{children}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p className="border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      {children}
    </p>
  );
}
