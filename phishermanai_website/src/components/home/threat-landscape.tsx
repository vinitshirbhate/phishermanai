import { CornerFrame } from "@/components/site/corner-frame";
import { RevealGroup, RevealItem } from "@/components/site/motion";
import { Section, SectionHeading } from "@/components/site/section";
import { threatVectors } from "@/lib/content";

export function ThreatLandscape() {
  return (
    <Section id="threat" tone="navy">
      <SectionHeading
        eyebrow="What changed"
        title="The tells investors were taught to spot"
        accent="don't exist any more."
        lead="Bad grammar, robotic voices, obviously edited video — generative models erased every one of those cues, and produce a million non-identical variants for free."
      />

      <RevealGroup
        className="mt-14 grid gap-px overflow-hidden border border-cream/12 bg-cream/10 md:grid-cols-2"
        stagger={0.08}
      >
        {threatVectors.map((vector) => (
          <RevealItem key={vector.channel}>
            <article className="h-full bg-navy p-6 sm:p-7">
              <div className="flex items-center gap-3">
                <span className="grid size-8 place-items-center border border-primary/25 bg-primary/10 text-primary">
                  <vector.icon className="size-4" aria-hidden />
                </span>
                <h3 className="text-base font-medium text-cream">{vector.channel}</h3>
              </div>
              <p className="mt-4 font-serif text-[1.0625rem] leading-relaxed text-cream/85">
                {vector.what}
              </p>
              <p className="copy mt-3 text-[1rem] text-cream/55">{vector.why}</p>
            </article>
          </RevealItem>
        ))}
      </RevealGroup>

      <CornerFrame className="mt-10">
        <div className="grid gap-6 border border-primary/25 bg-primary/8 p-6 sm:grid-cols-[1fr_auto] sm:items-center sm:p-8">
          <p className="font-serif text-lg leading-relaxed text-cream/85">
            A second gap sits opposite the first: no reliable way to confirm a notice really is
            from SEBI, an exchange, a listed company or a registered intermediary.
          </p>
          <p className="mono-label text-primary sm:w-40 sm:text-right">
            one problem, two halves
          </p>
        </div>
      </CornerFrame>
    </Section>
  );
}
