import type { Stat } from "@/lib/content";
import { cn } from "@/lib/utils";

export function StatStrip({
  stats,
  className,
  columns = 4,
}: {
  stats: Stat[];
  className?: string;
  columns?: 3 | 4;
}) {
  return (
    <dl
      className={cn(
        "grid gap-px overflow-hidden rounded-xl border border-border bg-border",
        columns === 4 ? "sm:grid-cols-2 lg:grid-cols-4" : "sm:grid-cols-3",
        className,
      )}
    >
      {stats.map((stat) => (
        <div key={stat.label} className="bg-card px-5 py-6">
          <dt className="mono-label text-foreground/45">{stat.label}</dt>
          <dd className="mt-3 text-[1.75rem] leading-none font-medium tracking-[-0.03em]">
            {stat.value}
          </dd>
          {stat.caption ? (
            <p className="mt-2 font-serif text-sm text-foreground/55 italic">{stat.caption}</p>
          ) : null}
        </div>
      ))}
    </dl>
  );
}
