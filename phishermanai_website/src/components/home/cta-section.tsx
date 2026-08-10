import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Reveal } from "@/components/site/motion";
import { Section } from "@/components/site/section";
import { Stamp } from "@/components/site/stamp";
import { Button } from "@/components/ui/button";

export function CtaSection() {
  return (
    <Section tone="navy" className="grid-lines py-24 sm:py-32">
      <Reveal className="mx-auto max-w-3xl text-center">
        <p className="eyebrow justify-center">Both halves, in one console</p>
        <h2 className="h-section mt-5 text-cream">
          Four outcomes, never two.
          <br className="hidden sm:block" />{" "}
          <span className="h-accent">Including the one that says “I don&rsquo;t know.”</span>
        </h2>
        <p className="copy-lg mx-auto mt-6 max-w-2xl text-cream/65">
          Watch a genuine circular get confirmed, a real one caught with a single figure altered
          — then paste your own text and watch the rules run, live, in your browser.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Button asChild className="h-11 rounded-full px-6 text-[0.9375rem]">
            <Link href="/demo">
              Open the demo
              <ArrowRight />
            </Link>
          </Button>
          <Button
            variant="outline"
            asChild
            className="h-11 rounded-full border-cream/25 px-6 text-[0.9375rem]"
          >
            <Link href="/evidence">Read the evidence</Link>
          </Button>
        </div>

        <div className="mt-10 flex justify-center">
          <Stamp className="border-cream/40 text-cream">
            377 tests · 5 CI gates · 0 false accusations
          </Stamp>
        </div>
      </Reveal>
    </Section>
  );
}
