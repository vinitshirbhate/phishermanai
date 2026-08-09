import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { LimitationsSection } from "@/components/home/limitations-section";
import { OutcomesSection } from "@/components/home/outcomes-section";
import { PageHeader, RuleLabel, Section, SectionHeading } from "@/components/site/section";
import { TerminalCard, TerminalRow } from "@/components/site/terminal-card";
import { Button } from "@/components/ui/button";
import { authLayers, targetUsers } from "@/lib/content";

export const metadata: Metadata = {
  title: "Authenticity framework",
  description:
    "Six layers that confirm a communication really is from SEBI, an exchange, a listed company or a registered intermediary — a positive confirmation, not merely the absence of a flag.",
};

const roadmap = [
  {
    state: "Built",
    tone: "verified" as const,
    title: "Verification against scraped public data",
    body: "8,434 BSE filings, 5,442 registered intermediaries and a hand-curated domain map, all read from a local cache. It works today and it runs offline, but it lags whatever the exchange published this morning.",
  },
  {
    state: "The gap",
    tone: "tampered" as const,
    title: "We scrape because we have no relationship with the exchanges",
    body: "Every source decays at a different rate — filings in hours, the register in weeks, the scrip master in months — and two guards exist purely to stop stale data producing a false accusation.",
  },
  {
    state: "Roadmap",
    tone: "quiet" as const,
    title: "Publication at issuance",
    body: "In a deployed version, SEBI, the exchanges and listed companies would publish a signed digest to the registry when a circular is issued. Verification becomes instant and exact rather than best-effort with a lag. This is a standards question, not an engineering one, and it is the reason SEBI is the anchor stakeholder.",
  },
];

