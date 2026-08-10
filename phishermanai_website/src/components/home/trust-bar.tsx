import { accreditations, dataSources } from "@/lib/content";
import { RevealGroup, RevealItem } from "@/components/site/motion";

/** A full-width ink ticker — plain-text sources, not customer logos. */
export function TrustBar() {
  const doubled = [...dataSources, ...dataSources];
  return (
    <div className="dark overflow-hidden border-y border-cream/12 bg-navy py-4">
      <p className="mono-label container-page mb-3 text-cream/35">checked against public data from</p>
      <div className="flex w-max animate-marquee items-center gap-8">
        {doubled.map((source, i) => (
          <span
            key={`${source}-${i}`}
            className="flex items-center gap-8 font-mono text-[0.8125rem] tracking-[0.02em] text-cream/55"
          >
            {source}
            <span className="size-1.5 bg-primary" aria-hidden />
          </span>
        ))}
      </div>
    </div>
  );
}

export function AccreditationRow() {
  return (
    <div className="container-page py-14 sm:py-16">
      <RevealGroup className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4" stagger={0.07}>
        {accreditations.map((item) => (
          <RevealItem key={item.label} className="flex gap-4">
            <span className="mt-0.5 grid size-10 shrink-0 place-items-center border border-primary/25 bg-primary/8 text-primary">
              <item.icon className="size-5" aria-hidden />
            </span>
            <div>
              <p className="text-[0.9375rem] font-medium">{item.label}</p>
              <p className="mt-1.5 font-serif text-sm leading-relaxed text-foreground/55">
                {item.caption}
              </p>
            </div>
          </RevealItem>
        ))}
      </RevealGroup>
    </div>
  );
}
