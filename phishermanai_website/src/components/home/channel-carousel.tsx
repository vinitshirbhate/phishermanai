"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, ChevronUp } from "lucide-react";

import { ChannelDiagram } from "@/components/diagrams/channel-diagram";
import { Reveal } from "@/components/site/motion";
import { Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import { channels, type Channel, maturityMeta } from "@/lib/content";
import { cn } from "@/lib/utils";

/** One fact per channel that lives only on the old standalone pages. */
const worthKnowing: Record<Channel["id"], string> = {
  email:
    "Six stages end to end — and 83% of genuine mail exits after stage three, before the expensive checks ever run.",
  voice:
    "Two capabilities were removed on purpose: a local model that scored real speech 100% spoof, and a rule that could never fire.",
  video:
    "Weighted at 0.20 alongside five other signals, and excluded — never scored zero — whenever it can't run.",
  social:
    "TF-IDF similarity plus burst timing: a method a regulator can be walked through in two minutes, not a black box.",
  web: "Registration lookup runs on-device in about 0.1 ms. Pull the plug, reload the page — the verdict still comes back.",
};

export function ChannelCarousel() {
  const [index, setIndex] = useState(0);
  const active = channels[index];

  const step = (delta: number) =>
    setIndex((current) => (current + delta + channels.length) % channels.length);

  // Deep link from another page's "#channel-x" — the hash only exists in the
  // browser, so this can't be resolved during the server render.
  useEffect(() => {
    const hash = window.location.hash.replace("#channel-", "");
    const match = channels.findIndex((channel) => channel.id === hash);
    if (match >= 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the URL, a genuine external system, once on mount
      setIndex(match);
      document.getElementById(`channel-${hash}`)?.scrollIntoView({ block: "center" });
    }
  }, []);

  return (
    <Section id="deep-dive">
      <Reveal className="flex flex-wrap items-end justify-between gap-6">
        <SectionHeading
          eyebrow="Channel by channel"
          title="What each detector actually reads,"
          accent="and what it hands back."
        />
        <div className="flex gap-2">
          <Button variant="outline" size="icon" onClick={() => step(-1)} className="size-10">
            <ChevronUp />
            <span className="sr-only">Previous channel</span>
          </Button>
          <Button variant="outline" size="icon" onClick={() => step(1)} className="size-10">
            <ChevronDown />
            <span className="sr-only">Next channel</span>
          </Button>
        </div>
      </Reveal>

      <div className="mt-12 grid gap-8 lg:grid-cols-2 lg:gap-12">
        <div className="space-y-3">
          {channels.map((channel, position) => {
            const isActive = position === index;
            return (
              <button
                key={channel.id}
                id={`channel-${channel.id}`}
                type="button"
                onClick={() => setIndex(position)}
                aria-expanded={isActive}
                className={cn(
                  "block w-full scroll-mt-24 border p-5 text-left transition-all sm:p-6",
                  isActive
                    ? "border-primary/45 bg-card shadow-[0_18px_44px_-28px_rgba(16,27,40,0.5)]"
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
                        <p className="font-serif text-[0.9375rem] leading-relaxed text-foreground/70">
                          {channel.threatBody}
                        </p>

                        <div className="flex flex-wrap gap-x-6 gap-y-1.5 border-t border-border pt-4">
                          <span className="font-serif text-sm text-foreground/55">
                            <span className="mono-label mr-2 text-foreground/35">for</span>
                            {channel.targetUsers.join(" · ")}
                          </span>
                        </div>

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

                        <div className="border-t border-primary/20 bg-primary/5 p-3.5">
                          <p className="mono-label text-primary">worth knowing</p>
                          <p className="mt-1.5 font-serif text-sm leading-relaxed text-foreground/65">
                            {worthKnowing[channel.id]}
                          </p>
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

          <dl className="mt-5 grid grid-cols-2 gap-px overflow-hidden border border-border bg-border">
            {active.evidence.map((item) => (
              <div key={item.label} className="bg-card px-4 py-3.5">
                <dt className="mono-label text-foreground/40">{item.label}</dt>
                <dd className="stat-figure mt-1.5 text-[1.0625rem]">{item.value}</dd>
                {item.caption ? (
                  <p className="mt-1 font-serif text-xs text-foreground/45 italic">
                    {item.caption}
                  </p>
                ) : null}
              </div>
            ))}
          </dl>

          <Button asChild className="mt-5 h-10 w-full rounded-full">
            <Link href="/demo">
              See {active.name.toLowerCase()} flag one, live
              <ArrowRight />
            </Link>
          </Button>
        </div>
      </div>
    </Section>
  );
}
