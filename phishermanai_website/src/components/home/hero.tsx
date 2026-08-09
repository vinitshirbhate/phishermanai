import Link from "next/link";
import { ArrowRight } from "lucide-react";

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

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-10 pb-16 sm:pt-16 sm:pb-20">
      <div
        className="pointer-events-none absolute -top-40 -right-40 size-[36rem] rounded-full bg-primary/8 blur-3xl"
        aria-hidden
      />
      <div className="container-page relative">
        <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
          <div>
            <p className="eyebrow">{site.hackathon}</p>

            <h1 className="h-display mt-5">
              Generative AI broke both halves of trust.
              <br className="hidden sm:block" />{" "}
              <span className="h-accent">This rebuilds both.</span>
            </h1>

            <p className="copy-lg mt-7 max-w-xl">
              Detection of synthetic content across{" "}
              <span className="text-foreground">email, voice, video and social</span> — and a
              framework for verifying that a communication really is from SEBI, an exchange, a
              listed company or a registered intermediary.
            </p>

            <p className="copy mt-5 max-w-xl">
              Every channel carries its own evidence, its own target user, and its own written
              statement of what it cannot do.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Button asChild className="h-11 rounded-lg px-6 text-[0.9375rem]">
                <Link href="/demo">
                  Run the demo
                  <ArrowRight />
                </Link>
              </Button>
              <Button
                variant="outline"
                asChild
                className="h-11 rounded-lg border-foreground/20 px-6 text-[0.9375rem]"
              >
                <Link href="#channels">See all five channels</Link>
              </Button>
            </div>
          </div>

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

            <div className="mt-5 rounded-lg border border-primary/30 bg-primary/10 px-3.5 py-3">
              <p className="mono-label text-primary">why both halves</p>
              <p className="mt-2 font-serif text-sm leading-relaxed text-cream/75">
                Catching the fake is only useful if the real thing can also be confirmed.
                Otherwise every genuine circular becomes suspect too.
              </p>
            </div>
          </TerminalCard>
        </div>

        <ul className="mt-14 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-3 lg:grid-cols-5">
          {channels.map((channel) => (
            <li key={channel.id}>
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
                <span className="font-serif text-xs text-foreground/50 italic">
                  {channel.tagline}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
