"""
Phisherman AI Browser v6 - FastAPI Backend

Trust-by-design browser companion. Powers a Chrome MV3 extension.
Deterministic pattern matching, no LLM required for core operation.

Endpoints:
    GET  /health               - service health
    POST /api/analyze/page     - full page analysis
    POST /api/analyze/text     - quick text scan
    POST /api/analyze/url      - URL-only reputation check
    POST /api/fact-check       - news article fact-check
    GET  /api/stats            - analysis statistics
    GET  /api/history          - recent analysis results

Runs on port 8798.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engines import trust_engine
from engines import fact_checker
from engines import scam_detector
from engines.scamgate import ScamGate
from engines import security_gate
from engines import link_reputation
from engines import securities_identity
from store import Store

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("phisherman.api")

# --- App ---
app = FastAPI(
    title="Phisherman AI Browser v6",
    description="Trust-by-design browser companion backend",
    version="6.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Chrome extensions use chrome-extension:// origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory stores ---
_history: deque[dict] = deque(maxlen=200)
_stats = {
    "total_analyses": 0,
    "page_analyses": 0,
    "text_analyses": 0,
    "url_analyses": 0,
    "fact_checks": 0,
    "categories_seen": {},
    "risk_levels": {"SAFE": 0, "CAUTION": 0, "WARNING": 0, "DANGER": 0},
    "started_at": datetime.now(timezone.utc).isoformat(),
}

_boot_time = time.time()
_scamgate = ScamGate(auto_escalate=True, max_tier=2)

# --- Local SQLite store + bundled reference data (F-B1 collision substrate) ---
_DATA_DIR = Path(__file__).resolve().parent / "data"
_store: Optional[Store] = None
try:
    _store = Store()
    _ref_counts = _store.load_reference_data(
        sebi_register=json.loads((_DATA_DIR / "sebi_register.json").read_text(encoding="utf-8")),
        upi_namespace=json.loads((_DATA_DIR / "valid_upi_namespace.json").read_text(encoding="utf-8")),
        official_domains=json.loads((_DATA_DIR / "official_domains.json").read_text(encoding="utf-8")),
    )
    logger.info("Store ready (schema v%d); reference data loaded: %s",
                _store.schema_version(), _ref_counts)
except Exception as exc:  # a store failure must degrade, never crash the API
    logger.warning("Store unavailable, securities collision detection disabled: %s", exc)
    _store = None


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _securities_block(text: str, url: str) -> dict:
    """Compact securities-identity summary for the additive analyze block (§3.2).
    Read-only against the register; does not persist to the collision substrate."""
    from urllib.parse import urlparse
    poster = ""
    if url:
        poster = urlparse(url if "://" in url else f"http://{url}").hostname or ""
    try:
        r = securities_identity.assess_registration(text=text, poster_identity=poster, store=_store)
    except Exception as exc:  # engine failure degrades the block, never the request
        return {"state": "unavailable", "error": str(exc), "degraded_to": "trust_engine_only"}
    return {
        "state": r["state"],
        "trust_delta": r["trust_delta"],
        "claims": r["claims"],
        "collisions": r["collisions"],
        "upi": r["upi"],
        "typologies_matched": r.get("typologies_matched", []),
        "typology_penalty": r.get("typology_penalty", 0),
        "reasons": r["reasons"],
        "register_as_of": r["register_as_of"],
        "layer": "1.7",
    }


# --- Request/Response Models ---

class PageAnalysisRequest(BaseModel):
    url: str = ""
    text: str = ""
    title: str = ""
    meta_description: str = ""
    form_fields: Optional[list[str]] = None

    model_config = {"json_schema_extra": {
        "examples": [{
            "url": "https://example.com/offer",
            "text": "Act now! Your account will be suspended unless you verify your KYC.",
            "title": "Urgent KYC Update Required",
        }]
    }}


class TextAnalysisRequest(BaseModel):
    text: str

    model_config = {"json_schema_extra": {
        "examples": [{
            "text": "Your SBI account has been blocked. Call 9876543210 to verify your KYC immediately."
        }]
    }}


class URLAnalysisRequest(BaseModel):
    url: str

    model_config = {"json_schema_extra": {
        "examples": [{"url": "https://sbi-kyc-update.top/verify"}]
    }}


class FactCheckRequest(BaseModel):
    text: str
    url: str = ""
    title: str = ""

    model_config = {"json_schema_extra": {
        "examples": [{
            "text": "According to sources, 100% of people who tried this supplement were cured instantly.",
            "url": "https://opindia.com/article",
            "title": "Shocking health discovery",
        }]
    }}


class TrustVerdictResponse(BaseModel):
    trust_score: int = Field(ge=0, le=100)
    risk_level: str
    signals: list[str]
    recommendations: list[str]
    fact_check: Optional[dict] = None
    scam_check: Optional[dict] = None
    domain_intel: Optional[dict] = None
    manipulation_check: Optional[dict] = None
    security_gate: Optional[dict] = None
    securities: Optional[dict] = None      # F-B1/F-B2 additive block (§3.2)
    ml: Optional[dict] = None              # F-A2 additive block (reserved)
    provenance: Optional[dict] = None      # F-B5 additive block (reserved)
    behavior: Optional[dict] = None        # behaviour_lane: tactics, combos, narrative
    processing_ms: float


class FactCheckResponse(BaseModel):
    credibility_score: int = Field(ge=0, le=100)
    source_tier: str
    source_category: str
    claim_count: int
    verified_claims: int
    unverified_claims: int
    manipulation_signals: list[str]
    claims_found: list[str]
    dates_found: list[str]
    attributions_found: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    engines: list[str]


class StatsResponse(BaseModel):
    total_analyses: int
    page_analyses: int
    text_analyses: int
    url_analyses: int
    fact_checks: int
    categories_seen: dict
    risk_levels: dict
    started_at: str
    uptime_seconds: float


# --- Helpers ---

def _record_history(endpoint: str, request_summary: str, verdict: dict):
    """Record an analysis result in history."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "request_summary": request_summary[:200],
        "trust_score": verdict.get("trust_score", verdict.get("credibility_score", 0)),
        "risk_level": verdict.get("risk_level", "UNKNOWN"),
    }
    _history.appendleft(entry)


