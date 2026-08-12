import type {
  EngineDemoExample,
  EngineHealth,
  EngineVerdictResponse,
} from "./engine-types";

/**
 * Browser-side client for the verification engine, via the route-handler proxy
 * at /api/engine. Every call is relative, so nothing here needs to know where
 * the Python service actually lives.
 */

const BASE = "/api/engine";

/** Thrown when the engine answered with an error, or could not be reached. */
export class EngineError extends Error {
  readonly status: number;
  /** True when the engine is not running, as opposed to running and failing. */
  readonly unreachable: boolean;

  constructor(message: string, status: number, unreachable: boolean) {
    super(message);
    this.name = "EngineError";
    this.status = status;
    this.unreachable = unreachable;
  }
}

async function readError(response: Response): Promise<EngineError> {
  let detail = `Engine returned ${response.status}`;
  let unreachable = response.status === 503;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
    if (body?.engine_unreachable === true) unreachable = true;
  } catch {
    // A non-JSON error body is not worth failing over; the status carries it.
  }
  return new EngineError(detail, response.status, unreachable);
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

/**
 * Is the engine up, and does it have a corpus loaded?
 *
 * Returns null instead of throwing: a console that works without the engine
 * should not treat its absence as an exception.
 */
export async function fetchHealth(): Promise<EngineHealth | null> {
  try {
    const response = await fetch(`${BASE}/health`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as EngineHealth;
  } catch {
    return null;
  }
}

/** Verify pasted text. Mirrors `POST /verify` with the text form field. */
export async function verifyText(
  text: string,
  options: { moneySent?: boolean } = {},
): Promise<EngineVerdictResponse> {
  const form = new FormData();
  form.set("text", text);
  form.set("channel", "WEB");
  if (options.moneySent) form.set("money_sent", "true");

  return json<EngineVerdictResponse>(
    await fetch(`${BASE}/verify`, { method: "POST", body: form }),
  );
}

/**
 * Verify an uploaded .eml, image or PDF.
 *
 * Goes to `POST /verify` rather than `/verify/email` even for .eml: that route
 * infers the type from the payload anyway, and it is the only one that accepts
 * `money_sent`, which is what decides whether the engine routes escalation to
 * the cybercrime helpline or to SCORES.
 */
export async function verifyFile(
  file: File,
  options: { moneySent?: boolean } = {},
): Promise<EngineVerdictResponse> {
  const form = new FormData();
  form.set("file", file);
  form.set("channel", "WEB");
  if (options.moneySent) form.set("money_sent", "true");

  return json<EngineVerdictResponse>(
    await fetch(`${BASE}/verify`, { method: "POST", body: form }),
  );
}

/** The engine rejects anything larger; checked client-side to fail fast. */
export const MAX_UPLOAD_BYTES = 12 * 1024 * 1024;

/** The fixtures the engine ships with, read from eval/fixtures/manifest.json. */
export async function fetchDemoExamples(): Promise<EngineDemoExample[]> {
  const body = await json<{ examples: EngineDemoExample[]; note?: string }>(
    await fetch(`${BASE}/demo/examples`, { cache: "no-store" }),
  );
  return body.examples ?? [];
}

/** Run one shipped fixture through the real pipeline. */
export async function verifyDemoFixture(name: string): Promise<EngineVerdictResponse> {
  return json<EngineVerdictResponse>(
    await fetch(`${BASE}/demo/verify/${encodeURIComponent(name)}`, { method: "POST" }),
  );
}

/** The shareable warning-card PNG for a completed verification. */
export function warningCardUrl(contentHash: string): string {
  return `${BASE}/warning-card/${encodeURIComponent(contentHash)}`;
}
