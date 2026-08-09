"""
backend/engines/context_gate.py - one definition of "is this actually evidence?"

WHY THIS MODULE EXISTS

    Two engines run the same keyword lists over page text: `scamgate.L0PatternDetector`
    and the legacy `scam_detector`. Both had the same defect, and fixing it in one
    left the other broken - `/api/analyze/page` (the path ordinary web pages take)
    routes through trust_engine, which uses BOTH. So the gate lives here once and
    both call in.

THE DEFECT IT CORRECTS

    scam_signals.json holds bare ENTITY names ("sebi", "rbi", "police", "sbi") and
    bare TOPIC words ("kyc", "otp", "investment", "pay", "upi", "payment"). They
    were substring-matched against page text, which means:

        MENTIONING the regulator scored as IMPERSONATING it.

    Measured before the fix: a Google results page for the query "sebi" scored
    21/100 DANGER - +25 for the word "sebi", +30 for "kyc", +24 for linking to
    three domains absent from a 26-entry whitelist. SEBI's own site tripped the
    same wires, as did any bank page ("bank account", "kyc", "pay") and any
    checkout page ("pay", "payment", "upi").

THE RULE

    An entity or a topic is not evidence. An entity or topic PLUS an act is.

    "RBI" is a noun. "RBI has frozen your account, pay now" is something being
    done to the reader. Gated tokens score only when a corroborating act pattern
    is present. Multi-word phrases that already contain the act ("share your otp",
    "digital arrest", "account will be closed") are never gated - they carry their
    own evidence.

    This is the same principle the behavioural lane uses for combos, and the same
    one the project's own thesis rests on: look for what must be there, not for
    words that merely sound alarming.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("phisherman.context_gate")

DATA = Path(__file__).resolve().parents[1] / "data"

# Which act group guards which keyword category.
GATE_FOR_CATEGORY = {
    "authority_impersonation": "impersonation_act",
    "financial_triggers": "credential_act",
    "money_ask": "payment_pressure_act",
    "pii_request": "credential_act",
}

# Categories whose presence is hard evidence, exempt from the corroboration cap.
HARD_EVIDENCE = {"scam_domain", "phishing_domain", "behavioral_manipulation"}


@lru_cache(maxsize=1)
def _pack() -> dict:
    try:
        doc = json.loads((DATA / "context_gates.json").read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("context_gates.json unreadable (%s) — gating disabled", e)
        return {"tokens": {}, "acts": {}, "cap": 100}
    return {
        "tokens": {
            g: {k.lower() for k in toks}
            for g, toks in doc.get("gated_tokens", {}).items()
            if not g.startswith("_")
        },
        "acts": {
            g: [re.compile(p) for p in pats]
            for g, pats in doc.get("acts", {}).items()
            if not g.startswith("_")
        },
        "cap": int(doc.get("corroboration", {}).get("single_category_max_score", 35)),
    }


def act_present(group: str, text: str) -> bool:
    """Is something being DONE TO the reader, or is this merely the topic?"""
    return any(rx.search(text or "") for rx in _pack()["acts"].get(group, []))


def should_score(category: str, matched_keywords: list[str], text: str) -> bool:
    """
    True if this category's match is real evidence.

    False only when EVERY keyword that matched is a bare entity/topic token AND
    no corroborating act appears in the text. A single ungated phrase in the
    match list is enough to let the category through.
    """
    gate = GATE_FOR_CATEGORY.get(category)
    if not gate:
        return True
    gated = _pack()["tokens"].get(gate, set())
    if not all(k.lower() in gated for k in matched_keywords):
        return True          # at least one self-evidencing phrase matched
    return act_present(gate, text)


def single_category_cap() -> int:
    return _pack()["cap"]


def apply_corroboration_cap(score: int, categories: list[str]) -> tuple[int, str | None]:
    """
    Real fraud leaves more than one kind of trace: a tactic, a blocklisted host, a
    payment handle, a registration mismatch. One keyword category with nothing
    behind it is thin, and must not reach DANGER alone.

    Returns (score, note_or_None). CAUTION is still shown - it is the accusation
    that gets withheld, not the warning.
    """
    cap = single_category_cap()
    if score <= cap:
        return score, None
    hard = any(c in HARD_EVIDENCE for c in categories) or any(
        c.startswith("feed:") for c in categories
    )
    keyword_cats = [
        c for c in categories if c not in HARD_EVIDENCE and not c.startswith("feed:")
    ]
    if len(keyword_cats) <= 1 and not hard:
        return cap, "Single weak indicator — not enough corroboration to call this fraud"
    return score, None