def _update_stats(endpoint: str, verdict: dict, categories: list[str] | None = None):
    """Update analysis statistics."""
    _stats["total_analyses"] += 1

    endpoint_map = {
        "page": "page_analyses",
        "text": "text_analyses",
        "url": "url_analyses",
        "fact-check": "fact_checks",
    }
    key = endpoint_map.get(endpoint, "page_analyses")
    _stats[key] = _stats.get(key, 0) + 1

    risk_level = verdict.get("risk_level", "")
    if risk_level in _stats["risk_levels"]:
        _stats["risk_levels"][risk_level] += 1

    if categories:
        for cat in categories:
            _stats["categories_seen"][cat] = _stats["categories_seen"].get(cat, 0) + 1


# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health():
    """Service health check."""
    return HealthResponse(
        status="ok",
        version="6.0.0",
        uptime_seconds=round(time.time() - _boot_time, 1),
        engines=[
            "trust_engine",
            "scam_detector",
            "fact_checker",
            "domain_intel",
            "manipulation_detector",
            "behavior_lane",
            "security_gate",
        ],
    )


@app.post("/api/analyze/page", response_model=TrustVerdictResponse)
async def analyze_page(req: PageAnalysisRequest):
    """Full page analysis — URL + text + signals combined."""
    if not req.url and not req.text:
        raise HTTPException(status_code=400, detail="Provide at least url or text")

    verdict = trust_engine.analyze_page(
        url=req.url,
        text=req.text,
        title=req.title,
        meta_description=req.meta_description,
        form_fields=req.form_fields,
    )
    result = verdict.to_dict()
    result["securities"] = _securities_block(
        text="\n".join(filter(None, [req.title, req.meta_description, req.text])),
        url=req.url,
    )

    # Extract scam categories for stats
    scam_cats = []
    if verdict.scam_check:
        scam_cats = verdict.scam_check.get("categories_hit", [])

    summary = req.url or req.title or req.text[:80]
    _record_history("page", summary, result)
    _update_stats("page", result, scam_cats)

    return result


