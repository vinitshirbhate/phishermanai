import { PipelineFlow } from "@/components/diagrams/pipeline-flow";
import { Section, SectionHeading } from "@/components/site/section";

export function PipelineSection() {
  return (
    <Section id="pipeline" tone="raised">
      <SectionHeading
        eyebrow="How it works"
        title="Six stages, one journey,"
        accent="and a branch that answers most mail in 10 ms."
        lead="Solid steps are the journey of a single message. Everything the checks read is local data — no step touches the internet."
      />

      <PipelineFlow className="mt-12" />
    </Section>
  );
}
