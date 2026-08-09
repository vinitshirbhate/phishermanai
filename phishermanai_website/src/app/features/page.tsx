import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { PageHeader, Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  authLayers,
  channels,
  chokepoints,
  lanes,
  maturityMeta,
  signals,
  targetUsers,
} from "@/lib/content";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Features",
  description:
    "Every capability, channel by channel — what each detector reads, what each can confirm, who it is for, and the state it is honestly in.",
};

export default function FeaturesPage() {
  return (
    <>
      <PageHeader
        eyebrow="Features"
        title="Five channels, six verification layers,"
        accent="and no headline feature."
        lead="Each channel below carries the same four things: what it detects, what it can confirm, who it is for, and the evidence behind it. None is presented as the flagship, because an attacker only needs the one you under-invested in."
      />

      <Section tone="raised">
        <div className="space-y-6">
          {channels.map((channel) => {
            const maturity = maturityMeta[channel.maturity];
            return (
              <article
                key={channel.id}
                id={channel.id}
                className="scroll-mt-24 overflow-hidden rounded-2xl border border-border bg-card"
              >
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-border p-6 sm:p-7">
                  <span className="grid size-10 place-items-center rounded-lg border border-primary/25 bg-primary/8 text-primary">
                    <channel.icon className="size-5" aria-hidden />
                  </span>
                  <div>
                    <span className="font-mono text-[0.6875rem] text-foreground/35">
                      {channel.index}
                    </span>
                    <h2 className="text-xl font-medium">{channel.name}</h2>
                  </div>
                  <span
                    className={cn(
                      "mono-label ml-auto rounded-full border px-2.5 py-1",
                      maturity.className,
                    )}
                  >
                    {maturity.label}
                  </span>
                </div>

                <div className="grid gap-px bg-border lg:grid-cols-2">
                  <div className="bg-card p-6 sm:p-7">
                    <h3 className="mono-label text-primary">Detection</h3>
                    <ul className="mt-4 space-y-4">
                      {channel.detection.map((item) => (
                        <li key={item.title}>
                          <p className="text-[0.9375rem] font-medium">{item.title}</p>
                          <p className="copy mt-1.5 text-[1rem]">{item.body}</p>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="bg-card p-6 sm:p-7">
                    <h3 className="mono-label text-verdict-verified">Verification</h3>
                    <ul className="mt-4 space-y-4">
                      {channel.authentication.map((item) => (
                        <li key={item.title}>
                          <p className="text-[0.9375rem] font-medium">{item.title}</p>
                          <p className="copy mt-1.5 text-[1rem]">{item.body}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="grid gap-px border-t border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
                  {channel.evidence.slice(0, 4).map((item) => (
                    <div key={item.label} className="bg-card px-5 py-4">
                      <p className="font-mono text-[1.0625rem] font-medium">{item.value}</p>
                      <p className="mono-label mt-1 text-foreground/40">{item.label}</p>
                      {item.caption ? (
                        <p className="mt-1 font-serif text-xs text-foreground/45 italic">
                          {item.caption}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border p-6 sm:px-7">
                  <div className="space-y-1">
                    <p className="font-serif text-sm text-foreground/60">
                      <span className="mono-label mr-2 text-foreground/35">for</span>
                      {channel.targetUsers.join(" · ")}
                    </p>
                    <p className="font-serif text-sm text-foreground/60">
                      <span className="mono-label mr-2 text-foreground/35">covers</span>
                      {channel.channelsAddressed.join(" · ")}
                    </p>
                  </div>
                  <Button variant="outline" asChild className="h-9 rounded-lg border-foreground/20">
                    <Link href={channel.href}>
                      Full detail
                      <ArrowRight />
                    </Link>
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      </Section>

      <Section>
        <SectionHeading
          eyebrow="The verification half"
          title="Six layers that run across"
          accent="every one of those channels."
          lead="Each answers a different question and each can fail independently, which is why a message can have a proven sender and a false claim at the same time."
        />
        <div className="mt-12 overflow-hidden rounded-xl border border-border bg-card">
          <div className="overflow-x-auto">
            <Table className="min-w-[46rem]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[20%]">Layer</TableHead>
                  <TableHead className="w-[26%]">Question it answers</TableHead>
                  <TableHead>How</TableHead>
                  <TableHead className="w-[16%]">Covers</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {authLayers.map((layer) => (
                  <TableRow key={layer.name}>
                    <TableCell className="align-top">
                      <span className="flex items-center gap-2.5 text-[0.9375rem] font-medium">
                        <layer.icon className="size-4 shrink-0 text-primary" aria-hidden />
                        {layer.name}
                      </span>
                    </TableCell>
                    <TableCell className="align-top font-serif text-[0.9375rem] text-foreground/75 italic">
                      {layer.answers}
                    </TableCell>
                    <TableCell className="align-top font-serif text-[0.9375rem] text-foreground/65">
                      {layer.body}
                    </TableCell>
                    <TableCell className="mono-label align-top text-foreground/40">
                      {layer.covers}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </Section>

      <Section tone="navy">
        <SectionHeading
          eyebrow="Shared mechanics"
          title="Four chokepoints, four lanes,"
          accent="six fused signals."
          lead="The chokepoints run on any message that reaches the engine. The lanes run in the browser. The signals are how independent readings become one band without any of them being able to vouch for another."
        />

        <div className="mt-12 grid gap-10 lg:grid-cols-2">
          <div>
            <h3 className="mono-label text-cream/45">Chokepoints — the messaging path</h3>
            <div className="mt-5 space-y-3">
              {chokepoints.map((chokepoint) => (
                <div
                  key={chokepoint.name}
                  className="rounded-xl border border-cream/12 bg-navy-raised p-5"
                >
                  <div className="flex items-center gap-3">
                    <chokepoint.icon className="size-4 text-primary" aria-hidden />
                    <h4 className="text-[0.9375rem] font-medium text-cream">{chokepoint.name}</h4>
                    <span className="mono-label ml-auto text-cream/30">
                      {chokepoint.register}
                    </span>
                  </div>
                  <p className="mt-2.5 font-serif text-sm text-cream/70 italic">
                    {chokepoint.question}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 className="mono-label text-cream/45">Lanes — the browser path</h3>
            <div className="mt-5 space-y-3">
              {lanes.map((lane) => (
                <div key={lane.name} className="rounded-xl border border-cream/12 bg-navy-raised p-5">
                  <div className="flex items-center gap-3">
                    <lane.icon className="size-4 text-primary" aria-hidden />
                    <h4 className="text-[0.9375rem] font-medium text-cream">{lane.name}</h4>
                    <span className="mono-label ml-auto text-cream/30">{lane.path}</span>
                  </div>
                  <p className="mt-2.5 font-serif text-sm text-cream/70 italic">{lane.question}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-12">
          <h3 className="mono-label text-cream/45">Fusion — weights and failure modes</h3>
          <div className="mt-5 space-y-3">
            {signals.map((signal) => (
              <div
                key={signal.name}
                className="grid gap-4 rounded-xl border border-cream/12 bg-navy-raised p-5 sm:grid-cols-[12rem_1fr_1fr] sm:items-start"
              >
                <div className="flex items-center gap-3">
                  <signal.icon className="size-4 shrink-0 text-primary" aria-hidden />
                  <div>
                    <p className="font-mono text-[0.8125rem] text-cream/85">{signal.name}</p>
                    <p className="mono-label mt-1 text-cream/35">
                      {signal.channel} · {signal.weight.toFixed(2)}
                    </p>
                  </div>
                </div>
                <p className="copy text-[1rem] text-cream/65">{signal.what}</p>
                <p className="font-serif text-sm leading-relaxed text-cream/45 italic">
                  {signal.limitation}
                </p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section tone="raised">
        <SectionHeading
          eyebrow="Target users"
          title="Who each of these is actually for."
        />
        <div className="mt-12 grid gap-6 md:grid-cols-2">
          {targetUsers.map((user) => (
            <div key={user.name} className="rounded-xl border border-border bg-card p-6">
              <user.icon className="size-5 text-primary" aria-hidden />
              <h3 className="mt-4 text-lg font-medium">{user.name}</h3>
              <p className="mono-label mt-1.5 text-primary">{user.role}</p>
              <p className="copy mt-3 text-[1rem]">{user.needs}</p>
              <p className="mono-label mt-4 border-t border-border pt-4 text-foreground/35">
                reached through — {user.surface}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-14 flex flex-wrap gap-3">
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
            <Link href="/evidence">See the evidence</Link>
          </Button>
        </div>
      </Section>
    </>
  );
}
