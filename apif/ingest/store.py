"""SQLite persistence via SQLAlchemy 2.0.

Persistence is what turns single-shot analysis into a monitoring product: the coordination
engine needs a corpus of posts to find clusters in, and the broker/regulator dashboards
need history to aggregate. An in-memory dict would lose all of that on reload.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, create_engine,
    func, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from ..config import get_settings


def utcnow() -> datetime:
    """Naive UTC.

    SQLite has no timezone type, so SQLAlchemy silently drops tzinfo on write and hands
    back naive datetimes on read. Storing aware values therefore creates a trap: any
    later `row.created_at >= datetime.now(timezone.utc)` raises "can't compare
    offset-naive and offset-aware datetimes". Everything that touches these columns uses
    this helper so both sides of a comparison are naive UTC.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


_utcnow = utcnow  # column defaults reference this name


class Base(DeclarativeBase):
    pass


class ContentItem(Base):
    """A scraped news item or social post."""

    __tablename__ = "content_item"
    # Re-running ingestion must update rather than duplicate; URL is the natural key.
    __table_args__ = (UniqueConstraint("url", name="uq_content_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(1024), default="")
    headline: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(255), default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    impact: Mapped[str] = mapped_column(String(32), default="")
    official: Mapped[bool] = mapped_column(Boolean, default=False)
    channel: Mapped[str] = mapped_column(String(32), default="web")  # web | twitter
    matched_query: Mapped[str] = mapped_column(String(512), default="")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Populated once the item has been scored.
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    verdict_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Analysis(Base):
    """An on-demand /verify or /analyze result, kept for the regulator rollup."""

    __tablename__ = "analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="text")  # text|audio|video|verify
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    band: Mapped[str] = mapped_column(String(16), default="Low")
    headline: Mapped[str] = mapped_column(Text, default="")
    claimed_issuer: Mapped[str] = mapped_column(String(255), default="")
    tickers: Mapped[str] = mapped_column(String(512), default="")  # comma-separated
    source: Mapped[str] = mapped_column(String(1024), default="")
    verdict_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        return
    _engine = create_engine(
        get_settings().database_url,
        # FastAPI runs handlers across threads; SQLite's default guard would reject that.
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def session() -> Session:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()


def upsert_content(items: list[dict[str, Any]], channel: str) -> int:
    """Insert scraped items, skipping URLs already stored. Returns the new-row count."""
    if not items:
        return 0
    inserted = 0
    with session() as db:
        for item in items:
            url = (item.get("url") or "").strip()
            if url and db.scalar(select(ContentItem).where(ContentItem.url == url)):
                continue
            db.add(ContentItem(
                url=url,
                headline=item.get("headline", "") or "",
                summary=item.get("summary", "") or "",
                source=item.get("source", "") or "",
                company=item.get("company", "") or "",
                impact=item.get("impact", "") or "",
                official=bool(item.get("official", False)),
                channel=channel,
                matched_query=item.get("matched_query", "") or "",
            ))
            inserted += 1
        db.commit()
    return inserted


def record_analysis(
    kind: str, verdict: Any, claimed_issuer: str = "",
    tickers: list[str] | None = None, source: str = "",
) -> int:
    with session() as db:
        row = Analysis(
            kind=kind,
            risk_score=verdict.risk_score,
            band=verdict.band,
            headline=verdict.headline,
            claimed_issuer=claimed_issuer or "",
            tickers=",".join(tickers or []),
            source=source or "",
            verdict_json=verdict.model_dump_json(),
        )
        db.add(row)
        db.commit()
        return row.id


def list_content(
    limit: int = 50, channel: str | None = None, company: str | None = None,
    min_score: float | None = None,
) -> list[ContentItem]:
    stmt = select(ContentItem).order_by(ContentItem.ingested_at.desc())
    if channel:
        stmt = stmt.where(ContentItem.channel == channel)
    if company:
        stmt = stmt.where(ContentItem.company.ilike(f"%{company}%"))
    if min_score is not None:
        stmt = stmt.where(ContentItem.risk_score >= min_score)
    with session() as db:
        return list(db.scalars(stmt.limit(limit)))


def social_posts_for_graph(limit: int = 500) -> list[dict[str, Any]]:
    """Twitter/X rows shaped for the coordination engine."""
    with session() as db:
        rows = db.scalars(
            select(ContentItem)
            .where(ContentItem.channel == "twitter")
            .order_by(ContentItem.ingested_at.desc())
            .limit(limit)
        )
        return [
            {"url": r.url, "headline": r.headline, "summary": r.summary, "company": r.company}
            for r in rows
        ]


def recent_analyses(limit: int = 100) -> list[Analysis]:
    with session() as db:
        return list(db.scalars(
            select(Analysis).order_by(Analysis.created_at.desc()).limit(limit)
        ))


def update_content_verdict(url: str, verdict: Any) -> None:
    with session() as db:
        row = db.scalar(select(ContentItem).where(ContentItem.url == url))
        if row is None:
            return
        row.risk_score = verdict.risk_score
        row.band = verdict.band
        row.verdict_json = verdict.model_dump_json()
        db.commit()


def dashboard_counts() -> dict[str, Any]:
    """Aggregates backing the broker and regulator dashboards."""
    with session() as db:
        total_content = db.scalar(select(func.count()).select_from(ContentItem)) or 0
        flagged_content = db.scalar(
            select(func.count()).select_from(ContentItem)
            .where(ContentItem.risk_score.is_not(None))
        ) or 0
        analyses = list(db.scalars(select(Analysis)))
    by_band: dict[str, int] = {}
    for a in analyses:
        by_band[a.band] = by_band.get(a.band, 0) + 1
    return {
        "content_items": total_content,
        "scored_content_items": flagged_content,
        "analyses": len(analyses),
        "by_band": by_band,
    }


def load_verdict_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
