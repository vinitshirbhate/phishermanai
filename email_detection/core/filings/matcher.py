"""Find the exchange filing a message corresponds to.

This is the first half of the project's novel contribution. Chokepoints 1-4 ask
whether a message looks legitimate. This asks a harder question: does what the
message SAYS match what the company actually told the exchange?

Four steps:

  1. ENTITY RESOLUTION   company name -> ISIN / scrip code, tolerating the
                         suffix variation real documents are full of
  2. CANDIDATE SELECTION filings for that entity, of a compatible type, within
                         a +/- 45 day window of any date in the document
  3. SEMANTIC RANKING    embed and rank by cosine similarity
  4. THREE-TIER MATCH    exact hash / visual pHash / semantic similarity

On step 3: sentence-transformers is an optional extra. When it is absent we
fall back to rapidfuzz token-set similarity, which is materially weaker on
paraphrase but keeps the whole pipeline working on a plain install. Which path
ran is recorded on the result rather than hidden, because it changes how much
weight the score deserves.
"""

from __future__ import annotations

import functools
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import or_, select

from core.db import session_scope
from core.fields import ExtractedFields, find_dates
from core.models import Entity, Filing
from core.textnorm import canonical_hash_text, normalise_company_name

log = logging.getLogger(__name__)

ENTITY_MATCH_THRESHOLD = 85
DATE_WINDOW_DAYS = 45
SEMANTIC_THRESHOLD = 0.82      # cosine similarity, bge-small-en-v1.5
LEXICAL_THRESHOLD = 0.90       # rapidfuzz token_set_ratio -- a different scale

# pHash Hamming-distance bands, justified empirically by eval/phash_drift.py.
PHASH_SAME_DOCUMENT = 10
PHASH_LIKELY_ALTERED = 20

DOC_TYPE_TO_FILING_TYPES = {
    "DIVIDEND": ["DIVIDEND", "BOARD_MEETING", "OTHER"],
    "EVOTING": ["EVOTING", "AGM_NOTICE", "EGM_NOTICE", "OTHER"],
    "AGM_NOTICE": ["AGM_NOTICE", "EVOTING", "OTHER"],
    "EGM_NOTICE": ["EGM_NOTICE", "EVOTING", "OTHER"],
    "BOARD_MEETING": ["BOARD_MEETING", "RESULTS", "OTHER"],
    "RESULTS": ["RESULTS", "BOARD_MEETING", "OTHER"],
    "OTHER": None,   # no restriction
}


@dataclass
class FilingMatch:
    filing_id: int | None = None
    tier: str = "NONE"                 # EXACT | VISUAL | STRUCTURED | SEMANTIC | NONE
    score: float = 0.0
    company_name: str | None = None
    filing_type: str | None = None
    filing_date: datetime | None = None
    headline: str | None = None
    pdf_url: str | None = None
    exchange: str | None = None
    matched_entity: dict[str, Any] | None = None
    candidates_considered: int = 0
    ranking_method: str = "none"
    notes: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.filing_id is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filing_id": self.filing_id,
            "tier": self.tier,
            "score": round(self.score, 4),
            "company_name": self.company_name,
            "filing_type": self.filing_type,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
            "headline": self.headline,
            "pdf_url": self.pdf_url,
            "exchange": self.exchange,
            "matched_entity": self.matched_entity,
            "candidates_considered": self.candidates_considered,
            "ranking_method": self.ranking_method,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# Step 1 -- entity resolution
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _company_index() -> dict[str, dict[str, Any]]:
    """Normalised company name -> identity, for listed companies only."""
    index: dict[str, dict[str, Any]] = {}
    try:
        with session_scope() as session:
            rows = session.execute(
                select(Entity.name, Entity.normalised_name, Entity.isin, Entity.scrip_code)
                .where(Entity.entity_type == "LISTED_COMPANY")
            ).all()
    except Exception:  # noqa: BLE001
        return {}
    for name, norm, isin, scrip in rows:
        if norm and norm not in index:
            index[norm] = {"name": name, "normalised_name": norm, "isin": isin, "scrip_code": scrip}
    return index


def reset_matcher_cache() -> None:
    _company_index.cache_clear()
    _despaced_company_index.cache_clear()


def resolve_company(name: str) -> dict[str, Any] | None:
    """Resolve a company name to its ISIN and scrip code.

    Handles the variation real documents contain: "Canara Bank Ltd",
    "CANARA BANK", "Canara Bank Limited" all reduce to the same key before
    comparison, and anything left over goes through fuzzy matching.
    """
    norm = normalise_company_name(name)
    if not norm:
        return None
    index = _company_index()
    if norm in index:
        return {**index[norm], "match_score": 100, "match_type": "EXACT"}

    match = process.extractOne(
        norm, index.keys(), scorer=fuzz.WRatio, score_cutoff=ENTITY_MATCH_THRESHOLD
    )
    if match:
        return {**index[match[0]], "match_score": int(match[1]), "match_type": "FUZZY"}
    return None


