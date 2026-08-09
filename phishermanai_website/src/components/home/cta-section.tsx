import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Section } from "@/components/site/section";
import { Button } from "@/components/ui/button";

export function CtaSection() {
  return (
    <Section tone="navy" className="py-24 sm:py-32">
      <div className="mx-auto max-w-3xl text-center">
        <p className="eyebrow">Both halves, in one console</p>
        <h2 className="h-section mt-5 text-cream">
          Four outcomes, never two.
          <br className="hidden sm:block" />{" "}
          <span className="h-accent">Including the one that says “I don&rsquo;t know”.</span>
        </h2>
        <p className="copy-lg mx-auto mt-6 max-w-2xl text-cream/65">
          Watch a genuine circular get confirmed, a real one caught with a single figure altered,
          and a message the system honestly cannot judge — then paste your own text and see the
          rules run in your browser.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Button asChild className="h-11 rounded-lg px-6 text-[0.9375rem]">
            <Link href="/demo">
              Open the demo
              <ArrowRight />
            </Link>
          </Button>
          <Button
            variant="outline"
            asChild
            className="h-11 rounded-lg border-cream/25 px-6 text-[0.9375rem]"
          >
            <Link href="/evidence">Read the evidence</Link>
          </Button>
        </div>

        <p className="mt-8 font-mono text-xs text-cream/35">
          five channels · six verification layers · 377 tests · 5 CI gates · false accusations: 0
        </p>
      </div>
    </Section>
  );
}