@app.post("/api/analyze/text", response_model=TrustVerdictResponse)
async def analyze_text(req: TextAnalysisRequest):
    """Quick text scan — no URL/domain analysis."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    verdict = trust_engine.analyze_text(text=req.text)
    result = verdict.to_dict()
    result["securities"] = _securities_block(text=req.text, url="")

    scam_cats = []
    if verdict.scam_check:
        scam_cats = verdict.scam_check.get("categories_hit", [])

    _record_history("text", req.text[:80], result)
    _update_stats("text", result, scam_cats)

    return result


@app.post("/api/analyze/url", response_model=TrustVerdictResponse)
async def analyze_url(req: URLAnalysisRequest):
    """URL-only reputation check."""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    verdict = trust_engine.analyze_url(url=req.url)
    result = verdict.to_dict()

    _record_history("url", req.url[:100], result)
    _update_stats("url", result)

    return result


@app.post("/api/fact-check", response_model=FactCheckResponse)
async def fact_check(req: FactCheckRequest):
    """News article fact-check."""
    text = "\n".join(filter(None, [req.title, req.text]))
    if not text.strip():
        raise HTTPException(status_code=400, detail="Provide text or title to fact-check")

    result_obj = fact_checker.check(text=text, url=req.url)
    result = result_obj.to_dict()

    _record_history("fact-check", req.url or req.title or req.text[:80], {
        "credibility_score": result["credibility_score"],
        "risk_level": "SAFE" if result["credibility_score"] >= 60 else "CAUTION",
    })
    _update_stats("fact-check", {"risk_level": "SAFE" if result["credibility_score"] >= 60 else "CAUTION"})

    return result


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Analysis statistics since server start."""
    return StatsResponse(
        **_stats,
        uptime_seconds=round(time.time() - _boot_time, 1),
    )


@app.get("/api/history")
async def get_history(limit: int = 50):
    """Recent analysis results. Returns up to `limit` entries (max 200)."""
    limit = min(max(1, limit), 200)
    return {"history": list(_history)[:limit], "total": len(_history)}


# --- ScamGate Direct Access ---

class ScamGateScanRequest(BaseModel):
    text: str = ""
    url: str = ""


@app.post("/api/scamgate/scan")
async def scamgate_scan(req: ScamGateScanRequest):
    """ScamGate auto-escalation scan (L0 → L1 → L2 as needed)."""
    if not req.text and not req.url:
        raise HTTPException(status_code=400, detail="Provide text or url")
    result = _scamgate.scan(req.text, req.url)
    _record_history("scamgate", req.url or req.text[:80], result.to_dict())
    _update_stats("text", result.to_dict(), result.categories)
    return result.to_dict()


@app.post("/api/scamgate/quick")
async def scamgate_quick(req: ScamGateScanRequest):
    """ScamGate L0-only scan (instant, deterministic)."""
    if not req.text and not req.url:
        raise HTTPException(status_code=400, detail="Provide text or url")
    result = _scamgate.quick_scan(req.text, req.url)
    return result.to_dict()


@app.post("/api/scamgate/deep")
async def scamgate_deep(req: ScamGateScanRequest):
    """ScamGate forced deep scan (all tiers: L0+L1+L2)."""
    if not req.text and not req.url:
        raise HTTPException(status_code=400, detail="Provide text or url")
    result = _scamgate.deep_scan(req.text, req.url)
    _record_history("scamgate-deep", req.url or req.text[:80], result.to_dict())
    _update_stats("text", result.to_dict(), result.categories)
    return result.to_dict()


