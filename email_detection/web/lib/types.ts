export type VerdictKind = "GENUINE" | "TAMPERED" | "UNVERIFIED" | "FRAUDULENT";

export interface Reason {
  code: string;
  message: string;
  evidence: Record<string, unknown>;
  severity: number;
}

export interface FieldComparison {
  field: string;
  extracted_value: string | number | null;
  filed_value: string | number | null;
  match: boolean | null;
  read_confidence: "HIGH" | "MEDIUM" | "UNREADABLE";
  severity: number;
  bbox: number[] | null;
  message: string;
}

export interface MatchedFiling {
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
}

export interface Action {
  priority: string;
  type: string;
  title: string;
  detail: string;
  contact?: Record<string, unknown> | null;
  channel?: Record<string, unknown> | null;
}

export interface CheckResult {
  chokepoint: string;
  passed: boolean | null;
  confidence: number;
  severity: number;
  reasons: Reason[];
}

export interface VerdictResponse {
  verdict: VerdictKind;
  confidence: number;
  summary: string;
  reasons: Reason[];
  field_comparisons: FieldComparison[];
  matched_filing: MatchedFiling | null;
  recommended_actions: Action[];
  checks: Record<string, CheckResult>;
  evidence_summary: Record<string, any>;
  content_hash: string;
  source_type: string;
  latency_ms: number;
  warning_card_url: string | null;
}

export interface StatsResponse {
  total_verifications: number;
  by_verdict: Record<string, number>;
  top_spoofed_entities: { entity: string; count: number }[];
  fraud_clusters: {
    fingerprint: string;
    report_count: number;
    first_seen: string | null;
    last_seen: string | null;
    verdict: string;
    claimed_entity: string | null;
    top_domain: string | null;
  }[];
  mean_latency_ms: number;
  corpus: { filings: number; entities: number; domains: number };
}

export const VERDICT_STYLES: Record<
  VerdictKind,
  { label: string; ring: string; bg: string; text: string; dot: string; badge: string }
> = {
  GENUINE: {
    label: "Verified",
    ring: "ring-emerald-200",
    bg: "bg-emerald-50",
    text: "text-emerald-800",
    dot: "bg-emerald-600",
    badge: "bg-emerald-600",
  },
  TAMPERED: {
    label: "Tampered",
    ring: "ring-amber-200",
    bg: "bg-amber-50",
    text: "text-amber-900",
    dot: "bg-amber-600",
    badge: "bg-amber-600",
  },
  UNVERIFIED: {
    // "No risk found" rather than "Unverified". Both mean the same thing --
    // we could not confirm the sender -- but "unverified" reads as an
    // accusation to somebody holding a perfectly genuine letter from a company
    // we simply have no record of, and that is the most common outcome for
    // legitimate mail. The wording should describe what we found, not imply
    // the sender failed something.
    label: "No risk found",
    ring: "ring-slate-200",
    bg: "bg-slate-50",
    text: "text-slate-700",
    dot: "bg-slate-500",
    badge: "bg-slate-500",
  },
  FRAUDULENT: {
    label: "Fraudulent",
    ring: "ring-red-200",
    bg: "bg-red-50",
    text: "text-red-900",
    dot: "bg-red-600",
    badge: "bg-red-600",
  },
};
