"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, ChevronUp } from "lucide-react";

import { ChannelDiagram } from "@/components/diagrams/channel-diagram";
import { Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import { channels, maturityMeta } from "@/lib/content";
import { cn } from "@/lib/utils";

export function ChannelCarousel() {
  const [index, setIndex] = useState(0);
  const active = channels[index];

  const step = (delta: number) =>
    setIndex((current) => (current + delta + channels.length) % channels.length);

  return (
    <Section id="deep-dive">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <SectionHeading
          eyebrow="Channel by channel"
          title="What each detector actually reads,"
          accent="and what it hands back."
        />
        <div className="flex gap-2">
          <Button variant="outline" size="icon" onClick={() => step(-1)} className="size-10 rounded-lg">
            <ChevronUp />
            <span className="sr-only">Previous channel</span>
          </Button>
          <Button variant="outline" size="icon" onClick={() => step(1)} className="size-10 rounded-lg">
            <ChevronDown />
            <span className="sr-only">Next channel</span>
          </Button>
        </div>
      </div>

      <div className="mt-12 grid gap-8 lg:grid-cols-2 lg:gap-12">
        <div className="space-y-3">
          {channels.map((channel, position) => {
            const isActive = position === index;
            return (
              <button
                key={channel.id}
                type="button"
                onClick={() => setIndex(position)}
                aria-expanded={isActive}
                className={cn(
                  "block w-full rounded-xl border p-5 text-left transition-all sm:p-6",
                  isActive
                    ? "border-primary/45 bg-card shadow-[0_18px_44px_-28px_rgba(11,21,48,0.5)]"
                    : "border-border bg-transparent hover:border-foreground/20",
                )}
              >
                <div className="flex items-start gap-4">
                  <span
                    className={cn(
                      "font-mono text-sm",
                      isActive ? "text-primary" : "text-foreground/30",
                    )}
                  >
                    {channel.index}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2.5">
                      <channel.icon
                        className={cn(
                          "size-4",
                          isActive ? "text-primary" : "text-foreground/35",
                        )}
                        aria-hidden
                      />
                      <h3 className="text-lg font-medium sm:text-xl">{channel.name}</h3>
                    </div>
                    <p className="mono-label mt-1.5 text-foreground/40">{channel.tagline}</p>

                    {isActive ? (
                      <div className="mt-5 space-y-5">
                        <div>
                          <p className="mono-label text-primary">detection</p>
                          <ul className="mt-2.5 space-y-2">
                            {channel.detection.map((item) => (
                              <li key={item.title}>
                                <span className="text-sm font-medium">{item.title}</span>
                                <span className="mt-1 block font-serif text-sm leading-relaxed text-foreground/60">
                                  {item.body}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        <div className="border-t border-border pt-5">
                          <p className="mono-label text-primary">verification</p>
                          <ul className="mt-2.5 space-y-2">
                            {channel.authentication.map((item) => (
                              <li key={item.title}>
                                <span className="text-sm font-medium">{item.title}</span>
                                <span className="mt-1 block font-serif text-sm leading-relaxed text-foreground/60">
                                  {item.body}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        <p
                          className={cn(
                            "mono-label inline-flex rounded-full border px-2.5 py-1",
                            maturityMeta[channel.maturity].className,
                          )}
                        >
                          {maturityMeta[channel.maturity].label}
                        </p>
                      </div>
                    ) : null}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        <div className="lg:sticky lg:top-28 lg:self-start">
          <ChannelDiagram variant={active.diagram} />

          <dl className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border">
            {active.evidence.map((item) => (
              <div key={item.label} className="bg-card px-4 py-3.5">
                <dt className="mono-label text-foreground/40">{item.label}</dt>
                <dd className="mt-1.5 font-mono text-[1.0625rem] font-medium">{item.value}</dd>
                {item.caption ? (
                  <p className="mt-1 font-serif text-xs text-foreground/45 italic">
                    {item.caption}
                  </p>
                ) : null}
              </div>
            ))}
          </dl>

          <Button variant="outline" asChild className="mt-5 h-10 w-full rounded-lg border-foreground/20">
            <Link href={active.href}>
              Everything on {active.name.toLowerCase()}
              <ArrowRight />
            </Link>
          </Button>
        </div>
      </div>
    </Section>
  );
}
