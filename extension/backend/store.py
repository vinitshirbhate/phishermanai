"""
backend/store.py - local SQLite persistence (todo.md §2, task 0.6).

Stdlib `sqlite3` only. One file, WAL mode, no ORM, no migration framework.
The schema is versioned in `schema_version`. This DB is LOCAL, on the user's
machine - NFR-5: no server-side persistence on the consumer path.

Retention (todo.md §2): observation + entity_sighting are capped at 500 rows /
90 days, whichever binds first, and are user-clearable. evidence_packet is
retained until the user deletes it.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "backend" / "data" / "phisherman.db"

SCHEMA_VERSION = 1

RETENTION_MAX_ROWS = 500
RETENTION_MAX_DAYS = 90

SCHEMA = """
CREATE TABLE IF NOT EXISTS registry_meta (
  source        TEXT PRIMARY KEY,
  source_url    TEXT NOT NULL,
  fetched_at    TEXT NOT NULL,
  record_count  INTEGER NOT NULL,
  licence       TEXT,
  sha256        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intermediary (
  reg_number      TEXT PRIMARY KEY,
  reg_prefix      TEXT NOT NULL,
  registered_name TEXT NOT NULL,
  name_normalised TEXT NOT NULL,
  category        TEXT NOT NULL,
  status          TEXT NOT NULL,
  website         TEXT,
  valid_upi       TEXT
);
CREATE INDEX IF NOT EXISTS idx_interm_name ON intermediary(name_normalised);
CREATE INDEX IF NOT EXISTS idx_interm_prefix ON intermediary(reg_prefix);

CREATE TABLE IF NOT EXISTS official_domain (
  domain      TEXT PRIMARY KEY,
  entity      TEXT NOT NULL,
  entity_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS upi_namespace (
  suffix         TEXT PRIMARY KEY,
  psp_bank       TEXT NOT NULL,
  category_codes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  observed_at    TEXT NOT NULL,
  channel        TEXT NOT NULL,
  surface_id     TEXT,
  content_sha256 TEXT NOT NULL,
  trust_score    INTEGER NOT NULL,
  tier           TEXT NOT NULL,
  layer          TEXT NOT NULL,
  model_version  TEXT,
  p_phishing     REAL,
  latency_ms     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_obs_time ON observation(observed_at);
CREATE INDEX IF NOT EXISTS idx_obs_hash ON observation(content_sha256);

CREATE TABLE IF NOT EXISTS entity_sighting (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  observation_id INTEGER NOT NULL REFERENCES observation(id) ON DELETE CASCADE,
  entity_type    TEXT NOT NULL,
  entity_value   TEXT NOT NULL,
  first_seen     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ent_lookup ON entity_sighting(entity_type, entity_value);

CREATE TABLE IF NOT EXISTS reason_code (
  observation_id INTEGER NOT NULL REFERENCES observation(id) ON DELETE CASCADE,
  code           TEXT NOT NULL,
  weight         INTEGER NOT NULL,
  source_url     TEXT,
  PRIMARY KEY (observation_id, code)
);

CREATE TABLE IF NOT EXISTS identity_assessment (
  observation_id   INTEGER PRIMARY KEY REFERENCES observation(id) ON DELETE CASCADE,
  reg_claimed      TEXT,
  reg_state        TEXT NOT NULL,
  reg_resolved_to  TEXT,
  name_match_score INTEGER,
  upi_claimed      TEXT,
  upi_state        TEXT,
  provenance_state TEXT,
  register_as_of   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign (
  id           TEXT PRIMARY KEY,
  first_seen   TEXT NOT NULL,
  last_seen    TEXT NOT NULL,
  channels     TEXT NOT NULL,
  entity_count INTEGER NOT NULL,
  event_count  INTEGER NOT NULL,
  resurfaced   INTEGER NOT NULL DEFAULT 0,
  dormant_days INTEGER
);

CREATE TABLE IF NOT EXISTS campaign_member (
  campaign_id    TEXT NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
  observation_id INTEGER NOT NULL REFERENCES observation(id) ON DELETE CASCADE,
  PRIMARY KEY (campaign_id, observation_id)
);

CREATE TABLE IF NOT EXISTS evidence_packet (
  id             TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,
  observation_id INTEGER REFERENCES observation(id),
  campaign_id    TEXT REFERENCES campaign(id),
  packet_json    TEXT NOT NULL,
  signature      TEXT NOT NULL,
  key_id         TEXT NOT NULL,
  exported       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS impersonation_alert (
  id                    TEXT PRIMARY KEY,
  created_at            TEXT NOT NULL,
  reg_number            TEXT NOT NULL,
  legitimate_holder     TEXT NOT NULL,
  impersonating_handles TEXT NOT NULL,
  content_hashes        TEXT NOT NULL,
  status                TEXT NOT NULL DEFAULT 'prepared'
);

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Thread-safe-ish SQLite wrapper. One connection guarded by a lock."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # --- schema ---
    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            row = self._conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            if row is None or row["v"] is None:
                self._conn.execute(
                    "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _utc_now()),
                )
            self._conn.commit()

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        return int(row["v"]) if row and row["v"] is not None else 0

    # --- reference-data loading (from bundled snapshots) ---
    def load_reference_data(
        self,
        sebi_register: Optional[dict] = None,
        upi_namespace: Optional[dict] = None,
        official_domains: Optional[dict] = None,
    ) -> dict[str, int]:
        """Idempotently load bundled snapshots into the reference tables."""
        counts = {}
        with self._lock:
            cur = self._conn.cursor()
            if sebi_register:
                meta = sebi_register.get("registry_meta", {})
                self._upsert_meta(cur, meta)
                for rec in sebi_register.get("intermediaries", []):
                    cur.execute(
                        """INSERT OR REPLACE INTO intermediary
                           (reg_number, reg_prefix, registered_name, name_normalised,
                            category, status, website, valid_upi)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        # `website` now carries domain_anchor: the real SEBI register
                        # publishes no website column, so the registrant's non-free
                        # e-mail domain is the identity anchor.
                        (rec["reg_number"], rec["reg_prefix"], rec["registered_name"],
                         rec["name_normalised"], rec["category"], rec["status"],
                         rec.get("domain_anchor") or rec.get("website"),
                         rec.get("valid_upi")),
                    )
                counts["intermediary"] = len(sebi_register.get("intermediaries", []))
            if upi_namespace:
                self._upsert_meta(cur, upi_namespace.get("registry_meta", {}))
                for s in upi_namespace.get("namespace_suffixes", []):
                    cur.execute(
                        "INSERT OR REPLACE INTO upi_namespace(suffix, psp_bank, category_codes) VALUES (?,?,?)",
                        (s["suffix"], s["psp_bank"], s["category_codes"]),
                    )
                counts["upi_namespace"] = len(upi_namespace.get("namespace_suffixes", []))
            if official_domains:
                self._upsert_meta(cur, official_domains.get("registry_meta", {}))
                rows = official_domains.get("regulator_and_mii", []) + official_domains.get("recovery_rails", [])
                for d in rows:
                    cur.execute(
                        "INSERT OR REPLACE INTO official_domain(domain, entity, entity_type) VALUES (?,?,?)",
                        (d["domain"], d["entity"], d["entity_type"]),
                    )
                counts["official_domain"] = len(rows)
            self._conn.commit()
        return counts

    @staticmethod
    def _upsert_meta(cur: sqlite3.Cursor, meta: dict) -> None:
        if not meta or "source" not in meta:
            return
        cur.execute(
            """INSERT OR REPLACE INTO registry_meta
               (source, source_url, fetched_at, record_count, licence, sha256)
               VALUES (?,?,?,?,?,?)""",
            (meta["source"], meta.get("source_url", ""), meta.get("fetched_at", ""),
             int(meta.get("record_count", 0)), meta.get("licence", ""),
             meta.get("sha256", "")),
        )

    def registry_meta(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM registry_meta ORDER BY source").fetchall()
        return [dict(r) for r in rows]

    # --- observations & correlation substrate ---
    def record_observation(self, obs: dict, entities: Optional[list[dict]] = None,
                           reasons: Optional[list[dict]] = None,
                           identity: Optional[dict] = None) -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """INSERT INTO observation
                   (observed_at, channel, surface_id, content_sha256, trust_score,
                    tier, layer, model_version, p_phishing, latency_ms)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (obs.get("observed_at") or _utc_now(), obs["channel"], obs.get("surface_id"),
                 obs["content_sha256"], int(obs["trust_score"]), obs["tier"], obs["layer"],
                 obs.get("model_version"), obs.get("p_phishing"), obs.get("latency_ms")),
            )
            oid = int(cur.lastrowid)
            now = _utc_now()
            for e in (entities or []):
                cur.execute(
                    """INSERT INTO entity_sighting(observation_id, entity_type, entity_value, first_seen)
                       VALUES (?,?,?,?)""",
                    (oid, e["entity_type"], e["entity_value"], e.get("first_seen") or now),
                )
            for rc in (reasons or []):
                cur.execute(
                    """INSERT OR REPLACE INTO reason_code(observation_id, code, weight, source_url)
                       VALUES (?,?,?,?)""",
                    (oid, rc["code"], int(rc.get("weight", 0)), rc.get("source_url")),
                )
            if identity:
                cur.execute(
                    """INSERT OR REPLACE INTO identity_assessment
                       (observation_id, reg_claimed, reg_state, reg_resolved_to, name_match_score,
                        upi_claimed, upi_state, provenance_state, register_as_of)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (oid, identity.get("reg_claimed"), identity["reg_state"],
                     identity.get("reg_resolved_to"), identity.get("name_match_score"),
                     identity.get("upi_claimed"), identity.get("upi_state"),
                     identity.get("provenance_state"), identity.get("register_as_of", now)),
                )
            self._conn.commit()
            self._enforce_retention(cur)
            self._conn.commit()
            return oid

    def handles_for_reg_number(self, reg_number: str) -> list[str]:
        """Distinct surface_ids that have claimed a given registration number
        (collision substrate for F-B1)."""
        rows = self._conn.execute(
            """SELECT DISTINCT o.surface_id
               FROM entity_sighting e JOIN observation o ON o.id = e.observation_id
               WHERE e.entity_type = 'reg_number' AND e.entity_value = ? AND o.surface_id IS NOT NULL""",
            (reg_number,),
        ).fetchall()
        return [r["surface_id"] for r in rows]

    def _enforce_retention(self, cur: sqlite3.Cursor) -> None:
        cur.execute(
            "DELETE FROM observation WHERE observed_at < datetime('now', ?)",
            (f"-{RETENTION_MAX_DAYS} days",),
        )
        cur.execute(
            """DELETE FROM observation WHERE id IN (
                 SELECT id FROM observation ORDER BY id DESC LIMIT -1 OFFSET ?
               )""",
            (RETENTION_MAX_ROWS,),
        )

    def clear_observations(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM observation")
            self._conn.commit()

    def counts(self) -> dict[str, int]:
        out = {}
        for t in ("intermediary", "official_domain", "upi_namespace",
                  "observation", "entity_sighting", "campaign", "evidence_packet"):
            out[t] = self._conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
