import type { Metadata } from "next";
import { MessageSquareWarning } from "lucide-react";
import { PageHeader } from "@/components/site/section";
import { SmsDetectionForm } from "@/components/sms/sms-detection-form";

export const metadata: Metadata = {
  title: "SMS Detection",
  description: "Check a suspicious SMS for phishing and scam signals.",
};

export default function SmsDetectionPage() {
  return (
    <>
      <PageHeader
        eyebrow="Message security / SMS analysis"
        title="Check the message."
        accent="Before you tap."
        lead="Paste an SMS to check whether it may be phishing. The result shows the detector’s label, confidence, and message."
      />
      <div className="container-page pb-20">
        <div className="mb-5 flex items-center gap-2 text-xs text-muted-foreground">
          <MessageSquareWarning className="size-4 text-primary" />
          <span>One message at a time · analysis runs through the SMS detection service</span>
        </div>
        <SmsDetectionForm />
      </div>
    </>
  );
}
