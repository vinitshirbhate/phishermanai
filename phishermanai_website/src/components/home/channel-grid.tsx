import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Section, SectionHeading } from "@/components/site/section";
import { channels, maturityMeta } from "@/lib/content";
import { cn } from "@/lib/utils";

export function ChannelGrid() {
  return (
    <Section id="channels" tone="raised">
      <SectionHeading
        eyebrow="Every channel, equally"
        title="Five channels. Five detectors."
        accent="Five separate sets of numbers."
        lead="No channel is the headline and no channel is a footnote. Each one names the users it is for, the channels it covers, the evidence behind it, and the state it is honestly in."
      />

      <div className="mt-14 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {channels.map((channel) => {
          const maturity = maturityMeta[channel.maturity];
          return (
            <Link
              key={channel.id}
              href={channel.href}
              className="group flex flex-col rounded-2xl border border-border bg-card p-6 transition-all hover:border-primary/45 hover:shadow-[0_18px_44px_-28px_rgba(11,21,48,0.5)]"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-3">
                  <span className="grid size-9 place-items-center rounded-lg border border-primary/25 bg-primary/8 text-primary">
                    <channel.icon className="size-4.5" aria-hidden />
                  </span>
                  <span className="font-mono text-[0.6875rem] text-foreground/35">
                    {channel.index}
                  </span>
                </span>
                <ArrowRight
                  className="size-4 text-foreground/25 transition-colors group-hover:text-primary"
                  aria-hidden
                />
              </div>

              <h3 className="mt-5 text-lg font-medium">{channel.name}</h3>
              <p className="copy mt-3 flex-1 text-[1rem]">{channel.summary}</p>

              <dl className="mt-5 space-y-2.5 border-t border-border pt-5">
                <div className="flex gap-3">
                  <dt className="mono-label w-16 shrink-0 pt-0.5 text-foreground/35">for</dt>
                  <dd className="font-serif text-sm text-foreground/60">
                    {channel.targetUsers.join(" · ")}
                  </dd>
                </div>
                <div className="flex gap-3">
                  <dt className="mono-label w-16 shrink-0 pt-0.5 text-foreground/35">covers</dt>
                  <dd className="font-serif text-sm text-foreground/60">
                    {channel.channelsAddressed.join(" · ")}
                  </dd>
                </div>
              </dl>

              <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
                {channel.evidence.slice(0, 2).map((item) => (
                  <div key={item.label} className="bg-background px-3 py-2.5">
                    <p className="font-mono text-[0.9375rem] font-medium">{item.value}</p>
                    <p className="mono-label mt-1 text-foreground/40">{item.label}</p>
                  </div>
                ))}
              </div>

              <span
                className={cn(
                  "mono-label mt-4 inline-flex items-center gap-1.5 self-start rounded-full border px-2.5 py-1",
                  maturity.className,
                )}
              >
                {maturity.label}
              </span>
            </Link>
          );
        })}

        <div className="flex flex-col justify-between rounded-2xl border border-primary/35 bg-primary/8 p-6">
          <div>
            <p className="mono-label text-primary">across all five</p>
            <h3 className="mt-5 text-lg font-medium">Authenticity framework</h3>
            <p className="copy mt-3 text-[1rem]">
              Six verification layers that confirm a genuine communication positively — sender
              authentication, lookalike detection, registration resolution, content verification,
              signature presence and the official-channel registry.
            </p>
          </div>
          <Link
            href="/product/authenticity"
            className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-primary"
          >
            The verification half
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </div>
      </div>
    </Section>
  );
}
