import Link from "next/link";

import { cn } from "@/lib/utils";

/** A fish hook read as a check mark — the product's two halves in one mark. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 28 28"
      fill="none"
      aria-hidden="true"
      className={cn("size-7", className)}
    >
      <rect width="28" height="28" rx="7" className="fill-navy" />
      <path
        d="M18.5 6.5v8.2a5.2 5.2 0 1 1-10.4 0"
        stroke="#e6500f"
        strokeWidth="2.1"
        strokeLinecap="round"
      />
      <path d="M15.6 8.9 18.5 6l2.9 2.9" stroke="#f6ede4" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="8.1" cy="20.9" r="1.6" fill="#e6500f" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "group flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      <LogoMark />
      <span className="text-[1.0625rem] font-medium tracking-[-0.02em]">
        Phisherman<span className="text-primary">AI</span>
      </span>
    </Link>
  );
}
