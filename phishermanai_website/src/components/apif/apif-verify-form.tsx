"use client";

import { useCallback, useState } from "react";
import { CheckCircle2, Radar, ShieldCheck, Upload } from "lucide-react";

import { ApifAnalysisLoader } from "@/components/apif/apif-analysis-loader";
import { ExpandableSignalCards } from "@/components/apif/expandable-signal-cards";
import { Button } from "@/components/ui/button";
import { FileUpload } from "@/components/ui/file-upload";
import { Input } from "@/components/ui/input";
import { SwitchField } from "@/components/ui/switch-field";
import { Textarea } from "@/components/ui/textarea";
import { ACCEPTED_MEDIA, kindForFile } from "@/lib/media-kind";
import { postFormDataWithProgress } from "@/lib/upload";
import { cn } from "@/lib/utils";

type SignalItem = {
  name: string;
  score: number;
  available: boolean;
  summary: string;
  evidence?: Record<string, unknown>;
  error?: string | null;
};

/**
 * Mirrors the Verdict model in apif/schemas.py — what POST /api/v1/verify really
 * returns. It previously declared `confidence` and an `evidence` array, neither
 * of which exists on the response, so the panel rendered a permanent em dash and
 * never showed any per-signal detail.
 */
type VerdictResponse = {
  risk_score: number;
  band: string;
  headline: string;
  explanation?: string;
  signals?: SignalItem[];
  override_applied?: string | null;
};

const VECTOR_LABELS: Record<string, string> = {
  text_phishing: "Text phishing",
  voice_spoof: "Audio spoof",
  video_deepfake: "Video manipulation",
  source_untrusted: "Source trust",
  coordination: "Coordinated campaign",
  market_anomaly: "Market anomaly",
};

