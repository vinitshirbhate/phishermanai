"""Fetch BSE announcement PDFs and recover their text.

Why this exists
---------------
Most BSE announcement records carry only a stub headline -- literally "Please
refer enclosed file" -- with the substance in an attached PDF. After the first
load only 41 of 8,434 filings had an extractable dividend amount, which is not
enough ground truth for tamper detection to compare against.

This scraper downloads the attachments for the filing types that actually
contain comparable structured values (dividends, e-voting windows, meeting
notices), extracts their text, and caches it to disk. The loader then reads the
cache and re-derives the structured fields, so the enrichment survives a
rebuild and the demo still runs offline.

Attachments live under /xml-data/corpfiling/AttachLive/<name>.pdf. A minority
404 there; those are retried against AttachHis and skipped if still missing.
"""

from __future__ import annotations

import argparse
import io
import logging
from typing import Any

from data.scrapers.http import BROWSER_UA, RateLimitedSession, read_cache, write_cache

log = logging.getLogger(__name__)

ATTACH_LIVE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
ATTACH_HIS = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/"

CACHE = "bse_pdf_text.json"
ANN_CACHE = "bse_announcements.json"

# Filing types whose PDFs carry values the tamper detector compares.
# 'Company Update' and similar are excluded -- high volume, low structured yield.
TARGET_SUBCATS = (
    "dividend", "record date", "book closure", "date of payment of dividend",
    "agm", "egm", "postal ballot", "voting",
)

MAX_PAGES = 8  # notices put the useful fields up front; full annual reports are noise


def _looks_relevant(row: dict[str, Any]) -> bool:
    sub = (row.get("SUBCATNAME") or "").lower()
    cat = (row.get("CATEGORYNAME") or "").lower()
    text = f"{row.get('NEWSSUB') or ''} {row.get('HEADLINE') or ''}".lower()
    if any(k in sub for k in TARGET_SUBCATS):
        return True
    if "agm/egm" in cat:
        return True
    return "dividend" in text or "e-voting" in text or "record date" in text


def extract_pdf_text(content: bytes) -> str:
    """Text of the first MAX_PAGES pages. Empty string if the PDF is unreadable.

    Scanned/image-only PDFs yield nothing here; that is expected and honest --
    they simply do not contribute structured ground truth.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        log.error("pypdf not installed; run: pip install pypdf")
        return ""

    try:
        reader = PdfReader(io.BytesIO(content))
        parts = []
        for page in reader.pages[:MAX_PAGES]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one bad page must not lose the rest
                continue
        return "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        log.debug("PDF parse failed: %s", exc)
        return ""


def scrape(limit: int | None = None) -> dict[str, Any]:
    announcements = read_cache(ANN_CACHE) or []
    if not announcements:
        return {"ok": False, "error": "no announcement cache; run the bse scraper first"}

    cached: dict[str, str] = read_cache(CACHE) or {}
    targets = [
        r for r in announcements
        if r.get("ATTACHMENTNAME") and _looks_relevant(r)
        and str(r.get("NEWSID")) not in cached
    ]
    if limit:
        targets = targets[:limit]

    log.info("%d relevant attachments to fetch (%d already cached)", len(targets), len(cached))

    session = RateLimitedSession(headers={
        "Referer": "https://www.bseindia.com/corporates/ann.html",
        "User-Agent": BROWSER_UA,
    })

    ok = empty = failed = 0
    for idx, row in enumerate(targets, 1):
        news_id = str(row.get("NEWSID"))
        attachment = (row.get("ATTACHMENTNAME") or "").strip()
        if not attachment:
            continue

        content = session.get_bytes(ATTACH_LIVE + attachment)
        if not content or not content.startswith(b"%PDF"):
            content = session.get_bytes(ATTACH_HIS + attachment)
        if not content or not content.startswith(b"%PDF"):
            failed += 1
            cached[news_id] = ""      # remember the miss so re-runs skip it
            continue

        text = extract_pdf_text(content)
        cached[news_id] = text
        if text:
            ok += 1
        else:
            empty += 1

        if idx % 50 == 0 or idx == len(targets):
            log.info("  [%d/%d] ok=%d empty=%d failed=%d", idx, len(targets), ok, empty, failed)
            write_cache(CACHE, cached)

    write_cache(CACHE, cached)
    result = {"ok": True, "fetched": len(targets), "with_text": ok,
              "no_text": empty, "failed": failed, "cached_total": len(cached)}
    log.info("PDF enrichment complete: %s", result)
    return result


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Fetch BSE announcement PDFs and cache their text")
    p.add_argument("--limit", type=int, help="only fetch this many (for a quick trial)")
    args = p.parse_args()
    scrape(limit=args.limit)
