"use client";

import { useEffect, useMemo, useState } from "react";

import { MultiStepLoader } from "@/components/ui/multi-step-loader";
import { selectStages, type StageContext } from "@/lib/apif-stages";

/** How long each stage holds before the next one lights up. */
const STAGE_MS = 2500;

/**
 * How long to wait before admitting the backend is probably cold. The deployed
 * API sleeps on Render's free tier, so a first request can sit well past the
 * point where the stage track has run out of stages.
 */
const COLD_START_HINT_MS = 20_000;

/**
 * Stage narration for an in-flight APIF request.
 *
 * `loop={false}` matters: it makes the underlying loader clamp on its final
 * stage rather than restarting, so a slow request holds at "Framing evidence-linked
 * verdict" instead of cycling and implying work that is not happening.
 */
/**
 * Mounted only while a request is in flight, so the delay restarts itself on
 * every submission without the parent having to reset any state.
 */
function ColdStartHint() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShow(true), COLD_START_HINT_MS);
    return () => clearTimeout(timer);
  }, []);

  if (!show) return null;

  return (
    <p
      role="status"
      className="fixed inset-x-0 bottom-12 z-101 text-center font-mono text-[0.6875rem] tracking-[0.14em] text-foreground/40"
    >
      backend cold start · this can take up to a minute
    </p>
  );
}

export function ApifAnalysisLoader({
  loading,
  hasLink,
  kind,
  includeCoordination,
}: { loading: boolean } & StageContext) {
  const loadingStates = useMemo(
    () => selectStages({ hasLink, kind, includeCoordination }),
    [hasLink, kind, includeCoordination],
  );

  return (
    <>
      <MultiStepLoader
        loadingStates={loadingStates}
        loading={loading}
        duration={STAGE_MS}
        loop={false}
      />

      {loading ? <ColdStartHint /> : null}
    </>
  );
}
