import { Section, SectionHeading } from "@/components/site/section";
import { type VerdictCode, verdictMeta } from "@/lib/analysis";
import { cn } from "@/lib/utils";

const order: VerdictCode[] = ["VERIFIED", "NO_RISK_FOUND", "TAMPERED", "FRAUDULENT"];

const detail: Record<VerdictCode, string> = {
  VERIFIED:
    "An aligned DKIM signature from a known domain, or passing checks that outnumber the weak findings. The sender is proven, not merely plausible.",
  NO_RISK_FOUND:
    "Nothing proves the sender, and nothing in the message asks for anything. This is the honest answer, and it is what makes the other three trustworthy.",
  TAMPERED:
    "The document matched a real filing and one parsed field disagreed with it. An unreadable field can never produce this verdict.",
  FRAUDULENT:
    "One disqualifying finding, or two weak ones alongside a request. Every finding names the register it came from and the date that register was read.",
};

export function OutcomesSection() {
  return (
    <Section id="outcomes">
      <SectionHeading
        eyebrow="Four outcomes, never two"
        title="A system that only knows safe and scam"
        accent="has to guess on everything it has not seen."
        lead="Most tools return a binary. The fourth outcome — a calibrated “I don't know, and here is exactly what I would have needed” — is the harder and more useful answer."
      />

      <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {order.map((code) => {
          const meta = verdictMeta[code];
          return (
            <article
              key={code}
              className={cn(
                "flex flex-col rounded-xl border bg-card p-6 transition-shadow hover:shadow-[0_16px_40px_-24px_rgba(11,21,48,0.4)]",
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
          );
        })}
      </div>
    </Section>
  );
}
