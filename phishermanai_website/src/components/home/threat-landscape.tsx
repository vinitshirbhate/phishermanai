import { Section, SectionHeading } from "@/components/site/section";
import { threatVectors } from "@/lib/content";

export function ThreatLandscape() {
  return (
    <Section id="threat" tone="navy">
      <SectionHeading
        eyebrow="What changed"
        title="The cues investors were taught to look for"
        accent="do not exist any more."
        lead="Bad grammar, generic salutations, a robotic voice, an obviously edited video. Every one of those tells has been removed by generative models that are cheap to run and produce a million non-identical variants."
      />

      <div className="mt-14 grid gap-px overflow-hidden rounded-xl border border-cream/12 bg-cream/10 md:grid-cols-2">
        {threatVectors.map((vector) => (
          <article key={vector.channel} className="bg-navy p-6 sm:p-7">
            <div className="flex items-center gap-3">
              <vector.icon className="size-4.5 text-primary" aria-hidden />
              <h3 className="text-base font-medium text-cream">{vector.channel}</h3>
            </div>
            <p className="mt-4 font-serif text-[1.0625rem] leading-relaxed text-cream/85">
              {vector.what}
            </p>
            <p className="copy mt-3 text-[1rem] text-cream/55">{vector.why}</p>
          </article>
        ))}
      </div>

      <div className="mt-10 grid gap-6 rounded-xl border border-primary/25 bg-primary/8 p-6 sm:grid-cols-[1fr_auto] sm:items-center sm:p-8">
        <p className="font-serif text-lg leading-relaxed text-cream/85 italic">
          And a second gap sits opposite the first: there is no reliable way to confirm that a
          notice really is from SEBI, an exchange, a listed company or a registered intermediary.
          That absence is what makes every attack above land harder.
        </p>
        <p className="mono-label text-primary sm:w-40 sm:text-right">
          the two dimensions are one problem
        </p>
      </div>
    </Section>
  );
}
