import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { FusionDiagram } from "@/components/diagrams/channel-diagram";
import { PipelineFlow } from "@/components/diagrams/pipeline-flow";
import { OutcomesSection } from "@/components/home/outcomes-section";
import { PageHeader, RuleLabel, Section, SectionHeading } from "@/components/site/section";
import { TerminalCard, TerminalRow } from "@/components/site/terminal-card";
import { Button } from "@/components/ui/button";
import { pipelineStages } from "@/lib/analysis";
import { channels } from "@/lib/content";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "Six stages, four chokepoints and one comparison against the filing. Every step explained, and why it exists.",
};

const freshness = [
  { source: "BSE filings", decay: "hours", guard: "verdicts carry data_as_of" },
  { source: "SEBI registers", decay: "weeks", guard: "coverage gaps reported as gaps" },
  { source: "Scrip master", decay: "months", guard: "never auto-inserted" },
  { source: "Threat feeds", decay: "days", guard: "feed date shown, not hidden" },
];

export default function HowItWorksPage() {
  return (
    <>
      <PageHeader
        eyebrow="How it works"
        title="Content enters through one API,"
        accent="routes by type, and leaves as one of four answers."
        lead="Text, audio, video and a URL are read by different detectors and judged by the same rules. Whichever path a piece of content takes, the answer carries the register it was checked against and the date that register was read."
      />

      <Section>
        <SectionHeading
          eyebrow="Routing"
          title="One entry point,"
          accent="five detectors, one verdict shape."
          lead="The channel decides which detectors run. It never decides what a finding means, and it never changes the four outcomes a verdict can take."
        />

        <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-5">
          {channels.map((channel) => (
            <div key={channel.id} className="bg-card p-5">
              <channel.icon className="size-4.5 text-primary" aria-hidden />
              <h3 className="mt-4 text-[0.9375rem] font-medium">{channel.name}</h3>
              <p className="mono-label mt-2 text-foreground/35">{channel.index}</p>
              <p className="copy mt-3 text-[0.9375rem]">{channel.channelsAddressed.join(" · ")}</p>
            </div>
          ))}
        </div>

        <div className="mt-12 grid gap-10 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16">
          <div>
            <h3 className="text-xl font-medium sm:text-2xl">
              Independent readings, fused only at the end
            </h3>
            <p className="copy mt-4">
              Each detector scores its own channel and reports separately. Fusion is a weighted
              mean over the ones that ran — a detector that was skipped or failed is excluded and
              the remaining weights renormalised, never scored as a zero.
            </p>
            <p className="copy mt-4">
              One override sits on top: content that is registry-verified{" "}
              <span className="text-foreground">and</span> digitally signed is capped at Low. A
              signed circular is not “somewhat suspicious” because its wording scored high.
            </p>
            <p className="copy mt-4">
              The consequence worth stating: with speaker verification removed, that cap is
              unopposed, so spoofed audio from a verified signed source is held at Low. It is a
              live weakness, documented rather than hidden.
            </p>
          </div>
          <FusionDiagram />
        </div>
      </Section>

      <Section tone="raised">
        <SectionHeading
          eyebrow="The messaging path in detail"
          title="Six stages, one journey,"
          accent="and a branch that answers most mail in 10 ms."
          lead="This is the email and chat route. Every lookup goes to local data — no step on this path touches the internet, which is why it runs with the network unplugged."
        />
        <PipelineFlow className="mt-12" />

        <div className="mt-16 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-3">
          {pipelineStages.map((stage) => (
            <article key={stage.id} className="bg-card p-6">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm text-primary">{stage.index}</span>
                <h3 className="text-base font-medium">{stage.title}</h3>
              </div>
              <p className="mono-label mt-2 text-foreground/35">{stage.caption}</p>
              <p className="copy mt-3 text-[1rem]">{stage.detail}</p>
            </article>
          ))}
        </div>
      </Section>

      <Section id="short-circuit" tone="navy">
        <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="Step 03 — the gate"
              title="Most genuine mail should never reach an expensive check."
              accent="Proving the sender is cheaper than judging the text."
              lead="A valid DKIM signature that is aligned with the From: domain, on a domain in the hand-verified map, answers the question outright."
            />
            <p className="copy mt-6 max-w-xl text-cream/65">
              Alignment is the part that matters. DMARC can pass on a domain that has no right to
              the name it trades under; alignment against a domain we have separately verified is
              a different claim. 83% of genuine mail exits here in 10 ms, and the remaining 17%
              gets the full 40 ms.
            </p>
            <p className="copy mt-5 max-w-xl text-cream/65">
              Turning the short-circuit off changes the false-positive rate not at all — it is a
              latency mechanism, not a precision one. That is worth knowing, and it is why both
              were measured separately.
            </p>
          </div>

          <TerminalCard label="SHORT CIRCUIT" meta="genuine_01.eml">
            <TerminalRow label="dkim signature" value="valid" state="pass" />
            <TerminalRow label="d= domain" value="kfintech.com" state="neutral" />
            <TerminalRow label="alignment" value="relaxed · matches From:" state="pass" />
            <TerminalRow label="domain map" value="row 41 · MX verified" state="pass" />
            <TerminalRow label="checks 04–06" value="not run" state="muted" />
            <div className="mt-5 rounded-lg border border-verdict-verified/25 bg-verdict-verified/8 px-3.5 py-3">
              <p className="mono-label text-verdict-verified">verified · 10 ms</p>
              <p className="mt-2 font-serif text-sm text-cream/70 italic">
                Answered without reading a single rule.
              </p>
            </div>
          </TerminalCard>
        </div>
      </Section>

      <OutcomesSection />

      <Section id="freshness" tone="raised">
        <SectionHeading
          eyebrow="The data, and keeping it current"
          title="Different sources decay at very different rates."
          accent="Two guards make sure stale data can never accuse."
          lead="Filings go out of date in hours, the SEBI registry in weeks, the scrip master in months. A single refresh cadence would be wrong for all three."
        />

        <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {freshness.map((row) => (
            <div key={row.source} className="bg-card p-6">
              <h3 className="text-base font-medium">{row.source}</h3>
              <p className="mono-label mt-3 text-foreground/40">decays in {row.decay}</p>
              <p className="copy mt-3 text-[1rem]">{row.guard}</p>
            </div>
          ))}
        </div>

        <RuleLabel className="mt-14">the two guards</RuleLabel>
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="text-base font-medium">Beyond the horizon, no accusation</h3>
            <p className="copy mt-3 text-[1rem]">
              If the message references a corporate action more recent than the data the engine
              holds, the comparison is not attempted. A missing filing is a coverage limit, and a
              coverage limit is never reported as a finding.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="text-base font-medium">Every verdict carries its date</h3>
            <p className="copy mt-3 text-[1rem]">
              <span className="font-mono text-sm">data_as_of</span> travels with the answer, so a
              verdict read next month can be judged on how old the evidence behind it was.
            </p>
          </div>
        </div>
      </Section>

      <Section>
        <div className="flex flex-col items-start justify-between gap-8 rounded-2xl border border-border bg-card p-8 sm:flex-row sm:items-center sm:p-10">
          <div className="max-w-xl">
            <h2 className="text-2xl font-medium">Watch it run</h2>
            <p className="copy mt-3">
              Four recorded fixtures, each deep-linkable, plus a browser-only rule preview for
              text you paste yourself.
            </p>
          </div>
          <Button asChild className="h-11 shrink-0 rounded-lg px-6 text-[0.9375rem]">
            <Link href="/demo">
              Open the demo
              <ArrowRight />
            </Link>
          </Button>
        </div>
      </Section>
    </>
  );
}
