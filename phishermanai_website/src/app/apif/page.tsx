import type { Metadata } from "next";
import { Braces, CheckCircle2, FileText, Link2, ShieldCheck } from "lucide-react";

import { ApifLinkPreview } from "@/components/apif/apif-link-preview";
import { ApifVerifyForm } from "@/components/apif/apif-verify-form";
import { PageHeader, Section, SectionHeading } from "@/components/site/section";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const metadata: Metadata = {
  title: "APIF endpoints",
  description:
    "API reference for APIF — the AI Propaganda Intelligence Framework backend. Includes the unified verify endpoint, per-modality analysis routes, and a live demo form.",
};

const endpoints = [
  {
    method: "POST",
    path: "/api/v1/verify",
    description:
      "Unified check for text, audio, video or image with optional coordination analysis.",
  },
  {
    method: "POST",
    path: "/api/v1/verify-link",
    description:
      "Preview a Twitter/X or news media URL with Firecrawl, then verify the extracted text.",
  },
  {
    method: "POST",
    path: "/api/v1/preview",
    description: "Extract title, summary, text and media from a URL using Firecrawl.",
  },
  {
    method: "POST",
    path: "/api/v1/analyze/text",
    description: "Text-only classification for messages, posts and social captions.",
  },
  {
    method: "POST",
    path: "/api/v1/analyze/audio",
    description: "Synthetic speech and captioned audio analysis from an uploaded file.",
  },
  {
    method: "POST",
    path: "/api/v1/analyze/video",
    description: "Deepfake video analysis plus any transcript or caption text.",
  },
  {
    method: "GET",
    path: "/health",
    description: "Service health and downstream dependency status.",
  },
  {
    method: "GET",
    path: "/",
    description: "API metadata and the primary endpoint for the service.",
  },
];

const examples = [
  {
    title: "Verify request",
    icon: Link2,
    body: (
      <pre className="rounded-3xl border border-border bg-background p-5 text-sm leading-relaxed text-foreground">
        <code>
          {`curl -X POST http://localhost:8000/api/v1/verify \
  -F "text=This notice is from SEBI." \
  -F "source=sender@example.com" \
  -F "include_coordination=true"`}
        </code>
      </pre>
    ),
  },
  {
    title: "Text analysis payload",
    icon: FileText,
    body: (
      <pre className="rounded-3xl border border-border bg-background p-5 text-sm leading-relaxed text-foreground">
        <code>
          {`{
  "text": "This stock tip is fraudulent.",
  "source_url": "https://social.example/post/123",
  "sender": "@marketwatch"
}`}
        </code>
      </pre>
    ),
  },
  {
    title: "Expected verdict",
    icon: ShieldCheck,
    body: (
      <pre className="rounded-3xl border border-border bg-background p-5 text-sm leading-relaxed text-foreground">
        <code>
          {`{
  "band": "low",
  "confidence": 0.89,
  "evidence": [
    { "signal": "dkim", "result": "aligned" },
    { "signal": "text", "result": "scam" }
  ]
}`}
        </code>
      </pre>
    ),
  },
];

export default function ApifPage() {
  return (
    <>
      <PageHeader
        eyebrow="APIF"
        title="Live verify inputs for text, audio, and video"
        accent="built around the architecture."
        lead="Submit a message body, source metadata, or a media file and see the real APIF /api/v1/verify pipeline in action, with evidence and system-level context." 
      />

      <Section tone="raised">
        <SectionHeading
          eyebrow="Live demo"
          title="Text, audio, and video inputs"
          accent="that exercise the unified verify route."
          lead="This form matches the system architecture: one endpoint, multi-modal intake, kind detection, and fused verdict output." 
        />

        <div className="mt-12">
          <ApifVerifyForm />
        </div>
      </Section>

      <Section tone="raised">
        <SectionHeading
          eyebrow="Link preview"
          title="Twitter and news URL verification"
          accent="using Firecrawl extraction."
          lead="Paste a Twitter/X or news media link, preview the extracted post/article content, and verify the discovered text with the APIF pipeline." 
        />

        <div className="mt-12">
          <ApifLinkPreview />
        </div>
      </Section>

      <Section>
        <SectionHeading
          eyebrow="Endpoint reference"
          title="APIF routes"
          accent="and the primary entry point."
          lead="Use the unified verify route for mixed input. The modality-specific analysis endpoints are there for text-only, audio-only, and video-only inspection." 
        />

        <div className="mt-12 overflow-hidden rounded-3xl border border-border bg-card">
          <Table className="min-w-full">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[16%]">Method</TableHead>
                <TableHead className="w-[34%]">Endpoint</TableHead>
                <TableHead>Description</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {endpoints.map((endpoint) => (
                <TableRow key={endpoint.path}>
                  <TableCell className="font-mono text-[0.875rem] uppercase text-foreground/70">
                    {endpoint.method}
                  </TableCell>
                  <TableCell className="font-mono text-[0.9375rem] text-foreground">
                    {endpoint.path}
                  </TableCell>
                  <TableCell className="text-[0.95rem] text-foreground/75">
                    {endpoint.description}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section tone="navy">
        <SectionHeading
          eyebrow="System architecture"
          title="How the live form maps to APIF."
          accent=""
          lead="The experience below explains what the demo does at each stage of the verification architecture." 
        />

        <div className="mt-12 grid gap-6 lg:grid-cols-2">
          <article className="rounded-3xl border border-cream/12 bg-navy-raised p-6">
            <div className="flex items-center gap-3 text-cream">
              <Braces className="size-6" aria-hidden />
              <div>
                <p className="font-semibold text-cream">Unified intake</p>
                <p className="mt-2 text-sm text-cream/65">
                  The form sends text and optional media through the same /api/v1/verify route, just like the architecture describes.
                </p>
              </div>
            </div>
          </article>
          <article className="rounded-3xl border border-cream/12 bg-navy-raised p-6">
            <div className="flex items-center gap-3 text-cream">
              <FileText className="size-6" aria-hidden />
              <div>
                <p className="font-semibold text-cream">Kind detection</p>
                <p className="mt-2 text-sm text-cream/65">
                  APIF determines whether an upload is audio, video, or image and routes it to the appropriate analysis pipeline.
                </p>
              </div>
            </div>
          </article>
          <article className="rounded-3xl border border-cream/12 bg-navy-raised p-6">
            <div className="flex items-center gap-3 text-cream">
              <ShieldCheck className="size-6" aria-hidden />
              <div>
                <p className="font-semibold text-cream">Verification layer</p>
                <p className="mt-2 text-sm text-cream/65">
                  The app fuses detector signals, registry checks, and optional coordination analysis into one verdict band.
                </p>
              </div>
            </div>
          </article>
          <article className="rounded-3xl border border-cream/12 bg-navy-raised p-6">
            <div className="flex items-center gap-3 text-cream">
              <CheckCircle2 className="size-6" aria-hidden />
              <div>
                <p className="font-semibold text-cream">Live result</p>
                <p className="mt-2 text-sm text-cream/65">
                  The result panel displays the actual payload returned by the backend, proving the page is wired to the running APIF service.
                </p>
              </div>
            </div>
          </article>
        </div>
      </Section>
    </>
  );
}
