import { Section, SectionHeading } from "@/components/site/section";
import { gates } from "@/lib/content";

export function GatesSection() {
  return (
    <Section id="gates" tone="navy">
      <div className="grid gap-12 lg:grid-cols-[1fr_1.15fr] lg:gap-16">
        <div>
          <SectionHeading
            eyebrow="The one rule everything obeys"
            title="Never cry wolf."
            accent="A tool that flags your real bank gets uninstalled by Tuesday."
            lead="This is enforced by machines, not good intentions. Five gates run in CI, and the build fails rather than shipping a claim the system cannot support."
          />

          <div className="mt-10 rounded-xl border border-cream/12 bg-navy-raised p-5">
            <p className="mono-label text-cream/40">what a clean link actually says</p>
            <pre className="mt-3 overflow-x-auto font-mono text-[0.8125rem] leading-relaxed text-cream/75">
{`Checked — www.marxists.org
Not listed on 3 blocklists covering
819,572 domains, as of 2026-03-23.
A domain registered since then
would not appear.`}
            </pre>
            <p className="mt-4 font-serif text-sm text-cream/45 italic">
              Dated, checkable, and honest about what it cannot see. Never “Safe ✓”.
            </p>
          </div>
        </div>

        <ul className="space-y-px overflow-hidden rounded-xl border border-cream/12 bg-cream/10">
          {gates.map((gate) => (
            <li key={gate.name} className="flex gap-4 bg-navy p-5 sm:p-6">
              <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                <gate.icon className="size-4.5" aria-hidden />
              </span>
              <div>
                <h3 className="text-[0.9375rem] font-medium text-cream">{gate.name}</h3>
                <p className="copy mt-2 text-[1rem] text-cream/60">{gate.what}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  );
}