@functools.lru_cache(maxsize=1)
def _despaced_company_index() -> list[tuple[str, str]]:
    """(name_without_spaces, normalised_name), longest first.

    Used only as a fallback for OCR text -- see find_company_in_text.
    """
    entries = [
        (norm.replace(" ", ""), norm)
        for norm in _company_index()
        # Short names ("wipro", "acc") would match inside unrelated words once
        # spaces are ignored, so the despaced path is restricted to names long
        # enough for a substring hit to be meaningful.
        if len(norm.replace(" ", "")) >= 10
    ]
    entries.sort(key=lambda pair: -len(pair[0]))
    return entries


def find_company_in_text(text: str) -> dict[str, Any] | None:
    """Longest company name mentioned anywhere in the document."""
    if not text:
        return None
    index = _company_index()
    if not index:
        return None

    normalised = normalise_company_name(text)
    words = normalised.split()
    best: dict[str, Any] | None = None
    for size in range(6, 1, -1):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i + size])
            if phrase in index:
                candidate = {**index[phrase], "match_score": 100,
                             "match_type": "EXACT", "matched_phrase": phrase}
                if best is None or len(phrase) > len(best.get("matched_phrase", "")):
                    best = candidate
        if best:
            return best

    # FALLBACK FOR OCR TEXT.
    # Word-boundary matching assumes the spaces are where they belong. OCR on a
    # compressed screenshot frequently runs words together -- measured output
    # included "BirlaCorporationLtdwishestoinform" -- and every n-gram lookup
    # then misses, so no filing is matched and a tampered document comes back
    # UNVERIFIED. Comparing with all spaces removed on both sides is immune to
    # exactly that error, and costs one pass over the company list.
    despaced = normalised.replace(" ", "")
    if len(despaced) >= 10:
        for candidate_despaced, norm in _despaced_company_index():
            if candidate_despaced in despaced:
                return {
                    **index[norm], "match_score": 95,
                    "match_type": "DESPACED", "matched_phrase": norm,
                }
    return None


