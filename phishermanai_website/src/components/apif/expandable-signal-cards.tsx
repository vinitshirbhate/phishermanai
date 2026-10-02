"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";

import { useOutsideClick } from "@/hooks/use-outside-click";
import { signals as documentedSignals } from "@/lib/content";
import { cn } from "@/lib/utils";

/**
 * One detector's live reading. Shaped to fit both APIF result payloads: the
 * link route returns full signals with evidence, the verify route returns a
 * thinner {signal, result} pair.
 */
export type SignalCard = {
  id: string;
  label: string;
  score?: number;
  available?: boolean;
  summary?: string;
  error?: string | null;
  evidence?: Record<string, unknown>;
};

/** Renders an evidence value without collapsing it to "[object Object]". */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join(", ") : "—";
  return JSON.stringify(value, null, 2);
}

/** The documented weight and known limitation for a detector, if we have them. */
function documentationFor(id: string) {
  return documentedSignals.find((entry) => entry.name === id);
}

function StatusPill({ card }: { card: SignalCard }) {
  const unavailable = card.available === false;
  return (
    <span
      className={cn(
        "mono-label rounded-full px-2 py-0.5",
        unavailable
          ? "bg-foreground/5 text-foreground/40"
          : "bg-primary/10 text-primary",
      )}
    >
      {unavailable ? "unavailable" : "scored"}
    </span>
  );
}

export function ExpandableSignalCards({ cards }: { cards: SignalCard[] }) {
  const [active, setActive] = useState<SignalCard | null>(null);
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setActive(null);
    }

    document.body.style.overflow = active ? "hidden" : "auto";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = "auto";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [active]);

  useOutsideClick(ref, () => setActive(null));

  const docs = active ? documentationFor(active.id) : undefined;
  const evidenceEntries = active?.evidence ? Object.entries(active.evidence) : [];

  return (
    <>
      <AnimatePresence>
        {active ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 h-full w-full bg-background/70 backdrop-blur-sm"
          />
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {active ? (
          <div className="fixed inset-0 z-50 grid place-items-center p-4">
            <motion.div
              layoutId={`signal-${active.id}-${id}`}
              ref={ref}
              role="dialog"
              aria-modal="true"
              aria-label={`${active.label} detail`}
              className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-xl"
            >
              <div className="flex items-start justify-between gap-4 border-b border-border p-5">
                <div>
                  <motion.p
                    layoutId={`signal-label-${active.id}-${id}`}
                    className="text-base font-medium"
                  >
                    {active.label}
                  </motion.p>
                  <p className="mono-label mt-1 text-foreground/40">{active.id}</p>
                </div>
                <div className="flex items-center gap-3">
                  {typeof active.score === "number" ? (
                    <span className="font-mono text-sm tabular-nums text-foreground/60">
                      {active.score.toFixed(2)}
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setActive(null)}
                    aria-label="Close detail"
                    className="grid size-7 place-items-center rounded-full border border-border text-foreground/50 transition-colors hover:text-foreground"
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </div>
              </div>

              <div className="space-y-5 overflow-y-auto p-5">
                {active.summary ? <p className="copy text-[0.9375rem]">{active.summary}</p> : null}

                {active.error ? (
                  <p className="rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground/60">
                    <span className="mono-label text-foreground/40">why it did not run</span>
                    <span className="mt-1 block">{active.error}</span>
                  </p>
                ) : null}

                {evidenceEntries.length ? (
                  <div>
                    <p className="mono-label text-foreground/35">Evidence</p>
                    <dl className="mt-3 divide-y divide-border overflow-hidden rounded-xl border border-border">
                      {evidenceEntries.map(([key, value]) => (
                        <div key={key} className="grid gap-1 bg-background px-4 py-3 sm:grid-cols-[10rem_1fr]">
                          <dt className="font-mono text-[0.8125rem] text-foreground/50">{key}</dt>
                          <dd className="font-mono text-[0.8125rem] break-words whitespace-pre-wrap text-foreground/80">
                            {formatValue(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ) : null}

                {docs ? (
                  <div className="space-y-3 border-t border-border pt-5">
                    <div className="flex items-baseline justify-between gap-4">
                      <p className="mono-label text-foreground/35">weight in fusion</p>
                      <p className="font-mono text-[0.8125rem] tabular-nums text-foreground/60">
                        {docs.weight.toFixed(2)}
                      </p>
                    </div>
                    <p className="copy text-[0.9375rem]">{docs.what}</p>
                    <p className="font-serif text-sm leading-relaxed text-foreground/50 italic">
                      {docs.limitation}
                    </p>
                  </div>
                ) : null}
              </div>
            </motion.div>
          </div>
        ) : null}
      </AnimatePresence>

      <div className="grid gap-3">
        {cards.map((card) => {
          const Icon = documentationFor(card.id)?.icon;
          return (
            <motion.button
              type="button"
              layoutId={`signal-${card.id}-${id}`}
              key={card.id}
              onClick={() => setActive(card)}
              aria-label={`Show detail for ${card.label}`}
              className="w-full cursor-pointer rounded-2xl border border-border/80 bg-background p-3 text-left transition-colors hover:border-primary/40"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  {Icon ? <Icon className="size-4 shrink-0 text-primary" aria-hidden /> : null}
                  <motion.p
                    layoutId={`signal-label-${card.id}-${id}`}
                    className="truncate font-medium"
                  >
                    {card.label}
                  </motion.p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusPill card={card} />
                  {typeof card.score === "number" ? (
                    <span className="font-mono text-sm tabular-nums text-foreground/60">
                      {card.score.toFixed(2)}
                    </span>
                  ) : null}
                </div>
              </div>
              <p className="mt-1 line-clamp-1 text-sm text-foreground/70">
                {card.summary || card.error || "No additional details."}
              </p>
              <p className="mono-label mt-2 text-foreground/30">click for detail</p>
            </motion.button>
          );
        })}
      </div>
    </>
  );
}
