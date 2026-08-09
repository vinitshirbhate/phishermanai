import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Section, SectionHeading } from "@/components/site/section";
import { TerminalCard, TerminalRow } from "@/components/site/terminal-card";
import { Button } from "@/components/ui/button";
import { authLayers } from "@/lib/content";

export function AuthFramework() {
  return (
    <Section id="authenticity" tone="navy">
      <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-start lg:gap-16">
        <div>
          <SectionHeading
            eyebrow="Half two — verification"
            title="A DMARC pass proves a domain sent the mail."
            accent="It proves nothing about the name it trades under."
            lead="A fraudster who registers canarabank-dividends.co.in, publishes correct SPF and DKIM records and sets a reject policy passes every authentication check in existence — while impersonating Canara Bank."
          />

          <p className="copy mt-6 max-w-xl text-cream/65">
            So six layers run instead of one, and the last of them is the part nothing deployed
            currently does: comparing what the message says against what the company actually
            filed.
          </p>

          <Button asChild className="mt-8 h-11 rounded-lg px-6 text-[0.9375rem]">
            <Link href="/product/authenticity">
              The full framework
              <ArrowRight />
            </Link>
          </Button>
        </div>

        <TerminalCard
          label="AUTHENTICATION ONLY"
          meta="every check green"
          footer={
            <p className="font-mono text-[0.6875rem] text-verdict-fraud">
              verdict: clean — and impersonating Canara Bank
            </p>
          }
        >
          <p className="font-mono text-[0.8125rem] break-all text-cream/85">
            canarabank-dividends.co.in
          </p>
          <p className="mt-1 font-serif text-xs text-cream/40 italic">
            registered last Tuesday · records published correctly
          </p>

          <div className="mt-5">
            <TerminalRow label="spf" value="pass" state="pass" />
            <TerminalRow label="dkim" value="pass" state="pass" />
            <TerminalRow label="dmarc" value="pass · p=reject" state="pass" />
            <TerminalRow label="tls" value="valid certificate" state="pass" />
            <TerminalRow label="blocklists" value="not listed" state="pass" />
          </div>

          <div className="mt-5 rounded-lg border border-primary/30 bg-primary/10 px-3.5 py-3">
            <p className="mono-label text-primary">the question nobody asks</p>
            <p className="mt-2 font-mono text-[0.8125rem] leading-relaxed text-cream/80">
              does this domain have any right to the name{" "}
              <span className="text-primary">Canara Bank</span>?
            </p>
          </div>
        </TerminalCard>
      </div>

      <div className="mt-16 grid gap-px overflow-hidden rounded-xl border border-cream/12 bg-cream/10 md:grid-cols-2 lg:grid-cols-3">
        {authLayers.map((layer) => (
          <article key={layer.name} className="bg-navy p-6">
            <div className="flex items-center gap-3">
              <layer.icon className="size-4.5 text-primary" aria-hidden />
              <h3 className="text-base font-medium text-cream">{layer.name}</h3>
            </div>
            <p className="mt-3 font-serif text-[0.9375rem] text-cream/80 italic">
              {layer.answers}
            </p>
            <p className="copy mt-3 text-[1rem] text-cream/55">{layer.body}</p>
            <p className="mono-label mt-4 text-cream/35">{layer.covers}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}
