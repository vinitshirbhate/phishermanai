import type { Metadata } from "next";
import { CircleCheck, CircleX } from "lucide-react";

import { LimitationsSection } from "@/components/home/limitations-section";
import { MetricsSection } from "@/components/home/metrics-section";
import { PageHeader, Section, SectionHeading } from "@/components/site/section";
import { StatStrip } from "@/components/site/stat-strip";
import { TerminalCard } from "@/components/site/terminal-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { corpusStats, extensionMetrics } from "@/lib/content";

export const metadata: Metadata = {
  title: "Evidence",
  description:
    "The numbers, including the ones that miss their target. Metrics, the precision ablation, the dataset audit, and every stated limitation.",
};

const commands = [
  { cmd: "python -m pytest tests backend/tests -q", note: "377 tests across both codebases" },
  { cmd: "python -m eval.run_eval", note: "fixture metrics → eval/RESULTS.md" },
  { cmd: "python -m eval.run_golden", note: "155 genuine samples, must be 0 FP" },
  { cmd: "python -m eval.report_hardening", note: "the precision ablation" },
  { cmd: "node eval/preflight_harness.js", note: "17/17, 0 false accusations" },
  { cmd: "python eval/parity_test.py", note: "JS and Python agree to ±0.02" },
  { cmd: "python scripts/check_blocked_claims.py", note: "no unsupportable claim ships" },
];

const defects = [
  "A genuine internship email flagged as a lottery scam — the scanner was reading the whole Gmail page, including other people's promotional mail, and attributing it to the open message.",
  "Every email address on earth read as a payment ID — support@sebi.gov.in parsed as a UPI handle.",
  "“Domain is on trusted whitelist”, a protective signal, rendered as a red danger warning in three separate places.",
  "820,000 blocklisted domains that had never once matched, because three feeds ship in three different file formats and nobody had checked.",
  "An entire analysis lane that loaded perfectly and was never called.",
];

export default function EvidencePage() {
  return (
    <>
      <PageHeader
        eyebrow="Evidence"
        title="The numbers,"
        accent="including the ones that miss."
        lead="Two of the four extension targets are not met. They are published beside the two that are, because a results table you can only read one way is not a results table."
      />

      <Section tone="raised">
        <StatStrip stats={corpusStats} className="lg:grid-cols-3" columns={3} />
      </Section>

      <MetricsSection />

      <Section tone="navy" id="extension-metrics">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="The bad ones"
              title="A worse number"
              accent="measuring a real thing."
              lead="The standard public phishing dataset everyone benchmarks on reports ~99% accuracy. We audited it."
            />
            <p className="copy mt-6 text-cream/65">
              100% of its “legitimate” URLs are tidy{" "}
              <span className="font-mono text-sm text-cream/80">https://www.domain</span>{" "}
              homepages with no path and no query — while its phishing URLs are deep links. A
              model handed those columns learns URL formatting, scores 0.99, and flags SEBI&rsquo;s
              own website at p = 1.000.
            </p>
            <p className="copy mt-5 text-cream/65">
              So scheme, <span className="font-mono text-sm text-cream/80">www</span>, path and
              query were stripped, the split was done by registrable domain, and the reported MCC
              is 0.66.
            </p>
          </div>

          <div className="overflow-hidden rounded-xl border border-cream/12 bg-navy-raised">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  <TableHead className="text-right">Result</TableHead>
                  <TableHead className="text-right">Target</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {extensionMetrics.map((row) => (
                  <TableRow key={row.metric}>
                    <TableCell className="align-top">
                      <span className="text-[0.9375rem] text-cream/85">{row.metric}</span>
                      {row.note ? (
                        <span className="mt-1 block font-mono text-[0.6875rem] text-cream/40">
                          {row.note}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right align-top font-mono text-[0.9375rem] text-cream">
                      {row.result}
                    </TableCell>
                    <TableCell className="text-right align-top font-mono text-[0.8125rem] text-cream/45">
                      {row.target}
                    </TableCell>
                    <TableCell className="align-top">
                      {row.pass ? (
                        <CircleCheck className="size-4 text-verdict-verified" aria-hidden />
                      ) : (
                        <CircleX className="size-4 text-verdict-fraud" aria-hidden />
                      )}
                      <span className="sr-only">{row.pass ? "meets target" : "misses target"}</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </Section>

      <Section>
        <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="What the engineering went into"
              title="The bug hunt"
              accent="is the demo."
              lead="Most entries in this space are a keyword list with a score attached — flag everything, demo well, uninstalled in a week. These are real defects found and fixed here, each now pinned by a regression test that fails against the old code."
            />
            <ul className="mt-10 space-y-4">
              {defects.map((defect) => (
                <li key={defect} className="border-l-2 border-primary/40 pl-5">
                  <p className="copy text-[1rem]">{defect}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="lg:pt-8">
            <TerminalCard label="VERIFY IT YOURSELF" meta="nothing is hand-typed">
              <div className="space-y-3">
                {commands.map((command) => (
                  <div key={command.cmd}>
                    <p className="font-mono text-[0.75rem] break-all text-cream/85">
                      <span className="text-primary">$ </span>
                      {command.cmd}
                    </p>
                    <p className="mt-1 font-serif text-xs text-cream/40 italic">{command.note}</p>
                  </div>
                ))}
              </div>
            </TerminalCard>

            <p className="mt-6 font-serif text-sm leading-relaxed text-foreground/50 italic">
              The golden corpus runs as a blocking test. If a rule becomes direction-blind and
              starts firing on genuine institutional mail, the build fails.
            </p>
          </div>
        </div>
      </Section>

      <LimitationsSection tone="raised" />
    </>
  );
}
