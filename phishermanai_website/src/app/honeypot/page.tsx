import { HoneypotSimulator } from "@/components/honeypot/honeypot-simulator";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Honeypot | PhishermanAI",
  description: "A contained, interactive demonstration of AI honeypot engagement and threat intelligence capture.",
};

export default function HoneypotPage() {
  return <HoneypotSimulator />;
}