import { AuthFramework } from "@/components/home/auth-framework";
import { ChannelCarousel } from "@/components/home/channel-carousel";
import { CtaSection } from "@/components/home/cta-section";
import { DualThreat } from "@/components/home/dual-threat";
import { GatesSection } from "@/components/home/gates-section";
import { Hero } from "@/components/home/hero";
import { OutcomeBand } from "@/components/home/outcome-band";
import { OutcomesSection } from "@/components/home/outcomes-section";
import { TargetUsers } from "@/components/home/target-users";
import { ThreatLandscape } from "@/components/home/threat-landscape";
import { AccreditationRow, TrustBar } from "@/components/home/trust-bar";

/**
 * The full metrics table, precision ablation and limitations accordion
 * already live on /evidence — repeating them here would be the same wall
 * of text twice. This page teases and redirects; /evidence and /how-it-works
 * carry the depth.
 */
export default function HomePage() {
  return (
    <>
      <Hero />
      <TrustBar />
      <OutcomeBand />
      <ThreatLandscape />
      <DualThreat />
      <AuthFramework />
      <ChannelCarousel />
      <OutcomesSection />
      <TargetUsers />
      <AccreditationRow />
      <GatesSection />
      <CtaSection />
    </>
  );
}
