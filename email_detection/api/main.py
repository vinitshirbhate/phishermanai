"""PhishermanAI HTTP API.

    uvicorn api.main:app --reload

Endpoints
    POST /verify           text and/or file -> Verdict
    POST /verify/email     .eml upload -> Verdict
    POST /gmail/latest/verify  fetch latest Gmail message -> both verdicts
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
import base64
import hmac
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import requests
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
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
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
BODY_DETECT_URL = os.environ.get(
    "BODY_DETECT_URL",
    "https://fraud-detect-1-6er0.onrender.com/detect",
)
OUTBOUND_HTTP_TIMEOUT = 180
APP_ROOT = Path(__file__).resolve().parent.parent
TEST_EMAIL_PAGE = APP_ROOT / "test_email.html"
_GMAIL_TOKEN_CACHE: dict[str, Any] | None = None


def _default_gmail_token_path() -> Path:
    """Find the local token without assuming the host's directory depth."""
    candidates = (
        APP_ROOT / "token.json",              # Docker: /app/token.json
        APP_ROOT.parent.parent / "token.json",  # Repository development layout
    )
    return next((path for path in candidates if path.is_file()), candidates[0])

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


def _gmail_token_data() -> dict[str, Any]:
    """Load Gmail OAuth data from a deployment secret or local token file."""
    global _GMAIL_TOKEN_CACHE
    if _GMAIL_TOKEN_CACHE is not None:
        return _GMAIL_TOKEN_CACHE

    raw_token = os.environ.get("GMAIL_TOKEN_JSON")
    if raw_token:
        try:
            _GMAIL_TOKEN_CACHE = json.loads(raw_token)
            return _GMAIL_TOKEN_CACHE
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="GMAIL_TOKEN_JSON is not valid JSON.") from exc

    token_path = Path(os.environ.get("GMAIL_TOKEN_FILE", _default_gmail_token_path()))
    if not token_path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Gmail is not configured. Set GMAIL_TOKEN_JSON or GMAIL_TOKEN_FILE.",
        )
    try:
        _GMAIL_TOKEN_CACHE = json.loads(token_path.read_text(encoding="utf-8"))
        return _GMAIL_TOKEN_CACHE
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Unable to read the Gmail token.") from exc


def _refresh_gmail_token(token_data: dict[str, Any]) -> str:
    """Refresh an expired Gmail access token using the OAuth refresh token."""
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Gmail token expired and has no refresh_token. Re-authorize Gmail with offline access.",
        )

    try:
        response = requests.post(
            token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            data={
                "client_id": token_data.get("client_id"),
                "client_secret": token_data.get("client_secret"),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        refreshed = response.json()
        access_token = refreshed["access_token"]
        token_data["token"] = access_token
        return access_token
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Unable to refresh Gmail token: {exc}") from exc


def _gmail_get(path: str, token_data: dict[str, Any], **params) -> dict[str, Any]:
    """Call Gmail, refreshing the access token once after a 401 response."""
    token = token_data.get("token")
    if not token:
        raise HTTPException(status_code=500, detail="Gmail token is missing the access token.")

    url = f"{GMAIL_API_BASE}/{path.lstrip('/')}"
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        if response.status_code == 401:
            token = _refresh_gmail_token(token_data)
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=30,
            )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else 502
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=status, detail=f"Gmail API request failed: {detail}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Gmail returned invalid JSON.") from exc


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _email_body(raw_email: bytes) -> tuple[str, dict[str, str]]:
    """Extract the preferred plain-text body and basic headers from an EML."""
    message = BytesParser(policy=policy.default).parsebytes(raw_email)
    plain_parts: list[str] = []
    html_parts: list[str] = []

    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace")
        if part.get_content_type() == "text/plain":
            plain_parts.append(str(content))
        else:
            html_parts.append(str(content))

    body = "\n".join(plain_parts).strip()
    if not body and html_parts:
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", "\n".join(html_parts))).strip()

    headers = {
        "subject": str(message.get("subject", "")),
        "from": str(message.get("from", "")),
        "to": str(message.get("to", "")),
        "date": str(message.get("date", "")),
        "message_id": str(message.get("message-id", "")),
    }
    return body, headers


def _require_gmail_api_key(provided_key: str | None) -> None:
    require_key = os.environ.get("GMAIL_REQUIRE_API_KEY", "1").strip().lower()
    if require_key in {"0", "false", "no", "off"}:
        return

    expected_key = os.environ.get("GMAIL_FETCH_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Gmail verification is not configured on this deployment.",
        )
    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key.")


