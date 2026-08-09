import type { Metadata } from "next";

import { ChannelPage } from "@/components/product/channel-page";
import { Section, SectionHeading } from "@/components/site/section";
import { TerminalCard } from "@/components/site/terminal-card";

export const metadata: Metadata = {
  title: "Voice",
  description:
    "Cloned executive and regulator calls, transcribed and scored for synthetic speech — with an explicit statement that the system cannot say whose voice was cloned.",
};

const removed = [
  {
    title: "The local checkpoint",
    body: "It scored genuine recordings as 100% spoof. Keeping it as an offline fallback would have meant a confidently wrong answer whenever the network was down, which is worse than no answer at all.",
  },
  {
    title: "The cloned-official verdict",
    body: "A rule once forced Critical when a voice both matched an enrolled official and carried synthetic artefacts. Removing the speaker-embedding model removed the match it tested, so the rule could never fire — and a rule that cannot fire is dead code pretending to be a safeguard.",
  },
];

export default function VoiceChannelPage() {
  return (
    <ChannelPage id="voice">
      <Section id="honest">
        <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="What was taken out"
              title="Two capabilities were removed"
              accent="rather than left in looking useful."
              lead="Both would have made the demo stronger. Both would have made the answer less trustworthy."
            />
            <div className="mt-10 space-y-6">
              {removed.map((item) => (
                <div key={item.title} className="border-l-2 border-primary/40 pl-5">
                  <h3 className="text-base font-medium">{item.title}</h3>
                  <p className="copy mt-2 text-[1rem]">{item.body}</p>
                </div>
              ))}
            </div>
            <p className="copy mt-8">
              The consequence worth knowing: with the cloned-official override gone, the
              trusted-source cap is unopposed. Spoofed audio arriving from a registry-verified,
              signed source is held at Low. That is a live weakness, and it is documented rather
              than hidden.
            </p>
          </div>

          <TerminalCard label="CONSTRAINTS" meta="voice path">
            <div className="space-y-3">
              {[
                ["transcode", "16 kHz mono MP3 before upload"],
                ["upload cap", "5 MB — a 10-minute clip lands near 3.6 MB"],
                ["duration cap", "120 s default; over it returns 413"],
                ["transcription", "Whisper, local"],
                ["spoof scoring", "hosted API — key and network required"],
                ["speaker match", "not implemented"],
                ["on failure", "available: false, excluded from fusion"],
              ].map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-4 border-b border-cream/8 pb-2.5 last:border-b-0">
                  <span className="mono-label shrink-0 text-cream/40">{label}</span>
                  <span className="text-right font-mono text-[0.75rem] text-cream/75">
                    {value}
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-5 font-serif text-xs leading-relaxed text-cream/45 italic">
              A clip over the duration cap is rejected outright. Returning an unscored low-risk
              verdict on audio nothing examined would be the worst failure this path could
              produce.
            </p>
          </TerminalCard>
        </div>
      </Section>
    </ChannelPage>
  );
}
