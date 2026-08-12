"""PhishermanAI HTTP API.

    uvicorn api.main:app --reload

Endpoints
    POST /verify           text and/or file -> Verdict
    POST /verify/email     .eml upload -> Verdict
    GET  /entity/{name}    entity lookup + verified official channels
    GET  /stats            aggregate verdicts, spoofed entities, fraud clusters
    GET  /warning-card/{h} the shareable PNG for a verification
    GET  /health

PRIVACY
-------
We persist a SHA-256 of the normalised content and the derived verdict. We do
not store the message body, the uploaded file, or anything identifying the
person who submitted it. The hash is what enables campaign clustering -- five
reports of the same fingerprint are one campaign, not five tickets -- without
retaining anyone's mail.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import (
    EntityResponse,
    FraudCluster,
    HealthResponse,
    StatsResponse,
    VerdictResponse,
)
from core.actions import build_warning_card, official_contact_for
from core.db import get_session, init_db
from core.models import ClaimRule, DomainMap, Entity, Filing, Verification
from core.pipeline import verify as run_verification
from core.textnorm import normalise_company_name

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("phishermanai.api")

DEMO_MODE = os.environ.get("PHISHERMANAI_DEMO_MODE", "1") == "1"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

# Origins that always work: local dev for the Next.js UI, and WhatsApp Web for
# the extension's content script.
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "https://web.whatsapp.com",
]


def _cors_origins() -> list[str]:
    """Defaults plus whatever the deployment adds.

    Deployed front-ends live on hostnames this code cannot know, so the origin
    list has to come from the environment. Comma-separated; a bare "*" turns
    the allowlist off entirely, which is only safe because we never accept
    credentials on these routes (allow_credentials=False below).
    """
    extra = os.environ.get("PHISHERMANAI_CORS_ORIGINS", "")
    origins = list(DEFAULT_CORS_ORIGINS)
    for raw in extra.split(","):
        origin = raw.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    log.info("PhishermanAI API started (demo_mode=%s)", DEMO_MODE)
    yield


app = FastAPI(
    title="PhishermanAI",
    version="0.1.0",
    description=(
        "Verification for Indian retail investors. Checks four universal fraud "
        "chokepoints and cross-checks content against what companies actually "
        "filed with the exchange."
    ),
    lifespan=lifespan,
)

# The browser extension and the Next.js UI both call this API directly.
_origins = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in _origins else _origins,
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Warning cards are held in memory keyed by content hash. They are a rendering
# of the verdict, so there is nothing to gain by persisting them.
_CARD_CACHE: dict[str, bytes] = {}
_CARD_CACHE_LIMIT = 200


def _persist(
    session: Session,
    verdict,
    parsed,
    timings: dict[str, Any],
    channel: str,
) -> None:
    """Record the verdict for /stats. Content itself is never stored."""
    try:
        domains = []
        from core.chokepoints.delivery import registrable_domain
        for url in parsed.urls[:5]:
            domain = registrable_domain(url)
            if domain:
                domains.append(domain)

        session.add(Verification(
            content_hash=parsed.content_hash,
            phash=parsed.phash,
            source_type=parsed.source_type,
            channel=channel,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            claimed_entity=verdict.evidence_summary.get("claimed_entity"),
            top_domain=domains[0] if domains else None,
            reason_codes=[r["code"] for r in verdict.reasons][:20],
            matched_filing_id=(verdict.matched_filing or {}).get("filing_id"),
            latency_ms=timings.get("total_ms"),
        ))
        session.commit()
    except Exception as exc:  # noqa: BLE001 - telemetry must never break a verdict
        log.warning("failed to persist verification: %s", exc)
        session.rollback()


def _to_response(verdict, parsed, timings) -> VerdictResponse:
    from core.scoring import DISPLAY_LABELS

    payload = verdict.to_dict()
    payload["label"] = DISPLAY_LABELS.get(verdict.verdict, verdict.verdict)
    payload["content_hash"] = parsed.content_hash
    payload["source_type"] = parsed.source_type
    payload["latency_ms"] = timings.get("total_ms", 0)
    payload["warning_card_url"] = f"/warning-card/{parsed.content_hash}"
    return VerdictResponse(**payload)


def _cache_card(content_hash: str, verdict, claimed_entity: str | None) -> None:
    try:
        if len(_CARD_CACHE) >= _CARD_CACHE_LIMIT:
            _CARD_CACHE.pop(next(iter(_CARD_CACHE)))
        _CARD_CACHE[content_hash] = build_warning_card(verdict, claimed_entity=claimed_entity)
    except Exception as exc:  # noqa: BLE001
        log.warning("warning card render failed: %s", exc)


@app.post("/verify", response_model=VerdictResponse, summary="Verify a message, file or link")
async def verify_endpoint(
    text: str | None = Form(default=None, description="Pasted message text or a URL"),
    file: UploadFile | None = File(default=None, description=".eml, image or PDF"),
    channel: str = Form(default="WEB", description="WEB | EXTENSION | API"),
    live_verify: bool = Form(default=False, description="Also confirm registrations against SEBI live"),
    money_sent: bool = Form(default=False, description="Has the user already sent money?"),
    session: Session = Depends(get_session),
) -> VerdictResponse:
    if not text and not file:
        raise HTTPException(status_code=400, detail="Provide text or a file to verify.")

    if file is not None:
        payload = await file.read()
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File larger than 12 MB.")
        data: bytes | str = payload
        filename = file.filename
    else:
        data, filename = text or "", None

    if DEMO_MODE and live_verify:
        # Demo mode is offline by contract; honour the flag but say we ignored it.
        live_verify = False

    try:
        verdict, parsed, timings = run_verification(
            data, filename, live_verify=live_verify, money_sent=money_sent,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("verification failed")
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}") from exc

    _persist(session, verdict, parsed, timings, channel)
    _cache_card(parsed.content_hash, verdict, verdict.evidence_summary.get("claimed_entity"))
    return _to_response(verdict, parsed, timings)


@app.post("/verify/email", response_model=VerdictResponse, summary="Verify an .eml file")
async def verify_email_endpoint(
    file: UploadFile = File(..., description="RFC 822 .eml message"),
    channel: str = Form(default="WEB"),
    session: Session = Depends(get_session),
) -> VerdictResponse:
    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File larger than 12 MB.")

    verdict, parsed, timings = run_verification(payload, file.filename, source_type="EMAIL")
    _persist(session, verdict, parsed, timings, channel)
    _cache_card(parsed.content_hash, verdict, verdict.evidence_summary.get("claimed_entity"))
    return _to_response(verdict, parsed, timings)


@app.get("/warning-card/{content_hash}", summary="Shareable warning card PNG")
def warning_card(content_hash: str) -> Response:
    card = _CARD_CACHE.get(content_hash)
    if card is None:
        raise HTTPException(
            status_code=404,
            detail="No card for that fingerprint. Cards are generated when a verification runs.",
        )
    return Response(
        content=card,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="phishermanai-{content_hash[:12]}.png"'},
    )


@app.get("/entity/{name}", response_model=EntityResponse, summary="Entity lookup and official channels")
def entity_lookup(name: str, session: Session = Depends(get_session)) -> EntityResponse:
    target = normalise_company_name(name)
    if not target:
        raise HTTPException(status_code=400, detail="Provide an entity name.")

    rows = session.execute(
        select(Entity).where(Entity.normalised_name == target).limit(10)
    ).scalars().all()
    if not rows:
        rows = session.execute(
            select(Entity).where(Entity.normalised_name.like(f"%{target}%")).limit(10)
        ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No registered entity matching '{name}'.")

    best = max(rows, key=lambda e: (bool(e.official_contact), bool(e.sebi_reg_no), bool(e.isin)))
    domains = [
        d for (d,) in session.execute(
            select(DomainMap.domain).where(DomainMap.entity_name == best.name)
        )
    ] or (best.official_domains or [])

    return EntityResponse(
        entity=best.name,
        entity_type=best.entity_type,
        sebi_registration=best.sebi_reg_no,
        isin=best.isin,
        status=best.status,
        official_domains=domains,
        official_contact=best.official_contact or {},
        caution=(
            "These details come from SEBI's registered-intermediary register and our "
            "verified domain map. Do not use a helpline number found through a search "
            "engine -- fraudulent numbers are deliberately placed there."
        ),
        matches=[
            {"name": e.name, "entity_type": e.entity_type, "sebi_reg_no": e.sebi_reg_no}
            for e in rows[:10]
        ],
    )


@app.get("/stats", response_model=StatsResponse, summary="Aggregate statistics and fraud clusters")
def stats(
    days: int = Query(default=90, ge=1, le=3650),
    session: Session = Depends(get_session),
) -> StatsResponse:
    since = datetime.utcnow() - timedelta(days=days)

    total = session.scalar(
        select(func.count()).select_from(Verification).where(Verification.created_at >= since)
    ) or 0

    by_verdict = {
        verdict: count
        for verdict, count in session.execute(
            select(Verification.verdict, func.count())
            .where(Verification.created_at >= since)
            .group_by(Verification.verdict)
        )
    }

    spoofed = [
        {"entity": name, "count": count}
        for name, count in session.execute(
            select(Verification.claimed_entity, func.count())
            .where(Verification.created_at >= since)
            .where(Verification.claimed_entity.is_not(None))
            .where(Verification.verdict.in_(["FRAUDULENT", "TAMPERED"]))
            .group_by(Verification.claimed_entity)
            .order_by(func.count().desc())
            .limit(10)
        )
    ]

    # CLUSTERING: identical content reported N times is one campaign, not N
    # incidents. Grouping by fingerprint is what turns a pile of tickets into a
    # picture of how far a single piece of fraud has spread.
    clusters: list[FraudCluster] = []
    for content_hash, count, first, last, verdict in session.execute(
        select(
            Verification.content_hash, func.count(),
            func.min(Verification.created_at), func.max(Verification.created_at),
            func.max(Verification.verdict),
        )
        .where(Verification.created_at >= since)
        .where(Verification.verdict.in_(["FRAUDULENT", "TAMPERED"]))
        .group_by(Verification.content_hash)
        .having(func.count() > 1)
        .order_by(func.count().desc())
        .limit(20)
    ):
        row = session.execute(
            select(Verification.claimed_entity, Verification.top_domain)
            .where(Verification.content_hash == content_hash).limit(1)
        ).first()
        clusters.append(FraudCluster(
            fingerprint=content_hash[:16],
            report_count=count,
            first_seen=str(first) if first else None,
            last_seen=str(last) if last else None,
            verdict=verdict,
            claimed_entity=row[0] if row else None,
            top_domain=row[1] if row else None,
        ))

    mean_latency = session.scalar(
        select(func.avg(Verification.latency_ms)).where(Verification.created_at >= since)
    ) or 0.0

    return StatsResponse(
        total_verifications=total,
        by_verdict=by_verdict,
        top_spoofed_entities=spoofed,
        fraud_clusters=clusters,
        mean_latency_ms=round(float(mean_latency), 1),
        corpus={
            "filings": session.scalar(select(func.count()).select_from(Filing)) or 0,
            "entities": session.scalar(select(func.count()).select_from(Entity)) or 0,
            "domains": session.scalar(select(func.count()).select_from(DomainMap)) or 0,
        },
    )


@app.get("/gateway/messages", summary="Mail processed by the SMTP gateway, newest first")
def gateway_messages(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Verdicts for mail that arrived through the SMTP gateway.

    Envelope metadata and the derived verdict only -- message bodies are never
    stored, so there is nothing here to leak.
    """
    from gateway import store

    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    messages = store.list_messages(limit=limit, offset=offset)
    total = store.count_messages()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "returned": len(messages),
        "messages": messages,
    }


