import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { Reveal, RevealGroup, RevealItem } from "@/components/site/motion";
import { channels } from "@/lib/content";

/**
 * The problem statement asks a solution to state three things. This answers
 * all three above the fold rather than leaving them to be inferred.
 */
const columns = [
  {
    label: "Target users",
    href: "/#who-its-for",
    lead: "Retail and first-generation investors",
    body: "The primary beneficiary — then intermediaries, infrastructure institutions, and SEBI.",
  },
  {
    label: "Channels addressed",
    href: "/#channels",
    lead: "Email · voice · video · social · web",
    body: "Plus WhatsApp text, screenshots, and files offered in chat.",
  },
  {
    label: "Evidence of performance",
    href: "/evidence",
    lead: "0 false positives in 155 genuine samples",
    body: "97.8% accuracy on email, MCC 0.6646 on web — measured, not claimed.",
  },
];

export function OutcomeBand() {
  return (
    <Reveal className="container-page py-14 sm:py-16">
      <div className="border border-border bg-card">
        <div className="grid gap-px overflow-hidden bg-border md:grid-cols-3">
          {columns.map((column) => (
            <Link
              key={column.label}
              href={column.href}
              className="group bg-card p-6 transition-colors hover:bg-primary/5 sm:p-7"
            >
              <span className="mono-label flex items-center gap-1.5 text-primary">
                {column.label}
                <ArrowUpRight
                  className="size-3 opacity-0 transition-opacity group-hover:opacity-100"
                  aria-hidden
                />
              </span>
              <p className="mt-4 text-[1.0625rem] leading-snug font-medium">{column.lead}</p>
              <p className="copy mt-3 text-[1rem]">{column.body}</p>
            </Link>
          ))}
        </div>

        <RevealGroup
          className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border px-6 py-4 sm:px-7"
          stagger={0.05}
        >
          <span className="mono-label text-foreground/35">coverage</span>
          {channels.map((channel) => (
            <RevealItem
              key={channel.id}
              className="inline-flex items-center gap-2 font-mono text-[0.75rem] text-foreground/55"
            >
              <channel.icon className="size-3.5 text-primary" aria-hidden />
              {channel.name.toLowerCase()}
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </Reveal>
  );
}
