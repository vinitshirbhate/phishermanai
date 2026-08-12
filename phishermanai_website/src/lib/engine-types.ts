/**
 * The verification engine's HTTP contract.
 *
 * These mirror `email_detection/api/schemas.py` field for field. When that file
 * changes, this one changes with it — nothing here is inferred or reshaped.
 *
 * Run the engine with:
 *   cd email_detection && uvicorn api.main:app --reload
 */

/** What the engine returns. Note these are NOT the display strings. */
export type EngineVerdict = "GENUINE" | "TAMPERED" | "UNVERIFIED" | "FRAUDULENT";

export interface EngineReason {
  /** Stable machine-readable reason code. */
  code: string;
  /** Plain-English explanation intended for the user. */
  message: string;
  evidence: Record<string, unknown>;
  /** 0–5. */
  severity: number;
}

export interface EngineFieldComparison {
  field: string;
  extracted_value: unknown;
  filed_value: unknown;
  match: boolean | null;
  /** An UNREADABLE field can never produce a tamper finding. */
  read_confidence: "HIGH" | "MEDIUM" | "UNREADABLE";
  severity: number;
  /** [x1,y1,x2,y2] for highlighting the source image. */
  bbox: number[] | null;
  message: string;
}

export interface EngineMatchedFiling {
  filing_id: number | null;
  tier: string;
  score: number;
  company_name: string | null;
  filing_type: string | null;
  filing_date: string | null;
  headline: string | null;
  pdf_url: string | null;
  exchange: string | null;
  ranking_method: string;
  candidates_considered: number;
  notes: string[];
  matched_entity: Record<string, unknown> | null;
}

export interface EngineAction {
  priority: string;
  type: string;
  title: string;
  detail: string;
  contact: Record<string, unknown> | null;
  channel: Record<string, unknown> | null;
}

export interface EngineVerdictResponse {
  verdict: EngineVerdict;
  /**
   * The display wording, served by the API precisely so every client — web UI,
   * extension, gateway — shows the same thing without keeping its own copy of
   * the mapping and drifting. Render this; do not re-derive it.
   */
  label: string;
  /**
   * 0–100, and it means **how much evidence was available**, not how bad the
   * message is. A low number is "I could not see much", not "this is fine".
   */
  confidence: number;
  summary: string;
  reasons: EngineReason[];
  field_comparisons: EngineFieldComparison[];
  matched_filing: EngineMatchedFiling | null;
  recommended_actions: EngineAction[];
  checks: Record<string, unknown>;
  evidence_summary: Record<string, unknown>;
  content_hash: string;
  source_type: string;
  latency_ms: number;
  warning_card_url: string | null;
}

export interface EngineDemoExample {
  file: string;
  expected_label: string;
  company: string | null;
  note: string | null;
}

export interface EngineHealth {
  status: string;
  database: string;
  filings: number;
  entities: number;
  domains: number;
  claim_rules: number;
  semantic_ranking: boolean;
  image_support: boolean;
  demo_mode: boolean;
}

/**
 * Verdict codes map onto the four outcome colours the site already uses.
 * Only the colour is mapped — the wording always comes from `label`.
 */
export const engineVerdictTone: Record<
  EngineVerdict,
  "VERIFIED" | "NO_RISK_FOUND" | "TAMPERED" | "FRAUDULENT"
> = {
  GENUINE: "VERIFIED",
  UNVERIFIED: "NO_RISK_FOUND",
  TAMPERED: "TAMPERED",
  FRAUDULENT: "FRAUDULENT",
};

/** Severity 4–5 is disqualifying, 2–3 weak, 0–1 context. Mirrors the engine's tiers. */
export function severityTier(severity: number): "disqualifying" | "weak" | "context" {
  if (severity >= 4) return "disqualifying";
  if (severity >= 2) return "weak";
  return "context";
}