@app.get("/gateway/messages/{message_id:path}", summary="One gateway-processed message")
def gateway_message(message_id: str) -> dict[str, Any]:
    """Look up a stored verdict by RFC Message-ID.

    `:path` in the route matters: a Message-ID is angle-bracketed and contains
    an '@' and often slashes, so it must not be split on path separators.
    """
    from gateway import store

    record = store.get_message(message_id)
    if record is None:
        # Clients commonly strip the angle brackets; try the bracketed form
        # before reporting a miss.
        record = store.get_message(f"<{message_id.strip('<>')}>")
    if record is None:
        raise HTTPException(status_code=404, detail=f"No gateway record for Message-ID {message_id}")
    return record


@app.get("/health", response_model=HealthResponse, summary="Health and corpus readiness")
def health(session: Session = Depends(get_session)) -> HealthResponse:
    try:
        filings = session.scalar(select(func.count()).select_from(Filing)) or 0
        entities = session.scalar(select(func.count()).select_from(Entity)) or 0
        domains = session.scalar(select(func.count()).select_from(DomainMap)) or 0
        rules = session.scalar(select(func.count()).select_from(ClaimRule)) or 0
        database = "ok"
    except Exception as exc:  # noqa: BLE001
        filings = entities = domains = rules = 0
        database = f"error: {exc}"

    try:
        from core.filings.matcher import semantic_available
        semantic = semantic_available()
    except Exception:  # noqa: BLE001
        semantic = False

    try:
        import importlib.util
        image_support = all(
            importlib.util.find_spec(m) is not None for m in ("cv2", "imagehash")
        )
    except Exception:  # noqa: BLE001
        image_support = False

    return HealthResponse(
        status="ok" if database == "ok" and filings > 0 else "degraded",
        database=database,
        filings=filings,
        entities=entities,
        domains=domains,
        claim_rules=rules,
        semantic_ranking=semantic,
        image_support=image_support,
        demo_mode=DEMO_MODE,
    )


