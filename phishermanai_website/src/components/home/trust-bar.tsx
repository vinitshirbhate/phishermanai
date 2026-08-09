import { accreditations, dataSources } from "@/lib/content";

export function TrustBar() {
  return (
    <div className="border-y border-border bg-cream-sunk/40">
      <div className="container-page py-8">
        <p className="mono-label text-center text-foreground/40">
          checked against public data from
        </p>
        <ul className="mt-5 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 sm:gap-x-12">
          {dataSources.map((source) => (
            <li
              key={source}
              className="font-sans text-[0.9375rem] font-medium tracking-[-0.01em] text-foreground/35 transition-colors hover:text-foreground/60"
            >
              {source}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function AccreditationRow() {
  return (
    <div className="container-page py-14 sm:py-16">
      <ul className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
        {accreditations.map((item) => (
          <li key={item.label} className="flex gap-4">
            <span className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/8 text-primary">
              <item.icon className="size-5" aria-hidden />
            </span>
            <div>
              <p className="text-[0.9375rem] font-medium">{item.label}</p>
              <p className="mt-1.5 font-serif text-sm leading-relaxed text-foreground/55">
                {item.caption}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
