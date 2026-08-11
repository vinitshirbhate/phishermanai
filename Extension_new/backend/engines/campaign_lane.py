"""
backend/engines/campaign_lane.py - F-A7 cross-channel campaign correlation.

Links independently-observed events into campaign objects entirely on-device
(NFR-5: no campaign data leaves the machine on the default path).

Correlation rule (§4.3): two or more events sharing >= 2 entities within a
30-day window form a campaign. The >=2 threshold is deliberate - a single shared
entity links everything through a common CDN host or URL shortener and produces
one giant useless cluster.

Resurfacing (F-A7): a campaign whose assets reappear after a takedown-consistent
dormancy (>= 14 days) raises `campaign_resurfaced`.

Campaign ids are deterministic (hash of the seed entity set) so the same inputs
always produce the same id - Date.now()/random are avoided so runs are
reproducible and the evaluation harness can assert on them.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

CORRELATION_WINDOW_DAYS = 30
MIN_SHARED_ENTITIES = 2
DORMANCY_DAYS = 14

# Entity extractors. Kept aligned with securities_identity so the same string
# yields the same entity value in both engines.
_RE = {
    "upi": re.compile(r"\b([a-z0-9.\-_]{2,}@[a-z][a-z0-9.]{1,})\b", re.IGNORECASE),
    "phone": re.compile(r"\b(?:\+91[\-\s]?)?([6-9]\d{9})\b"),
    "domain": re.compile(r"\b((?:[a-z0-9\-]+\.)+(?:com|in|net|org|co|xyz|top|click|shop|site|online))\b",
                         re.IGNORECASE),
    "handle": re.compile(r"(?:^|\s)@([a-z0-9_]{3,32})\b", re.IGNORECASE),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: Optional[str]) -> datetime:
    if not ts:
        return _utc_now()
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return _utc_now()


def extract_entities(text: str = "", url: str = "", reg_numbers: Optional[list[str]] = None,
                     phash: Optional[str] = None, package: Optional[str] = None,
                     group: Optional[str] = None) -> list[dict]:
    """Entity set for one observation. Deduplicated, order-stable."""
    ents: list[tuple[str, str]] = []
    blob = f"{text}\n{url}"
    for etype, rx in _RE.items():
        for m in rx.findall(blob):
            val = (m if isinstance(m, str) else m[0]).lower()
            ents.append((etype, val))
    for n in (reg_numbers or []):
        ents.append(("reg_number", n.upper()))
    if phash:
        ents.append(("phash", phash))
    if package:
        ents.append(("package", package.lower()))
    if group:
        ents.append(("group", group.lower()))
    seen, out = set(), []
    for etype, val in ents:
        key = (etype, val)
        if key in seen:
            continue
        seen.add(key)
        out.append({"entity_type": etype, "entity_value": val})
    return out


def campaign_id_for(entities: list[dict]) -> str:
    """Deterministic id from the seed entity set."""
    key = "|".join(sorted(f"{e['entity_type']}:{e['entity_value']}" for e in entities))
    return "cmp_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class CampaignLane:
    """Correlation over the store's entity_sighting substrate."""

    def __init__(self, store):
        self.store = store

    # --- internals -------------------------------------------------------- #
    def _candidate_observations(self, entities: list[dict], since: datetime) -> dict[int, set]:
        """observation_id -> set of shared (type,value) tuples, within the window."""
        conn = self.store._conn
        hits: dict[int, set] = {}
        for e in entities:
            rows = conn.execute(
                """SELECT es.observation_id, o.observed_at
                   FROM entity_sighting es JOIN observation o ON o.id = es.observation_id
                   WHERE es.entity_type = ? AND es.entity_value = ?""",
                (e["entity_type"], e["entity_value"]),
            ).fetchall()
            for r in rows:
                if _parse(r["observed_at"]) >= since:
                    hits.setdefault(r["observation_id"], set()).add(
                        (e["entity_type"], e["entity_value"]))
        return hits

    def _campaign_of(self, observation_id: int) -> Optional[str]:
        row = self.store._conn.execute(
            "SELECT campaign_id FROM campaign_member WHERE observation_id = ?",
            (observation_id,)).fetchone()
        return row["campaign_id"] if row else None

    # --- public API ------------------------------------------------------- #
    def ingest(self, observation_id: int, entities: list[dict], channel: str,
               observed_at: Optional[str] = None) -> dict:
        """
        Correlate one already-recorded observation. Returns:
        { campaign_id, is_new, resurfaced, dormant_days, shared_entities, event_count }
        """
        conn = self.store._conn
        now = _parse(observed_at)
        since = now - timedelta(days=CORRELATION_WINDOW_DAYS)

        candidates = self._candidate_observations(entities, since)
        candidates.pop(observation_id, None)

        # Prefer an existing campaign reachable through >= MIN_SHARED_ENTITIES.
        linked_campaign, shared = None, set()
        for obs_id, shared_set in sorted(candidates.items(), key=lambda kv: -len(kv[1])):
            if len(shared_set) >= MIN_SHARED_ENTITIES:
                cid = self._campaign_of(obs_id)
                if cid:
                    linked_campaign, shared = cid, shared_set
                    break
                if linked_campaign is None:
                    linked_campaign, shared = ("__new__", shared_set)

        if linked_campaign is None:
            return {"campaign_id": None, "is_new": False, "resurfaced": False,
                    "dormant_days": None, "shared_entities": [], "event_count": 0,
                    "reason": f"fewer than {MIN_SHARED_ENTITIES} shared entities within "
                              f"{CORRELATION_WINDOW_DAYS} days"}

        resurfaced, dormant_days, is_new = False, None, False

        if linked_campaign == "__new__":
            # Seed a campaign from this observation plus the ones it links to.
            members = [observation_id] + [oid for oid, s in candidates.items()
                                          if len(s) >= MIN_SHARED_ENTITIES]
            cid = campaign_id_for(entities)
            first_seen = now
            for oid in members:
                row = conn.execute("SELECT observed_at FROM observation WHERE id = ?", (oid,)).fetchone()
                if row:
                    first_seen = min(first_seen, _parse(row["observed_at"]))
            channels = sorted({r["channel"] for r in conn.execute(
                f"SELECT channel FROM observation WHERE id IN ({','.join('?' * len(members))})",
                members).fetchall()} | {channel})
            conn.execute(
                """INSERT OR REPLACE INTO campaign
                   (id, first_seen, last_seen, channels, entity_count, event_count, resurfaced, dormant_days)
                   VALUES (?,?,?,?,?,?,0,NULL)""",
                (cid, first_seen.isoformat(), now.isoformat(), json.dumps(channels),
                 len(entities), len(members)))
            for oid in members:
                conn.execute("INSERT OR REPLACE INTO campaign_member(campaign_id, observation_id) VALUES (?,?)",
                             (cid, oid))
            is_new = True
        else:
            cid = linked_campaign
            row = conn.execute("SELECT * FROM campaign WHERE id = ?", (cid,)).fetchone()
            last_seen = _parse(row["last_seen"]) if row else now
            gap = (now - last_seen).days
            if gap >= DORMANCY_DAYS:
                resurfaced, dormant_days = True, gap
            chans = set(json.loads(row["channels"])) | {channel} if row else {channel}
            conn.execute(
                """UPDATE campaign SET last_seen = ?, event_count = event_count + 1,
                   channels = ?, resurfaced = ?, dormant_days = ?
                   WHERE id = ?""",
                (max(now, last_seen).isoformat(), json.dumps(sorted(chans)),
                 1 if (resurfaced or (row and row["resurfaced"])) else 0,
                 dormant_days if resurfaced else (row["dormant_days"] if row else None), cid))
            conn.execute("INSERT OR REPLACE INTO campaign_member(campaign_id, observation_id) VALUES (?,?)",
                         (cid, observation_id))

        conn.commit()
        crow = conn.execute("SELECT * FROM campaign WHERE id = ?", (cid,)).fetchone()
        return {"campaign_id": cid, "is_new": is_new, "resurfaced": resurfaced,
                "dormant_days": dormant_days,
                "shared_entities": [f"{t}:{v}" for t, v in sorted(shared)],
                "event_count": crow["event_count"] if crow else 1,
                "channels": json.loads(crow["channels"]) if crow else [channel]}

    def get(self, campaign_id: str) -> Optional[dict]:
        conn = self.store._conn
        row = conn.execute("SELECT * FROM campaign WHERE id = ?", (campaign_id,)).fetchone()
        if not row:
            return None
        members = conn.execute(
            """SELECT o.id, o.observed_at, o.channel, o.surface_id, o.trust_score, o.tier
               FROM campaign_member cm JOIN observation o ON o.id = cm.observation_id
               WHERE cm.campaign_id = ? ORDER BY o.observed_at""", (campaign_id,)).fetchall()
        ents = conn.execute(
            """SELECT DISTINCT es.entity_type, es.entity_value
               FROM campaign_member cm JOIN entity_sighting es ON es.observation_id = cm.observation_id
               WHERE cm.campaign_id = ?""", (campaign_id,)).fetchall()
        c = dict(row)
        c["channels"] = json.loads(c["channels"])
        return {"campaign": c,
                "members": [dict(m) for m in members],
                "entities": [f"{e['entity_type']}:{e['entity_value']}" for e in ents],
                "timeline": [{"at": m["observed_at"], "channel": m["channel"],
                              "surface": m["surface_id"], "tier": m["tier"]} for m in members]}

    def list_campaigns(self, limit: int = 50) -> list[dict]:
        rows = self.store._conn.execute(
            "SELECT * FROM campaign ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["channels"] = json.loads(d["channels"])
            out.append(d)
        return out
