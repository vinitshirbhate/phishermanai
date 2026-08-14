"use client";

import { useCallback, useState } from "react";
import { ArrowRight, FileText, Link2, Radar, ShieldCheck, Video, Music, ImageIcon } from "lucide-react";

import { ApifAnalysisLoader } from "@/components/apif/apif-analysis-loader";
import { Button } from "@/components/ui/button";
import { FileUpload } from "@/components/ui/file-upload";
import { Input } from "@/components/ui/input";
import { SwitchField } from "@/components/ui/switch-field";
import { kindForFile } from "@/lib/media-kind";
import { postFormDataWithProgress } from "@/lib/upload";
import { cn } from "@/lib/utils";

type MediaItem = {
  
  type: "video" | "audio" | "image";
  url: string;
  description: string;
};

type LinkPreviewPayload = {
  url: string;
  title: string;
  summary: string;
  text: string;
  source_name?: string | null;
  media: MediaItem[];
};

type SignalItem = {
  name: string;
  score: number;
  available: boolean;
  summary: string;
  evidence?: Record<string, unknown>;
  error?: string | null;
};

type VerdictPayload = {
  risk_score: number;
  band: string;
  headline: string;
  explanation: string;
  signals: SignalItem[];
  transcript?: string;
  override_applied?: string | null;
};

type VerifyResponse = {
  preview: LinkPreviewPayload;
  verdict: VerdictPayload;
};

const VECTOR_LABELS: Record<string, string> = {
  text_phishing: "Text phishing",
  voice_spoof: "Audio spoof",
  video_deepfake: "Video manipulation",
  source_untrusted: "Source trust",
  coordination: "Coordinated campaign",
  market_anomaly: "Market anomaly",
};

const VECTOR_ORDER = [
  "text_phishing",
  "voice_spoof",
  "video_deepfake",
  "source_untrusted",
  "coordination",
  "market_anomaly",
];