@app.get("/api/scamgate/stats")
async def scamgate_stats():
    """ScamGate-specific statistics."""
    return _scamgate.stats()


# --- Security Gates ---

class URLGateRequest(BaseModel):
    url: str


class DownloadGateRequest(BaseModel):
    filename: str
    content_type: str = ""
    url: str = ""


class FormGateRequest(BaseModel):
    field_names: list[str]
    form_action: str = ""
    domain_trusted: bool = False


class ClipboardGateRequest(BaseModel):
    text: str
    target_field: str = ""


@app.post("/api/gate/url")
async def gate_url(req: URLGateRequest):
    """Check URL safety before navigation."""
    result = security_gate.url_gate(req.url)
    return result.to_dict()


@app.post("/api/gate/download")
async def gate_download(req: DownloadGateRequest):
    """Check file download safety."""
    result = security_gate.download_gate(req.filename, req.content_type, req.url)
    return result.to_dict()


@app.post("/api/gate/form")
async def gate_form(req: FormGateRequest):
    """Check form fields for sensitive data collection."""
    result = security_gate.form_gate(req.field_names, req.form_action, req.domain_trusted)
    return result.to_dict()


@app.post("/api/gate/clipboard")
async def gate_clipboard(req: ClipboardGateRequest):
    """Check clipboard content before paste."""
    result = security_gate.clipboard_gate(req.text, req.target_field)
    return result.to_dict()


@app.post("/api/gate/input")
async def gate_input(req: TextAnalysisRequest):
    """Check text for prompt injection."""
    result = security_gate.input_gate(req.text)
    return result.to_dict()


# --- Securities identity (F-B1 / F-B2) ---

class SecuritiesIdentityRequest(BaseModel):
    text: str = ""
    url: str = ""
    handle: str = ""
    page_date: Optional[str] = None
    record: bool = True  # persist to collision substrate

    model_config = {"json_schema_extra": {"examples": [{
        "text": "Join my VIP group! SEBI INZ000031633 guaranteed profit trading",
        "handle": "ProfitGuruji", "page_date": "2026-07-01",
    }]}}


class UPIVerifyRequest(BaseModel):
    upi_id: str
    claimed_category: Optional[str] = None


def _poster_identity(req: SecuritiesIdentityRequest) -> str:
    if req.handle:
        return req.handle
    if req.url:
        from urllib.parse import urlparse
        host = urlparse(req.url if "://" in req.url else f"http://{req.url}").hostname
        if host:
            return host
    return ""


@app.post("/api/securities/identity")
async def securities_identity_check(req: SecuritiesIdentityRequest):
    """F-B1: extract → resolve → five states, with collision detection."""
    t0 = time.perf_counter()
    poster = _poster_identity(req)
    result = securities_identity.assess_registration(
        text=req.text, poster_identity=poster, page_date=req.page_date, store=_store,
    )
    # Persist to the collision substrate so repeat claims across handles surface.
    if req.record and _store is not None and result["claims"]:
        try:
            entities = [{"entity_type": "reg_number", "entity_value": c["number"]}
                        for c in result["claims"]]
            _store.record_observation(
                {"channel": "web" if req.url else "text", "surface_id": poster or None,
                 "content_sha256": _sha256_text(req.text), "trust_score": 50,
                 "tier": "MEDIUM", "layer": "1.7", "model_version": None},
                entities=entities,
                reasons=[{"code": r["code"], "weight": abs(securities_identity.SECURITIES_DELTA.get(result["state"], 0)),
                          "source_url": r.get("source_url")} for r in result["reasons"]],
                identity={"reg_claimed": result["claims"][0]["number"],
                          "reg_state": result["state"],
                          "reg_resolved_to": result["claims"][0].get("resolved_name"),
                          "name_match_score": result["claims"][0].get("name_match_score"),
                          "register_as_of": result["register_as_of"]},
            )
        except Exception as exc:
            logger.warning("Could not persist securities observation: %s", exc)
    result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    result["layer"] = "1.7"
    return result


