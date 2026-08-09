"""Populate phishermanai.db from data/cache/ and data/reference/.

    python -m data.load_all            # incremental, idempotent
    python -m data.load_all --reset    # drop and rebuild

Runs entirely offline. Every byte it reads is a file already on disk, so this
works with the network unplugged -- which is also how the demo runs.

Idempotency strategy per table:
  filings, entities  -> keyed inserts, existing keys skipped
  domain_map, claim_rules -> the CSV is authoritative, so wipe and reload
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select

from core.db import DEFAULT_DB_PATH, engine, init_db, session_scope
from core.fields import (
    extract_dividend_per_share,
    extract_evoting_window,
    extract_meeting_date,
    extract_record_date,
)
from core.models import Base, ClaimRule, DomainMap, Entity, Filing
from core.textnorm import canonical_hash_text, collapse_ws, normalise_company_name, normalise_domain

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache"
REF_DIR = REPO_ROOT / "data" / "reference"

import hashlib


def _read_json(name: str) -> Any:
    path = CACHE_DIR / name
    if not path.exists():
        log.warning("cache file missing: %s", path.name)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Filing type classification
# --------------------------------------------------------------------------

def classify_filing_type(category: str, subcategory: str, text: str) -> str:
    """Map BSE's category/subcategory taxonomy onto our filing_type enum."""
    cat = (category or "").lower().strip()
    sub = (subcategory or "").lower().strip()
    low = (text or "").lower()

    if "dividend" in sub or "record date" in sub or "book closure" in sub:
        return "DIVIDEND"
    if "corp" in cat and "action" in cat and "dividend" in low:
        return "DIVIDEND"
    if "e-voting" in low or "evoting" in low or "e voting" in low or "remote voting" in low:
        return "EVOTING"
    if "postal ballot" in sub or "egm" in sub or "extra-ordinary" in low or "extraordinary general" in low:
        return "EGM_NOTICE"
    if "agm" in sub or "annual general meeting" in low:
        return "AGM_NOTICE"
    if "board meeting" in cat or "board meeting" in sub:
        return "BOARD_MEETING"
    if cat.startswith("result") or "financial results" in sub:
        return "RESULTS"
    return "OTHER"


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------

def load_filings(session) -> dict[str, Any]:
    rows = _read_json("bse_announcements.json") or []
    if not rows:
        return {"loaded": 0, "skipped": 0, "note": "no BSE cache found"}

    # Attachment text, where we fetched it. Most BSE headlines are a stub
    # ("Please refer enclosed file") with the real content in the PDF, so
    # without this the structured fields the tamper detector compares are
    # mostly empty. See data/scrapers/bse_pdf.py.
    pdf_text: dict[str, str] = _read_json("bse_pdf_text.json") or {}

    existing = {
        sid for (sid,) in session.execute(
            select(Filing.source_id).where(Filing.exchange == "BSE")
        )
    }

    loaded = skipped = 0
    type_counts: Counter[str] = Counter()

    for row in rows:
        source_id = str(row.get("NEWSID") or "").strip()
        if not source_id or source_id in existing:
            skipped += 1
            continue

        headline = collapse_ws(row.get("NEWSSUB") or "")
        # BSE doubles apostrophes in HEADLINE (SQL-escaping leaking into the
        # payload), so undo that before it reaches the text comparators.
        body = collapse_ws((row.get("HEADLINE") or "").replace("''", "'"))

        # The attachment text is the authoritative content when we have it.
        attachment_text = collapse_ws(pdf_text.get(source_id) or "")
        if attachment_text:
            body = f"{body}\n{attachment_text}" if body else attachment_text
        combined = f"{headline}\n{body}"

        filing_date = None
        raw_dt = row.get("News_submission_dt") or row.get("NEWS_DT") or row.get("DT_TM")
        if raw_dt:
            try:
                filing_date = datetime.fromisoformat(str(raw_dt).replace("Z", ""))
            except ValueError:
                filing_date = None

        attachment = (row.get("ATTACHMENTNAME") or "").strip()
        pdf_url = (
            f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}"
            if attachment else None
        )

        ev_start, ev_end = extract_evoting_window(combined)
        filing_type = classify_filing_type(row.get("CATEGORYNAME"), row.get("SUBCATNAME"), combined)
        type_counts[filing_type] += 1

        session.add(Filing(
            company_name=collapse_ws(row.get("SLONGNAME") or ""),
            isin=(row.get("_ISIN") or "").strip() or None,
            scrip_code=str(row.get("_SCRIP_CD") or row.get("SCRIP_CD") or "").strip() or None,
            exchange="BSE",
            filing_type=filing_type,
            filing_date=filing_date,
            headline=headline,
            body_text=body,
            pdf_url=pdf_url,
            raw_json=row,
            dividend_per_share=extract_dividend_per_share(combined),
            record_date=extract_record_date(combined),
            meeting_date=extract_meeting_date(combined),
            evoting_start=ev_start,
            evoting_end=ev_end,
            source_id=source_id,
            content_sha256=hashlib.sha256(canonical_hash_text(combined).encode()).hexdigest(),
        ))
        loaded += 1

    session.flush()
    return {"loaded": loaded, "skipped": skipped, "by_type": dict(type_counts)}


