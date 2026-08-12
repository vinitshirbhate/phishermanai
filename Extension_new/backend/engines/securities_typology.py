"""
backend/engines/securities_typology.py - F-A1 securities-aware detection.

Loads the functional typology pack (backend/data/securities_typologies.json) and
matches text against the 9 SEBI-published typology classes. Each match carries a
`source` advisory URL so the sidepanel can show the user *why* and *on whose
authority* (F-A1 / F-C2). Regex compiled once at load.

Note: scam_patterns.yaml is legacy and not loaded by any engine; this JSON pack
is the live source (PyYAML is intentionally not a dependency - NFR-9).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=1)
def _pack() -> list[dict]:
    doc = json.loads((DATA / "securities_typologies.json").read_text(encoding="utf-8"))
    out = []
    for t in doc["typologies"]:
        out.append({
            "id": t["id"],
            "weight": int(t["weight"]),
            "source": t.get("source", ""),
            "regexes": [re.compile(p) for p in t.get("patterns", [])],
            "keywords": [k.lower() for k in t.get("keywords", [])],
            "keywords_hi": t.get("keywords_hi", []),
        })
    return out


def match_typologies(text: str) -> list[dict]:
    """Return matched typology classes, worst-weight first. Each dict:
    { id, weight, source, matched_on: 'pattern'|'keyword', cue }"""
    low = (text or "").lower()
    matches = []
    for t in _pack():
        cue = None
        matched_on = None
        for rx in t["regexes"]:
            m = rx.search(text or "")
            if m:
                cue, matched_on = m.group(0)[:80], "pattern"
                break
        if not matched_on:
            hit = next((k for k in t["keywords"] if k in low), None)
            if hit is None:
                hit = next((k for k in t["keywords_hi"] if k in (text or "")), None)
            if hit:
                cue, matched_on = hit, "keyword"
        if matched_on:
            matches.append({
                "id": t["id"], "weight": t["weight"], "source": t["source"],
                "matched_on": matched_on, "cue": cue,
            })
    matches.sort(key=lambda m: m["weight"], reverse=True)
    return matches


def combined_penalty(matches: list[dict]) -> int:
    """Total trust penalty from matched typologies (F-A1 combined-verdict rule)."""
    return sum(m["weight"] for m in matches)