export default function AuthenticityPage() {
  return (
    <>
      <PageHeader
        eyebrow="The verification half"
        title="Not flagged is not the same as confirmed."
        accent="Investors need the second one."
        lead="There is currently no reliable way to check that a notice purporting to be from SEBI, a stock exchange, a listed company or a registered intermediary is genuine. That absence is what makes every synthetic-media attack land harder — and it is the half of the problem that detection alone cannot close."
      >
        <div className="mt-10 flex flex-wrap gap-3">
          <Button asChild className="h-11 rounded-lg px-6 text-[0.9375rem]">
            <Link href="/demo?demo=genuine_01.eml">
              See a confirmation
              <ArrowRight />
            </Link>
          </Button>
          <Button
            variant="outline"
            asChild
            className="h-11 rounded-lg border-foreground/20 px-6 text-[0.9375rem]"
          >
            <Link href="/demo?demo=tampered_01.eml">See a tampered filing</Link>
          </Button>
        </div>
      </PageHeader>

      <Section tone="navy">
        <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="Why one layer is not enough"
              title="SPF, DKIM and DMARC are excellent"
              accent="at the narrow thing they do."
            />

            <blockquote className="mt-9 border-l-2 border-primary pl-5">
              <p className="font-serif text-lg leading-relaxed text-cream/85 italic sm:text-xl">
                “This mail genuinely came from the domain it claims, and that domain&rsquo;s owner
                authorised it.”
              </p>
            </blockquote>

            <p className="copy mt-7 max-w-xl text-cream/65">
              That is the whole assertion. It says nothing about whether the domain has any right
              to the <span className="text-cream">name</span> it is trading under. A fraudster who
              registers a plausible domain, publishes correct records and sets a reject policy
              passes every authentication check in existence — while impersonating a bank. Every
              mail provider marks it clean.
            </p>

            <p className="copy mt-5 max-w-xl text-cream/65">
              Lookalike domains are the standard escape hatch, which is why registrable domains
              are extracted with the Public Suffix List and compared{" "}
              <span className="text-cream">without</span> folding homoglyphs. Folding would make a
              Cyrillic substitution compare equal to the genuine domain, and the tool would vouch
              for the impostor.
            </p>
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
      </Section>

      <Section id="registry">
        <SectionHeading
          eyebrow="Six layers"
          title="Each answers a different question,"
          accent="and each can fail independently."
          lead="They are not a chain where one failure stops the rest. A message can have a proven sender and a false claim, or an unknown sender and nothing wrong with it at all — which is exactly why there are four outcomes rather than two."
        />

        <div className="mt-14 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-3">
          {authLayers.map((layer, index) => (
            <article key={layer.name} className="bg-card p-6">
              <div className="flex items-center justify-between gap-3">
                <span className="grid size-9 place-items-center rounded-lg border border-primary/25 bg-primary/8 text-primary">
                  <layer.icon className="size-4.5" aria-hidden />
                </span>
                <span className="font-mono text-[0.6875rem] text-foreground/30">
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <h3 className="mt-5 text-base font-medium">{layer.name}</h3>
              <p className="mt-3 font-serif text-[0.9375rem] text-foreground/75 italic">
                {layer.answers}
              </p>
              <p className="copy mt-3 text-[1rem]">{layer.body}</p>
              <p className="mono-label mt-4 border-t border-border pt-4 text-foreground/35">
                {layer.covers}
              </p>
            </article>
          ))}
        </div>
      </Section>

      <Section id="filing" tone="raised">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.05fr] lg:items-center lg:gap-16">
          <TerminalCard label="CONTENT VERIFICATION" meta="birla corporation · 500335">
            <p className="mono-label text-cream/40">interim dividend per equity share</p>

            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-verdict-fraud/30 bg-verdict-fraud/8 px-4 py-3.5">
                <p className="mono-label text-cream/45">this document says</p>
                <p className="mt-2 font-mono text-2xl text-verdict-fraud">₹125.00</p>
              </div>
              <div className="rounded-lg border border-verdict-verified/30 bg-verdict-verified/8 px-4 py-3.5">
                <p className="mono-label text-cream/45">birla corporation filed</p>
                <p className="mt-2 font-mono text-2xl text-verdict-verified">₹12.50</p>
                <p className="mt-2 font-mono text-[0.6875rem] text-cream/40">
                  BSE corporate announcements · 09 July 2026
                </p>
              </div>
            </div>

            <div className="mt-5 space-y-2">
              {[
                ["record date", "24 Jul 2026"],
                ["face value", "₹10"],
                ["scrip code", "500335"],
              ].map(([field, value]) => (
                <div key={field} className="flex items-baseline justify-between gap-3">
                  <span className="mono-label text-cream/40">{field}</span>
                  <span className="font-mono text-[0.8125rem] text-cream/60">
                    {value} <span className="text-verdict-verified">· matches</span>
                  </span>
                </div>
              ))}
            </div>
          </TerminalCard>

          <div>
            <SectionHeading
              eyebrow="Layer four — the differentiator"
              title="Every authentication check passes"
              accent="because nothing about the sender is fake."
              lead="A genuine circular, from a real company, with one number edited. Source authentication cannot catch this by definition — the source is real. Only comparing the content against the filing can."
            />

            <div className="mt-10 space-y-6">
              <div className="border-l-2 border-primary/40 pl-5">
                <h3 className="text-base font-medium">Python compares, models do not</h3>
                <p className="copy mt-2 text-[1rem]">
                  Whether 125.00 equals 12.50 is an integer comparison. One field parser runs on
                  both sides, so the document and the filing are read the same way before either
                  is judged.
                </p>
              </div>
              <div className="border-l-2 border-primary/40 pl-5">
                <h3 className="text-base font-medium">
                  An unreadable field can never produce “tampered”
                </h3>
                <p className="copy mt-2 text-[1rem]">
                  A false accusation against a real document destroys credibility faster than a
                  miss. If a value cannot be parsed with confidence, the comparison is skipped and
                  reported as skipped.
                </p>
              </div>
            </div>

            <p className="mt-8 font-serif text-foreground/55 italic">
              Tamper recall is 70%. Tampered documents called genuine: 0. Those two numbers are
              the trade this design makes deliberately.
            </p>
          </div>
        </div>
      </Section>

      <OutcomesSection />

      <Section tone="navy">
        <SectionHeading
          eyebrow="What it would take to close the gap"
          title="The last mile is a standard,"
          accent="not a model."
        />

        <div className="mt-12 space-y-4">
          {roadmap.map((item) => (
            <div
              key={item.title}
              className="grid gap-4 rounded-xl border border-cream/12 bg-navy-raised p-6 sm:grid-cols-[7rem_1fr] sm:gap-6"
            >
              <span
                className={
                  item.tone === "verified"
                    ? "mono-label h-fit rounded-full border border-verdict-verified/35 bg-verdict-verified/10 px-2.5 py-1 text-center text-verdict-verified"
                    : item.tone === "tampered"
                      ? "mono-label h-fit rounded-full border border-verdict-tampered/35 bg-verdict-tampered/10 px-2.5 py-1 text-center text-verdict-tampered"
                      : "mono-label h-fit rounded-full border border-verdict-quiet/35 bg-verdict-quiet/10 px-2.5 py-1 text-center text-verdict-quiet"
                }
              >
                {item.state}
              </span>
              <div>
                <h3 className="text-base font-medium text-cream">{item.title}</h3>
                <p className="copy mt-2 text-[1rem] text-cream/60">{item.body}</p>
              </div>
            </div>
          ))}
        </div>

        <RuleLabel className="mt-14 text-cream/40">who owns which piece</RuleLabel>
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {targetUsers.map((user) => (
            <div key={user.name} className="flex gap-4">
              <user.icon className="mt-1 size-4.5 shrink-0 text-primary" aria-hidden />
              <div>
                <h3 className="text-[0.9375rem] font-medium text-cream">{user.name}</h3>
                <p className="mono-label mt-1 text-primary">{user.role}</p>
                <p className="copy mt-2 text-[1rem] text-cream/60">{user.needs}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <LimitationsSection scopes={["Authentication"]} tone="raised" />
    </>
  );
}
