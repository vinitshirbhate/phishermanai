import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The dark UI-mockup frame that recurs across the page: navy ground, faint
 * blueprint grid, monospace label in the header bar.
 */
export function TerminalCard({
  label,
  meta,
  footer,
  className,
  bodyClassName,
  children,
}: {
  label: string;
  meta?: ReactNode;
  footer?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "dark grid-lines overflow-hidden rounded-xl border border-cream/12 bg-navy text-cream shadow-[0_24px_60px_-24px_rgba(16,27,40,0.55)]",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-4 border-b border-cream/10 bg-navy-sunk/60 px-4 py-2.5">
        <span className="mono-label text-primary">{`// ${label}`}</span>
        {meta ? <span className="mono-label text-cream/40">{meta}</span> : null}
      </div>
      <div className={cn("p-4 sm:p-5", bodyClassName)}>{children}</div>
      {footer ? (
        <div className="border-t border-cream/10 bg-navy-sunk/40 px-4 py-2.5">{footer}</div>
      ) : null}
    </div>
  );
}

export function TerminalRow({
  label,
  value,
  state = "neutral",
}: {
  label: string;
  value: ReactNode;
  state?: "neutral" | "pass" | "fail" | "warn" | "muted";
}) {
  const stateClass = {
    neutral: "text-cream",
    pass: "text-verdict-verified",
    fail: "text-verdict-fraud",
    warn: "text-verdict-tampered",
    muted: "text-cream/40",
  }[state];

  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-cream/8 py-2 last:border-b-0">
      <span className="mono-label text-cream/45">{label}</span>
      <span className={cn("font-mono text-[0.8125rem]", stateClass)}>{value}</span>
    </div>
  );
}