# --------------------------------------------------------------------------
# Demo endpoints
# --------------------------------------------------------------------------
#
# One-click examples for the demo, served from the fixtures on disk so the
# whole flow works with the network disconnected.

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval", "fixtures")


@app.get("/demo/examples", summary="List the built-in demo examples")
def demo_examples() -> JSONResponse:
    manifest_path = os.path.join(FIXTURE_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        return JSONResponse({"examples": [], "note": "Run: python -m eval.make_fixtures"})
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return JSONResponse({
        "examples": [
            {
                "file": item["file"],
                "expected_label": item["label"],
                "company": item.get("company"),
                "note": item.get("note") or item.get("tampered_field"),
            }
            for item in manifest
        ]
    })


@app.post("/demo/verify/{name}", response_model=VerdictResponse, summary="Verify a demo fixture")
def demo_verify(name: str, session: Session = Depends(get_session)) -> VerdictResponse:
    # Path traversal guard: only a bare filename inside the fixtures directory.
    safe_name = os.path.basename(name)
    path = os.path.join(FIXTURE_DIR, safe_name)
    if not os.path.isfile(path) or os.path.dirname(os.path.abspath(path)) != os.path.abspath(FIXTURE_DIR):
        raise HTTPException(status_code=404, detail=f"No demo fixture named '{safe_name}'.")

    with open(path, "rb") as fh:
        payload = fh.read()

    verdict, parsed, timings = run_verification(payload, safe_name)
    _persist(session, verdict, parsed, timings, "WEB")
    _cache_card(parsed.content_hash, verdict, verdict.evidence_summary.get("claimed_entity"))
    return _to_response(verdict, parsed, timings)


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse({
        "name": "PhishermanAI",
        "docs": "/docs",
        "endpoints": ["/verify", "/verify/email", "/entity/{name}", "/stats", "/health"],
    })
