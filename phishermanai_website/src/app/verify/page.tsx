import type { Metadata } from "next";

import { PageHeader, Section, SectionHeading } from "@/components/site/section";
import { VerifyWorkbench } from "@/components/verify/verify-workbench";
import { verdictMeta } from "@/lib/analysis";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Check an email",
  description:
    "Drop in an .eml, a screenshot or the text of a message. It is checked against real BSE filings and SEBI's register, and you get a report of exactly what was checked and why.",
};

const order = ["VERIFIED", "NO_RISK_FOUND", "TAMPERED", "FRAUDULENT"] as const;

export default function VerifyPage() {
  return (
    <>
      <PageHeader
        eyebrow="Check an email"
        title="Forward it here before you act on it."
        accent="You will get the reasoning, not a score."
        lead="Drop in the .eml, a screenshot, or the text. It is checked against the corporate action the company actually filed with the exchange, and against SEBI's register of who is allowed to ask you for money."
      />

      <div className="container-page pb-20">
        <VerifyWorkbench />
      </div>

      <Section tone="raised">
        <SectionHeading
          eyebrow="What comes back"
          title="One of four answers,"
          accent="and never a number on its own."
          lead="A verdict you cannot interrogate is not evidence. Every answer names the register it used and the date that register was read."
        />

        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {order.map((code) => {
            const meta = verdictMeta[code];
            return (
              <article
                key={code}
                className={cn("rounded-xl border bg-card p-6", meta.border)}
              >
                <span
                  className={cn("size-2.5 rounded-full", meta.dot)}
                  aria-hidden
                />
                <h3 className={cn("mt-5 text-lg font-medium", meta.text)}>
                  {meta.label}
                </h3>
                <p className="mt-3 font-serif text-[0.9375rem] leading-relaxed text-foreground/70">
                  {meta.summary}
                </p>
              </article>
            );
          })}
        </div>

      </Section>
    </>
  );
}