def load_listed_companies(session) -> dict[str, Any]:
    """Listed companies from the BSE scrip master -- real names with real ISINs."""
    rows = _read_json("bse_scrips.json") or []
    if not rows:
        return {"loaded": 0, "note": "no scrip master found"}

    existing = {
        (n, t) for n, t in session.execute(
            select(Entity.normalised_name, Entity.entity_type)
        )
    }

    loaded = 0
    for row in rows:
        name = collapse_ws(row.get("Scrip_Name") or "")
        if not name:
            continue
        norm = normalise_company_name(name)
        key = (norm, "LISTED_COMPANY")
        if not norm or key in existing:
            continue
        existing.add(key)
        session.add(Entity(
            name=name,
            normalised_name=norm,
            entity_type="LISTED_COMPANY",
            isin=(row.get("ISIN_NUMBER") or "").strip() or None,
            scrip_code=str(row.get("SCRIP_CD") or "").strip() or None,
            status="ACTIVE" if str(row.get("Status", "")).lower() == "active" else "INACTIVE",
            notes=f"BSE group {row.get('GROUP') or '-'}; source: BSE scrip master",
        ))
        loaded += 1

    session.flush()
    return {"loaded": loaded}


def load_sebi_intermediaries(session) -> dict[str, Any]:
    """SEBI-registered intermediaries: real registration numbers and names.

    The registered e-mail address also yields a legitimate sending domain,
    which is stored on the entity for the ENTITY chokepoint to use.
    """
    payload = _read_json("sebi_intermediaries.json")
    if not payload:
        return {"loaded": 0, "note": "no SEBI cache found"}

    existing_regs = {
        r for (r,) in session.execute(
            select(Entity.sebi_reg_no).where(Entity.sebi_reg_no.is_not(None))
        )
    }

    loaded = 0
    by_type: Counter[str] = Counter()
    for rec in payload.get("records", []):
        reg = (rec.get("registration_no") or "").strip()
        name = collapse_ws(rec.get("name") or "")
        if not name or not reg or reg in existing_regs:
            continue
        existing_regs.add(reg)

        email = (rec.get("email") or "").strip().lower()
        domain = normalise_domain(email.split("@")[-1]) if "@" in email else ""
        # Free mail providers are not corporate identity -- many small advisers
        # register a gmail address, and treating that as an official domain
        # would let anyone with a gmail account impersonate them.
        if domain in {"gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com",
                      "rediffmail.com", "live.com", "googlemail.com", ""}:
            domain = ""

        entity_type = rec.get("entity_type") or "OTHER_INTERMEDIARY"
        by_type[entity_type] += 1
        session.add(Entity(
            name=name,
            normalised_name=normalise_company_name(name),
            entity_type=entity_type,
            sebi_reg_no=reg,
            status="ACTIVE",
            official_domains=[domain] if domain else [],
            official_contact={
                "email": email or None,
                "phone": rec.get("telephone") or None,
                "city": rec.get("city") or None,
                "state": rec.get("state") or None,
            },
            notes=f"SEBI register: {rec.get('category_label')}; valid {rec.get('valid_from')} to {rec.get('valid_to')}",
        ))
        loaded += 1

    session.flush()
    return {"loaded": loaded, "by_type": dict(by_type)}


def load_domain_map(session) -> dict[str, Any]:
    """Reload domain_map from CSV. The CSV is authoritative, so wipe first."""
    path = REF_DIR / "domain_map.csv"
    if not path.exists():
        return {"loaded": 0, "note": "domain_map.csv missing"}

    session.execute(delete(DomainMap))

    # Resolve each row to an entity so /entity/{name} can surface official
    # contact details alongside the domain.
    entities = {
        norm: eid for norm, eid in session.execute(
            select(Entity.normalised_name, Entity.id)
        )
    }

    loaded = linked = 0
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            domain = normalise_domain(row.get("domain", ""))
            entity_name = collapse_ws(row.get("entity_name", ""))
            if not domain or not entity_name:
                continue
            key = (domain, entity_name)
            if key in seen:
                continue
            seen.add(key)

            entity_id = entities.get(normalise_company_name(entity_name))
            if entity_id:
                linked += 1
            session.add(DomainMap(
                domain=domain,
                entity_id=entity_id,
                entity_name=entity_name,
                entity_type=row.get("entity_type", "LISTED_COMPANY").strip(),
                relationship_type=row.get("relationship", "OFFICIAL").strip(),
                verified_source=row.get("source", "").strip(),
            ))
            loaded += 1

    session.flush()
    return {"loaded": loaded, "linked_to_entity": linked}


