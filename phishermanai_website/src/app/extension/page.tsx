import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Download } from "lucide-react";

import { Reveal, RevealGroup, RevealItem } from "@/components/site/motion";
import { PageHeader, Section, SectionHeading } from "@/components/site/section";
import { SpeedVideo } from "@/components/site/speed-video";
import { Button } from "@/components/ui/button";
import { getChannel, lanes } from "@/lib/content";

export const metadata: Metadata = {
  title: "Browser extension",
  description:
    "Download the PhishermanAI Chrome extension — checks the page you're on against SEBI's real registers, offline, in about 0.1 ms.",
};

const ZIP_HREF = "/extension/phisherman-extension-V07.zip";

const steps = [
  {
    title: "Download it",
    body: "Grab the .zip below and unzip it wherever you like. No installer, no account, nothing to sign up for.",
  },
  {
    title: "Open Chrome's extensions page",
    body: "Type chrome://extensions into your address bar and hit enter. Then flip on Developer mode, top-right corner.",
  },
  {
    title: "Load it up",
    body: "Click Load unpacked, then pick the folder you just unzipped. That's the whole install.",
  },
  {
    title: "You're covered",
    body: "The icon shows up next to your address bar. From here it checks pages for you automatically — nothing else to click.",
  },
];

const checks = [
  {
    title: "It loaded cleanly",
    body: "chrome://extensions shows “PhishermanAI” with no errors, and the toolbar icon appears next to the address bar.",
  },
  {
    title: "It catches a registration collision",
    body: "Browse to a page or message claiming a SEBI registration number. If that number belongs to someone else, the side panel names the mismatch — not just a red badge.",
  },
  {
    title: "It still works offline",
    body: "Turn your network off, then reload the page. The registration lookup runs on-device in about 0.1 ms, so the verdict still comes back, with an “offline check” note attached.",
  },
];

const web = getChannel("web");

export default function ExtensionPage() {
  return (
    <>
      <PageHeader eyebrow="Browser extension" title="See the warning" accent="before you click, install, or pay." lead={web.summary}>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild className="h-11 rounded-full px-6 text-[0.9375rem]">
            <a href={ZIP_HREF} download>
              Download the extension
              <Download />
            </a>
          </Button>
          <Button variant="outline" asChild className="h-11 rounded-full border-foreground/20 px-6 text-[0.9375rem]">
            <Link href="#install">See how to install it</Link>
          </Button>
        </div>
        <p className="mono-label mt-5 text-foreground/35">v0.6 · 252 KB · unsigned · no telemetry</p>
      </PageHeader>

      <Section id="install" tone="navy" className="py-14 sm:py-16">
        <div className="relative">
          <div
            className="absolute top-5 left-5 right-5 hidden h-px bg-cream/15 sm:block"
            aria-hidden
          />
          <RevealGroup className="relative grid gap-8 sm:grid-cols-4" stagger={0.1}>
            {steps.map((step, i) => (
              <RevealItem key={step.title}>
                <span className="relative z-10 grid size-10 place-items-center rounded-full border-2 border-primary bg-navy font-mono text-sm font-semibold text-primary">
                  {i + 1}
                </span>
                <h3 className="mt-4 text-base font-medium text-cream">{step.title}</h3>
                <p className="copy mt-1.5 text-[0.9375rem] text-cream/60">{step.body}</p>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </Section>

      <Section className="pt-10 pb-16 sm:pt-12 sm:pb-20">
        <Reveal>
          <div className="mx-auto max-h-[34rem] max-w-4xl overflow-hidden rounded-[2rem] bg-navy shadow-[0_32px_64px_-32px_rgba(16,27,40,0.4)]">
            <SpeedVideo
              src="/extension/upscaled-video.mp4"
              rate={1.5}
              className="max-h-[34rem] w-full object-contain"
            />
          </div>
        </Reveal>
      </Section>

      <Section>
        <SectionHeading
          eyebrow="What it actually watches"
          title="Four lanes,"
          accent="one question each."
          lead="Each one minds its own business and reports back on its own — nothing gets mashed into a single, unexplained score."
        />

        <RevealGroup
          className="mt-12 grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2"
          stagger={0.07}
        >
          {lanes.map((lane) => (
            <RevealItem key={lane.name}>
              <article className="h-full bg-card p-6">
                <div className="flex items-center gap-3">
                  <span className="grid size-9 place-items-center border border-primary/25 bg-primary/8 text-primary">
                    <lane.icon className="size-4.5" aria-hidden />
                  </span>
                  <h3 className="text-base font-medium">{lane.name}</h3>
                  <span className="ml-auto font-mono text-[0.6875rem] text-foreground/30">
                    {lane.path}
                  </span>
                </div>
                <p className="mt-4 font-serif text-[0.9375rem] text-foreground/75">
                  {lane.question}
                </p>
                <p className="copy mt-2 text-[1rem]">{lane.how}</p>
              </article>
            </RevealItem>
          ))}
        </RevealGroup>
      </Section>

      <Section tone="navy">
        <SectionHeading
          eyebrow="Test it yourself"
          title="Three quick checks,"
          accent="all on your own machine."
          lead="Nothing to fake, nothing to take our word for — you can watch every one of these happen yourself."
        />

        <RevealGroup className="mt-12 space-y-4" stagger={0.08}>
          {checks.map((check, i) => (
            <RevealItem key={check.title}>
              <div className="grid gap-4 border border-cream/12 bg-navy-raised p-6 sm:grid-cols-[3rem_1fr] sm:gap-6">
                <span className="mono-label h-fit text-cream/35">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="text-[0.9375rem] font-medium text-cream">{check.title}</h3>
                  <p className="copy mt-2 text-[1rem] text-cream/60">{check.body}</p>
                </div>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </Section>

      <Section>
        <div className="flex flex-col items-start justify-between gap-8 border border-border bg-card p-8 sm:flex-row sm:items-center sm:p-10">
          <div className="max-w-xl">
            <h2 className="text-2xl font-medium">Ready when you are</h2>
            <p className="copy mt-3">
              Or read the{" "}
              <Link href="/#channel-web" className="text-primary underline-offset-4 hover:underline">
                detection evidence
              </Link>{" "}
              first, if that&rsquo;s how you&rsquo;d rather start.
            </p>
          </div>
          <Button asChild className="h-11 shrink-0 rounded-full px-6 text-[0.9375rem]">
            <a href={ZIP_HREF} download>
              Download the extension
              <ArrowRight />
            </a>
          </Button>
        </div>
      </Section>
    </>
  );
}