export function ApifVerifyForm() {
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [includeCoordination, setIncludeCoordination] = useState(true);
  const [result, setResult] = useState<VerdictResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  const handleFilesChange = useCallback((files: File[]) => {
    setResult(null);
    setError(null);
    setUploadProgress(null);
    setFile(files[0] ?? null);
  }, []);

  const apiBase = process.env.NEXT_PUBLIC_APIF_BASE_URL ?? "http://localhost:8000";

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!text.trim() && !file) {
      setError("Provide either text or a media file to verify.");
      return;
    }

    const form = new FormData();
    form.append("text", text);
    if (file) {
      form.append("file", file, file.name);
    }
    if (source.trim()) {
      form.append("source", source.trim());
    }
    form.append("include_coordination", String(includeCoordination));

    setBusy(true);
    setUploadProgress(file ? 0 : null);

    try {
      const body = await postFormDataWithProgress(
        `${apiBase}/api/v1/verify`,
        form,
        file ? setUploadProgress : undefined,
      );

      setResult(JSON.parse(body) as VerdictResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setUploadProgress(null);
    }
  };

  return (
    <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr]">
      <ApifAnalysisLoader
        loading={busy}
        hasLink={false}
        kind={kindForFile(file)}
        includeCoordination={includeCoordination}
      />

      <div className="space-y-6 rounded-3xl border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-primary">
            <Upload className="size-5" aria-hidden />
          </div>
          <div>
            <p className="font-medium">Live verification</p>
            <p className="text-sm text-foreground/60">
              Submit text, audio or video to the APIF /api/v1/verify route and see the fused verdict.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label htmlFor="apif-text" className="font-medium">
              Text input
            </label>
            <Textarea
              id="apif-text"
              value={text}
              onChange={(event) => {
                setResult(null);
                setError(null);
                setText(event.target.value);
              }}
              placeholder="Paste a suspicious message, circular text, or social caption..."
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="apif-source" className="font-medium">
              Source metadata
            </label>
            <Input
              id="apif-source"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="URL, sender address, or handle"
            />
          </div>

          <div className="space-y-2">
            <span className="font-medium">Audio / video / image file</span>
            <FileUpload
              accept={ACCEPTED_MEDIA}
              maxSizeMB={100}
              disabled={busy}
              uploadProgress={uploadProgress}
              onFilesChange={handleFilesChange}
              title="Drop your media here"
              hint="Audio, video or image ∙ Up to 100MB"
              selectLabel="Select media"
            />
            <p className="text-sm text-foreground/50">
              Supported formats: audio, video, and image files. Text is optional when a file is present.
            </p>
          </div>

          <SwitchField
            id="apif-coordination"
            checked={includeCoordination}
            onCheckedChange={setIncludeCoordination}
            disabled={busy}
            icon={Radar}
            label="Include coordination analysis"
            sublabel="slower"
            description="Cross-checks the submission against known coordinated campaign clusters before the verdict is fused."
          />

          <div className="flex justify-end">
            <Button type="submit" disabled={busy} className="h-11 rounded-full px-6">
              {busy ? "Verifying…" : "Verify now"}
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
              <p className="font-medium">APIF result</p>
              <p className="text-sm text-foreground/60">
                The unified endpoint returns a fused verdict and per-signal evidence when available.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            {result ? (
              <div className="space-y-4 rounded-3xl border border-border bg-background p-5">
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      "grid h-11 w-11 place-items-center rounded-2xl",
                      result.band === "Low"
                        ? "bg-verdict-verified/10 text-verdict-verified"
                        : "bg-verdict-fraud/10 text-verdict-fraud",
                    )}
                  >
                    <CheckCircle2 className="size-5" aria-hidden />
                  </div>
                  <div>
                    <p className="font-medium">Band: {result.band}</p>
                    <p className="text-sm text-foreground/65">
                      Risk score {result.risk_score?.toFixed?.(2) ?? "—"}
                    </p>
                  </div>
                </div>

                {result.headline ? <p className="font-medium">{result.headline}</p> : null}
                {result.explanation ? (
                  <p className="copy text-[0.9375rem]">{result.explanation}</p>
                ) : null}

                {result.signals?.length ? (
                  <div className="space-y-2">
                    <p className="mono-label text-foreground/45">Signals</p>
                    <ExpandableSignalCards
                      cards={result.signals.map((item) => ({
                        id: item.name,
                        label: VECTOR_LABELS[item.name] ?? item.name,
                        score: item.score,
                        available: item.available,
                        summary: item.summary,
                        error: item.error,
                        evidence: item.evidence,
                      }))}
                    />
                  </div>
                ) : (
                  <p className="text-sm text-foreground/65">
                    This verdict carried no per-signal breakdown.
                  </p>
                )}
              </div>
            ) : (
              <div className="rounded-3xl border border-border/80 bg-background p-6 text-sm text-foreground/65">
                Submit text or a media file and click Verify now. The form sends a real request to
                <span className="font-mono"> /api/v1/verify</span> in your current environment.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-3xl border border-border bg-card p-6">
          <h3 className="font-medium">What this matches in the architecture</h3>
          <ul className="mt-4 space-y-4">
            <li className="rounded-2xl border border-border/80 bg-background p-4">
              <p className="font-medium">Text or media intake</p>
              <p className="text-sm text-foreground/65">
                The form accepts text, audio, video, or image inputs, matching APIF’s unified ingest path.
              </p>
            </li>
            <li className="rounded-2xl border border-border/80 bg-background p-4">
              <p className="font-medium">Kind detection</p>
              <p className="text-sm text-foreground/65">
                APIF detects whether the file is audio, video, or image and routes it through the right analysis pipeline.
              </p>
            </li>
            <li className="rounded-2xl border border-border/80 bg-background p-4">
              <p className="font-medium">Verification plus coordination</p>
              <p className="text-sm text-foreground/65">
                The endpoint fuses raw detector outputs with registry checks and optional coordination signals.
              </p>
            </li>
            <li className="rounded-2xl border border-border/80 bg-background p-4">
              <p className="font-medium">Real verdict output</p>
              <p className="text-sm text-foreground/65">
                The result panel shows the live API verdict band, confidence, and evidence in the same style as the system architecture.
              </p>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
