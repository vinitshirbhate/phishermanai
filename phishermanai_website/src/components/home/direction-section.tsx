import { Section, SectionHeading } from "@/components/site/section";
import { chokepoints } from "@/lib/content";

const examples = [
  {
    text: "The system will authenticate the user by sending OTP on registered Mobile",
    verdict: "harmless",
    tone: "verified" as const,
    note: "the credential travels inward",
  },
  {
    text: "Please share the OTP with me",
    verdict: "severity 5",
    tone: "fraud" as const,
    note: "the credential travels outward",
  },
];

export function DirectionSection() {
  return (
    <Section id="direction">
      <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
        <div>
          <SectionHeading
            eyebrow="Rules match direction"
            title="Same keywords."
            accent="Only direction separates them."
            lead="Keyword systems fail exactly where investor-awareness copy lives — a warning about a scam contains every word the scam does. Every rule here declares an entity, an action, a direction and its suppressors."
          />
          <p className="copy mt-6">
            The engine refuses to load a rule that declares no action but claims a severity above
            1. A rule that cannot say what is being done to what is not allowed to accuse anyone.
          </p>
        </div>

        <div className="space-y-4">
          {examples.map((example) => (
            <div
              key={example.text}
              className="rounded-xl border border-border bg-card p-5 sm:p-6"
            >
              <p className="font-mono text-[0.875rem] leading-relaxed">“{example.text}”</p>
              <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span
                  className={
                    example.tone === "verified"
                      ? "mono-label rounded-full border border-verdict-verified/35 bg-verdict-verified/10 px-2.5 py-0.5 text-verdict-verified"
                      : "mono-label rounded-full border border-verdict-fraud/35 bg-verdict-fraud/10 px-2.5 py-0.5 text-verdict-fraud"
                  }
                >
                  {example.verdict}
                </span>
                <span className="font-serif text-sm text-foreground/55 italic">
                  {example.note}
                </span>
              </div>
            </div>
          ))}

          <p className="pt-2 font-serif text-sm text-foreground/50 italic">
            Turning awareness suppression off raises the false-positive rate from 0.0% to 1.9%,
            with fraud recall unchanged at 95%. Every one of those false positives came from the
            adversarial set.
          </p>
        </div>
      </div>

      <div className="mt-16 border-t border-border pt-14">
        <h3 className="text-xl font-medium sm:text-2xl">
          Four chokepoints carry everything a filing cannot
        </h3>
        <p className="copy mt-4 max-w-2xl">
          The filings comparison only reaches listed-company corporate actions. These four run on
          every message, whether or not a filing exists to compare against.
        </p>

        <div className="mt-10 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
          {chokepoints.map((chokepoint) => (
            <div key={chokepoint.name} className="bg-card p-6">
              <div className="flex items-center gap-3">
                <chokepoint.icon className="size-4.5 text-primary" aria-hidden />
                <h4 className="text-base font-medium">{chokepoint.name}</h4>
              </div>
              <p className="mt-3 font-serif text-[0.9375rem] text-foreground/75 italic">
                {chokepoint.question}
              </p>
              <p className="copy mt-3 text-[1rem]">{chokepoint.detail}</p>
              <p className="mono-label mt-4 text-foreground/35">{chokepoint.register}</p>
            </div>
          ))}
        </div>
      </div>
    </Section>
  );
}
