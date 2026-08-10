import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { Reveal, RevealGroup, RevealItem } from "@/components/site/motion";
import { Section, SectionHeading } from "@/components/site/section";
import { halves } from "@/lib/content";

export function DualThreat() {
  return (
    <Section id="halves">
      <SectionHeading
        eyebrow="Two halves, weighted equally"
        title="Catching the fake is half the job."
        accent="Confirming the real thing is the other half."
        lead="A system that only flags teaches people to distrust everything, including genuine notices. Both halves ship. Both are measured."
        align="center"
      />

      <RevealGroup className="mt-14 grid gap-6 lg:grid-cols-2" stagger={0.1}>
        {halves.map((half) => (
          <RevealItem key={half.title}>
            <article className="flex h-full flex-col border border-border bg-card p-7 sm:p-8">
              <div className="flex items-center gap-3">
                <span className="grid size-10 place-items-center border border-primary/25 bg-primary/8 text-primary">
                  <half.icon className="size-5" aria-hidden />
                </span>
                <span className="mono-label text-foreground/40">{half.kicker}</span>
              </div>

              <h3 className="mt-6 text-xl font-medium sm:text-2xl">{half.title}</h3>
              <p className="copy mt-4">{half.body}</p>

              <ul className="mt-6 space-y-2.5 border-t border-border pt-6">
                {half.points.map((point) => (
                  <li key={point} className="flex gap-2.5">
                    <Check className="mt-1 size-3.5 shrink-0 text-primary" aria-hidden />
                    <span className="font-serif text-[0.9375rem] leading-relaxed text-foreground/65">
                      {point}
                    </span>
                  </li>
                ))}
              </ul>
            </article>
          </RevealItem>
        ))}
      </RevealGroup>

      <Reveal delay={0.15}>
        <p className="mx-auto mt-12 max-w-2xl text-center font-serif text-foreground/55">
          A cloned voice is convincing because the caller cites a circular you cannot check —{" "}
          <Link href="/#authenticity" className="text-primary underline-offset-4 hover:underline">
            being able to check it
            <ArrowRight className="ml-1 inline size-3.5" aria-hidden />
          </Link>{" "}
          removes the leverage.
        </p>
      </Reveal>
    </Section>
  );
}
