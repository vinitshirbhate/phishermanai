import { Suspense } from "react";
import type { Metadata } from "next";

import { VerifyConsole } from "@/components/demo/verify-console";
import { Eyebrow } from "@/components/site/section";

export const metadata: Metadata = {
  title: "Demo",
  description:
    "Four recorded examples — verified, tampered, fraudulent and no risk found — plus a browser-only rule preview for text you paste yourself.",
};

export default function DemoPage() {
  return (
    <div className="pt-12 pb-24 sm:pt-16">
      <div className="container-page">
        <Eyebrow>Interactive demo</Eyebrow>
        <h1 className="h-display mt-4 max-w-3xl">
          Four outcomes, one message at a time.{" "}
          <span className="h-accent">Spend the time on tampered.</span>
        </h1>
        <p className="copy-lg mt-6 max-w-2xl">
          The altered value beside the filed value is the whole point. Then close on{" "}
          <span className="text-foreground">no risk found</span> — a calibrated “I don&rsquo;t
          know, and here is exactly what I would have needed”.
        </p>

        <div className="mt-14">
          <Suspense
            fallback={
              <div className="min-h-[24rem] rounded-xl border border-dashed border-border" />
            }
          >
            <VerifyConsole />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
