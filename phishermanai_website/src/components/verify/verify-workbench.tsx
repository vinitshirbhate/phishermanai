"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Download,
  FileJson,
  FileText,
  Image as ImageIcon,
  Loader2,
  Plug,
  RefreshCw,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { LiveResult } from "@/components/demo/live-result";
import { EscalationPanel } from "@/components/verify/escalation-panel";
import { FileDropzone } from "@/components/verify/file-dropzone";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  EngineError,
  fetchHealth,
  verifyFile,
  verifyText,
  warningCardUrl,
} from "@/lib/engine-client";
import type { EngineHealth, EngineVerdictResponse } from "@/lib/engine-types";
import { PREVIEW_HANDOFF_KEY } from "@/lib/handoff";
import {
  buildJsonReport,
  buildMarkdownReport,
  downloadText,
  reportFilename,
} from "@/lib/verification-report";

type Mode = "file" | "text";

export function VerifyWorkbench() {
  const [health, setHealth] = useState<EngineHealth | null>(null);
  const [probing, setProbing] = useState(true);
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [moneySent, setMoneySent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EngineVerdictResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** Used by the "Check again" button, where setting state is an event, not an effect. */
  const probe = useCallback(async () => {
    setProbing(true);
    const found = await fetchHealth();
    setHealth(found);
    setProbing(false);
  }, []);

  // The probe on mount reads an external service, so the state lands in a
  // callback rather than synchronously in the effect body.
  useEffect(() => {
    let cancelled = false;
    fetchHealth().then((found) => {
      if (cancelled) return;
      setHealth(found);
      setProbing(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    try {
      const handoff = window.sessionStorage.getItem(PREVIEW_HANDOFF_KEY);
      if (handoff) {
        window.sessionStorage.removeItem(PREVIEW_HANDOFF_KEY);
        // eslint-disable-next-line react-hooks/set-state-in-effect -- reading an external store on mount
        setText(handoff);
        setMode("text");
      }
    } catch {
      // Storage may be unavailable; the page works without the hand-off.
    }
  }, []);

  const ready = mode === "file" ? file !== null : text.trim().length > 0;
  const inputLabel = mode === "file" ? (file?.name ?? "file") : "pasted text";

  const submit = useCallback(async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const verdict =
        mode === "file" && file
          ? await verifyFile(file, { moneySent })
          : await verifyText(text, { moneySent });
      setResult(verdict);
    } catch (caught) {
      if (caught instanceof EngineError) {
        setError(caught.message);
        if (caught.unreachable) setHealth(null);
      } else {
        setError(
          caught instanceof Error ? caught.message : "Verification failed.",
        );
      }
    } finally {
      setBusy(false);
    }
  }, [busy, file, mode, moneySent, ready, text]);

  const engineDown = !probing && health === null;

  return (
    <div className="space-y-8">
      {probing ? (
        <div className="rounded-lg border border-border bg-muted/40 px-4 py-3">
          <span className="mono-label inline-flex items-center gap-2 text-foreground/45">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            looking for the engine
          </span>
        </div>
      ) : engineDown ? (
        <div className="rounded-xl border border-verdict-tampered/35 bg-verdict-tampered/8 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <span className="mono-label inline-flex items-center gap-2 text-verdict-tampered">
              <Plug className="size-3.5" aria-hidden />
              engine not running
            </span>
            <Button
              variant="outline"
              onClick={() => void probe()}
              className="ml-auto h-8"
            >
              <RefreshCw className="size-3.5" />
              Check again
            </Button>
          </div>
          <p className="copy mt-3 text-[1rem]">
            This page checks your own message against real filings and
            registers, so it needs the engine. Start it and press check again:
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg border border-border bg-card px-4 py-3 font-mono text-xs leading-relaxed">
            {`cd email_detection
python -m data.load_all          # first run only, ~30 s
uvicorn api.main:app --reload`}
          </pre>
          <p className="mt-3 font-serif text-sm text-foreground/55 italic">
            The recorded walkthrough on{" "}
            <a
              href="/demo"
              className="text-primary underline-offset-4 hover:underline"
            >
              the demo page
            </a>{" "}
            works without it.
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-verdict-verified/30 bg-verdict-verified/8 px-4 py-3">
          <span className="mono-label inline-flex items-center gap-2 text-verdict-verified">
            <Zap className="size-3.5" aria-hidden />
            live engine
          </span>
          <span className="font-mono text-[0.6875rem] text-foreground/50">
            {health?.filings.toLocaleString()} filings ·{" "}
            {health?.entities.toLocaleString()} entities ·{" "}
            {health?.domains.toLocaleString()} domains · {health?.claim_rules}{" "}
            rules
          </span>
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
        <div className="space-y-5">
          <Tabs
            value={mode}
            onValueChange={(value) => setMode(value as Mode)}
            className="gap-5"
          >
            <TabsList className="w-full max-w-sm">
              <TabsTrigger value="file">Upload a file</TabsTrigger>
              <TabsTrigger value="text">Paste the text</TabsTrigger>
            </TabsList>

            <TabsContent value="file">
              <FileDropzone
                file={file}
                onSelect={setFile}
                onError={setError}
                disabled={busy || engineDown}
              />
              {/* <ul className="mt-4 space-y-2">
                {[
                  { icon: FileText, label: ".eml", note: "Best result — headers let DKIM alignment be checked" },
                  { icon: ImageIcon, label: "Screenshot", note: "Weaker: OCR on compressed text runs words together" },
                  { icon: FileText, label: "PDF", note: "Circulars are matched to the filing and compared field by field" },
                ].map((item) => (
                  <li key={item.label} className="flex items-start gap-3">
                    <item.icon className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden />
                    <span className="font-serif text-sm leading-relaxed text-foreground/60">
                      <span className="font-mono text-xs text-foreground/75">{item.label}</span> —{" "}
                      {item.note}
                    </span>
                  </li>
                ))}
              </ul> */}
            </TabsContent>

            <TabsContent value="text">
              <label
                htmlFor="verify-text"
                className="mono-label text-foreground/45"
              >
                paste the message
              </label>
              <Textarea
                id="verify-text"
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={14}
                disabled={busy || engineDown}
                placeholder="Paste the email or WhatsApp message exactly as you received it, including any links…"
                className="mt-3 resize-none font-serif text-[0.9375rem] leading-relaxed"
              />
              <p className="mt-3 font-serif text-sm text-foreground/50 italic">
                Paste it unedited. Removing a link or a payment handle removes
                the evidence the checks run on.
              </p>
            </TabsContent>
          </Tabs>

          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4">
            <input
              type="checkbox"
              checked={moneySent}
              onChange={(event) => setMoneySent(event.target.checked)}
              disabled={busy || engineDown}
              className="mt-0.5 size-4 shrink-0 accent-[var(--color-primary)]"
            />
            <span>
              <span className="text-[0.9375rem] font-medium">
                I have already sent money
              </span>
              <span className="mt-1 block font-serif text-sm leading-relaxed text-foreground/60">
                This changes where you are sent next. Money already gone is a
                cybercrime report inside the golden hour, not a market-conduct
                complaint.
              </span>
            </span>
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={submit}
              disabled={!ready || busy || engineDown}
              className="h-11 px-6"
            >
              {busy ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                  Verifying
                </>
              ) : (
                <>
                  <ShieldCheck className="size-4" />
                  Verify this message
                </>
              )}
            </Button>
            {result || error ? (
              <Button
                variant="ghost"
                className="h-11"
                onClick={() => {
                  setResult(null);
                  setError(null);
                  setFile(null);
                  setText("");
                }}
                disabled={busy}
              >
                Start over
              </Button>
            ) : null}
          </div>

          {result ? <EscalationPanel result={result} /> : null}
        </div>

        <div className="space-y-6">
          {/* <div className="rounded-xl border border-border bg-card p-5 sm:p-6">
            <h2 className="mono-label text-foreground/45">
              before you send anything
            </h2>
            <dl className="mt-4 space-y-4">
              {[
                {
                  term: "Nothing is reported for you",
                  detail:
                    "The system warns; it never acts. Nothing is blocked, forwarded or reported without your click — and the contacts you are given come from SEBI's register, not from a search engine.",
                },
                {
                  term: "Your message is not stored",
                  detail:
                    "A SHA-256 fingerprint of the normalised content and the verdict are kept. The body, the file, and anything identifying you are not. The fingerprint is what makes five reports of one scam legible as a single campaign.",
                },
                {
                  term: "A miss is safer than a false accusation",
                  detail:
                    "A field that cannot be read confidently is never compared, so it can never produce a tamper finding. Tamper recall is 70%; tampered documents called genuine: zero.",
                },
              ].map((item) => (
                <div key={item.term}>
                  <dt className="text-[0.9375rem] font-medium">{item.term}</dt>
                  <dd className="mt-1.5 font-serif text-sm leading-relaxed text-foreground/60">
                    {item.detail}
                  </dd>
                </div>
              ))}
            </dl>
          </div> */}

          {error ? (
            <div className="rounded-xl border border-verdict-fraud/35 bg-verdict-fraud/8 p-5">
              <p className="mono-label inline-flex items-center gap-2 text-verdict-fraud">
                <AlertTriangle className="size-3.5" aria-hidden />
                could not verify
              </p>
              <p className="mt-2 font-serif text-sm leading-relaxed text-foreground/70">
                {error}
              </p>
            </div>
          ) : null}

          {result ? (
            <>
              <LiveResult
                result={result}
                showReasons={false}
                showActions={false}
              />

              <div className="rounded-xl border border-border bg-card p-5">
                <h2 className="mono-label text-foreground/45">
                  keep the evidence
                </h2>
                <p className="copy mt-2 text-[1rem]">
                  Everything the engine checked, what it compared against, and
                  what it could not see — generated here in your browser from
                  the verdict already on screen.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    className="h-9"
                    onClick={() =>
                      downloadText(
                        reportFilename(result, "md"),
                        buildMarkdownReport(result, { inputLabel, moneySent }),
                        "text/markdown",
                      )
                    }
                  >
                    <Download className="size-3.5" />
                    Report (Markdown)
                  </Button>
                  <Button
                    variant="outline"
                    className="h-9"
                    onClick={() =>
                      downloadText(
                        reportFilename(result, "json"),
                        buildJsonReport(result, { inputLabel, moneySent }),
                        "application/json",
                      )
                    }
                  >
                    <FileJson className="size-3.5" />
                    Raw verdict (JSON)
                  </Button>
                  {result.content_hash ? (
                    <Button variant="outline" className="h-9" asChild>
                      <a
                        href={warningCardUrl(result.content_hash)}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        <ImageIcon className="size-3.5" />
                        Warning card
                      </a>
                    </Button>
                  ) : null}
                </div>
                {/* <p className="mt-4 border-t border-border pt-4 font-serif text-sm leading-relaxed text-foreground/50 italic">
                  The report carries every reason code, its severity and the
                  evidence behind it — the detail a complaint needs, kept out of
                  the way until you want it.
                </p> */}
              </div>
            </>
          ) : !error ? (
            <div className="flex min-h-96 items-center justify-center rounded-xl border border-dashed border-border p-8 text-center">
              <p className="max-w-sm font-serif text-foreground/50 italic">
                The verdict, every reason behind it, the filing it was compared
                against, and where to take it next — all appear here.
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
