import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Braces } from "lucide-react";

import { ChannelDiagram } from "@/components/diagrams/channel-diagram";
import { PageHeader, Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import { getChannel, lanes, limitations, maturityMeta } from "@/lib/content";
import { cn } from "@/lib/utils";

const channel = getChannel("web");
const maturity = maturityMeta[channel.maturity];
const webLimitations = limitations.filter((item) => item.scope === "Web");

export const metadata: Metadata = {
  title: "Web and browser",
  description: channel.summary,
};

export default function WebChannelPage() {
  return (
    <>
      <PageHeader
        eyebrow={`Channel ${channel.index} — ${channel.name}`}
        title={channel.threatTitle}
        lead={channel.threatBody}
      >
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <span
            className={cn("mono-label rounded-full border px-2.5 py-1", maturity.className)}
          >
            {maturity.label}
          </span>
          <Button asChild className="h-10 rounded-full px-5 text-[0.875rem]">
            <Link href="/apif">
              Run it against APIF
              <ArrowRight />
            </Link>
          </Button>
        </div>
      </PageHeader>

      <Section tone="raised">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-12">
          <div>
            <SectionHeading eyebrow="Detection" title="What runs" accent="on-device, before anything is trusted." />
            <ul className="mt-8 space-y-5">
              {channel.detection.map((item) => (
                <li key={item.title}>
                  <p className="text-[0.9375rem] font-medium">{item.title}</p>
                  <p className="copy mt-1.5 text-[1rem]">{item.body}</p>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <SectionHeading
              eyebrow="Verification"
              title="What it can confirm,"
              accent="not merely fail to flag."
            />
            <ul className="mt-8 space-y-5">
              {channel.authentication.map((item) => (
                <li key={item.title}>
                  <p className="text-[0.9375rem] font-medium">{item.title}</p>
                  <p className="copy mt-1.5 text-[1rem]">{item.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      <Section>
        <SectionHeading
          eyebrow="Lanes"
          title="Four lanes watch the page"
          accent="you're actually on."
          lead="Each lane reads a different surface of the page and answers one question, without reading content it doesn't need to."
        />
        <div className="mt-12 grid gap-4 sm:grid-cols-2">
          {lanes.map((lane) => (
            <div key={lane.name} className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-3">
                <lane.icon className="size-4 text-primary" aria-hidden />
                <h3 className="text-[0.9375rem] font-medium">{lane.name}</h3>
                <span className="mono-label ml-auto text-foreground/35">{lane.path}</span>
              </div>
              <p className="mt-2.5 font-serif text-sm italic text-foreground/60">
                {lane.question}
              </p>
              <p className="copy mt-2 text-[0.9375rem]">{lane.how}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section tone="raised">
        <SectionHeading eyebrow="Evidence" title="Where this channel" accent="stands today." />
        <div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {channel.evidence.map((item) => (
            <div key={item.label} className="bg-card px-5 py-5">
              <p className="stat-figure text-[1.0625rem]">{item.value}</p>
              <p className="mono-label mt-1.5 text-foreground/40">{item.label}</p>
              {item.caption ? (
                <p className="mt-1 font-serif text-xs italic text-foreground/45">{item.caption}</p>
              ) : null}
            </div>
          ))}
        </div>
        <div className="mt-8">
          <ChannelDiagram variant="web" />
        </div>
      </Section>

      {webLimitations.length ? (
        <Section>
          <SectionHeading eyebrow="Limitations" title="Where this channel" accent="is honestly limited." />
          <div className="mt-10 space-y-6">
            {webLimitations.map((item) => (
              <div key={item.title} className="border-t border-border pt-5">
                <p className="text-[0.9375rem] font-medium">{item.title}</p>
                <p className="copy mt-1.5 text-[1rem]">{item.body}</p>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <Section tone="navy">
        <SectionHeading
          eyebrow="Try it"
          title="This channel's checks feed the same"
          accent="APIF verify pipeline as every other channel."
        />
        <div className="mt-10 flex flex-wrap gap-3">
          <Button asChild className="h-11 rounded-lg px-6 text-[0.9375rem]">
            <Link href="/apif">
              <Braces />
              Open APIF endpoints
              <ArrowRight />
            </Link>
          </Button>
          <Button
            variant="outline"
            asChild
            className="h-11 rounded-lg border-cream/25 px-6 text-[0.9375rem] text-cream hover:bg-cream/10"
          >
            <Link href="/extension">Get the extension</Link>
          </Button>
        </div>
      </Section>
    </>
  );
}