def _load_gmail_message(
    gmail_message_id: str,
    token_data: dict[str, Any],
) -> tuple[bytes, str, dict[str, str]]:
    """Download and parse one Gmail message by its Gmail ID."""
    raw_result = _gmail_get(
        f"messages/{gmail_message_id}",
        token_data,
        format="raw",
    )
    raw_email = _decode_base64url(raw_result.get("raw", ""))
    if not raw_email:
        raise HTTPException(status_code=502, detail="Gmail returned an empty raw message.")
    if len(raw_email) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Email is larger than 12 MB.")
    body, headers = _email_body(raw_email)
    return raw_email, body, headers


def _verify_gmail_message(
    gmail_message_id: str,
    token_data: dict[str, Any],
    session: Session,
) -> dict[str, Any]:
    """Run both detectors for one selected Gmail message."""
    raw_email, body, headers = _load_gmail_message(gmail_message_id, token_data)

    try:
        verdict, parsed, timings = run_verification(
            raw_email,
            f"{gmail_message_id}.eml",
            source_type="EMAIL",
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Gmail message verification failed")
        raise HTTPException(status_code=500, detail=f"Email verification failed: {exc}") from exc

    _persist(session, verdict, parsed, timings, "API")
    _cache_card(parsed.content_hash, verdict, verdict.evidence_summary.get("claimed_entity"))
    email_verification = _to_response(verdict, parsed, timings).model_dump(mode="json")

    if not body:
        body_detection: dict[str, Any] = {"error": "The selected email has no text body."}
    else:
        try:
            response = requests.post(
                BODY_DETECT_URL,
                json={"text": body},
                timeout=OUTBOUND_HTTP_TIMEOUT,
            )
            if response.ok:
                body_detection = response.json()
            else:
                try:
                    error_response: Any = response.json()
                except ValueError:
                    error_response = response.text
                body_detection = {
                    "error": f"Body detection endpoint returned HTTP {response.status_code}",
                    "response": error_response,
                }
        except requests.RequestException as exc:
            body_detection = {"error": f"Body detection endpoint failed: {exc}"}
        except ValueError:
            body_detection = {"error": "Body detection endpoint returned invalid JSON."}

    return {
        "email": {
            "gmail_message_id": gmail_message_id,
            **headers,
            "body": body,
        },
        "email_verification": email_verification,
        "body_detection": body_detection,
    }


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


@app.post(
    "/gmail/latest/verify",
    summary="Fetch and verify the latest Gmail inbox message",
)
def verify_latest_gmail_endpoint(
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Fetch the newest inbox email and return both detection results.

    The raw message and body remain in memory and are not saved by this route.
    Configure Gmail with ``GMAIL_TOKEN_JSON`` (recommended for deployment) or
    ``GMAIL_TOKEN_FILE``. API-key protection is controlled by
    ``GMAIL_REQUIRE_API_KEY``; when enabled, clients must send the configured
    ``GMAIL_FETCH_API_KEY`` value in the ``X-API-Key`` header.
    """
    _require_gmail_api_key(request.headers.get("X-API-Key"))
    token_data = _gmail_token_data()
    listing = _gmail_get(
        "messages",
        token_data,
        labelIds="INBOX",
        maxResults=1,
    )
    messages = listing.get("messages", [])
    if not messages:
        raise HTTPException(status_code=404, detail="No emails found in the inbox.")

    return _verify_gmail_message(messages[0]["id"], token_data, session)


@app.get("/gmail/emails", summary="List recent Gmail inbox messages")
def list_gmail_emails(
    request: Request,
    limit: int = Query(default=2, ge=1, le=10),
) -> dict[str, Any]:
    """Return safe preview data for the most recent inbox messages."""
    _require_gmail_api_key(request.headers.get("X-API-Key"))
    token_data = _gmail_token_data()
    listing = _gmail_get("messages", token_data, labelIds="INBOX", maxResults=limit)
    previews = []
    for item in listing.get("messages", []):
        _raw, body, headers = _load_gmail_message(item["id"], token_data)
        previews.append({
            "gmail_message_id": item["id"],
            **headers,
            "preview": re.sub(r"\s+", " ", body)[:240],
        })
    return {"emails": previews, "count": len(previews)}


@app.post(
    "/gmail/messages/{gmail_message_id}/verify",
    summary="Run both detectors for a selected Gmail message",
)
def verify_selected_gmail_endpoint(
    gmail_message_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_gmail_api_key(request.headers.get("X-API-Key"))
    return _verify_gmail_message(gmail_message_id, _gmail_token_data(), session)


@app.get("/test-email", include_in_schema=False)
def test_email_page() -> FileResponse:
    if not TEST_EMAIL_PAGE.is_file():
        raise HTTPException(status_code=404, detail="test_email.html is missing.")
    return FileResponse(TEST_EMAIL_PAGE, media_type="text/html")


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
        "endpoints": [
            "/verify", "/verify/email", "/gmail/latest/verify",
            "/entity/{name}", "/stats", "/health",
        ],
    })
