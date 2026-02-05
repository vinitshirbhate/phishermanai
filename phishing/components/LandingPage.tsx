"use client";

import { Hero } from "@/components/Hero";
import { Features } from "@/components/Features";
import { HowItWorks } from "@/components/HowItWorks";
import { DemoCard } from "@/components/DemoCard";
import { WhyItMatters } from "@/components/WhyItMatters";
import { Footer } from "@/components/Footer";

export function LandingPage() {
  return (
    <div className="min-h-screen bg-midnight-blue">
      <Hero />
      <Features />
      <HowItWorks />
      <DemoCard />
      <WhyItMatters />
      <Footer />
    </div>
  );
}
