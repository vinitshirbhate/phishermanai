import { type VerdictCode, verdictMeta } from "@/lib/analysis";
import { cn } from "@/lib/utils";

export function VerdictBadge({
  verdict,
  size = "default",
  className,
}: {
  verdict: VerdictCode;
  size?: "sm" | "default" | "lg";
  className?: string;
}) {
  const meta = verdictMeta[verdict];
  const sizing = {
    sm: "gap-1.5 px-2 py-0.5 text-[0.6875rem]",
    default: "gap-2 px-2.5 py-1 text-xs",
    lg: "gap-2.5 px-3.5 py-1.5 text-sm",
  }[size];

  return (
    <span
      className={cn(
        "mono-label inline-flex items-center rounded-full border",
        sizing,
        meta.border,
        meta.bg,
        meta.text,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", meta.dot)} aria-hidden />
      {meta.label}
    </span>
  );
}
