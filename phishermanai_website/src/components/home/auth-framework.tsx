import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { AuthBadgeRow, type AuthCheckItem } from "@/components/site/auth-badge-row";
import { Reveal, RevealGroup, RevealItem } from "@/components/site/motion";
import { RuleLabel, Section, SectionHeading } from "@/components/site/section";
import { Button } from "@/components/ui/button";
import { authLayers } from "@/lib/content";
import { cn } from "@/lib/utils";

const impostorChecks: AuthCheckItem[] = [
  { code: "SPF", state: "pass", detail: "Correctly published for this new domain." },
  { code: "DKIM", state: "pass", detail: "Valid signature — the domain does sign it." },
  { code: "DMARC", state: "pass", detail: "Policy p=reject, and this mail meets it." },
  { code: "TLS", state: "pass", detail: "Valid certificate. Not listed on any blocklist." },
];

const roadmap = [
  {
    state: "Built",
    tone: "verified" as const,
    title: "Verification against scraped public data",
    body: "8,434 BSE filings, 5,442 registered intermediaries, a hand-curated domain map — all read locally, offline.",
  },
  {
    state: "The gap",
    tone: "tampered" as const,
    title: "We scrape because we have no relationship with the exchanges",
    body: "Filings decay in hours, the register in weeks — two guards exist purely to stop stale data producing a false accusation.",
  },
  {
    state: "Roadmap",
    tone: "quiet" as const,
    title: "Publication at issuance",
    body: "SEBI, the exchanges and listed companies publish a signed digest at issue — verification instant, not best-effort. A standards question, not an engineering one.",
  },
];

const roadmapTone: Record<(typeof roadmap)[number]["tone"], string> = {
  verified: "border-verdict-verified/35 bg-verdict-verified/10 text-verdict-verified",
  tampered: "border-verdict-tampered/35 bg-verdict-tampered/10 text-verdict-tampered",
  quiet: "border-verdict-quiet/35 bg-verdict-quiet/10 text-verdict-quiet",
};

export function AuthFramework() {
  return (
    <Section id="authenticity" tone="navy">
      <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-start lg:gap-16">
        <div>
          <SectionHeading
            eyebrow="Half two — verification"
            title="A DMARC pass proves a domain sent the mail."
            accent="It proves nothing about the name it trades under."
            lead="Register canarabank-dividends.co.in, publish correct SPF and DKIM, set a reject policy — every authentication check in existence passes, while impersonating Canara Bank."
          />

          <p className="copy mt-6 max-w-xl text-cream/65">
            So six layers run instead of one. The last is what nothing else does: comparing what
            the message says against what the company actually filed.
          </p>

          <Button asChild className="mt-8 h-11 rounded-full px-6 text-[0.9375rem]">
            <Link href="#authenticity-detail">
              The full framework
              <ArrowRight />
            </Link>
          </Button>
        </div>

        <Reveal delay={0.1} className="border border-cream/12 bg-navy-raised">
          <div className="border-b border-cream/10 px-4 py-3 sm:px-5">
            <p className="font-mono text-[0.8125rem] break-all text-cream/85">
              canarabank-dividends.co.in
            </p>
            <p className="mt-1 font-serif text-xs text-cream/40">
              registered last Tuesday · every record published correctly
            </p>
          </div>

          <AuthBadgeRow items={impostorChecks} className="border-none" />

          <div className="m-4 border border-primary/30 bg-primary/10 px-3.5 py-3 sm:m-5">
            <p className="mono-label text-primary">the question nobody asks</p>
            <p className="mt-2 font-mono text-[0.8125rem] leading-relaxed text-cream/80">
              does this domain have any right to the name{" "}
              <span className="text-primary">Canara Bank</span>?
            </p>
          </div>

          <div className="border-t border-cream/10 px-4 py-2.5 sm:px-5">
            <p className="font-mono text-[0.6875rem] text-verdict-fraud">
              verdict: clean — and impersonating Canara Bank
            </p>
          </div>
        </Reveal>
      </div>

      <RevealGroup
        className="mt-16 grid gap-px overflow-hidden border border-cream/12 bg-cream/10 md:grid-cols-2 lg:grid-cols-3"
        stagger={0.06}
      >
        {authLayers.map((layer) => (
          <RevealItem key={layer.name}>
            <article className="h-full bg-navy p-6">
              <div className="flex items-center gap-3">
                <layer.icon className="size-4.5 text-primary" aria-hidden />
                <h3 className="text-base font-medium text-cream">{layer.name}</h3>
              </div>
              <p className="mt-3 font-serif text-[0.9375rem] text-cream/80">{layer.answers}</p>
              <p className="copy mt-3 text-[1rem] text-cream/55">{layer.body}</p>
              <p className="mono-label mt-4 text-cream/35">{layer.covers}</p>
            </article>
          </RevealItem>
        ))}
      </RevealGroup>

      <div id="authenticity-detail" className="scroll-mt-24 pt-16">
        <RuleLabel className="text-cream/40">what it would take to close the gap fully</RuleLabel>
        <RevealGroup className="mt-6 space-y-3" stagger={0.07}>
          {roadmap.map((item) => (
            <RevealItem key={item.title}>
              <div className="grid gap-3 border border-cream/12 bg-navy-raised p-5 sm:grid-cols-[7rem_1fr] sm:gap-6">
                <span
                  className={cn(
                    "mono-label h-fit border px-2.5 py-1 text-center",
                    roadmapTone[item.tone],
                  )}
                >
                  {item.state}
                </span>
                <div>
                  <h3 className="text-[0.9375rem] font-medium text-cream">{item.title}</h3>
                  <p className="copy mt-1.5 text-[0.9375rem] text-cream/60">{item.body}</p>
                </div>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </Section>
  );
}
