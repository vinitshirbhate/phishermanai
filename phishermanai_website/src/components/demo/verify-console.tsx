"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CircleAlert,
  CircleCheck,
  CircleSlash,
  Loader2,
  Paperclip,
  Play,
  Plug,
  RotateCcw,
  Zap,
} from "lucide-react";

import { FindingCard } from "@/components/demo/finding-card";
import { LiveResult } from "@/components/demo/live-result";
import { VerdictBadge } from "@/components/site/verdict-badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  demoMessages,
  getDemoMessage,
  pipelineStages,
  verdictMeta,
  type AnalysisResult,
  type DemoMessage,
} from "@/lib/analysis";
import {
  EngineError,
  fetchHealth,
  verifyDemoFixture,
  verifyText,
} from "@/lib/engine-client";
import type { EngineHealth, EngineVerdictResponse } from "@/lib/engine-types";
import { PREVIEW_HANDOFF_KEY } from "@/lib/handoff";
import { runPreview, type PreviewOutcome } from "@/lib/preview-rules";
import { cn } from "@/lib/utils";

type Phase = "idle" | "running" | "done";

const STAGE_MS = 260;

function AuthChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={cn(
        "mono-label inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5",
        ok
          ? "border-verdict-verified/35 bg-verdict-verified/10 text-verdict-verified"
          : "border-foreground/15 bg-muted text-foreground/40",
      )}
    >
      {label} {ok ? "pass" : "—"}
    </span>
  );
}

