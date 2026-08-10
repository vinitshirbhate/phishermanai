import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A rotated rubber-stamp mark — the physical form of "this was verified". */
export function Stamp({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "animate-stamp inline-flex w-max -rotate-3 items-center border-2 border-primary px-3 py-1.5 font-mono text-xs font-semibold tracking-[0.14em] text-primary uppercase",
        className,
      )}
    >
      {children}
    </span>
  );
}
