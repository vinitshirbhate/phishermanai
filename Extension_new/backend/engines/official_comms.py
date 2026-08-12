"""
official_comms.py - "Did SEBI actually say this?"

THE GAP THIS FILLS
-------------------
The problem statement names it precisely: there are limited mechanisms to
verify that a communication purportedly from SEBI, an exchange, a listed
company, or a registered intermediary is genuine, and that absence
compounds the harm from synthetic media.

Everything else in this codebase authenticates the SENDER - is INA000017523
a real registration, does this domain belong to that registrant, is this
UPI handle in the @valid namespace. None of it authenticates the MESSAGE.
A fabricated "SEBI circular" PDF, a fake exchange notice, an invented
press release quoting the Chairperson - these pass every sender check we
have, because they never claim to come from a registered intermediary at
all. They claim to come from the regulator.

The approach, borrowed in shape from the SEBI circular-monitoring work in
aditya8975/compliance-agent (MIT), inverts what that project does with the
corpus. That agent scrapes circulars to extract obligations for compliance
teams - a RegTech use. The same corpus, indexed by circular number, date,
title and content hash, is an AUTHENTICITY ORACLE: a claimed circular that
does not appear in the regulator's own published index is a claim with no
referent, and one that does appear can be diffed against the real text.

WHAT THIS DOES AND DOES NOT ASSERT
------------------------------------
    matched_exact     the cited reference exists in the official index and
                      the content hash agrees. The strongest statement
                      available: this is the real document.
    matched_reference the reference exists, but the text in front of the
                      user differs from the published text. Worth showing
                      the diff. NOT automatically "forged" - quoting,
                      excerpting and reformatting all produce this.
    not_in_index      no such reference in the official index. This is the
                      state that catches an invented circular number, and
                      it is deliberately bounded: see `coverage` on every
                      response. An index that only goes back to 2024 cannot
                      speak to a 2019 circular, and says so rather than
                      calling it fake.
    no_claim          nothing here purports to be an official communication.
    index_unavailable the index has not been built or refreshed.

`not_in_index` is the only adverse state and even it is worded as an
absence, not an accusation - consistent with the rule this codebase
already applies to missing registrations.

REFRESH
-------
scripts/refresh_official_comms.py builds the index from SEBI's own
published listings. Until it is run the module answers
`index_unavailable`, which is honest, rather than answering `not_in_index`
for everything, which would be catastrophic - it would flag every genuine
circular as unverifiable-therefore-suspect.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("phisherman.official_comms")

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"
INDEX_PATH = DATA_DIR / "official_comms_index.json"

# SEBI circular / press-release reference formats. Derived from SEBI's own
# published numbering rather than invented: circulars carry a slashed path
# beginning SEBI/HO/<department>/..., press releases are "PR No. NN/YYYY".
_CIRCULAR_RE = re.compile(
    r"\bSEBI\s*/\s*(?:HO|LAD|MRD|CFD|IMD|DDHS)\s*/\s*[A-Z0-9\-]+"
    r"(?:\s*/\s*[A-Z0-9\-]+){1,5}\b", re.IGNORECASE)
_PR_RE = re.compile(r"\bPR\s*(?:No\.?)?\s*[:\-]?\s*(\d{1,3}\s*/\s*20\d{2})\b",
                    re.IGNORECASE)
_MASTER_RE = re.compile(r"\bmaster\s+circular\b", re.IGNORECASE)

# Phrases that assert regulatory origin. Presence of one of these WITHOUT a
# resolvable reference is the interesting case: official communications cite
# themselves, impersonations frequently do not.
_AUTHORITY_CLAIM_RE = re.compile(
    r"\b(?:issued\s+by\s+SEBI|SEBI\s+has\s+(?:issued|directed|ordered|mandated)"
    r"|as\s+per\s+SEBI\s+(?:circular|guidelines|regulations)"
    r"|SEBI\s+notification|regulatory\s+directive"
    r"|by\s+order\s+of\s+the\s+(?:Board|Chairperson))\b", re.IGNORECASE)

COMMS_DELTA = {
    "matched_exact": +25,
    "matched_reference": 0,
    "no_claim": 0,
    "index_unavailable": 0,
    "not_in_index": -30,
}


@dataclass
class CommsVerdict:
    state: str
    trust_delta: int = 0
    claims: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    index_as_of: Optional[str] = None
    disclosure: str = (
        "This checks whether a cited official reference exists in the "
        "regulator's own published index. It does not and cannot confirm "
        "that any particular sender is authorised to forward it."
    )


_index_cache: Optional[dict] = None


def _index() -> dict:
    global _index_cache
    if _index_cache is None:
        try:
            _index_cache = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            _index_cache = {}
    return _index_cache


def reload_index() -> None:
    global _index_cache
    _index_cache = None


def normalise_reference(ref: str) -> str:
    """Whitespace and case are not semantic in a circular number."""
    return re.sub(r"\s+", "", (ref or "")).upper().strip("/")


def content_hash(text: str) -> str:
    """
    Hash of the normalised body. Collapses whitespace and strips punctuation
    so that a PDF-to-text round trip, a re-flow, or a copy-paste does not
    change the hash - only the words changing changes it.
    """
    norm = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def extract_claims(text: str) -> list:
    """Pull every official-communication reference out of free text."""
    out, seen = [], set()
    for m in _CIRCULAR_RE.finditer(text or ""):
        ref = normalise_reference(m.group(0))
        if ref not in seen:
            seen.add(ref)
            out.append({"kind": "circular", "reference": m.group(0).strip(),
                        "normalised": ref})
    for m in _PR_RE.finditer(text or ""):
        ref = "PR" + normalise_reference(m.group(1))
        if ref not in seen:
            seen.add(ref)
            out.append({"kind": "press_release",
                        "reference": m.group(0).strip(), "normalised": ref})
    return out


def verify(text: str, *, body_for_hash: Optional[str] = None) -> dict:
    """
    Check any text that purports to relay an official communication.

    `body_for_hash` lets a caller pass the extracted document body
    separately from the surrounding page chrome, so the content hash is
    computed over the circular text rather than over navigation menus.
    """
    idx = _index()
    entries = idx.get("entries") or {}
    coverage = idx.get("coverage") or {}
    as_of = idx.get("built_at")

    claims = extract_claims(text)
    asserts_authority = bool(_AUTHORITY_CLAIM_RE.search(text or ""))

    if not claims and not asserts_authority:
        return asdict(CommsVerdict(state="no_claim", index_as_of=as_of,
                                    coverage=coverage))

    if not entries:
        return asdict(CommsVerdict(
            state="index_unavailable", claims=claims, index_as_of=as_of,
            coverage=coverage,
            reasons=[{
                "code": "COMMS_NO_INDEX",
                "text": ("The official-communications index has not been "
                         "built on this install, so a cited reference cannot "
                         "be checked either way. Run "
                         "scripts/refresh_official_comms.py."),
                "source_url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7",
            }]))

    # An authority claim with no citation at all. Real circulars cite
    # themselves; this is worth surfacing, but as a prompt, not a verdict.
    if asserts_authority and not claims:
        return asdict(CommsVerdict(
            state="matched_reference", trust_delta=0, claims=[],
            index_as_of=as_of, coverage=coverage,
            reasons=[{
                "code": "COMMS_UNCITED_AUTHORITY",
                "text": ("This states that a regulator issued or directed "
                         "something but cites no circular or press-release "
                         "number, so there is nothing to look up. Official "
                         "communications normally carry their own reference."),
                "source_url": None,
            }]))

    reasons, states = [], []
    observed_hash = content_hash(body_for_hash if body_for_hash is not None else text)

    for c in claims:
        entry = entries.get(c["normalised"])
        if not entry:
            in_range = _within_coverage(c, coverage)
            if in_range:
                states.append("not_in_index")
                reasons.append({
                    "code": "COMMS_REFERENCE_NOT_FOUND",
                    "text": (f"No official record of {c['reference']}. The "
                             "index covers this period, so a genuine "
                             "reference would be expected to appear. Treat "
                             "this as a strong reason to check the "
                             "regulator's own site before acting."),
                    "source_url": idx.get("source_url"),
                })
            else:
                states.append("index_unavailable")
                reasons.append({
                    "code": "COMMS_OUTSIDE_COVERAGE",
                    "text": (f"{c['reference']} falls outside the period this "
                             "index covers, so it could not be checked either "
                             "way. That is a limit of our data, not a finding "
                             "about the document."),
                    "source_url": idx.get("source_url"),
                })
            continue

        c["title"] = entry.get("title")
        c["published_at"] = entry.get("published_at")
        c["official_url"] = entry.get("url")

        if entry.get("content_sha256") and entry["content_sha256"] == observed_hash:
            states.append("matched_exact")
            reasons.append({
                "code": "COMMS_EXACT_MATCH",
                "text": (f"{c['reference']} exists and the text here matches "
                         "the published version exactly."),
                "source_url": entry.get("url"),
            })
        else:
            states.append("matched_reference")
            reasons.append({
                "code": "COMMS_REFERENCE_ONLY",
                "text": (f"{c['reference']} is a real reference, published "
                         f"{entry.get('published_at') or 'on an unrecorded date'}"
                         f"{' as ' + entry['title'] if entry.get('title') else ''}. "
                         "The wording here differs from the published text — "
                         "which is normal for an excerpt or summary, and worth "
                         "reading side by side before acting on it."),
                "source_url": entry.get("url"),
            })

    order = ["not_in_index", "matched_reference", "index_unavailable",
             "no_claim", "matched_exact"]
    state = next((s for s in order if s in states), "no_claim")
    return asdict(CommsVerdict(
        state=state, trust_delta=COMMS_DELTA.get(state, 0), claims=claims,
        reasons=reasons, coverage=coverage, index_as_of=as_of))


def _within_coverage(claim: dict, coverage: dict) -> bool:
    """
    Can the index legitimately speak to this reference?

    Without this guard, `not_in_index` would fire on every pre-coverage
    circular and the module would confidently flag genuine 2015 documents as
    fabricated. A year is pulled from the reference where the numbering
    carries one; when it does not, we decline to judge.
    """
    m = re.search(r"(20\d{2})", claim.get("normalised", ""))
    if not m:
        return False
    year = int(m.group(1))
    lo, hi = coverage.get("from_year"), coverage.get("to_year")
    if not lo or not hi:
        return False
    return lo <= year <= hi


def index_status() -> dict:
    idx = _index()
    entries = idx.get("entries") or {}
    return {
        "built": bool(entries),
        "entry_count": len(entries),
        "built_at": idx.get("built_at"),
        "coverage": idx.get("coverage") or {},
        "source_url": idx.get("source_url"),
        "refresh_hint": "python scripts/refresh_official_comms.py",
        "note": (None if entries else
                 "Index not built. Until it is, official-communication "
                 "claims return `index_unavailable` rather than being "
                 "treated as unverified — flagging every genuine circular "
                 "as suspect would be worse than not checking at all."),
    }
