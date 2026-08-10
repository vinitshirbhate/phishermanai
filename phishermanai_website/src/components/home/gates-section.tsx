import { CornerFrame } from "@/components/site/corner-frame";
import { Reveal, RevealGroup, RevealItem } from "@/components/site/motion";
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
            lead="Enforced by machines, not good intentions. Five gates run in CI — the build fails rather than ship a claim the system can't support."
          />

          <Reveal delay={0.1}>
            <CornerFrame className="mt-10" label="SAMPLE OUTPUT">
              <div className="border border-cream/12 bg-navy-raised p-5">
                <p className="mono-label text-cream/40">what a clean link actually says</p>
                <pre className="mt-3 overflow-x-auto font-mono text-[0.8125rem] leading-relaxed text-cream/75">
{`Checked — www.marxists.org
Not listed on 3 blocklists covering
819,572 domains, as of 2026-03-23.
A domain registered since then
would not appear.`}
                </pre>
                <p className="mt-4 font-serif text-sm text-cream/45">
                  Dated and checkable. Never “Safe ✓”.
                </p>
              </div>
            </CornerFrame>
          </Reveal>
        </div>

        <RevealGroup
          className="space-y-px overflow-hidden border border-cream/12 bg-cream/10"
          stagger={0.06}
        >
          {gates.map((gate) => (
            <RevealItem key={gate.name}>
              <div className="flex gap-4 bg-navy p-5 sm:p-6">
                <span className="mt-0.5 grid size-9 shrink-0 place-items-center border border-primary/25 bg-primary/10 text-primary">
                  <gate.icon className="size-4.5" aria-hidden />
                </span>
                <div>
                  <h3 className="text-[0.9375rem] font-medium text-cream">{gate.name}</h3>
                  <p className="copy mt-2 text-[1rem] text-cream/60">{gate.what}</p>
                </div>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </Section>
  );
}
