"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ShieldQuestion, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { verdictMeta } from "@/lib/analysis";
import { PREVIEW_HANDOFF_KEY } from "@/lib/handoff";
import { runPreview, type PreviewOutcome } from "@/lib/preview-rules";
import { cn } from "@/lib/utils";

export function QuickCheckWidget() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [outcome, setOutcome] = useState<PreviewOutcome | null>(null);

  const run = () => {
    if (!text.trim()) return;
    setOutcome(runPreview(text));
  };

  const handOff = () => {
    try {
      window.sessionStorage.setItem(PREVIEW_HANDOFF_KEY, text);
    } catch {
      // Private-mode storage refusal is not worth blocking navigation over.
    }
  };

  return (
    <div className="fixed right-4 bottom-4 z-50 flex flex-col items-end gap-3 sm:right-6 sm:bottom-6">
      {open ? (
        <div className="w-[min(21rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-border bg-card shadow-[0_18px_50px_-12px_rgba(16,27,40,0.35)]">
          <div className="dark flex items-start justify-between gap-3 bg-navy px-4 py-3.5 text-cream">
            <div>
              <p className="text-sm font-medium">Quick check</p>
              <p className="mt-0.5 text-xs text-cream/60">
                Runs the rule subset in this tab. Nothing is uploaded.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md p-1 text-cream/60 transition-colors hover:text-cream"
            >
              <X className="size-4" />
              <span className="sr-only">Close quick check</span>
            </button>
          </div>

          <div className="p-4">
            <Textarea
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                setOutcome(null);
              }}
              rows={4}
              placeholder="Paste the message you were sent…"
              className="resize-none font-serif text-[0.9375rem]"
            />

            {outcome ? (
              <div
                className={cn(
                  "mt-3 rounded-lg border p-3",
                  verdictMeta[outcome.verdict].border,
                  verdictMeta[outcome.verdict].bg,
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={cn("size-2 rounded-full", verdictMeta[outcome.verdict].dot)}
                    aria-hidden
                  />
                  <span
                    className={cn(
                      "mono-label",
                      verdictMeta[outcome.verdict].text,
                    )}
                  >
                    {verdictMeta[outcome.verdict].label}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-foreground/70">
                  {outcome.headline}
                  {outcome.findings.length > 0 ? (
                    <>
                      {" — "}
                      {outcome.findings[0].title.toLowerCase()}.
                    </>
                  ) : (
                    "."
                  )}
                </p>
                <p className="mt-2 text-[0.6875rem] text-foreground/45">
                  Preview only: it cannot prove a sender or reach the filings, so it never
                  returns Verified or Tampered.
                </p>
              </div>
            ) : null}

            <div className="mt-3 flex items-center gap-2">
              <Button onClick={run} disabled={!text.trim()} className="h-9 flex-1">
                Run preview
              </Button>
              <Button variant="outline" asChild className="h-9">
                <Link href="/demo" onClick={handOff}>
                  Full demo
                  <ArrowUpRight />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex size-13 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-[0_10px_30px_-6px_rgba(230,80,15,0.6)] transition-transform hover:scale-105 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        {open ? <X className="size-5" /> : <ShieldQuestion className="size-5.5" />}
        <span className="sr-only">{open ? "Close quick check" : "Open quick check"}</span>
      </button>
    </div>
  );
}