@app.post("/api/upi/verify")
async def upi_verify(req: UPIVerifyRequest):
    """F-B2: @valid namespace membership + category-mismatch + SEBI Check link."""
    if not req.upi_id.strip():
        raise HTTPException(status_code=400, detail="upi_id cannot be empty")
    return securities_identity.upi_namespace_check(req.upi_id, req.claimed_category)


# --- Campaign correlation (F-A7) ---

class CampaignIngestRequest(BaseModel):
    text: str = ""
    url: str = ""
    channel: str = "web"
    surface_id: Optional[str] = None
    trust_score: int = 50
    tier: str = "MEDIUM"
    phash: Optional[str] = None
    group: Optional[str] = None
    observed_at: Optional[str] = None


@app.post("/api/campaign/ingest")
async def campaign_ingest(req: CampaignIngestRequest):
    """F-A7: correlate an observation into a campaign object. Local-only."""
    if _store is None:
        return {"campaign_id": None, "error": "store unavailable", "degraded_to": "no_correlation"}
    from engines.campaign_lane import CampaignLane, extract_entities
    sec = securities_identity.assess_registration(req.text, req.surface_id or req.url, store=_store)
    entities = extract_entities(
        text=req.text, url=req.url,
        reg_numbers=[c["number"] for c in sec.get("claims", [])],
        phash=req.phash, group=req.group,
    )
    if not entities:
        return {"campaign_id": None, "is_new": False, "reason": "no linkable entities"}
    oid = _store.record_observation(
        {"channel": req.channel, "surface_id": req.surface_id or req.url or None,
         "content_sha256": _sha256_text(req.text), "trust_score": req.trust_score,
         "tier": req.tier, "layer": "4.1", "observed_at": req.observed_at},
        entities=entities)
    result = CampaignLane(_store).ingest(oid, entities, req.channel, req.observed_at)
    result["observation_id"] = oid
    return result


@app.get("/api/campaign/{campaign_id}")
async def campaign_get(campaign_id: str):
    """Campaign detail: members, timeline, channel set, entities."""
    if _store is None:
        raise HTTPException(status_code=503, detail="store unavailable")
    from engines.campaign_lane import CampaignLane
    data = CampaignLane(_store).get(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"no campaign {campaign_id}")
    return data


@app.get("/api/campaigns")
async def campaigns_list(limit: int = 50):
    """F-C7 substrate: campaigns most recently seen first. Read-only."""
    if _store is None:
        return {"campaigns": []}
    from engines.campaign_lane import CampaignLane
    return {"campaigns": CampaignLane(_store).list_campaigns(limit)}


@app.post("/api/link/inspect")
async def link_inspect(req: URLAnalysisRequest):
    """
    Reputation for a single link, WITH PROVENANCE.

    Serves the hover card. Unlike /api/analyze/url this does not run the full
    trust engine - it answers "what is known about this domain, and what did you
    actually consult", which is the question a user hovering a link is asking.

    `checked` is returned on every call, hit or miss. A card that says "no
    signals" and nothing else is true and useless; one that says which lists were
    searched, how many domains they hold and when they were refreshed is
    falsifiable, and lets the user weigh it themselves.
    """
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    return link_reputation.inspect(req.url)


@app.get("/api/registry/meta")
async def registry_meta():
    """I-ALL: data recency for every bundled snapshot."""
    if _store is None:
        return {"registries": [], "note": "store unavailable"}
    return {"registries": _store.registry_meta()}


# --- Main ---

def main():
    """Run the server directly."""
    import uvicorn
    port = int(os.environ.get("PHISHERMAN_PORT", "8799"))
    logger.info("Starting Phisherman AI Browser v6 backend on port %d", port)
    uvicorn.run(
        "api:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
