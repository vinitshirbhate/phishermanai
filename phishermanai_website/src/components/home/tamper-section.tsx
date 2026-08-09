import { Section, SectionHeading } from "@/components/site/section";
import { TerminalCard } from "@/components/site/terminal-card";

const rules = [
  {
    title: "Python compares, models do not",
    body: "Whether 125.00 equals 12.50 is an integer comparison. One field parser runs on both sides of that comparison, so the document and the filing are read the same way before either is judged.",
  },
  {
    title: "An unreadable field can never produce “tampered”",
    body: "A false accusation against a real document destroys credibility faster than a miss. If a value cannot be parsed with confidence, the comparison is skipped and reported as skipped.",
  },
];

export function TamperSection() {
  return (
    <Section id="tamper" tone="navy">
      <div className="grid gap-12 lg:grid-cols-[1fr_1.05fr] lg:items-center lg:gap-16">
        <TerminalCard label="TAMPER CHECK" meta="birla corporation · 500335">
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
              ["record date", "24 Jul 2026", "matches"],
              ["face value", "₹10", "matches"],
              ["scrip code", "500335", "matches"],
            ].map(([field, value, state]) => (
              <div key={field} className="flex items-baseline justify-between gap-3">
                <span className="mono-label text-cream/40">{field}</span>
                <span className="font-mono text-[0.8125rem] text-cream/60">
                  {value}{" "}
                  <span className="text-verdict-verified">· {state}</span>
                </span>
              </div>
            ))}
          </div>
        </TerminalCard>

        <div>
          <SectionHeading
            eyebrow="What makes it different"
            title="A genuine circular, from a real company,"
            accent="with one number edited."
            lead="Every authentication check passes, because nothing about the sender is fake. The only way to catch it is to know what the company actually filed."
          />

          <div className="mt-10 space-y-6">
            {rules.map((rule) => (
              <div key={rule.title} className="border-l-2 border-primary/40 pl-5">
                <h3 className="text-base font-medium text-cream">{rule.title}</h3>
                <p className="copy mt-2 text-cream/60">{rule.body}</p>
              </div>
            ))}
          </div>

          <p className="mt-10 font-serif text-cream/50 italic">
            Tamper recall is 70%. Tampered documents called genuine: 0. Those two numbers are the
            trade this design makes deliberately.
          </p>
        </div>
      </div>
    </Section>
  );
}
