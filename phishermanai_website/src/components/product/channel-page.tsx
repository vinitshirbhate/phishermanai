import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { ChannelDiagram } from "@/components/diagrams/channel-diagram";
import { LimitationsSection } from "@/components/home/limitations-section";
import { PageHeader, Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import {
  getChannel,
  maturityMeta,
  type Channel,
  type LimitationScope,
} from "@/lib/content";
import { cn } from "@/lib/utils";

const limitationScope: Record<Channel["id"], LimitationScope> = {
  email: "Email",
  voice: "Voice",
  video: "Video",
  social: "Social",
  web: "Web",
};

export function ChannelPage({
  id,
  children,
  cta,
}: {
  id: Channel["id"];
  /** Channel-specific sections, dropped in before the limitations. */
  children?: ReactNode;
  cta?: { href: string; label: string };
}) {
  const channel = getChannel(id);
  const maturity = maturityMeta[channel.maturity];

  return (
    <>
      <PageHeader
        eyebrow={`${channel.index} · ${channel.name}`}
        title={`${channel.tagline}.`}
        lead={channel.summary}
      >
        <span
          className={cn(
            "mono-label mt-8 inline-flex rounded-full border px-3 py-1.5",
            maturity.className,
          )}
        >
          {maturity.label}
        </span>
        <p className="copy mt-4 max-w-2xl">{channel.maturityNote}</p>
      </PageHeader>

      <div className="container-page">
        <dl className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
          <div className="bg-card p-6">
            <dt className="mono-label text-primary">Target users</dt>
            <dd className="mt-3 space-y-1.5">
              {channel.targetUsers.map((user) => (
                <p key={user} className="font-serif text-[0.9375rem] text-foreground/70">
                  {user}
                </p>
              ))}
            </dd>
          </div>
          <div className="bg-card p-6">
            <dt className="mono-label text-primary">Channels addressed</dt>
            <dd className="mt-3 space-y-1.5">
              {channel.channelsAddressed.map((item) => (
                <p key={item} className="font-serif text-[0.9375rem] text-foreground/70">
                  {item}
                </p>
              ))}
            </dd>
          </div>
        </dl>
      </div>

      <Section tone="navy">
        <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="The threat"
              title={channel.threatTitle}
            />
            <p className="copy mt-6 max-w-xl text-cream/65">{channel.threatBody}</p>
          </div>
          <ChannelDiagram variant={channel.diagram} />
        </div>
      </Section>

      <Section>
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
          <div>
            <SectionHeading eyebrow="Detection" title="What it reads." />
            <div className="mt-8 space-y-6">
              {channel.detection.map((item) => (
                <div key={item.title} className="border-l-2 border-primary/40 pl-5">
                  <h3 className="text-base font-medium">{item.title}</h3>
                  <p className="copy mt-2 text-[1rem]">{item.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div>
            <SectionHeading eyebrow="Verification" title="What it can confirm." />
            <div className="mt-8 space-y-6">
              {channel.authentication.map((item) => (
                <div key={item.title} className="border-l-2 border-verdict-verified/40 pl-5">
                  <h3 className="text-base font-medium">{item.title}</h3>
                  <p className="copy mt-2 text-[1rem]">{item.body}</p>
                </div>
              ))}
            </div>
            <Button
              variant="outline"
              asChild
              className="mt-8 h-10 rounded-lg border-foreground/20"
            >
              <Link href="/product/authenticity">
                The full authenticity framework
                <ArrowRight />
              </Link>
            </Button>
          </div>
        </div>
      </Section>

      <Section tone="raised" id="evidence">
        <SectionHeading
          eyebrow="Evidence"
          title="The numbers for this channel,"
          accent="separate from every other channel's."
          lead="Blending performance across channels would hide the weak ones. These are reported on their own, targets included, whether or not they are met."
        />
        <dl className="mt-12 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {channel.evidence.map((item) => (
            <div key={item.label} className="bg-card px-5 py-6">
              <dt className="mono-label text-foreground/45">{item.label}</dt>
              <dd className="mt-3 font-mono text-[1.75rem] leading-none font-medium">
                {item.value}
              </dd>
              {item.caption ? (
                <p className="mt-2 font-serif text-sm text-foreground/55 italic">
                  {item.caption}
                </p>
              ) : null}
            </div>
          ))}
        </dl>
      </Section>

      {children}

      <LimitationsSection scopes={[limitationScope[channel.id]]} tone="cream" />

      <Section tone="navy" className="py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-2xl font-medium text-cream sm:text-3xl">
            Every other tool tells you it caught something
          </h2>
          <p className="copy-lg mt-5 text-cream/65">
            This one tells you what it checked, when, and what it still cannot see.
          </p>
          <Button asChild className="mt-8 h-11 rounded-lg px-6 text-[0.9375rem]">
            <Link href={cta?.href ?? "/demo"}>
              {cta?.label ?? "Run the demo"}
              <ArrowRight />
            </Link>
          </Button>
        </div>
      </Section>
    </>
  );
}
