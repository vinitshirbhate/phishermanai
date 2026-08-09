"""Persistence and deduplication for gateway-processed mail.

Reuses the existing `verifications` table rather than adding a parallel one, so
gateway traffic feeds the same /stats aggregation and campaign clustering as the
web UI and the extension. The gateway-specific columns were added additively --
see `_ADDED_COLUMNS` in core/db.py.

DEDUP: the RFC Message-ID is the key. The same message can legitimately reach a
gateway more than once (an SMTP retry after a timeout, or a copy addressed to
two allowlisted recipients), and re-running verification would waste the work
and double-count the message in /stats.

PRIVACY: envelope metadata and the derived verdict only. The body is never
stored. The subject is kept because the gateway rewrites it, and an operator
needs the original to explain what the recipient is looking at.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from core.db import session_scope
from core.models import Verification
from gateway.verify_client import GatewayVerdict

log = logging.getLogger("phishermanai.gateway.store")


def find_by_message_id(message_id: str) -> Verification | None:
    if not message_id:
        return None
    try:
        with session_scope() as session:
            return session.execute(
                select(Verification)
                .where(Verification.message_id == message_id)
                .order_by(desc(Verification.id))
                .limit(1)
            ).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 - a storage problem must not lose mail
        log.warning("dedup lookup failed: %s", exc)
        return None


def cached_verdict(message_id: str) -> GatewayVerdict | None:
    """Return a previously computed verdict for this Message-ID, if any."""
    row = find_by_message_id(message_id)
    if row is None:
        return None
    return GatewayVerdict(
        verdict=row.verdict,
        confidence=row.confidence or 0,
        summary="",
        reason_codes=list(row.reason_codes or []),
        checks={},
        matched_filing={"filing_id": row.matched_filing_id} if row.matched_filing_id else None,
        verification_id=str(row.id),
        content_hash=row.content_hash,
        latency_ms=0,
        ok=True,
        cached=True,
    )


def record(
    verdict: GatewayVerdict,
    *,
    message_id: str,
    from_addr: str,
    to_addr: str,
    subject_original: str,
    content_hash: str,
    latency_ms: int,
) -> int | None:
    """Persist one gateway verification. Returns the row id."""
    try:
        with session_scope() as session:
            row = Verification(
                content_hash=content_hash,
                source_type="EMAIL",
                channel="GATEWAY",
                verdict=verdict.verdict,
                confidence=verdict.confidence,
                reason_codes=verdict.reason_codes[:12],
                matched_filing_id=(verdict.matched_filing or {}).get("filing_id"),
                latency_ms=latency_ms,
                message_id=message_id[:998],
                from_addr=(from_addr or "")[:320],
                to_addr=(to_addr or "")[:998],
                subject_original=subject_original,
                processed_at=datetime.now(),
            )
            session.add(row)
            session.flush()
            return row.id
    except Exception as exc:  # noqa: BLE001
        log.warning("could not persist verification: %s", exc)
        return None


def list_messages(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Newest first, for GET /gateway/messages."""
    with session_scope() as session:
        rows = session.execute(
            select(Verification)
            .where(Verification.channel == "GATEWAY")
            .order_by(desc(Verification.id))
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return [_serialise(r) for r in rows]


def count_messages() -> int:
    from sqlalchemy import func

    with session_scope() as session:
        return session.scalar(
            select(func.count()).select_from(Verification)
            .where(Verification.channel == "GATEWAY")
        ) or 0


def get_message(message_id: str) -> dict[str, Any] | None:
    row = find_by_message_id(message_id)
    return _serialise(row) if row else None


def _serialise(row: Verification) -> dict[str, Any]:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "from_addr": row.from_addr,
        "to_addr": row.to_addr,
        "subject_original": row.subject_original,
        "verdict": row.verdict,
        "confidence": row.confidence,
        "reason_codes": row.reason_codes or [],
        "matched_filing_id": row.matched_filing_id,
        "latency_ms": row.latency_ms,
        "content_hash": row.content_hash,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
