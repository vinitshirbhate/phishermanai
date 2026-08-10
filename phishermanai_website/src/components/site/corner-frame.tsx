import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const tick = "absolute size-2.5 border-foreground/25";

/**
 * Spec-sheet chrome: an optional measurement rule with a width label above
 * the frame, and L-shaped hairline ticks at all four corners of the frame.
 */
export function CornerFrame({
  children,
  className,
  label,
}: {
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <div className={className}>
      {label ? (
        <div className="mb-3 flex items-center gap-3 text-foreground/35">
          <span className="h-px flex-1 bg-border" />
          <span className="font-mono text-[0.6875rem] tracking-[0.14em]">{label}</span>
          <span className="h-px flex-1 bg-border" />
        </div>
      ) : null}
      <div className="relative">
        <span className={cn(tick, "-top-1 -left-1 border-t border-l")} aria-hidden />
        <span className={cn(tick, "-top-1 -right-1 border-t border-r")} aria-hidden />
        <span className={cn(tick, "-bottom-1 -left-1 border-b border-l")} aria-hidden />
        <span className={cn(tick, "-bottom-1 -right-1 border-b border-r")} aria-hidden />
        {children}
      </div>
    </div>
  );
}