/** Says which of the two modes the console is in, and never pretends. */
function EngineStatus({ health }: { health: EngineHealth | null }) {
  if (health) {
    return (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-verdict-verified/30 bg-verdict-verified/8 px-4 py-3">
        <span className="mono-label inline-flex items-center gap-2 text-verdict-verified">
          <Zap className="size-3.5" aria-hidden />
          live engine
        </span>
        <span className="font-mono text-[0.6875rem] text-foreground/50">
          {health.filings.toLocaleString()} filings · {health.entities.toLocaleString()} entities ·{" "}
          {health.domains.toLocaleString()} domains · {health.claim_rules} rules
        </span>
        <span className="ml-auto font-mono text-[0.6875rem] text-foreground/40">
          status {health.status}
          {health.demo_mode ? " · demo mode (offline by contract)" : ""}
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-muted/50 px-4 py-3">
      <span className="mono-label inline-flex items-center gap-2 text-foreground/45">
        <Plug className="size-3.5" aria-hidden />
        engine not running — showing recorded results
      </span>
      <p className="mt-2 font-serif text-sm leading-relaxed text-foreground/55">
        Start it and this console switches to live verdicts automatically:{" "}
        <span className="font-mono text-xs">cd email_detection</span> then{" "}
        <span className="font-mono text-xs">uvicorn api.main:app --reload</span>. Point the UI
        elsewhere with <span className="font-mono text-xs">PHISHERMANAI_API_URL</span>.
      </p>
    </div>
  );
}

function MessagePane({ message }: { message: DemoMessage }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border bg-muted/50 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mono-label rounded-full border border-foreground/15 px-2 py-0.5 text-foreground/45">
            {message.channel}
          </span>
          <span className="font-mono text-[0.6875rem] text-foreground/40">{message.id}</span>
        </div>
        <p className="mt-3 text-[0.9375rem] font-medium">{message.subject}</p>
        <p className="mt-1.5 font-mono text-xs text-foreground/50">
          {message.fromName} &lt;{message.from}&gt;
        </p>
        <p className="mt-1 font-mono text-xs text-foreground/35">{message.received}</p>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <AuthChip label="spf" ok={message.auth.spf} />
          <AuthChip label="dkim" ok={message.auth.dkim} />
          <AuthChip label="dmarc" ok={message.auth.dmarc} />
          <AuthChip label="aligned" ok={message.auth.aligned} />
        </div>
      </div>

      <pre className="max-h-104 overflow-auto px-5 py-5 font-serif text-[0.9375rem] leading-[1.75] whitespace-pre-wrap text-foreground/80">
        {message.body}
      </pre>

      {message.attachments?.length ? (
        <div className="border-t border-border px-5 py-3.5">
          {message.attachments.map((attachment) => (
            <span
              key={attachment}
              className="inline-flex items-center gap-2 rounded-md border border-verdict-fraud/30 bg-verdict-fraud/8 px-2.5 py-1.5 font-mono text-xs text-verdict-fraud"
            >
              <Paperclip className="size-3.5" aria-hidden />
              {attachment}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StageTrack({
  phase,
  stageIndex,
  stopAt,
}: {
  phase: Phase;
  stageIndex: number;
  stopAt: number;
}) {
  return (
    <ol className="space-y-1.5">
      {pipelineStages.map((stage, index) => {
        const skipped = phase === "done" && index > stopAt;
        const active = phase === "running" && index === stageIndex;
        const complete = (phase === "done" && index <= stopAt) || index < stageIndex;

        return (
          <li key={stage.id} className="flex items-center gap-3">
            <span
              className={cn(
                "grid size-5 shrink-0 place-items-center rounded-full border font-mono text-[0.5625rem]",
                active
                  ? "border-primary bg-primary/15 text-primary"
                  : complete
                    ? "border-verdict-verified/45 bg-verdict-verified/10 text-verdict-verified"
                    : "border-foreground/15 text-foreground/30",
              )}
            >
              {stage.index}
            </span>
            <span
              className={cn(
                "font-mono text-xs",
                active ? "text-primary" : complete ? "text-foreground/70" : "text-foreground/30",
              )}
            >
              {stage.title}
            </span>
            <span className="dashed-rule h-px flex-1 text-foreground/15" aria-hidden />
            <span className="mono-label text-foreground/30">
              {active ? "running" : complete ? "ok" : skipped ? "skipped" : "—"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Renders the recorded fixtures and the in-browser preview. */
function RecordedResult({
  result,
  preview,
}: {
  result: AnalysisResult;
  preview?: PreviewOutcome | null;
}) {
  const meta = verdictMeta[result.verdict];

  return (
    <div className="space-y-5">
      <div className={cn("rounded-xl border p-5 sm:p-6", meta.border, meta.bg)}>
        <div className="flex flex-wrap items-center gap-3">
          <VerdictBadge verdict={result.verdict} size="lg" />
          <span className="ml-auto font-mono text-xs text-foreground/40">
            {result.latencyMs} ms
            {result.shortCircuit ? " · short-circuit" : ""}
          </span>
        </div>
        <p className="mt-4 font-serif text-lg leading-snug">{result.headline}</p>
        <p className="mt-3 font-mono text-[0.6875rem] text-foreground/45">
          confidence {result.confidence.toFixed(2)} · data_as_of {result.dataAsOf}
        </p>
      </div>

      {preview ? (
        <div className="rounded-lg border border-primary/30 bg-primary/6 p-4">
          <p className="mono-label text-primary">browser preview</p>
          <p className="mt-2 font-serif text-sm leading-relaxed text-foreground/70">
            {preview.rulesEvaluated} rules ran in this tab and nothing was uploaded. The preview
            cannot prove a sender or reach the filings corpus, so it never returns Verified or
            Tampered.
          </p>
          {preview.suppressed.length > 0 ? (
            <ul className="mt-3 space-y-1.5 border-t border-primary/20 pt-3">
              {preview.suppressed.map((item) => (
                <li key={item.id} className="font-mono text-[0.6875rem] text-foreground/50">
                  suppressed · {item.title} — {item.reason}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div>
        <h3 className="mono-label text-foreground/45">findings · {result.findings.length}</h3>
        <div className="mt-3 space-y-3">
          {result.findings.length > 0 ? (
            result.findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)
          ) : (
            <p className="rounded-lg border border-border bg-card p-4 font-serif text-sm text-foreground/55">
              No rule in the subset fired. That is not a clean bill of health — it is the absence
              of a finding.
            </p>
          )}
        </div>
      </div>

      <div>
        <h3 className="mono-label text-foreground/45">checks</h3>
        <ul className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
          {result.checks.map((check) => (
            <li
              key={check.name}
              className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0"
            >
              {check.status === "pass" ? (
                <CircleCheck className="size-4 shrink-0 text-verdict-verified" aria-hidden />
              ) : check.status === "fail" ? (
                <CircleAlert className="size-4 shrink-0 text-verdict-fraud" aria-hidden />
              ) : (
                <CircleSlash className="size-4 shrink-0 text-foreground/25" aria-hidden />
              )}
              <span className="text-sm">{check.name}</span>
              <span className="ml-auto text-right font-mono text-[0.6875rem] text-foreground/40">
                {check.note}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 font-serif text-xs text-foreground/45 italic">
          A check that could not run is excluded from the verdict. It is never counted as
          evidence of innocence.
        </p>
      </div>

      <div>
        <h3 className="mono-label text-foreground/45">provenance</h3>
        <ul className="mt-3 space-y-1.5">
          {result.provenance.map((source) => (
            <li key={source} className="font-mono text-[0.6875rem] text-foreground/50">
              · {source}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ErrorPane({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-verdict-fraud/35 bg-verdict-fraud/8 p-5">
      <p className="mono-label text-verdict-fraud">engine error</p>
      <p className="mt-2 font-serif text-sm leading-relaxed text-foreground/70">{message}</p>
    </div>
  );
}

export function VerifyConsole() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requested = searchParams.get("demo");

  const [messageId, setMessageId] = useState(() => getDemoMessage(requested).id);
  const [phase, setPhase] = useState<Phase>("idle");
  const [stageIndex, setStageIndex] = useState(0);
  const [customText, setCustomText] = useState("");
  const [preview, setPreview] = useState<PreviewOutcome | null>(null);

  const [health, setHealth] = useState<EngineHealth | null>(null);
  const [liveFixture, setLiveFixture] = useState<EngineVerdictResponse | null>(null);
  const [liveCustom, setLiveCustom] = useState<EngineVerdictResponse | null>(null);
  const [customBusy, setCustomBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const message = useMemo(() => getDemoMessage(messageId), [messageId]);
  const stopAt = message.result.shortCircuit ? 2 : pipelineStages.length - 1;
  const live = health !== null;

  // Probe the engine once on mount. This is a read of external state, which is
  // why setState lands in an effect: there is no server-side equivalent to
  // seed it with, and guessing would cause a hydration mismatch.
  useEffect(() => {
    let cancelled = false;
    fetchHealth().then((result) => {
      if (cancelled) return;
      setHealth(result);
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
        setCustomText(handoff);
      }
    } catch {
      // Storage may be unavailable; the console works without the hand-off.
    }
  }, []);

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const reset = useCallback(() => {
    clearTimers();
    setPhase("idle");
    setStageIndex(0);
    setLiveFixture(null);
    setError(null);
  }, [clearTimers]);

  /** Advance the stage track for legibility while the work happens. */
  const animateStages = useCallback(
    (limit: number) => {
      for (let step = 1; step <= limit; step += 1) {
        timers.current.push(setTimeout(() => setStageIndex(step), STAGE_MS * step));
      }
    },
    [],
  );

  const run = useCallback(async () => {
    clearTimers();
    setError(null);
    setLiveFixture(null);
    setPhase("running");
    setStageIndex(0);

    if (!live) {
      animateStages(stopAt);
      timers.current.push(setTimeout(() => setPhase("done"), STAGE_MS * (stopAt + 1)));
      return;
    }

    animateStages(pipelineStages.length - 1);
    try {
      // The fixture ids are the real filenames the engine ships in
      // eval/fixtures, so the same selection drives both modes.
      const result = await verifyDemoFixture(message.id);
      clearTimers();
      setLiveFixture(result);
      setPhase("done");
    } catch (caught) {
      clearTimers();
      const detail =
        caught instanceof EngineError ? caught.message : "The engine could not be reached.";
      setError(detail);
      setPhase("done");
      if (caught instanceof EngineError && caught.unreachable) setHealth(null);
    }
  }, [animateStages, clearTimers, live, message.id, stopAt]);

  const runCustom = useCallback(async () => {
    if (!customText.trim()) return;
    setError(null);

    if (!live) {
      setPreview(runPreview(customText));
      return;
    }

    setCustomBusy(true);
    setLiveCustom(null);
    try {
      setLiveCustom(await verifyText(customText));
    } catch (caught) {
      const detail =
        caught instanceof EngineError ? caught.message : "The engine could not be reached.";
      setError(detail);
      if (caught instanceof EngineError && caught.unreachable) {
        setHealth(null);
        setPreview(runPreview(customText));
      }
    } finally {
      setCustomBusy(false);
    }
  }, [customText, live]);

  const selectMessage = (id: string) => {
    reset();
    setMessageId(id);
    router.replace(`/demo?demo=${encodeURIComponent(id)}`, { scroll: false });
  };

  return (
    <div className="space-y-6">
      <EngineStatus health={health} />

      <Tabs defaultValue="fixtures" className="w-full gap-8">
        <TabsList className="w-full max-w-md">
          <TabsTrigger value="fixtures">
            {live ? "Shipped fixtures" : "Recorded examples"}
          </TabsTrigger>
          <TabsTrigger value="custom">Your own text</TabsTrigger>
        </TabsList>

        <TabsContent value="fixtures" className="space-y-8">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {demoMessages.map((item) => {
              const isActive = item.id === messageId;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectMessage(item.id)}
                  aria-pressed={isActive}
                  className={cn(
                    "rounded-xl border p-4 text-left transition-all",
                    isActive
                      ? "border-primary/50 bg-card shadow-[0_14px_36px_-26px_rgba(16,27,40,0.5)]"
                      : "border-border bg-transparent hover:border-foreground/20",
                  )}
                >
                  <VerdictBadge verdict={item.result.verdict} size="sm" />
                  <p className="mt-3 text-[0.9375rem] leading-snug font-medium">{item.label}</p>
                  <p className="mt-2 font-serif text-xs leading-relaxed text-foreground/50">
                    {item.blurb}
                  </p>
                </button>
              );
            })}
          </div>

          <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
            <div className="space-y-5">
              <MessagePane message={message} />

              <div className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="mono-label text-foreground/45">pipeline</h3>
                  {phase === "idle" ? (
                    <Button onClick={run} className="h-9">
                      <Play className="size-3.5" />
                      {live ? "Verify with the engine" : "Run verification"}
                    </Button>
                  ) : phase === "running" ? (
                    <span className="inline-flex items-center gap-2 font-mono text-xs text-primary">
                      <Loader2 className="size-3.5 animate-spin" aria-hidden />
                      running
                    </span>
                  ) : (
                    <Button variant="outline" onClick={reset} className="h-9">
                      <RotateCcw className="size-3.5" />
                      Run again
                    </Button>
                  )}
                </div>
                <div className="mt-4">
                  <StageTrack
                    phase={phase}
                    stageIndex={stageIndex}
                    stopAt={live ? pipelineStages.length - 1 : stopAt}
                  />
                </div>
                {phase === "done" && !live && message.result.shortCircuit ? (
                  <p className="mt-4 font-serif text-xs text-foreground/50 italic">
                    Stages 04–06 never ran. An aligned signature from a known domain answered
                    first, which is how 83% of genuine mail exits in 10 ms.
                  </p>
                ) : null}
              </div>
            </div>

            <div>
              {error ? (
                <ErrorPane message={error} />
              ) : phase === "done" ? (
                liveFixture ? (
                  <LiveResult result={liveFixture} />
                ) : (
                  <RecordedResult result={message.result} />
                )
              ) : (
                <div className="flex h-full min-h-80 flex-col items-center justify-center rounded-xl border border-dashed border-border p-8 text-center">
                  <p className="font-serif text-foreground/50 italic">
                    {phase === "running"
                      ? "Working through the stages…"
                      : "Run the verification to see the verdict, every finding, and the register each one came from."}
                  </p>
                </div>
              )}
            </div>
          </div>

          <p className="font-serif text-sm text-foreground/45 italic">
            {live
              ? "These are the fixtures the engine ships in eval/fixtures, scored live by the running pipeline. The verdict, the reasons and the field comparisons all come from the engine."
              : "These are recorded outputs for the four fixtures the engine ships with, held in the same shape the API returns, so the page can be read with no backend running."}
          </p>
        </TabsContent>

        <TabsContent value="custom" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
            <div>
              <label htmlFor="custom-text" className="mono-label text-foreground/45">
                paste a message
              </label>
              <Textarea
                id="custom-text"
                value={customText}
                onChange={(event) => {
                  setCustomText(event.target.value);
                  setPreview(null);
                  setLiveCustom(null);
                }}
                rows={14}
                placeholder={
                  "SEBI-registered advisory. Reg. No. INA000000383.\nGuaranteed 40% returns…"
                }
                className="mt-3 resize-none font-serif text-[0.9375rem] leading-relaxed"
              />
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Button onClick={runCustom} disabled={!customText.trim() || customBusy} className="h-10">
                  {customBusy ? (
                    <>
                      <Loader2 className="size-3.5 animate-spin" aria-hidden />
                      verifying
                    </>
                  ) : live ? (
                    "Verify with the engine"
                  ) : (
                    "Run browser preview"
                  )}
                </Button>
                <Button
                  variant="ghost"
                  className="h-10"
                  onClick={() => {
                    setCustomText(demoMessages[2].body);
                    setPreview(null);
                    setLiveCustom(null);
                  }}
                >
                  Load a sample
                </Button>
              </div>
              <p className="mt-4 font-serif text-sm leading-relaxed text-foreground/50 italic">
                {live
                  ? "Sent to the engine at POST /verify, which runs the four chokepoints and the filings cross-check. The engine stores a SHA-256 of the normalised content and the verdict — never the text itself."
                  : "This runs the direction-aware claim and money rules in your browser. Nothing is sent anywhere. It cannot verify a sender or reach the filings, so it returns only Fraudulent or No risk found."}
              </p>
            </div>

            <div>
              {error && !preview ? (
                <ErrorPane message={error} />
              ) : liveCustom ? (
                <LiveResult result={liveCustom} />
              ) : preview ? (
                <RecordedResult result={preview} preview={preview} />
              ) : (
                <div className="flex h-full min-h-80 items-center justify-center rounded-xl border border-dashed border-border p-8 text-center">
                  <p className="font-serif text-foreground/50 italic">
                    Paste anything — including an investor-awareness notice, which is the case
                    that breaks keyword systems.
                  </p>
                </div>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
