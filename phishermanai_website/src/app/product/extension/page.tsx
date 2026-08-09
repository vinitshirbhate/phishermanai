import type { Metadata } from "next";
import { CircleCheck, CircleX } from "lucide-react";

import { GatesSection } from "@/components/home/gates-section";
import { ChannelPage } from "@/components/product/channel-page";
import { RuleLabel, Section, SectionHeading } from "@/components/site/section";
import { TerminalCard } from "@/components/site/terminal-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { extensionMetrics, lanes } from "@/lib/content";

export const metadata: Metadata = {
  title: "Browser extension",
  description:
    "A Chrome extension that warns Indian retail investors about securities fraud — before they click, install or pay. No build step, works offline, nothing leaves the device.",
};

const trap = [
  {
    move: "They keep a registration number",
    consequence:
      "It resolves against the real SEBI register and comes back held by someone else — a collision.",
  },
  {
    move: "They remove it",
    consequence: "The page is breaking a disclosure rule that has been mandatory since 1 May 2026.",
  },
];

const status = [
  {
    heading: "Works and is measured",
    tone: "pass" as const,
    items: [
      "Registration collision detection against 3,179 real SEBI registrants, offline",
      "Link preflight: 17/17 on its harness, zero false accusations on the guard set",
      "Blocklist lookup across 819,572 domains with dated provenance",
      "APK offer analysis, including fake-broker filenames",
    ],
  },
  {
    heading: "Built, not yet running in a browser",
    tone: "warn" as const,
    items: [
      "The WhatsApp lane's modules are complete and tested, but adapter.start() has no caller",
      "Chat context is not fed into the SEBI-disclosure rule; enable_chat_context() refuses unless confirmed",
    ],
  },
  {
    heading: "Not verified",
    tone: "fail" as const,
    items: [
      "WhatsApp and Gmail DOM selectors have never run against live markup — fixtures we write would match selectors we wrote, and prove nothing",
    ],
  },
  {
    heading: "Not built",
    tone: "muted" as const,
    items: ["Voice analysis in the extension", "C2PA parsing", "Email integration", "Org console"],
  },
];

