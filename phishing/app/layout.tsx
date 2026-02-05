import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title:
    "Phisherman AI - AI-Resistant Phishing Detection & Deception Framework",
  description:
    "Stop AI-powered phishing with LLM-aware multi-channel protection. Detect, deceive, and defeat sophisticated threats with adaptive honeypots and forensic evidence.",
  keywords:
    "phishing detection, AI security, cybersecurity, honeypot, CERT-IN, multi-channel protection",
  authors: [{ name: "Phisherman AI" }],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="antialiased">{children}</body>
    </html>
  );
}
