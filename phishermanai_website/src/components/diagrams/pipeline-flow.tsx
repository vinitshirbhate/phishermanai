"use client";

import { useState } from "react";
import { CornerDownRight } from "lucide-react";

import { pipelineStages } from "@/lib/analysis";
import { cn } from "@/lib/utils";

/**
 * The methodology flow: pill nodes connected by arrows, colour-coded by
 * phase. Orange marks the phases that loop or branch; outlined pills are
 * the linear ones.
 */
export function PipelineFlow({ className }: { className?: string }) {
  const [activeId, setActiveId] = useState(pipelineStages[3].id);
  const active = pipelineStages.find((stage) => stage.id === activeId) ?? pipelineStages[0];

  return (
    <div className={cn("w-full", className)}>
      <div className="flex flex-wrap items-stretch gap-y-3">
        {pipelineStages.map((stage, index) => {
          const isActive = stage.id === activeId;
          const emphasised = stage.kind !== "linear";

          return (
            <div key={stage.id} className="flex flex-1 basis-40 items-stretch gap-2">
              <button
                type="button"
                onClick={() => setActiveId(stage.id)}
                aria-pressed={isActive}
                className={cn(
                  "group flex flex-1 flex-col justify-between rounded-2xl border px-4 py-3 text-left transition-all",
                  emphasised
                    ? "border-primary/45 bg-primary/8"
                    : "border-border bg-transparent",
                  isActive
                    ? "border-primary bg-primary/15 ring-3 ring-primary/15"
                    : "hover:border-primary/50",
                )}
              >
                <span
                  className={cn(
                    "mono-label",
                    isActive ? "text-primary" : "text-foreground/40",
                  )}
                >
                  {stage.index}
                </span>
                <span className="mt-3 text-[0.9375rem] leading-tight font-medium">
                  {stage.title}
                </span>
                <span className="mt-1 font-serif text-xs text-foreground/50 italic">
                  {stage.caption}
                </span>
              </button>

              {index < pipelineStages.length - 1 ? (
                <div className="flex w-6 shrink-0 items-center" aria-hidden>
                  <svg viewBox="0 0 24 8" className="w-full text-foreground/25">
                    <line
                      x1="0"
                      y1="4"
                      x2="17"
                      y2="4"
                      stroke="currentColor"
                      strokeWidth="1.25"
                      strokeDasharray={stage.kind === "gate" ? "3 3" : undefined}
                    />
                    <path d="M17 1.5 22 4l-5 2.5z" fill="currentColor" />
                  </svg>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* The branch the gate takes when a sender is already proven. */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <CornerDownRight className="size-4 shrink-0 text-primary/60" aria-hidden />
        <span className="mono-label text-foreground/40">from 03</span>
        <span className="dashed-rule h-px w-8 text-foreground/30" aria-hidden />
        <span className="rounded-full border border-verdict-verified/40 bg-verdict-verified/10 px-3 py-1 font-mono text-[0.6875rem] tracking-[0.08em] text-verdict-verified uppercase">
          yes → verified · 83% · 10 ms
        </span>
      </div>

      <div className="mt-6 rounded-xl border border-border bg-card/60 p-5 sm:p-6">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="mono-label text-primary">Step {active.index}</span>
          <h3 className="text-lg font-medium">{active.title}</h3>
          <span className="font-serif text-sm text-foreground/50 italic">{active.caption}</span>
        </div>
        <p className="copy mt-3">{active.detail}</p>
      </div>
    </div>
  );
}