# --------------------------------------------------------------------------
# Step 3 -- semantic ranking
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _embedding_model():
    """Load BAAI/bge-small-en-v1.5 if sentence-transformers is installed."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.info("sentence-transformers not installed; using lexical ranking")
        return None
    try:
        return SentenceTransformer("BAAI/bge-small-en-v1.5")
    except Exception as exc:  # noqa: BLE001 - no model cache, offline, etc.
        log.warning("embedding model unavailable (%s); using lexical ranking", exc)
        return None


def semantic_available() -> bool:
    return _embedding_model() is not None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def rank_candidates(text: str, candidates: list[Filing]) -> list[tuple[Filing, float, str]]:
    """Rank candidate filings by similarity to the document text."""
    if not candidates:
        return []

    model = _embedding_model()
    if model is not None:
        try:
            query_vec = model.encode(text, normalize_embeddings=True).tolist()
            scored: list[tuple[Filing, float, str]] = []
            to_embed: list[tuple[int, str]] = []
            for idx, filing in enumerate(candidates):
                if filing.embedding:
                    scored.append((filing, _cosine(query_vec, filing.embedding), "embedding_cached"))
                else:
                    to_embed.append((idx, f"{filing.headline or ''}\n{filing.body_text or ''}"))
            if to_embed:
                vectors = model.encode([t for _, t in to_embed], normalize_embeddings=True)
                for (idx, _), vec in zip(to_embed, vectors):
                    scored.append((candidates[idx], _cosine(query_vec, vec.tolist()), "embedding"))
            scored.sort(key=lambda row: -row[1])
            return scored
        except Exception as exc:  # noqa: BLE001
            log.warning("semantic ranking failed (%s); falling back to lexical", exc)

    # Lexical fallback. token_set_ratio ignores word order and duplication,
    # which suits comparing a letter against a filing summary.
    scored = [
        (
            filing,
            fuzz.token_set_ratio(text, f"{filing.headline or ''} {filing.body_text or ''}") / 100.0,
            "lexical",
        )
        for filing in candidates
    ]
    scored.sort(key=lambda row: -row[1])
    return scored


# --------------------------------------------------------------------------
# Structured-field agreement -- the primary discriminator
# --------------------------------------------------------------------------
#
# WHY THIS EXISTS, AND WHY IT RANKS ABOVE SEMANTIC SIMILARITY
#
# Measured on the fixtures: ranking candidates by text similarity put the
# CORRECT filing 2nd to 9th, and the wrong filing always scored higher. That is
# not a threshold problem, it is the wrong signal. Every dividend notice a
# company issues is near-identical boilerplate -- same letterhead, same
# regulatory phrasing, same signatory -- so prose similarity cannot tell two of
# them apart. It measures "is this a dividend notice from this company", which
# we already knew from candidate selection.
#
# What distinguishes one filing from another is precisely the structured
# values: a record date of 10 July 2026 for Canara Bank is close to unique.
# So we match on those, and the residual text score is only a tiebreak.
#
# This still works on a tampered document. We alter one field; the others
# continue to anchor the match, the document is found, and the altered field is
# then reported as the mismatch. That is the desired behaviour -- a tampered
# document must still MATCH its original, otherwise there is nothing to
# compare it against.

STRUCTURED_FIELDS = ("record_date", "dividend_per_share", "meeting_date",
                     "evoting_start", "evoting_end", "isin")


def structured_agreement(fields: ExtractedFields | None, filing: Filing) -> dict[str, Any]:
    """Compare every structured field present on both sides.

    Returns counts plus the field names, so the caller can rank candidates and
    explain why a particular filing was chosen.
    """
    if fields is None:
        return {"matched": 0, "conflicts": 0, "comparable": 0,
                "matched_fields": [], "conflicting_fields": []}

    matched: list[str] = []
    conflicting: list[str] = []

    for name in STRUCTURED_FIELDS:
        doc_value = getattr(fields, name, None)
        filed_value = getattr(filing, name, None)
        if doc_value is None or filed_value is None:
            continue
        if name == "dividend_per_share":
            same = abs(float(doc_value) - float(filed_value)) <= 0.005
        elif name == "isin":
            same = str(doc_value).strip().upper() == str(filed_value).strip().upper()
        else:
            same = doc_value == filed_value
        (matched if same else conflicting).append(name)

    return {
        "matched": len(matched),
        "conflicts": len(conflicting),
        "comparable": len(matched) + len(conflicting),
        "matched_fields": matched,
        "conflicting_fields": conflicting,
    }


# --------------------------------------------------------------------------
# Steps 2 + 4 -- candidates and tiered matching
# --------------------------------------------------------------------------

def _candidate_dates(text: str, fields: ExtractedFields | None) -> list[date]:
    dates: list[date] = []
    if fields:
        for value in (fields.record_date, fields.meeting_date,
                      fields.evoting_start, fields.evoting_end):
            if value:
                dates.append(value)
    dates.extend(d for d, _, _ in find_dates(text or "")[:8])
    return dates


def match_filing(
    text: str,
    fields: ExtractedFields | None = None,
    *,
    phash: str | None = None,
    company_hint: str | None = None,
) -> FilingMatch:
    """Find the filing this document corresponds to."""
    result = FilingMatch()
    text = text or ""

    # ---- Step 1
    company = None
    if company_hint:
        company = resolve_company(company_hint)
    if company is None and fields and fields.company_name:
        company = resolve_company(fields.company_name)
    if company is None:
        company = find_company_in_text(text)

    if company is None:
        result.notes.append("Could not identify which listed company this document refers to.")
        return result
    result.matched_entity = company

    # ---- Step 2
    with session_scope() as session:
        conditions = []
        if company.get("isin"):
            conditions.append(Filing.isin == company["isin"])
        if company.get("scrip_code"):
            conditions.append(Filing.scrip_code == str(company["scrip_code"]))
        conditions.append(Filing.company_name == company["name"])

        query = select(Filing).where(or_(*conditions))

        doc_type = (fields.doc_type if fields else None) or "OTHER"
        allowed = DOC_TYPE_TO_FILING_TYPES.get(doc_type)
        if allowed:
            query = query.where(Filing.filing_type.in_(allowed))

        candidates = session.execute(query).scalars().all()

        # Narrow by date proximity when the document carries dates. If nothing
        # survives the window, keep the unfiltered set rather than returning
        # nothing -- a document may quote no date at all.
        doc_dates = _candidate_dates(text, fields)
        if doc_dates and candidates:
            window = timedelta(days=DATE_WINDOW_DAYS)
            near = [
                f for f in candidates
                if f.filing_date and any(
                    abs(f.filing_date.date() - d) <= window for d in doc_dates
                )
            ]
            if near:
                candidates = near

        result.candidates_considered = len(candidates)
        if not candidates:
            result.notes.append(
                f"{company['name']} was identified, but no filing of a matching type was "
                "found in the cached corpus."
            )
            return result

        # ---- Step 4, TIER 1: exact content hash
        doc_hash = hashlib.sha256(canonical_hash_text(text).encode()).hexdigest()
        for filing in candidates:
            if filing.content_sha256 and filing.content_sha256 == doc_hash:
                result.filing_id = filing.id
                result.tier = "EXACT"
                result.score = 1.0
                result.ranking_method = "sha256"
                _fill(result, filing)
                return result

        # ---- TIER 2: visual pHash
        if phash:
            best_distance = None
            best_filing = None
            for filing in candidates:
                stored = (filing.raw_json or {}).get("_PHASH") if filing.raw_json else None
                if not stored:
                    continue
                distance = _hamming(phash, stored)
                if distance is not None and (best_distance is None or distance < best_distance):
                    best_distance, best_filing = distance, filing
            if best_filing is not None and best_distance is not None:
                if best_distance < PHASH_SAME_DOCUMENT:
                    result.tier, result.score = "VISUAL", 1.0 - best_distance / 64.0
                    result.notes.append(f"Visually identical to the filed document (pHash distance {best_distance}).")
                    result.filing_id = best_filing.id
                    result.ranking_method = "phash"
                    _fill(result, best_filing)
                    return result
                if best_distance <= PHASH_LIKELY_ALTERED:
                    result.tier, result.score = "VISUAL", 1.0 - best_distance / 64.0
                    result.notes.append(
                        f"Same document as filed, but altered or cropped "
                        f"(pHash distance {best_distance})."
                    )
                    result.filing_id = best_filing.id
                    result.ranking_method = "phash"
                    _fill(result, best_filing)
                    return result

        # ---- TIER 3: structured-field agreement (see the note above)
        agreements = [(f, structured_agreement(fields, f)) for f in candidates]
        anchored = [(f, a) for f, a in agreements if a["matched"] >= 1]
        if anchored:
            text_scores = {
                f.id: s for f, s, _ in rank_candidates(text, [f for f, _ in anchored])
            }
            # Rank by agreement, then by how much evidence the filing offers.
            #
            # NOT by fewest conflicts, which is the intuitive choice and is
            # wrong. Ranking a conflict as a penalty means a tampered document
            # prefers whichever filing has the fewest comparable fields --
            # precisely the filing that cannot reveal the tampering. Measured:
            # a tampered dividend notice matched a sibling filing carrying only
            # a record date, and came back clean.
            #
            # A conflict is a FINDING, not a disqualification. So among filings
            # that agree equally, prefer the one with the most comparable
            # fields: the most informative comparison, whichever way it falls.
            anchored.sort(
                key=lambda pair: (
                    -pair[1]["matched"],
                    -pair[1]["comparable"],
                    -text_scores.get(pair[0].id, 0.0),
                )
            )
            filing, agreement = anchored[0]
            result.filing_id = filing.id
            result.tier = "STRUCTURED"
            # Confidence in the MATCH, not in the document being genuine: it
            # rises with how many independent fields agree.
            result.score = min(1.0, 0.75 + 0.08 * agreement["matched"])
            result.ranking_method = "structured_fields"
            result.notes.append(
                "Matched on "
                + ", ".join(agreement["matched_fields"])
                + f" agreeing with the filing {filing.company_name} made with "
                f"{filing.exchange}."
            )
            if agreement["conflicting_fields"]:
                result.notes.append(
                    "Fields that do NOT agree: " + ", ".join(agreement["conflicting_fields"])
                )
            _fill(result, filing)
            return result

        # ---- TIER 4: semantic / lexical similarity
        ranked = rank_candidates(text, candidates)
        if ranked:
            filing, score, method = ranked[0]
            result.ranking_method = method
            # A threshold belongs to a scoring method, not to the pipeline.
            # Cosine similarity from bge-small and rapidfuzz token_set_ratio are
            # different scales, and applying one number to both was letting a
            # 0.74 lexical score be judged against a 0.82 cosine bar. The
            # lexical bar is deliberately strict because it was measured
            # ranking the wrong filing first -- a confident match against the
            # wrong document is worse than no match at all, since every field
            # would then compare as tampered.
            threshold = SEMANTIC_THRESHOLD if method.startswith("embedding") else LEXICAL_THRESHOLD
            if score >= threshold:
                result.filing_id = filing.id
                result.tier = "SEMANTIC"
                result.score = score
                _fill(result, filing)
                return result
            result.score = score
            result.notes.append(
                f"Closest filing scored {score:.2f}, below the {SEMANTIC_THRESHOLD} "
                "threshold for a confident match."
            )
            # Surface the near miss so the UI can offer it as context.
            _fill(result, filing)
            result.filing_id = None

    return result


def _fill(result: FilingMatch, filing: Filing) -> None:
    result.company_name = filing.company_name
    result.filing_type = filing.filing_type
    result.filing_date = filing.filing_date
    result.headline = filing.headline
    result.pdf_url = filing.pdf_url
    result.exchange = filing.exchange


def _hamming(a: str, b: str) -> int | None:
    """Hamming distance between two hex pHash strings."""
    if not a or not b or len(a) != len(b):
        return None
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return None
