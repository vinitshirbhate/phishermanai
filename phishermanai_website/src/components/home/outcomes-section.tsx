import { RevealGroup, RevealItem } from "@/components/site/motion";
import { Section, SectionHeading } from "@/components/site/section";
import { type VerdictCode, verdictMeta } from "@/lib/analysis";
import { cn } from "@/lib/utils";

const order: VerdictCode[] = ["VERIFIED", "NO_RISK_FOUND", "TAMPERED", "FRAUDULENT"];

const detail: Record<VerdictCode, string> = {
  VERIFIED: "Aligned DKIM from a known domain, or passing checks that outnumber weak findings.",
  NO_RISK_FOUND: "Nothing proves the sender — but nothing asks for anything either. Not an accusation.",
  TAMPERED: "Matched a real filing, and one parsed field disagreed with it.",
  FRAUDULENT: "One disqualifying finding, or two weak ones alongside a request.",
};

export function OutcomesSection() {
  return (
    <Section id="outcomes">
      <SectionHeading
        eyebrow="Four outcomes, never two"
        title="Safe or scam"
        accent="has to guess on everything it hasn't seen."
        lead="Most tools return a binary. The fourth outcome — a calibrated “I don't know, and here's what I'd have needed” — is the harder, more honest answer."
      />

      <RevealGroup className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4" stagger={0.08}>
        {order.map((code) => {
          const meta = verdictMeta[code];
          return (
            <RevealItem key={code}>
              <article
                className={cn(
                  "flex h-full flex-col border bg-card p-6 transition-shadow hover:shadow-[0_16px_40px_-24px_rgba(16,27,40,0.4)]",
                  meta.border,
                )}
              >
                <span className={cn("size-2.5 rounded-full", meta.dot)} aria-hidden />
                <h3 className={cn("mt-5 text-lg font-medium", meta.text)}>{meta.label}</h3>
                <p className="mt-3 font-serif text-[0.9375rem] leading-relaxed text-foreground/70">
                  {meta.summary}
                </p>
                <p className="mt-4 border-t border-border pt-4 font-serif text-sm leading-relaxed text-foreground/50">
                  {detail[code]}
                </p>
              </article>
            </RevealItem>
          );
        })}
      </RevealGroup>
    </Section>
  );
}
