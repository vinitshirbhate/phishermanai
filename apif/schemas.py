"""Shared vocabulary. Every detector and engine speaks in Signals; the fusion engine
turns a list of Signals into a Verdict. Nothing else crosses module boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Band = Literal["Low", "Medium", "High", "Critical"]

# Canonical signal names. The fusion weights in config.py are keyed by these, so a typo
# here silently drops a signal from scoring — keep the two in sync.
SIGNAL_TEXT_PHISHING = "text_phishing"
SIGNAL_VOICE_SPOOF = "voice_spoof"
SIGNAL_VIDEO_DEEPFAKE = "video_deepfake"
SIGNAL_SOURCE_UNTRUSTED = "source_untrusted"
SIGNAL_COORDINATION = "coordination"
SIGNAL_MARKET_ANOMALY = "market_anomaly"


class Signal(BaseModel):
    """One detector's contribution to the verdict.

    `available=False` means the detector was skipped or failed — the fusion engine
    excludes it and renormalizes, rather than treating absence as innocence.
    """

    name: str
    score: float = Field(0.0, ge=0.0, le=1.0, description="0.0 benign -> 1.0 malicious")
    available: bool = True
    summary: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @classmethod
    def unavailable(cls, name: str, error: str) -> "Signal":
        return cls(name=name, score=0.0, available=False, error=error,
                   summary=f"{name}: not evaluated ({error})")


class Verdict(BaseModel):
    risk_score: float = Field(..., ge=0.0, le=1.0)
    band: Band
    headline: str
    explanation: str = ""
    signals: list[Signal] = Field(default_factory=list)
    transcript: str | None = None
    # Set when an override fired, so the score is never unexplainable.
    override_applied: str | None = None
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def signal(self, name: str) -> Signal | None:
        return next((s for s in self.signals if s.name == name), None)


class ExtractedEntities(BaseModel):
    """What the LLM analyst pulls out of a piece of content, used to drive the
    registry lookup (claimed_issuer) and market correlation (tickers)."""

    claimed_issuer: str | None = Field(
        None, description="Organisation the content claims to be from, e.g. 'SEBI'"
    )
    companies: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list, description="NSE/BSE symbols")
    urgency_cues: list[str] = Field(default_factory=list)
    requested_actions: list[str] = Field(default_factory=list)
    impersonation_markers: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


# --- API request/response models ---


class TextAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_url: str | None = None
    sender: str | None = Field(None, description="Email address or @handle")


class RegistryLookupResult(BaseModel):
    query: str
    matched: bool
    organisation: str | None = None
    match_type: str | None = Field(None, description="domain | handle | email_domain")
    lookalike_of: str | None = Field(
        None, description="Set when the query impersonates a trusted source"
    )
    notes: list[str] = Field(default_factory=list)


class ContentItemOut(BaseModel):
    id: int
    headline: str
    summary: str = ""
    source: str = ""
    url: str = ""
    company: str = ""
    official: bool = False
    impact: str = ""
    risk_score: float | None = None
    band: Band | None = None
    ingested_at: datetime


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    dependencies: dict[str, str]