export default function ExtensionPage() {
  return (
    <ChannelPage
      id="web"
      cta={{ href: "/demo?demo=fraud_02_guaranteed_returns.eml", label: "See a collision" }}
    >
      <Section id="trap">
        <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-start lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="The trap with no exit"
              title="A fraudster can rewrite their pitch endlessly."
              accent="They cannot make a real number resolve to their own name."
              lead="SEBI requires every legitimate adviser, broker and research analyst to display a registration number, and to take money only through a verified @valid UPI handle. So instead of hunting for signs of a scam, we check whether the credential the law requires is actually there."
            />

            <div className="mt-10 space-y-4">
              {trap.map((row) => (
                <div key={row.move} className="rounded-xl border border-border bg-card p-5">
                  <p className="text-[0.9375rem] font-medium">{row.move}</p>
                  <p className="copy mt-2 text-[1rem]">{row.consequence}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 rounded-xl border border-primary/30 bg-primary/6 p-6">
              <p className="mono-label text-primary">one design call worth calling out</p>
              <p className="copy mt-3">
                Lookalike letters are deliberately <span className="text-foreground">not</span>{" "}
                folded when comparing identity. Folding makes a Cyrillic{" "}
                <span className="font-mono text-sm">nseindia.com</span> compare equal to the real
                NSE domain — the tool would actively vouch for the impostor. Missing an attack is
                bad; endorsing one is worse.
              </p>
            </div>
          </div>

          <div>
            <TerminalCard label="INSTALL" meta="chrome mv3">
              <pre className="overflow-x-auto font-mono text-[0.75rem] leading-relaxed text-cream/80">
{`# 1. Load the extension
chrome://extensions → Developer mode
  → Load unpacked → select extension/

# 2. Serve the demo pages
python -m http.server 8801

# 3. Optional backend — adds 820k
#    blocklisted domains
cd backend && pip install -r requirements.txt
uvicorn api:app --port 8799`}
              </pre>
            </TerminalCard>

            <div className="mt-6 rounded-xl border border-border bg-card p-5">
              <p className="mono-label text-foreground/40">pull the plug</p>
              <p className="copy mt-3 text-[1rem]">
                Stop the backend, turn Wi-Fi off, reload the scam page. You still get a verdict,
                with an “offline check” note. The registration lookup runs on-device in about
                0.1 ms.
              </p>
            </div>
          </div>
        </div>
      </Section>

      <Section tone="navy" id="lanes">
        <SectionHeading
          eyebrow="The four lanes"
          title="Four inputs, one question each,"
          accent="merged into a verdict that carries its own reasoning."
          lead="Merging is where four checks that know nothing about each other become one answer. Each finding is classified by its own meaning — risk, protective or context — deduplicated, ordered worst-first, and combined floor-only: a bad signal can drag trust down, a benign one can never lift a page that already looks dangerous."
        />

        <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-cream/12 bg-cream/10 sm:grid-cols-2">
          {lanes.map((lane) => (
            <div key={lane.name} className="bg-navy p-6">
              <div className="flex items-center gap-3">
                <lane.icon className="size-4.5 text-primary" aria-hidden />
                <h3 className="text-base font-medium text-cream">{lane.name}</h3>
                <span className="font-mono text-[0.6875rem] text-cream/30">{lane.path}</span>
              </div>
              <p className="mt-3 font-serif text-[0.9375rem] text-cream/80 italic">
                {lane.question}
              </p>
              <p className="copy mt-3 text-[1rem] text-cream/60">{lane.how}</p>
            </div>
          ))}
        </div>

        <p className="copy mt-10 max-w-3xl text-cream/60">
          A verdict is not a score. It is a code plus its evidence plus its provenance, and every
          finding stays tagged with which of four truths it speaks to — identity, content, channel
          or interaction. They are never collapsed into one number, because “this chat behaves
          oddly” and “this registration belongs to someone else” are different claims with
          different consequences.
        </p>
      </Section>

      <Section id="demo-pages" tone="raised">
        <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="Try it in five minutes"
              title="The flagship demo"
              accent="is impersonation."
              lead="The page calls itself Alpha Wealth Circle and quotes INA000000383 — a real registration number from SEBI's public register, held by a different firm entirely. That mismatch is the detection, and no amount of rewriting the sales copy removes it."
            />

            <RuleLabel className="mt-10">what you should see</RuleLabel>
            <dl className="mt-5 space-y-3">
              {[
                ["Badge", "Low trust, red"],
                ["Side panel", "Securities Identity → registration collision"],
                ["Reason", "Registered to V R WEALTH ADVISORS PRIVATE LIMITED, not this sender"],
                ["UPI row", "investprofit99@ybl — outside @valid, with a SEBI Check link"],
                ["Footer", "Register data as of 2026-08-06"],
              ].map(([term, description]) => (
                <div key={term} className="flex flex-wrap gap-x-4 border-b border-border pb-3">
                  <dt className="mono-label w-24 shrink-0 pt-1 text-foreground/40">{term}</dt>
                  <dd className="flex-1 font-serif text-[0.9375rem] text-foreground/70">
                    {description}
                  </dd>
                </div>
              ))}
            </dl>

            <p className="copy mt-8">
              Then open the safe page. High trust, no securities card, no warnings. A tool that
              flags everything is useless — showing that it stays quiet is half the pitch.
            </p>
          </div>

          <div>
            <h3 className="mono-label text-foreground/45">targets, met and missed</h3>
            <div className="mt-5 overflow-hidden rounded-xl border border-border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead className="text-right">Result</TableHead>
                    <TableHead className="text-right">Target</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {extensionMetrics.map((row) => (
                    <TableRow key={row.metric}>
                      <TableCell className="align-top text-[0.875rem]">
                        {row.metric}
                        {row.note ? (
                          <span className="mt-1 block font-mono text-[0.6875rem] text-foreground/40">
                            {row.note}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right align-top font-mono text-[0.875rem]">
                        {row.result}
                      </TableCell>
                      <TableCell className="text-right align-top font-mono text-xs text-foreground/45">
                        {row.target}
                      </TableCell>
                      <TableCell className="align-top">
                        {row.pass ? (
                          <CircleCheck className="size-4 text-verdict-verified" aria-hidden />
                        ) : (
                          <CircleX className="size-4 text-verdict-fraud" aria-hidden />
                        )}
                        <span className="sr-only">
                          {row.pass ? "meets target" : "misses target"}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div className="mt-8 grid gap-5 sm:grid-cols-2">
              {status.map((group) => (
                <div key={group.heading} className="rounded-xl border border-border bg-card p-5">
                  <h4
                    className={
                      group.tone === "pass"
                        ? "text-sm font-medium text-verdict-verified"
                        : group.tone === "warn"
                          ? "text-sm font-medium text-verdict-tampered"
                          : group.tone === "fail"
                            ? "text-sm font-medium text-verdict-fraud"
                            : "text-sm font-medium text-foreground/45"
                    }
                  >
                    {group.heading}
                  </h4>
                  <ul className="mt-3 space-y-2">
                    {group.items.map((item) => (
                      <li
                        key={item}
                        className="font-serif text-sm leading-relaxed text-foreground/60"
                      >
                        · {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      <GatesSection />
    </ChannelPage>
  );
}
