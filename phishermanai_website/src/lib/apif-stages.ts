/**
 * The stage narration shown while an APIF request is in flight.
 *
 * The backend answers /api/v1/verify and /api/v1/verify-link with a single JSON
 * response — there is no progress stream — so these stages are a timed narrative,
 * not measured progress. What they *are* honest about is which work runs: the
 * sequence is filtered to the pipeline the submission will actually take, so a
 * text-only check never claims to have chunked frames.
 */

import type { MediaKind } from "@/lib/media-kind";

export type LoadingState = { text: string };

type Stage = LoadingState & {
  /** Which submissions this stage applies to. */
  applies: (ctx: StageContext) => boolean;
};

export interface StageContext {
  /** The link form fetches a URL first; the direct-upload form does not. */
  hasLink: boolean;
  /** Pipeline the backend will route an attached file to, or null for text only. */
  kind: MediaKind | null;
  /** Mirrors the existing "Include coordination analysis" switch. */
  includeCoordination: boolean;
}

/** Frame work only exists where there are frames to decode. */
const hasFrames = (kind: MediaKind | null) => kind === "video" || kind === "image";
/** A container to demux means a real media stream, which images do not have. */
const hasStreams = (kind: MediaKind | null) => kind === "video" || kind === "audio";

const STAGES: Stage[] = [
  {
    text: "Resolving link · Firecrawl DOM extraction",
    applies: (c) => c.hasLink,
  },
  {
    text: "Demultiplexing container streams",
    applies: (c) => hasStreams(c.kind),
  },
  {
    text: "Decoding frames · face-region localisation",
    applies: (c) => hasFrames(c.kind),
  },
  {
    text: "Validating content · duration and codec guards",
    applies: () => true,
  },
  {
    text: "Chunking frames into inference batches",
    applies: (c) => hasFrames(c.kind),
  },
  {
    text: "Scoring frame-level deepfake artefacts",
    applies: (c) => hasFrames(c.kind),
  },
  {
    text: "Correlating coordinated campaign clusters",
    applies: (c) => c.includeCoordination,
  },
  {
    text: "Cross-referencing market anomaly surface",
    applies: () => true,
  },
  {
    text: "Executing XGBoost gradient-boosted ensemble",
    applies: () => true,
  },
  {
    text: "Framing evidence-linked verdict",
    applies: () => true,
  },
];

/**
 * The stages this submission will run, in pipeline order.
 *
 * Always returns at least the four unconditional stages, so the loader is never
 * handed an empty list.
 */
export function selectStages(context: StageContext): LoadingState[] {
  return STAGES.filter((stage) => stage.applies(context)).map(({ text }) => ({ text }));
}
