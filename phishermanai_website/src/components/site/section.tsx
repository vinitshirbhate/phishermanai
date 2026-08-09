import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type Tone = "cream" | "raised" | "navy";

const toneClass: Record<Tone, string> = {
  cream: "bg-background text-foreground",
  raised: "bg-cream-sunk/50 text-foreground",
  // `.dark` flips every shadcn token for the primitives nested inside.
  navy: "dark bg-navy text-cream",
};

export function Section({
  id,
  tone = "cream",
  className,
  children,
}: {
  id?: string;
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={cn("scroll-mt-24 py-20 sm:py-28", toneClass[tone], className)}
    >
      <div className="container-page">{children}</div>
    </section>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("eyebrow", className)}>{children}</p>;
}

export function SectionHeading({
  eyebrow,
  title,
  accent,
  lead,
  align = "left",
  className,
  children,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  accent?: ReactNode;
  lead?: ReactNode;
  align?: "left" | "center";
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "max-w-3xl",
        align === "center" && "mx-auto text-center",
        className,
      )}
    >
      {eyebrow ? <Eyebrow className="mb-4">{eyebrow}</Eyebrow> : null}
      <h2 className="h-section">
        {title}
        {accent ? (
          <>
            {" "}
            <span className="h-accent">{accent}</span>
          </>
        ) : null}
      </h2>
      {lead ? <p className="copy-lg mt-6">{lead}</p> : null}
      {children}
    </div>
  );
}

/** The masthead every inner page opens with. */
export function PageHeader({
  eyebrow,
  title,
  accent,
  lead,
  children,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  accent?: ReactNode;
  lead?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="pt-12 pb-16 sm:pt-16 sm:pb-20">
      <div className="container-page">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="h-display mt-4 max-w-4xl">
          {title}
          {accent ? (
            <>
              {" "}
              <span className="h-accent">{accent}</span>
            </>
          ) : null}
        </h1>
        {lead ? <p className="copy-lg mt-6 max-w-2xl">{lead}</p> : null}
        {children}
      </div>
    </header>
  );
}

/** A hairline label + rule used to open a subsection. */
export function RuleLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      <span className="mono-label text-foreground/45">{children}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
