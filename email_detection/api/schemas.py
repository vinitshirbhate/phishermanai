"""Pydantic v2 models for the API surface."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VerdictLiteral = Literal["GENUINE", "TAMPERED", "UNVERIFIED", "FRAUDULENT"]


class ReasonOut(BaseModel):
    code: str = Field(description="Stable machine-readable reason code")
    message: str = Field(description="Plain-English explanation shown to the user")
    evidence: dict[str, Any] = Field(default_factory=dict)
    severity: int = Field(ge=0, le=5)


class FieldComparisonOut(BaseModel):
    field: str
    extracted_value: Any = None
    filed_value: Any = None
    match: bool | None = None
    read_confidence: Literal["HIGH", "MEDIUM", "UNREADABLE"] = "HIGH"
    severity: int = 0
    bbox: list[int] | None = Field(
        default=None, description="[x1,y1,x2,y2] for drawing a highlight on the source image"
    )
    message: str = ""


class MatchedFilingOut(BaseModel):
    filing_id: int | None = None
    tier: str = "NONE"
    score: float = 0.0
    company_name: str | None = None
    filing_type: str | None = None
    filing_date: str | None = None
    headline: str | None = None
    pdf_url: str | None = None
    exchange: str | None = None
    ranking_method: str = "none"
    candidates_considered: int = 0
    notes: list[str] = Field(default_factory=list)
    matched_entity: dict[str, Any] | None = None


class ActionOut(BaseModel):
    priority: str
    type: str
    title: str
    detail: str
    contact: dict[str, Any] | None = None
    channel: dict[str, Any] | None = None


class VerdictResponse(BaseModel):
    verdict: VerdictLiteral
    # The human-readable form of `verdict`. Served by the API so every client --
    # web UI, extension, gateway -- shows the same wording without each one
    # keeping its own copy of the mapping and drifting.
    label: str = Field(
        default="",
        description='Display label: VERIFIED | NO RISK FOUND | TAMPERED | FRAUDULENT',
    )
    confidence: int = Field(ge=0, le=100, description="How much evidence was available, not how bad it is")
    summary: str
    reasons: list[ReasonOut] = Field(default_factory=list)
    field_comparisons: list[FieldComparisonOut] = Field(default_factory=list)
    matched_filing: MatchedFilingOut | None = None
    recommended_actions: list[ActionOut] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""
    source_type: str = "TEXT"
    latency_ms: int = 0
    warning_card_url: str | None = None


class EntityResponse(BaseModel):
    entity: str
    entity_type: str
    sebi_registration: str | None = None
    isin: str | None = None
    status: str = "ACTIVE"
    official_domains: list[str] = Field(default_factory=list)
    official_contact: dict[str, Any] = Field(default_factory=dict)
    caution: str
    matches: list[dict[str, Any]] = Field(default_factory=list)


class FraudCluster(BaseModel):
    fingerprint: str
    report_count: int
    first_seen: str | None = None
    last_seen: str | None = None
    verdict: str
    claimed_entity: str | None = None
    top_domain: str | None = None


class StatsResponse(BaseModel):
    total_verifications: int
    by_verdict: dict[str, int]
    top_spoofed_entities: list[dict[str, Any]]
    fraud_clusters: list[FraudCluster]
    mean_latency_ms: float
    corpus: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    database: str
    filings: int
    entities: int
    domains: int
    claim_rules: int
    semantic_ranking: bool
    image_support: bool
    demo_mode: bool