const bandClasses: Record<string, string> = {
  low: "bg-emerald-100 text-emerald-700",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

function iconForMedia(type: string) {
  switch (type) {
    case "video":
      return Video;
    case "audio":
      return Music;
    case "image":
      return ImageIcon;
    default:
      return FileText;
  }
}

export function ApifLinkPreview() {
  const apiBase = process.env.NEXT_PUBLIC_APIF_BASE_URL ?? "http://localhost:8000";
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [includeCoordination, setIncludeCoordination] = useState(true);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  const handleFilesChange = useCallback((files: File[]) => {
    setFile(files[0] ?? null);
    setResult(null);
    setError(null);
    setUploadProgress(null);
  }, []);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!url.trim()) {
      setError("Enter a Twitter/X or news link to preview and verify.");
      return;
    }

    const form = new FormData();
    form.append("url", url.trim());
    form.append("include_coordination", String(includeCoordination));
    if (file) {
      form.append("file", file, file.name);
    }

    setBusy(true);
    setUploadProgress(file ? 0 : null);

    try {
      const body = await postFormDataWithProgress(
        `${apiBase}/api/v1/verify-link`,
        form,
        file ? setUploadProgress : undefined,
      );

      setResult(JSON.parse(body) as VerifyResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setUploadProgress(null);
    }
  };

  const band = result?.verdict.band.toLowerCase() ?? "low";

  return (
    <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr]">
      <ApifAnalysisLoader
        loading={busy}
        hasLink
        kind={kindForFile(file)}
        includeCoordination={includeCoordination}
      />

      <div className="space-y-6 rounded-3xl border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-primary">
            <Link2 className="size-5" aria-hidden />
          </div>
          <div>
            <p className="font-medium">Link preview and verify</p>
            <p className="text-sm text-foreground/60">
              Paste a Twitter/X or news media link and APIF will extract the page preview with Firecrawl, then verify the text content.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label htmlFor="apif-link-url" className="font-medium">
              Media link
            </label>
            <Input
              id="apif-link-url"
              type="url"
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
                setError(null);
                setResult(null);
              }}
              placeholder="https://x.com/example/status/123456789"
            />
          </div>

          <div className="space-y-2">
            <span className="font-medium">Optional video/audio upload</span>
            <FileUpload
              accept=".wav,.mp3,.m4a,.flac,.ogg,.aac,.wma,.opus,.mp4,.mov,.mkv,.avi,.webm,.m4v"
              maxSizeMB={100}
              disabled={busy}
              uploadProgress={uploadProgress}
              onFilesChange={handleFilesChange}
              title="Drop an audio or video file"
              hint="Optional ∙ Up to 100MB"
              selectLabel="Select media"
            />
            <p className="text-sm text-foreground/50">
              Optionally upload a video or audio file to analyse together with the extracted post text.
            </p>
          </div>

          <SwitchField
            id="apif-link-coordination"
            checked={includeCoordination}
            onCheckedChange={setIncludeCoordination}
            disabled={busy}
            icon={Radar}
            label="Include coordination analysis"
            sublabel="slower"
            description="Cross-checks the extracted post against known coordinated campaign clusters before the verdict is fused."
          />

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-foreground/65">
              Firecrawl links are fetched server-side and summarized before APIF scoring.
            </p>
            <Button type="submit" disabled={busy} className="h-11 rounded-full px-6">
              {busy ? "Previewing…" : "Preview and verify"}
            </Button>
          </div>

          {error ? (
            <p className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </form>
      </div>

      <div className="space-y-6">
        <div className="rounded-3xl border border-border bg-card p-6">
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-primary">
              <ShieldCheck className="size-5" aria-hidden />
            </div>
            <div>
              <p className="font-medium">Preview & risk summary</p>
              <p className="text-sm text-foreground/60">
                The result includes the extracted page preview and APIF’s fused verdict over the discovered text.
              </p>
            </div>
          </div>

          {result ? (
            <div className="mt-6 space-y-4 rounded-3xl border border-border bg-background p-5">
              <div className="grid gap-4">
                <div className="rounded-3xl border border-border/80 bg-card p-4">
                  <p className="text-sm uppercase tracking-wide text-foreground/50">Preview</p>
                  <p className="mt-3 font-semibold text-foreground">{result.preview.title || "Untitled preview"}</p>
                  <p className="mt-2 text-sm text-foreground/70">{result.preview.summary}</p>
                  {result.preview.source_name ? (
                    <p className="mt-2 text-sm text-foreground/65">Source: {result.preview.source_name}</p>
                  ) : null}
                  <p className="mt-3 text-sm text-foreground/65 line-clamp-4">{result.preview.text}</p>
                  <a
                    href={result.preview.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 inline-flex items-center gap-2 text-sm text-primary hover:text-primary/80"
                  >
                    View original link
                    <ArrowRight className="size-4" aria-hidden />
                  </a>
                </div>

                <div className="space-y-3 rounded-3xl border border-border/80 bg-card p-4">
                  <p className="text-sm uppercase tracking-wide text-foreground/50">Extracted media</p>
                  {result.preview.media.length ? (
                    <div className="space-y-3">
                      {result.preview.media.map((item, index) => {
                        const Icon = iconForMedia(item.type);
                        return (
                          <div key={`${item.type}-${index}`} className="flex items-start gap-3 rounded-2xl border border-border/80 bg-background p-3">
                            <div className="grid h-10 w-10 place-items-center rounded-2xl bg-primary/10 text-primary">
                              <Icon className="size-5" aria-hidden />
                            </div>
                            <div className="min-w-0">
                              <p className="font-medium capitalize">{item.type}</p>
                              <p className="text-sm text-foreground/65">{item.description || "Media found on the page."}</p>
                              <a
                                href={item.url}
                                target="_blank"
                                rel="noreferrer"
                                className="mt-1 text-sm text-primary hover:text-primary/80"
                              >
                                Open media
                              </a>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm leading-6 text-foreground/65">
                      No audio or video media links were extracted from this page. Firecrawl may still have fetched the page text, but embedded players and JS-loaded media are not always returned as direct media URLs.
                    </p>
                  )}
                </div>

                <div className="rounded-3xl border border-border/80 bg-card p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm uppercase tracking-wide text-foreground/50">Verdict</p>
                      <p className="mt-2 text-lg font-semibold text-foreground">{result.verdict.headline}</p>
                    </div>
                    <span className={cn("rounded-full px-3 py-1 text-sm font-semibold", bandClasses[band] ?? "bg-slate-100 text-slate-800") }>
                      {result.verdict.band}
                    </span>
                  </div>
                  <p className="mt-3 text-sm text-foreground/65">Risk score: {result.verdict.risk_score.toFixed(2)}</p>
                  <p className="mt-2 text-sm text-foreground/65">{result.verdict.explanation}</p>
                </div>

                <div className="rounded-3xl border border-border/80 bg-card p-4">
                  <p className="text-sm uppercase tracking-wide text-foreground/50">Attack vector signals</p>
                  <div className="mt-4 grid gap-3">
                    {VECTOR_ORDER.map((name) => {
                      const signal = result.verdict.signals.find((item) => item.name === name);
                      if (!signal) return null;
                      return (
                        <div key={name} className="rounded-2xl border border-border/80 bg-background p-3">
                          <div className="flex items-center justify-between gap-3">
                            <p className="font-medium">{VECTOR_LABELS[name] ?? name}</p>
                            <span className="text-sm text-foreground/65">{signal.score.toFixed(2)}</span>
                          </div>
                          <p className="mt-1 text-sm text-foreground/70">{signal.summary || signal.error || "No additional details."}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-6 rounded-3xl border border-border/80 bg-background p-6 text-sm text-foreground/65">
              Enter a link and click Preview and verify to extract text and media, then see APIF’s fused risk verdict.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
