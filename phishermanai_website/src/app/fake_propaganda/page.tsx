import type { Metadata } from "next";
import { Braces, FileText, Link2, ShieldCheck } from "lucide-react";

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
    "API reference for APIF — the AI Propaganda Intelligence Framework backend. Includes the primary verify endpoint, per-modality analysis routes, and health checks.",
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
  -F "text=SEBI circular confirmed" \
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
  "text": "The IPO allotment notice is fake.",
  "source_url": "https://x.com/post/12345",
  "sender": "noreply@company.com"
}`}
        </code>
      </pre>
    ),
  },
  {
    title: "What APIF returns",
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
        title="API endpoints for the verification engine"
        accent="and the payloads that power it."
        lead="A concise reference for the backend routes used by APIF, including the unified verify endpoint and modality-specific analysis paths."
      />

      <Section tone="raised">
        <SectionHeading
          eyebrow="Endpoint reference"
          title="Six routes, one engine," 
          accent="and a single primary entry point."
          lead="Start with /api/v1/verify for mixed text and media. The other routes are available when you want modality-specific analysis or service status." 
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

      <Section>
        <SectionHeading
          eyebrow="Usage"
          title="How to call APIF"
          accent="from curl or a client."
          lead="The following examples show a verify request, the text-only payload shape, and the form of the verdict response." 
        />

        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {examples.map((example) => (
            <article
              key={example.title}
              className="rounded-3xl border border-border bg-card p-6 shadow-sm transition-colors hover:border-primary/40"
            >
              <div className="flex items-center gap-3">
                <span className="grid size-11 place-items-center rounded-2xl bg-primary/10 text-primary">
                  <example.icon className="size-5" aria-hidden />
                </span>
                <h3 className="text-lg font-medium">{example.title}</h3>
              </div>
              <div className="mt-6">{example.body}</div>
            </article>
          ))}
        </div>
      </Section>
    </>
  );
}
