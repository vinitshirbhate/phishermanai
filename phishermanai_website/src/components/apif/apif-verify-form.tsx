"use client";

import { useState } from "react";
import {
  CheckCircle2,
  FileText,
  ShieldCheck,
  Upload,
  Video,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { FileUpload } from "../ui/file-upload";

type VerdictResponse = {
  band: string;
  confidence: number;
  evidence?: Array<{ signal: string; result: string }>;
  message?: string;
  [key: string]: unknown;
};

const ACCEPTED_MEDIA = [
  ".wav",
  ".mp3",
  ".m4a",
  ".flac",
  ".ogg",
  ".aac",
  ".wma",
  ".opus",
  ".mp4",
  ".mov",
  ".mkv",
  ".avi",
  ".webm",
  ".m4v",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".bmp",
  ".gif",
].join(",");

export function ApifVerifyForm() {
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [includeCoordination, setIncludeCoordination] = useState(true);
  const [result, setResult] = useState<VerdictResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleFileChange = (filesOrEvent: File[] | React.ChangeEvent<HTMLInputElement>) => {
    setResult(null);
    setError(null);

    const selected = Array.isArray(filesOrEvent)
      ? filesOrEvent
      : Array.from(filesOrEvent.target.files ?? []);

    setFile(selected[0] ?? null);
  };

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

    try {
      const response = await fetch(`${apiBase}/api/v1/verify`, {
        method: "POST",
        body: form,
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(body || "APIF request failed.");
      }

      const data = (await response.json()) as VerdictResponse;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr]">
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
            <label htmlFor="file-upload-handle" className="font-medium">
              Audio / video / image file
            </label>

            <FileUpload onChange={handleFileChange} />
            <p className="text-sm text-foreground/50">
              Supported formats: audio, video, and image files. Text is optional when a file is present.
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-foreground/70">
              <input
                type="checkbox"
                checked={includeCoordination}
                onChange={(event) => setIncludeCoordination(event.target.checked)}
                className="h-4 w-4 rounded border-input text-primary focus-visible:ring-ring"
              />
              Include coordination analysis
            </label>
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
                      result.band === "low" ? "bg-verdict-fraud/10 text-verdict-fraud" : "bg-verdict-verified/10 text-verdict-verified",
                    )}
                  >
                    <CheckCircle2 className="size-5" aria-hidden />
                  </div>
                  <div>
                    <p className="font-medium">Band: {result.band}</p>
                    <p className="text-sm text-foreground/65">
                      Confidence {result.confidence?.toFixed?.(2) ?? "—"}
                    </p>
                  </div>
                </div>

                {result.evidence?.length ? (
                  <div className="space-y-2">
                    <p className="mono-label text-foreground/45">Evidence</p>
                    <div className="space-y-2">
                      {result.evidence.map((item, index) => (
                        <div
                          key={`${item.signal}-${index}`}
                          className="rounded-2xl border border-border/80 bg-card p-3"
                        >
                          <p className="font-medium">{item.signal}</p>
                          <p className="text-sm text-foreground/65">{item.result}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-foreground/65">
                    If the backend returns no raw evidence array, check the full payload in the console.
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
