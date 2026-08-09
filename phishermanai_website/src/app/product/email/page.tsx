import type { Metadata } from "next";

import { DirectionSection } from "@/components/home/direction-section";
import { TamperSection } from "@/components/home/tamper-section";
import { ChannelPage } from "@/components/product/channel-page";
import { PipelineFlow } from "@/components/diagrams/pipeline-flow";
import { Section, SectionHeading } from "@/components/site/section";

export const metadata: Metadata = {
  title: "Email & messaging",
  description:
    "LLM-written phishing detection plus the check nothing deployed makes: comparing a circular against the corporate action the company actually filed with the exchange.",
};

export default function EmailChannelPage() {
  return (
    <ChannelPage id="email" cta={{ href: "/demo?demo=tampered_01.eml", label: "See a tampered filing" }}>
      <Section id="pipeline">
        <SectionHeading
          eyebrow="The pipeline"
          title="Six stages, one journey,"
          accent="and a branch that answers most mail in 10 ms."
          lead="Solid steps are the journey of a single message. Every lookup goes to local data — no step on this path touches the internet."
        />
        <PipelineFlow className="mt-12" />
      </Section>

      <TamperSection />
      <DirectionSection />
    </ChannelPage>
  );
}
