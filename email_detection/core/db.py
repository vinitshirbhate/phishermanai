"""Database engine and session management.

SQLite for the hackathon. `DATABASE_URL` overrides it, so pointing at Postgres
is an env-var change and nothing else -- see the portability note in models.py.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.models import Base

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "phishermanai.db"

DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DEFAULT_DB_PATH}"

# check_same_thread=False: FastAPI serves requests on a threadpool and SQLite's
# default thread affinity would reject those connections. Safe here because we
# use one short-lived session per request.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine: Engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
    """WAL + foreign keys. No-op on non-SQLite backends."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables if they do not exist. Idempotent."""
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _add_missing_columns()


# Columns added after the table first shipped. `create_all` only creates missing
# TABLES, never missing columns, so an existing database would keep its old
# `verifications` shape and every gateway insert would fail. Rebuilding with
# --reset would fix it too, but that discards verification history, so we widen
# the table in place instead.
#
# This is a deliberately minimal stand-in for Alembic: additive columns only,
# never a drop or a type change. Anything more complex needs a real migration.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "verifications": [
        ("message_id", "VARCHAR(998)"),
        ("from_addr", "VARCHAR(320)"),
        ("to_addr", "VARCHAR(998)"),
        ("subject_original", "TEXT"),
        ("processed_at", "DATETIME"),
    ],
    "claim_rules": [
        ("safe_context", "TEXT"),
    ],
}


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl_type in columns:
                if name in present:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope. Commits on success, rolls back on exception."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