def load_claim_rules(session) -> dict[str, Any]:
    path = REF_DIR / "claim_rules.csv"
    if not path.exists():
        return {"loaded": 0, "note": "claim_rules.csv missing"}

    session.execute(delete(ClaimRule))

    loaded = 0
    severities: Counter[int] = Counter()
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("code") or "").strip()
            pattern = row.get("pattern") or ""
            if not code or not pattern:
                continue
            severity = int(row.get("severity") or 3)
            severities[severity] += 1
            session.add(ClaimRule(
                code=code,
                pattern=pattern,
                safe_context=(row.get("safe_context") or "").strip() or None,
                rule_type=(row.get("rule_type") or "OTHER").strip(),
                severity=severity,
                explanation=(row.get("explanation") or "").strip(),
                legal_basis=(row.get("legal_basis") or "").strip() or None,
                enabled=1,
            ))
            loaded += 1

    session.flush()
    return {"loaded": loaded, "by_severity": dict(sorted(severities.items()))}


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def summarise(session) -> None:
    print("\n" + "=" * 72)
    print("  PhishermanAI database summary")
    print("=" * 72)

    counts = [
        ("filings", session.scalar(select(func.count()).select_from(Filing))),
        ("entities", session.scalar(select(func.count()).select_from(Entity))),
        ("domain_map", session.scalar(select(func.count()).select_from(DomainMap))),
        ("claim_rules", session.scalar(select(func.count()).select_from(ClaimRule))),
    ]
    print(f"\n  {'TABLE':<16}{'ROWS':>10}")
    print("  " + "-" * 26)
    for name, n in counts:
        print(f"  {name:<16}{n:>10,}")

    lo, hi = session.execute(
        select(func.min(Filing.filing_date), func.max(Filing.filing_date))
    ).one()
    companies = session.scalar(select(func.count(func.distinct(Filing.company_name))))
    print(f"\n  filing date range      {str(lo)[:10]} -> {str(hi)[:10]}")
    print(f"  distinct companies     {companies:,}")

    print("\n  filings by type")
    for ftype, n in session.execute(
        select(Filing.filing_type, func.count()).group_by(Filing.filing_type).order_by(func.count().desc())
    ):
        print(f"    {ftype:<16}{n:>8,}")

    print("\n  entities by type")
    for etype, n in session.execute(
        select(Entity.entity_type, func.count()).group_by(Entity.entity_type).order_by(func.count().desc())
    ):
        print(f"    {etype:<24}{n:>8,}")

    extractable = session.scalar(
        select(func.count()).select_from(Filing).where(Filing.dividend_per_share.is_not(None))
    )
    with_record = session.scalar(
        select(func.count()).select_from(Filing).where(Filing.record_date.is_not(None))
    )
    with_evoting = session.scalar(
        select(func.count()).select_from(Filing).where(Filing.evoting_start.is_not(None))
    )
    print("\n  structured fields recovered (these are what tamper detection compares)")
    print(f"    dividend_per_share    {extractable:>8,}")
    print(f"    record_date           {with_record:>8,}")
    print(f"    evoting window        {with_evoting:>8,}")
    print(f"\n  database: {DEFAULT_DB_PATH}")
    print("=" * 72 + "\n")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Load PhishermanAI reference data")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()

    if args.reset:
        log.warning("--reset: dropping all tables in %s", DEFAULT_DB_PATH)
        Base.metadata.drop_all(engine)

    init_db()

    with session_scope() as session:
        log.info("loading listed companies (BSE scrip master) ...")
        r_companies = load_listed_companies(session)
        log.info("  %s", r_companies)

        log.info("loading SEBI registered intermediaries ...")
        r_sebi = load_sebi_intermediaries(session)
        log.info("  %s", r_sebi)

        log.info("loading filings (BSE announcements) ...")
        r_filings = load_filings(session)
        log.info("  %s", r_filings)

        log.info("loading domain map ...")
        log.info("  %s", load_domain_map(session))

        log.info("loading claim rules ...")
        log.info("  %s", load_claim_rules(session))

    with session_scope() as session:
        summarise(session)


if __name__ == "__main__":  # pragma: no cover
    main()
