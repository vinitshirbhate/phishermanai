import { AuthFramework } from "@/components/home/auth-framework";
import { ChannelCarousel } from "@/components/home/channel-carousel";
import { ChannelGrid } from "@/components/home/channel-grid";
import { CtaSection } from "@/components/home/cta-section";
import { DualThreat } from "@/components/home/dual-threat";
import { GatesSection } from "@/components/home/gates-section";
import { Hero } from "@/components/home/hero";
import { LimitationsSection } from "@/components/home/limitations-section";
import { MetricsSection } from "@/components/home/metrics-section";
import { OutcomeBand } from "@/components/home/outcome-band";
import { OutcomesSection } from "@/components/home/outcomes-section";
import { TargetUsers } from "@/components/home/target-users";
import { ThreatLandscape } from "@/components/home/threat-landscape";
import { AccreditationRow, TrustBar } from "@/components/home/trust-bar";

export default function HomePage() {
  return (
    <>
      <Hero />
      <TrustBar />
      <OutcomeBand />
      <ThreatLandscape />
      <DualThreat />
      <ChannelGrid />
      <AuthFramework />
      <ChannelCarousel />
      <OutcomesSection />
      <TargetUsers />
      <AccreditationRow />
      <GatesSection />
      <MetricsSection />
      <LimitationsSection />
      <CtaSection />
    </>
  );
}
