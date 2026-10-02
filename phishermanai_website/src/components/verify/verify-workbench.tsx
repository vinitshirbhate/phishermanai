"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Download,
  FileJson,
  Image as ImageIcon,
  Inbox,
  Loader2,
  Mail,
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
  fetchRecentGmailEmails,
  fetchHealth,
  verifyFile,
  verifyGmailMessage,
  verifyText,
  warningCardUrl,
} from "@/lib/engine-client";
import type {
  BodyDetectionResult,
  EngineHealth,
  EngineVerdictResponse,
  GmailEmailPreview,
} from "@/lib/engine-types";
import { PREVIEW_HANDOFF_KEY } from "@/lib/handoff";
import { downloadPdfReport } from "@/lib/verification-pdf";
import {
  buildJsonReport,
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
  const [pdfBusy, setPdfBusy] = useState(false);
  const [result, setResult] = useState<EngineVerdictResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gmailEmails, setGmailEmails] = useState<GmailEmailPreview[] | null>(null);
  const [gmailLoading, setGmailLoading] = useState(false);
  const [gmailVerifyingId, setGmailVerifyingId] = useState<string | null>(null);
  const [gmailError, setGmailError] = useState<string | null>(null);
  const [selectedGmailEmail, setSelectedGmailEmail] = useState<GmailEmailPreview | null>(null);
  const [bodyDetection, setBodyDetection] = useState<BodyDetectionResult | null>(null);

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
  const inputLabel = selectedGmailEmail
    ? `Gmail: ${selectedGmailEmail.subject || "No subject"}`
    : mode === "file"
      ? (file?.name ?? "file")
      : "pasted text";

  const loadGmailEmails = useCallback(async () => {
    if (gmailLoading || gmailVerifyingId) return;
    setGmailLoading(true);
    setGmailError(null);
    try {
      setGmailEmails(await fetchRecentGmailEmails(4));
    } catch (caught) {
      const message =
        caught instanceof Error ? caught.message : "Could not fetch your inbox.";
      setGmailError(message);
      if (caught instanceof EngineError && caught.unreachable) setHealth(null);
    } finally {
      setGmailLoading(false);
    }
  }, [gmailLoading, gmailVerifyingId]);

  const verifyInboxEmail = useCallback(
    async (email: GmailEmailPreview) => {
      if (gmailVerifyingId || busy) return;
      setGmailVerifyingId(email.gmail_message_id);
      setGmailError(null);
      setError(null);
      setResult(null);
      setBodyDetection(null);
      setSelectedGmailEmail(email);
      try {
        const verification = await verifyGmailMessage(email.gmail_message_id);
        setResult(verification.email_verification);
        setBodyDetection(verification.body_detection);
      } catch (caught) {
        const message =
          caught instanceof Error
            ? caught.message
            : "Could not verify this email.";
        setGmailError(message);
        if (caught instanceof EngineError && caught.unreachable) setHealth(null);
      } finally {
        setGmailVerifyingId(null);
      }
    },
    [busy, gmailVerifyingId],
  );

  const submit = useCallback(async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setSelectedGmailEmail(null);
    setBodyDetection(null);
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

      <section className="border border-border bg-card">
        <div className="flex flex-col gap-5 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="flex size-9 items-center justify-center bg-primary text-primary-foreground">
                <Inbox className="size-4" aria-hidden />
              </span>
              <h2 className="text-xl font-semibold tracking-[-0.02em]">
                Check an email from your inbox
              </h2>
            </div>
            <p className="mt-3 font-serif text-sm leading-relaxed text-foreground/65 sm:ml-12">
              Load your four newest messages, then choose one. The email and its
              text are checked by both detection systems.
            </p>
          </div>
          <Button
            onClick={() => void loadGmailEmails()}
            disabled={gmailLoading || Boolean(gmailVerifyingId) || engineDown}
            className="h-11 shrink-0 px-5"
          >
            {gmailLoading ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : gmailEmails ? (
              <RefreshCw className="size-4" aria-hidden />
            ) : (
              <Mail className="size-4" aria-hidden />
            )}
            {gmailLoading
              ? "Fetching emails"
              : gmailEmails
                ? "Refresh latest 4"
                : "Fetch latest 4 emails"}
          </Button>
        </div>

        {gmailError ? (
          <div className="flex items-start gap-3 border-b border-verdict-fraud/30 bg-verdict-fraud/8 px-5 py-4 text-verdict-fraud sm:px-6">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p className="font-serif text-sm leading-relaxed">{gmailError}</p>
          </div>
        ) : null}

        {gmailEmails ? (
          gmailEmails.length > 0 ? (
            <div className="divide-y divide-border" aria-label="Latest Gmail messages">
              {gmailEmails.map((email) => {
                const isVerifying = gmailVerifyingId === email.gmail_message_id;
                const isSelected = selectedGmailEmail?.gmail_message_id === email.gmail_message_id;
                return (
                  <button
                    key={email.gmail_message_id}
                    type="button"
                    onClick={() => void verifyInboxEmail(email)}
                    disabled={Boolean(gmailVerifyingId) || busy}
                    aria-pressed={isSelected}
                    className="group grid w-full gap-3 px-5 py-5 text-left transition-colors hover:bg-muted/55 focus-visible:bg-muted/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset disabled:cursor-wait disabled:opacity-65 sm:grid-cols-[minmax(0,1fr)_auto] sm:px-6"
                  >
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className="truncate text-[0.9375rem] font-semibold">
                          {email.subject || "No subject"}
                        </span>
                        <span className="font-mono text-[0.6875rem] text-foreground/45">
                          {email.date}
                        </span>
                      </span>
                      <span className="mt-1 block truncate font-serif text-sm text-foreground/65">
                        From {email.from}
                      </span>
                      <span className="mt-2 line-clamp-2 block max-w-3xl font-serif text-sm leading-relaxed text-foreground/50">
                        {email.preview || "No text preview available."}
                      </span>
                    </span>
                    <span className="flex items-center gap-2 self-center font-mono text-[0.6875rem] tracking-[0.08em] text-primary uppercase">
                      {isVerifying ? (
                        <>
                          <Loader2 className="size-3.5 animate-spin" aria-hidden />
                          Checking
                        </>
                      ) : isSelected && result ? (
                        <>
                          <ShieldCheck className="size-3.5" aria-hidden />
                          Checked
                        </>
                      ) : (
                        <>
                          Check email
                          <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
                        </>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="px-5 py-8 text-center font-serif text-sm text-foreground/55 sm:px-6">
              No messages were found in the inbox.
            </p>
          )
        ) : null}
      </section>

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
                  setSelectedGmailEmail(null);
                  setBodyDetection(null);
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

              {bodyDetection ? (
                <div className="border border-border bg-card p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h2 className="text-base font-semibold">Body-text check</h2>
                    <span
                      className={`font-mono text-[0.6875rem] tracking-[0.1em] uppercase ${
                        bodyDetection.is_phishing
                          ? "text-verdict-fraud"
                          : "text-verdict-verified"
                      }`}
                    >
                      {bodyDetection.label} · {Math.round(bodyDetection.confidence * 100)}%
                    </span>
                  </div>
                  <p className="mt-3 font-serif text-sm leading-relaxed text-foreground/65">
                    {bodyDetection.message}
                  </p>
                </div>
              ) : null}

              <div className="rounded-xl border border-border bg-card p-5">
                <h2 className="mono-label text-foreground/45">
                  keep the evidence
                </h2>
                <p className="copy mt-2 text-[1rem]">
                  A readable PDF of everything the engine checked, what it
                  compared against, and what it could not see — laid out here in
                  your browser from the verdict already on screen, so nothing is
                  sent anywhere to produce it.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    className="h-9"
                    disabled={pdfBusy}
                    onClick={async () => {
                      setPdfBusy(true);
                      try {
                        await downloadPdfReport(
                          result,
                          { inputLabel, moneySent },
                          reportFilename(result, "pdf"),
                        );
                      } catch (caught) {
                        setError(
                          caught instanceof Error
                            ? `Could not build the PDF: ${caught.message}`
                            : "Could not build the PDF.",
                        );
                      } finally {
                        setPdfBusy(false);
                      }
                    }}
                  >
                    {pdfBusy ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden />
                    ) : (
                      <Download className="size-3.5" />
                    )}
                    Report (PDF)
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
