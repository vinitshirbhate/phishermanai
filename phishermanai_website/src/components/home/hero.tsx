import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { AuthBadgeRow, type AuthCheckItem } from "@/components/site/auth-badge-row";
import { CornerFrame } from "@/components/site/corner-frame";
import { Reveal, RevealGroup, RevealItem } from "@/components/site/motion";
import { TerminalCard } from "@/components/site/terminal-card";
import { Button } from "@/components/ui/button";
import { channels } from "@/lib/content";
import { site } from "@/lib/site";
import { cn } from "@/lib/utils";

const readings = [
  { channel: "email", detection: "0.99 phishing", auth: "dkim aligned · no filing match" },
  { channel: "voice", detection: "0.91 synthetic", auth: "source not in registry" },
  { channel: "video", detection: "unavailable", auth: "no content credentials" },
  { channel: "social", detection: "0.31 coordinated", auth: "handle not official" },
] as const;

const authChecks: AuthCheckItem[] = [
  { code: "SPF", state: "pass", detail: "Envelope sender authorised for this domain." },
  { code: "DKIM", state: "pass", detail: "Signature valid and aligned to the From: domain." },
  { code: "DMARC", state: "pass", detail: "Policy p=reject, and this message meets it." },
  {
    code: "FILING",
    state: "fail",
    detail: "Dividend field reads ₹125.00. BSE filing says ₹12.50.",
  },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-8 pb-16 sm:pt-14 sm:pb-20">
      <div className="grid-blueprint pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent_85%)]" aria-hidden />
      <div className="pointer-events-none absolute -top-32 -right-32 size-[32rem] rounded-full bg-primary/6 blur-3xl" aria-hidden />

      <div className="container-page relative">
        <div className="grid items-start gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
          <div>
            <Reveal>
              <p className="eyebrow">{site.hackathon}</p>
            </Reveal>

            <Reveal delay={0.08}>
              <h1 className="h-display mt-5">
                Generative AI can fake the message.
                <br className="hidden sm:block" />{" "}
                <span className="h-accent">We prove whether it&rsquo;s real.</span>
              </h1>
            </Reveal>

            <Reveal delay={0.14}>
              <p className="copy-lg mt-6 max-w-xl">
                Detection across{" "}
                <span className="font-medium text-foreground">email, voice, video and social</span>{" "}
                — and a way to confirm a notice really is from SEBI, an exchange, a listed company,
                or a registered intermediary.
              </p>
            </Reveal>

            <Reveal delay={0.2}>
              <div className="mt-9 flex flex-wrap items-center gap-3">
                <Button asChild className="h-11 rounded-full px-6 text-[0.9375rem]">
                  <Link href="/demo">
                    Run the demo
                    <ArrowRight />
                  </Link>
                </Button>
                <Button
                  variant="outline"
                  asChild
                  className="h-11 rounded-full border-foreground/20 px-6 text-[0.9375rem]"
                >
                  <Link href="#channels">See all five channels</Link>
                </Button>
              </div>
            </Reveal>
          </div>

          <Reveal delay={0.16}>
            <CornerFrame label={`${site.name.toUpperCase()} · ONE INCIDENT REPLAYED`}>
              <TerminalCard
                label="ONE INCIDENT"
                meta="four channels · one campaign"
                footer={
                  <p className="font-mono text-[0.6875rem] text-cream/40">
                    data_as_of 2026-08-06 · 2 detectors excluded, weights renormalised
                  </p>
                }
              >
                <div className="grid grid-cols-[auto_1fr_1fr] items-baseline gap-x-4 gap-y-0 border-b border-cream/10 pb-2">
                  <span className="mono-label text-cream/35">channel</span>
                  <span className="mono-label text-cream/35">detection</span>
                  <span className="mono-label text-cream/35">verification</span>
                </div>

                {readings.map((row) => {
                  const unavailable = row.detection === "unavailable";
                  return (
                    <div
                      key={row.channel}
                      className="grid grid-cols-[auto_1fr_1fr] items-baseline gap-x-4 border-b border-cream/8 py-2.5 last:border-b-0"
                    >
                      <span className="w-12 font-mono text-[0.75rem] text-cream/70">
                        {row.channel}
                      </span>
                      <span
                        className={cn(
                          "font-mono text-[0.75rem]",
                          unavailable ? "text-cream/30" : "text-verdict-fraud",
                        )}
                      >
                        {row.detection}
                      </span>
                      <span className="font-mono text-[0.75rem] text-verdict-tampered">
                        {row.auth}
                      </span>
                    </div>
                  );
                })}
              </TerminalCard>
            </CornerFrame>

            <div className="mt-4 border border-border bg-card px-4 py-4 sm:px-5">
              <p className="mono-label text-foreground/40">the email that started it</p>
              <AuthBadgeRow items={authChecks} className="mt-3 border-x-0 border-t-0" />
              <p className="copy mt-4 text-[0.9375rem]">
                Every authentication check passes. The filing comparison is what actually catches
                it — a real circular, with one number changed.
              </p>
            </div>
          </Reveal>
        </div>

        <RevealGroup
          className="mt-14 grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-3 lg:grid-cols-5"
          stagger={0.06}
        >
          {channels.map((channel) => (
            <RevealItem key={channel.id}>
              <Link
                href={channel.href}
                className="flex h-full flex-col gap-2 bg-card px-4 py-4 transition-colors hover:bg-primary/6"
              >
                <span className="flex items-center gap-2.5">
                  <channel.icon className="size-4 text-primary" aria-hidden />
                  <span className="font-mono text-[0.6875rem] text-foreground/35">
                    {channel.index}
                  </span>
                </span>
                <span className="text-[0.9375rem] leading-tight font-medium">{channel.name}</span>
                <span className="font-serif text-xs text-foreground/50">{channel.tagline}</span>
              </Link>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}
