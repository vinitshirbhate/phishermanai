"use client";

import { useRef, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, FileUp, LoaderCircle, MessageSquareText, RotateCcw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type SmsResult = {
  text: string;
  label: string;
  confidence: number;
  is_phishing: boolean;
  message: string;
};

const DEMO_MESSAGE = "Your bank account will be suspended today. Verify your details immediately: secure-bank-check.example/confirm";
const DETECTOR_URL = process.env.NEXT_PUBLIC_SMS_DETECTION_API_URL ?? "https://fraud-detect-1-6er0.onrender.com/detect";

export function SmsDetectionForm() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<SmsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const analyze = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = text.trim();
    setResult(null);
    setError(null);
    if (!message) {
      setError("Paste the SMS message you want to check.");
      return;
    }

    setBusy(true);
    try {
      const response = await fetch(DETECTOR_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ text: message }),
      });
      const payload = (await response.json().catch(() => null)) as Partial<SmsResult> | null;
      if (!response.ok) {
        throw new Error(payload?.message || `The SMS detector returned HTTP ${response.status}.`);
      }
      if (
        !payload || typeof payload.is_phishing !== "boolean" ||
        typeof payload.confidence !== "number" || typeof payload.label !== "string"
      ) {
        throw new Error("The detector response did not match the expected result format.");
      }
      setResult({
        text: typeof payload.text === "string" ? payload.text : message,
        label: payload.label,
        confidence: payload.confidence,
        is_phishing: payload.is_phishing,
        message: typeof payload.message === "string" ? payload.message : "Analysis complete.",
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not reach the SMS detection service.");
    } finally {
      setBusy(false);
    }
  };

  const confidence = result
    ? `${Math.round(result.confidence <= 1 ? result.confidence * 100 : result.confidence)}%`
    : null;

  return (
    <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
      <section className="border border-border bg-card p-5 sm:p-7">
        <div className="flex items-center gap-3 border-b border-border pb-5">
          <span className="grid size-11 place-items-center border border-primary/20 bg-primary/5 text-primary"><MessageSquareText className="size-5" /></span>
          <div><p className="text-sm font-medium">SMS message</p><p className="mt-1 text-xs text-muted-foreground">Paste the full text, including links or sender claims.</p></div>
        </div>
        <form onSubmit={analyze} className="mt-5 space-y-4">
          <div>
            <label htmlFor="sms-text" className="mono-label mb-2 block text-muted-foreground">Message to analyze</label>
            <Textarea
              id="sms-text"
              value={text}
              onChange={(event) => { setText(event.target.value); setResult(null); setError(null); }}
              placeholder="Paste a suspicious SMS here…"
              rows={8}
              maxLength={5000}
              aria-describedby="sms-count"
              className="min-h-56 resize-y font-mono text-sm leading-relaxed"
            />
            <div className="mt-2 flex justify-between text-[10px] text-muted-foreground"><span>Text is sent to the configured detection service for analysis.</span><span id="sms-count">{text.length}/5000</span></div>
          </div>
          {error && <div role="alert" className="flex gap-2 border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"><AlertTriangle className="mt-0.5 size-4 shrink-0"/><span>{error}</span></div>}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <div className="flex flex-wrap items-center gap-3">
              <input ref={fileRef} type="file" accept=".txt,text/plain" className="sr-only" onChange={async (event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                if (file.size > 20_000) { setError("Text files must be 20 KB or smaller."); return; }
                setText((await file.text()).slice(0, 5000));
                setResult(null);
                setError(null);
                event.target.value = "";
              }} />
              <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()}><FileUp className="size-3.5"/>Upload .txt</Button>
              <button type="button" onClick={() => { setText(DEMO_MESSAGE); setResult(null); setError(null); }} className="text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground">Try a sample SMS</button>
            </div>
            <Button type="submit" disabled={busy} className="min-w-36">
              {busy ? <><LoaderCircle className="size-4 animate-spin"/>Analyzing</> : <>Analyze SMS<ArrowRight className="size-4"/></>}
            </Button>
          </div>
        </form>
      </section>

      <section className="border border-border bg-card p-5 sm:p-7" aria-live="polite">
        <div className="flex items-center gap-3 border-b border-border pb-5">
          <span className="grid size-11 place-items-center border border-verdict-verified/20 bg-verdict-verified/5 text-verdict-verified"><ShieldCheck className="size-5" /></span>
          <div><p className="text-sm font-medium">Detection result</p><p className="mt-1 text-xs text-muted-foreground">The service response appears here after analysis.</p></div>
        </div>
        {result ? (
          <div className="mt-5 space-y-4">
            <div className={cn("flex items-start gap-3 border p-4", result.is_phishing ? "border-verdict-fraud/30 bg-verdict-fraud/5" : "border-verdict-verified/30 bg-verdict-verified/5")}>
              <span className={cn("mt-0.5", result.is_phishing ? "text-verdict-fraud" : "text-verdict-verified")}>{result.is_phishing ? <AlertTriangle className="size-5"/> : <CheckCircle2 className="size-5"/>}</span>
              <div className="min-w-0"><p className={cn("font-display text-xl font-bold", result.is_phishing ? "text-verdict-fraud" : "text-verdict-verified")}>{result.is_phishing ? "Potential phishing" : "No phishing detected"}</p><p className="mt-1 text-xs text-muted-foreground">Detector label: <span className="font-medium text-foreground">{result.label}</span></p></div>
              <div className="ml-auto shrink-0 text-right"><p className="stat-figure text-2xl">{confidence}</p><p className="mono-label text-[9px] text-muted-foreground">confidence</p></div>
            </div>
            <div className="border border-border bg-background p-4"><p className="mono-label text-[9px] text-muted-foreground">Analysis message</p><p className="mt-2 text-sm leading-relaxed">{result.message}</p></div>
            <details className="border border-border bg-background p-4"><summary className="cursor-pointer text-xs font-medium">Analyzed message</summary><p className="mt-3 whitespace-pre-wrap break-words text-xs leading-relaxed text-muted-foreground">{result.text}</p></details>
            <button type="button" onClick={() => { setResult(null); setText(""); setError(null); }} className="inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"><RotateCcw className="size-3.5"/>Check another message</button>
          </div>
        ) : (
          <div className="mt-5 grid min-h-64 place-items-center border border-dashed border-border bg-background p-6 text-center">
            <div><div className="mx-auto grid size-12 place-items-center border border-border text-muted-foreground"><MessageSquareText className="size-5"/></div><p className="mt-4 text-sm font-medium">Waiting for an SMS</p><p className="mx-auto mt-2 max-w-xs text-xs leading-relaxed text-muted-foreground">Paste a message and run the check to see its phishing label and confidence.</p></div>
          </div>
        )}
        <p className="mt-4 border-t border-border pt-3 text-[10px] leading-relaxed text-muted-foreground">A phishing result is a warning to verify the sender through an official channel. Do not open links or share codes from suspicious texts.</p>
      </section>
    </div>
  );
}