"""
backend/engines/behavior_lane.py - behavioural analysis for messaging surfaces.

WHY THIS EXISTS, separate from manipulation_detector.py:

    manipulation_detector targets e-commerce dark patterns on web PAGES - cookie
    banners, countdown timers, fake reviews, subscription traps. Run it over a
    WhatsApp recruitment scam and it scores 0, because that message contains none
    of those things. It is not the wrong engine; it is an engine for a different
    surface.

    This lane asks the message-shaped question instead: what is this text DOING to
    the reader? How does it open, what does it promise, what does it ask for first,
    and how does it escalate? Those are tactics, not topics - which is why a
    message can carry no scam keyword at all and still be structurally a scam.

WHY REGEX AND NOT KEYWORD SUBSTRINGS:

    The substring lists in scam_signals.json are matched with `k in text`. That
    misses ordinary grammatical variation, and the misses are silent:

        "work from home"  does not match  "working from home"
        "joining fee"     does not match  "joining bonus"
        "rating task"     does not match  "give positive ratings"
        "earn daily"      does not match  "earn 1500 to 5000 rupees per day"

    A real task-scam message hit ZERO of the 24 keyword categories and scored 92
    (SAFE) as a result. Patterns here are anchored on message grammar instead.

SCORING PHILOSOPHY:

    Individual tactics are weak evidence and are weighted accordingly - plenty of
    honest messages contain urgency or a cold introduction. The signal is in
    CO-OCCURRENCE: a specific payout figure attached to trivial work is a
    structure, not a phrase, and that structure is what `combos` scores.

    Fail-open: any error returns an empty, non-accusatory result. A behavioural
    engine that crashes must never be the reason a page is called dangerous.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("phisherman.behavior_lane")

DATA = Path(__file__).resolve().parents[1] / "data"

# A tactic sheet this dense will always find *something* in a long web page, so
# the trust penalty is capped PER BAND rather than by one flat ceiling.
#
# The point of the per-band cap: a single weak tactic must never move a page far
# (ordinary marketing trips "act now" all day), while a message carrying several
# reinforcing tactics plus a combo is a recognised playbook and should be allowed
# to drive the verdict on its own. A flat cap gave both the same headroom and let
# a textbook task scam settle at merely "suspicious".
BAND_PENALTY_CAP = {
    "none": 10,
    "weak": 15,
    "moderate": 35,
    "strong": 50,
    "severe": 65,
}
PENALTY_RATE = 0.65


@dataclass
class BehaviorResult:
    behavior_score: int                       # 0-100, higher = more manipulative
    band: str                                 # none | weak | moderate | strong | severe
    band_note: str
    tactics: list[dict] = field(default_factory=list)   # {id,label,explain,severity,weight,cue}
    combos: list[dict] = field(default_factory=list)    # {id,explain,bonus,requires}
    narrative: str = ""                       # one-paragraph plain-English read
    trust_penalty: int = 0                    # subtract from a 100 trust baseline

    def to_dict(self) -> dict:
        return {
            "behavior_score": self.behavior_score,
            "band": self.band,
            "band_note": self.band_note,
            "tactics": self.tactics,
            "combos": self.combos,
            "narrative": self.narrative,
            "trust_penalty": self.trust_penalty,
        }


@lru_cache(maxsize=1)
def _pack() -> dict:
    doc = json.loads((DATA / "behavior_tactics.json").read_text(encoding="utf-8"))
    tactics = []
    for t in doc["tactics"]:
        tactics.append({
            "id": t["id"],
            "label": t["label"],
            "explain": t["explain"],
            "weight": int(t["weight"]),
            "severity": t.get("severity", "medium"),
            "regexes": [re.compile(p) for p in t.get("patterns", [])],
        })
    return {
        "tactics": tactics,
        "combos": doc.get("combos", []),
        "bands": sorted(doc.get("bands", []), key=lambda b: int(b["min"]), reverse=True),
        "meta": doc.get("meta", {}),
    }


def _band(score: int) -> tuple[str, str]:
    for b in _pack()["bands"]:
        if score >= int(b["min"]):
            return b["label"], b.get("note", "")
    return "none", ""


def analyze(text: str) -> BehaviorResult:
    """Behavioural read of a message or page. Never raises."""
    try:
        return _analyze_inner(text)
    except Exception as e:  # pragma: no cover - fail-open guard
        logger.error("Behaviour analysis error (fail-open): %s", e)
        return BehaviorResult(behavior_score=0, band="none", band_note="",
                              narrative="Behavioural analysis unavailable for this message.")


def _analyze_inner(text: str) -> BehaviorResult:
    raw = (text or "").strip()
    if not raw:
        return BehaviorResult(behavior_score=0, band="none", band_note="")

    # Long pages: behaviour is about the message, not the boilerplate.
    raw = raw[:20000]

    pack = _pack()
    found: list[dict] = []
    total = 0

    for t in pack["tactics"]:
        cue = None
        for rx in t["regexes"]:
            m = rx.search(raw)
            if m:
                cue = " ".join(m.group(0).split())[:100]
                break
        if cue is None:
            continue
        found.append({
            "id": t["id"],
            "label": t["label"],
            "explain": t["explain"],
            "severity": t["severity"],
            "weight": t["weight"],
            "cue": cue,
        })
        total += t["weight"]

    hit_ids = {f["id"] for f in found}
    combos_hit: list[dict] = []
    for c in pack["combos"]:
        req = c.get("requires", [])
        if req and all(r in hit_ids for r in req):
            combos_hit.append({
                "id": c["id"],
                "requires": req,
                "bonus": int(c["bonus"]),
                "explain": c["explain"],
            })
            total += int(c["bonus"])

    score = max(0, min(100, total))
    band, note = _band(score)

    # Worst first, so the sidepanel truncation keeps what matters.
    order = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda f: (order.get(f["severity"], 3), -f["weight"]))
    combos_hit.sort(key=lambda c: -c["bonus"])

    penalty = min(BAND_PENALTY_CAP.get(band, 35), round(score * PENALTY_RATE))

    return BehaviorResult(
        behavior_score=score,
        band=band,
        band_note=note,
        tactics=found,
        combos=combos_hit,
        narrative=_narrative(found, combos_hit, score, band),
        trust_penalty=int(penalty),
    )


def _narrative(tactics: list[dict], combos: list[dict], score: int, band: str) -> str:
    """Plain-English read. Describes what the message DOES, never who sent it."""
    if not tactics:
        return ("No recognised social-engineering structure in this text. That is not the "
                "same as safe — it means the persuasion tactics this lane looks for are absent.")

    labels = [t["label"].lower() for t in tactics[:3]]
    if len(labels) == 1:
        tactic_str = labels[0]
    elif len(labels) == 2:
        tactic_str = f"{labels[0]} and {labels[1]}"
    else:
        tactic_str = f"{labels[0]}, {labels[1]} and {labels[2]}"

    parts = [f"Behaviourally this reads as {tactic_str}."]

    if combos:
        parts.append(combos[0]["explain"])

    if band in ("strong", "severe"):
        parts.append(
            "Tactics like these reinforce each other, which is why the combination scores "
            "higher than any single one of them. Treat any request for money, documents or "
            "an OTP that follows as the actual objective."
        )
    elif band == "moderate":
        parts.append(
            "Individually these are common persuasive devices; together in an unrequested "
            "message they are worth pausing over. Verify the sender through a channel you "
            "chose yourself, not one they gave you."
        )
    else:
        parts.append(
            "This is weak evidence on its own and appears in ordinary marketing too."
        )

    return " ".join(parts)


def top_signals(result: BehaviorResult, limit: int = 4) -> list[str]:
    """Signal strings for the extension's flat signal list."""
    return [f"[behaviour] {t['label']}" for t in result.tactics[:limit]]
