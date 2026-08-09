import type { Metadata } from "next";

import { FusionDiagram } from "@/components/diagrams/channel-diagram";
import { ChannelPage } from "@/components/product/channel-page";
import { Section, SectionHeading } from "@/components/site/section";

export const metadata: Metadata = {
  title: "Video",
  description:
    "Frame-level deepfake scoring with the audio pipeline alongside it — and an explicit statement that detectors do not generalise to unseen generators.",
};

export default function VideoChannelPage() {
  return (
    <ChannelPage id="video">
      <Section id="generalisation" tone="raised">
        <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="The generalisation problem"
              title="A detector that scores 0.95 on its own test set"
              accent="can score near chance on next month's generator."
              lead="This is the consistent finding across published surveys of deepfake video detection, not a quirk of this implementation. Treating it as solved would be the single easiest way to mislead a judge."
            />

            <p className="copy mt-6">
              Three consequences follow, and all three are built in rather than promised:
            </p>

            <ol className="mt-6 space-y-4">
              {[
                "The video signal is weighted at 0.20 alongside five others, never trusted on its own.",
                "When the detector cannot run, it is excluded from the mean and the remaining weights are renormalised — it is never scored as zero, because a detector that did not run is not evidence of innocence.",
                "The phrase “this is a deepfake” is on the blocked-claims list. It cannot appear in user-facing text, and the build fails if it does.",
              ].map((item, index) => (
                <li key={item} className="flex gap-4">
                  <span className="font-mono text-sm text-primary">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="font-serif text-[1.0625rem] leading-relaxed text-foreground/70">
                    {item}
                  </span>
                </li>
              ))}
            </ol>

            <p className="copy mt-8">
              What would change this: content credentials at source. If an exchange or a listed
              company published official video carrying provenance metadata, a synthesised copy
              would simply lack it — a positive check rather than a forensic guess. Almost
              nothing carries it today, so its absence is not currently treated as evidence.
            </p>
          </div>

          <FusionDiagram />
        </div>
      </Section>
    </ChannelPage>
  );
}
