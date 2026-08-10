import Image from "next/image";
import Link from "next/link";

import { cn } from "@/lib/utils";

/** The knot mark — detection and verification, interlocked into one shape. */
export function LogoMark({ className, spin = true }: { className?: string; spin?: boolean }) {
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-full border border-cream/40 bg-cream/80 p-1.5 shadow-[0_1px_0_0_rgba(16,27,40,0.06)] backdrop-blur-sm",
        className,
      )}
    >
      <Image
        src="/brand/phisherman-mark.png"
        alt=""
        width={40}
        height={40}
        priority
        className={cn("size-full object-contain", spin && "animate-spin-slow")}
      />
    </span>
  );
}

export function Logo({ className, markClassName }: { className?: string; markClassName?: string }) {
  return (
    <Link
      href="/"
      aria-label={`${"PhishermanAI"} — home`}
      className={cn(
        "group flex items-center gap-2.5 rounded-full outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      <LogoMark className={cn("size-9", markClassName)} />
      <span className="text-[1.0625rem] font-medium tracking-[-0.02em]">
        Phisherman<span className="text-primary">AI</span>
      </span>
    </Link>
  );
}
