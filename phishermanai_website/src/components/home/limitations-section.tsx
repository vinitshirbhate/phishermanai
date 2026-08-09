import { Section, SectionHeading } from "@/components/site/section";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { limitations, type Limitation } from "@/lib/content";

export function LimitationsSection({
  scopes,
  tone = "raised",
}: {
  scopes?: Limitation["scope"][];
  tone?: "cream" | "raised";
}) {
  const items = scopes
    ? limitations.filter((item) => scopes.includes(item.scope))
    : limitations;

  return (
    <Section id="limitations" tone={tone}>
      <SectionHeading
        eyebrow="Coverage and limitations"
        title="Stated plainly, because"
        accent="bounded claims are worth more than broad ones."
        lead="Every one of these is a thing the system cannot currently do. They are published for the same reason the failing metrics are: a tool that hides its edges cannot be trusted at its centre."
      />

      <Accordion type="single" collapsible className="mt-12 w-full">
        {items.map((item, index) => (
          <AccordionItem key={item.title} value={`limitation-${index}`}>
            <AccordionTrigger className="gap-4 py-5 text-left">
              <span className="flex flex-1 flex-wrap items-center gap-3">
                <Badge
                  variant="outline"
                  className="mono-label border-foreground/15 text-foreground/45"
                >
                  {item.scope}
                </Badge>
                <span className="text-[1.0625rem] font-medium">{item.title}</span>
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <p className="copy max-w-3xl pb-2">{item.body}</p>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </Section>
  );
}
