"""Ingestion control, the scored content feed, and the broker/regulator dashboards.

The two dashboard endpoints return exactly the aggregates plan.md's broker console and
SEBI command centre need, so a frontend can be built against them later without changing
anything below this layer.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Query

from ..engines import coordination
from ..ingest import exchanges, firecrawl, store
from ..schemas import ContentItemOut, Signal

router = APIRouter(prefix="/api/v1", tags=["feed & dashboards"])


@router.post("/ingest/run")
async def run_ingestion(
    background: BackgroundTasks,
    wait: bool = Query(False, description="Run inline and return counts instead of queueing"),
) -> dict:
    """Sweep Firecrawl (official sources + X/Twitter) and the NSE/BSE feeds.

    Defaults to a background task: a full sweep hits 13 remote endpoints and would
    otherwise hold the HTTP connection open for minutes.
    """
    async def _sweep() -> dict:
        return {
            "firecrawl": await firecrawl.run_ingestion(),
            "exchanges": await exchanges.run_exchange_ingestion(),
        }

    if wait:
        return await _sweep()
    background.add_task(_sweep)
    return {"status": "started", "note": "poll GET /api/v1/feed for results"}


@router.get("/feed", response_model=list[ContentItemOut])
async def feed(
    limit: int = Query(50, ge=1, le=500),
    channel: str | None = Query(None, description="'web' or 'twitter'"),
    company: str | None = Query(None),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
) -> list[ContentItemOut]:
    """Ingested market content, newest first, optionally filtered."""
    rows = store.list_content(
        limit=limit, channel=channel, company=company, min_score=min_score
    )
    return [
        ContentItemOut(
            id=r.id, headline=r.headline, summary=r.summary, source=r.source,
            url=r.url, company=r.company, official=r.official, impact=r.impact,
            risk_score=r.risk_score, band=r.band, ingested_at=r.ingested_at,
        )
        for r in rows
    ]


@router.get("/coordination", response_model=Signal)
async def coordination_report() -> Signal:
    """Campaign analysis across all stored X/Twitter chatter.

    Heuristic by design (TF-IDF similarity + burst timing), not a trained GNN -- see the
    module docstring in engines/coordination.py for why.
    """
    posts = store.social_posts_for_graph()
    return coordination.analyze(posts)


@router.get("/dashboard/broker")
async def broker_dashboard(limit: int = Query(20, ge=1, le=100)) -> dict:
    """Threat feed for a broker or RIA desk: what is being manipulated right now."""
    analyses = store.recent_analyses(limit=200)
    ticker_counter: Counter[str] = Counter()
    for a in analyses:
        if a.band in ("High", "Critical"):
            ticker_counter.update(t for t in a.tickers.split(",") if t)

    posts = store.social_posts_for_graph()
    campaign = coordination.analyze(posts)

    return {
        "generated_at": store.utcnow(),
        "trending_flagged_tickers": [
            {"ticker": t, "flagged_mentions": n} for t, n in ticker_counter.most_common(limit)
        ],
        "active_campaigns": campaign.evidence.get("clusters", []),
        "recent_high_risk": [
            {
                "id": a.id, "kind": a.kind, "band": a.band,
                "risk_score": a.risk_score, "headline": a.headline,
                "claimed_issuer": a.claimed_issuer, "created_at": a.created_at,
            }
            for a in analyses if a.band in ("High", "Critical")
        ][:limit],
    }


@router.get("/dashboard/regulator")
async def regulator_dashboard(days: int = Query(7, ge=1, le=90)) -> dict:
    """Cross-platform rollup for SEBI: impersonation attempts, campaigns, hot sectors."""
    # Naive UTC on both sides -- stored timestamps come back from SQLite without tzinfo.
    since = store.utcnow() - timedelta(days=days)
    analyses = [a for a in store.recent_analyses(limit=1000) if a.created_at >= since]

    impersonated: Counter[str] = Counter()
    for a in analyses:
        if a.claimed_issuer and a.band in ("High", "Critical"):
            impersonated.update([a.claimed_issuer])

    posts = store.social_posts_for_graph()
    campaign = coordination.analyze(posts)
    counts = store.dashboard_counts()

    return {
        "generated_at": store.utcnow(),
        "window_days": days,
        "totals": counts,
        "verdicts_in_window": len(analyses),
        "by_band": dict(Counter(a.band for a in analyses)),
        "by_kind": dict(Counter(a.kind for a in analyses)),
        "most_impersonated_issuers": [
            {"issuer": k, "incidents": v} for k, v in impersonated.most_common(10)
        ],
        "coordination": {
            "score": campaign.score,
            "available": campaign.available,
            "summary": campaign.summary,
            "cluster_count": campaign.evidence.get("cluster_count", 0),
            "method": campaign.evidence.get("method"),
        },
    }
