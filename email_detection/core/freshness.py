"""Corpus freshness: how old our reference data is, and what that forbids.

WHY THIS EXISTS
---------------
Every verdict is a comparison against local data with a known end date. Most of
the time staleness is harmless, because it fails safe: if yesterday's dividend
filing is not in the corpus, the matcher finds nothing and the verdict is
UNVERIFIED. Missing data cannot manufacture a false GENUINE.

There is exactly one dangerous case, and it is the reason this module exists.

    A company revises a dividend from Rs 4 to Rs 5. We hold the old filing.
    A genuine new circular arrives quoting Rs 5. We compare it against the
    superseded record and report TAMPERED.

That is a confident false accusation against a real document -- the worst
failure this system can produce, and worse than any miss. Two guards prevent it:

  1. NEVER ACCUSE ACROSS THE DATA HORIZON. If the document is dated after our
     corpus ends, we cannot know whether a newer filing exists, so a mismatch
     is not evidence of tampering.
  2. NEVER ACCUSE ON AN AMENDED FILING. If the matched filing was later
     corrected, the mismatch may be with the correction, not the document.

Both downgrade to UNVERIFIED with an explanation. Neither ever upgrades
anything -- freshness can only make us more cautious, never more confident.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache"

# Beyond this the UI shows a staleness banner. Corporate actions are announced
# daily, so a corpus more than a few days old is materially incomplete.
STALE_AFTER_DAYS = 3

# Announcement wording that marks a filing as superseded or corrected.
AMENDMENT_MARKERS = (
    "corrigendum", "corrigenda", "revised", "revision", "amended", "amendment",
    "modification", "modified", "supersede", "superseded", "in supersession",
    "addendum", "rectification", "erratum",
)


@dataclass
class SourceStatus:
    name: str
    as_of: datetime | None
    rows: int = 0
    last_ok: str | None = None
    error: str | None = None

    @property
    def age_days(self) -> int | None:
        if self.as_of is None:
            return None
        return (datetime.now() - self.as_of).days

    @property
    def stale(self) -> bool:
        age = self.age_days
        return age is not None and age > STALE_AFTER_DAYS

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.name,
            "as_of": self.as_of.isoformat(timespec="seconds") if self.as_of else None,
            "rows": self.rows,
            "age_days": self.age_days,
            "stale": self.stale,
            "error": self.error,
        }


def _cache_retrieved_at(filename: str) -> datetime | None:
    path = CACHE_DIR / filename
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    stamp = payload.get("retrieved_at") if isinstance(payload, dict) else None
    if stamp:
        try:
            return datetime.fromisoformat(str(stamp))
        except ValueError:
            pass
    # Fall back to the file's own mtime, which is when we last wrote it.
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def corpus_status() -> dict[str, SourceStatus]:
    """Freshness per source. Never raises -- an unknown age is reported as None."""
    from sqlalchemy import func, select

    from core.db import session_scope
    from core.models import Entity, Filing

    statuses: dict[str, SourceStatus] = {}

    # BSE filings: the source that decays fastest and matters most.
    try:
        with session_scope() as session:
            rows = session.scalar(select(func.count()).select_from(Filing)) or 0
            newest = session.scalar(select(func.max(Filing.filing_date)))
            scraped = session.scalar(select(func.max(Filing.scraped_at)))
        statuses["bse_filings"] = SourceStatus(
            name="BSE corporate filings",
            # `as_of` is when we last COLLECTED, not the newest filing date --
            # an empty trading day must not read as a stale corpus.
            as_of=scraped or newest, rows=rows,
            last_ok=newest.isoformat(timespec="seconds") if newest else None,
        )
    except Exception as exc:  # noqa: BLE001
        statuses["bse_filings"] = SourceStatus("BSE corporate filings", None, error=str(exc)[:120])

    try:
        with session_scope() as session:
            reg = session.scalar(
                select(func.count()).select_from(Entity).where(Entity.sebi_reg_no.is_not(None))
            ) or 0
        statuses["sebi_registry"] = SourceStatus(
            name="SEBI intermediary registers",
            as_of=_cache_retrieved_at("sebi_intermediaries.json"), rows=reg,
        )
    except Exception as exc:  # noqa: BLE001
        statuses["sebi_registry"] = SourceStatus("SEBI intermediary registers", None, error=str(exc)[:120])

    return statuses


def data_horizon() -> date | None:
    """The date after which we hold no filing data at all."""
    status = corpus_status().get("bse_filings")
    return status.as_of.date() if status and status.as_of else None


def document_postdates_corpus(document_date: date | datetime | None) -> bool:
    """Is this document newer than everything we hold?

    A mismatch against a corpus that ends before the document was written is
    not evidence of tampering -- it is evidence that we are looking at the
    wrong filing, or at no filing at all.
    """
    if document_date is None:
        return False
    if isinstance(document_date, datetime):
        document_date = document_date.date()
    horizon = data_horizon()
    if horizon is None:
        return False
    # One day of slack: a filing collected at 18:00 legitimately precedes a
    # document written later the same evening.
    return document_date > horizon + timedelta(days=1)


def filing_is_amended(filing) -> bool:
    """Is this filing itself a correction of an earlier one?

    HEADLINE ONLY, deliberately. Scanning the body text as well suppressed
    almost every tamper accusation in the corpus -- tamper recall fell from 70%
    to 0% -- because words like "revised" and "modification" appear routinely in
    the body of ordinary BSE announcements. A corrigendum announces itself in
    its subject line; the body of a normal filing does not.
    """
    if filing is None:
        return False
    headline = str(getattr(filing, "headline", "") or "").lower()
    return any(marker in headline for marker in AMENDMENT_MARKERS)


# A corrigendum follows its original closely. Beyond this window a later filing
# using the same words is a different corporate action, not a correction.
AMENDMENT_WINDOW_DAYS = 60


def has_later_amendment(filing) -> bool:
    """Does a corrigendum for THIS filing exist?

    Three constraints, all needed to avoid suppressing genuine tamper findings:
    the same company, the same filing type, and inside a short window. Without
    the type and window constraints, any company that ever published a "revised"
    anything made every one of its documents unaccusable.
    """
    if filing is None or not filing.filing_date:
        return False
    try:
        from datetime import timedelta as _td

        from sqlalchemy import select

        from core.db import session_scope
        from core.models import Filing

        with session_scope() as session:
            candidates = session.execute(
                select(Filing)
                .where(Filing.company_name == filing.company_name)
                .where(Filing.filing_type == filing.filing_type)
                .where(Filing.filing_date > filing.filing_date)
                .where(Filing.filing_date <= filing.filing_date + _td(days=AMENDMENT_WINDOW_DAYS))
                .limit(40)
            ).scalars().all()
        return any(filing_is_amended(c) for c in candidates)
    except Exception:  # noqa: BLE001 - a lookup failure must not block a verdict
        return False


def summary() -> dict[str, Any]:
    """Freshness block attached to every verdict."""
    statuses = corpus_status()
    return {
        "sources": {key: status.to_dict() for key, status in statuses.items()},
        "data_as_of": (
            statuses["bse_filings"].as_of.isoformat(timespec="seconds")
            if statuses.get("bse_filings") and statuses["bse_filings"].as_of else None
        ),
        "any_stale": any(status.stale for status in statuses.values()),
        "stale_after_days": STALE_AFTER_DAYS,
    }
