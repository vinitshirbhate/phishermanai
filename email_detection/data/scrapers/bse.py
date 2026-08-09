"""BSE corporate announcements scraper.

Retrieved: 2026-08-06. Endpoints (undocumented but public, same ones the
bseindia.com announcements page calls from the browser):

  Scrip master : api.bseindia.com/BseIndiaAPI/api/ListofScripData/w
  Announcements: api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w

TWO BEHAVIOURS DISCOVERED THE HARD WAY, both worked around here:

  1. The all-company query (strScrip empty) returns `{}` -- no error, just
     nothing. Announcements are only served per scrip code, so we iterate over
     a company list instead of paging a global feed.
  2. Date windows wider than ~30 days return
     {"Status":false,"Message":"Date range exceeded threshold."}
     so a 90-day harvest is split into 30-day chunks.

Everything is cached to data/cache/ and the loader reads only from there. This
module is never imported by the API.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta
from typing import Any

from data.scrapers.http import RateLimitedSession, read_cache, write_cache

log = logging.getLogger(__name__)

BSE_HEADERS = {
    "Referer": "https://www.bseindia.com/corporates/ann.html",
    "Origin": "https://www.bseindia.com",
    "Accept": "application/json, text/plain, */*",
}

SCRIP_MASTER_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
ANNOUNCEMENTS_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
ATTACHMENT_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

SCRIP_CACHE = "bse_scrips.json"
ANN_CACHE = "bse_announcements.json"

MAX_WINDOW_DAYS = 30


def fetch_scrip_master(session: RateLimitedSession, *, refresh: bool = False) -> list[dict[str, Any]]:
    """Full list of active BSE equity scrips: code, name, ISIN, group.

    This doubles as our listed-company entity registry -- real names paired with
    real ISINs, which is what makes ISIN validation meaningful rather than a
    format check.
    """
    if not refresh:
        cached = read_cache(SCRIP_CACHE)
        if cached:
            log.info("scrip master: %d rows (cached)", len(cached))
            return cached

    log.info("fetching BSE scrip master ...")
    data = session.get_json(
        SCRIP_MASTER_URL,
        params={"Group": "", "Scripcode": "", "industry": "", "segment": "Equity", "status": "Active"},
    )
    if not data:
        log.error("scrip master fetch FAILED -- no data returned")
        return []

    rows = [r for r in data if str(r.get("Segment", "")).strip().lower() == "equity"]
    write_cache(SCRIP_CACHE, rows)
    log.info("scrip master: %d active equity scrips", len(rows))
    return rows


def _date_windows(days: int, end: date | None = None) -> list[tuple[date, date]]:
    """Split `days` back from `end` into <= MAX_WINDOW_DAYS chunks."""
    end = end or date.today()
    start = end - timedelta(days=days)
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=MAX_WINDOW_DAYS - 1), end)
        windows.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return windows


def fetch_announcements_for_scrip(
    session: RateLimitedSession,
    scrip_code: str,
    days: int = 90,
    end: date | None = None,
) -> list[dict[str, Any]]:
    """All announcements for one scrip over `days`, across chunked windows."""
    out: list[dict[str, Any]] = []
    for win_start, win_end in _date_windows(days, end):
        payload = session.get_json(
            ANNOUNCEMENTS_URL,
            params={
                "pageno": 1,
                "strCat": -1,
                "strPrevDate": win_start.strftime("%Y%m%d"),
                "strScrip": scrip_code,
                "strSearch": "P",
                "strToDate": win_end.strftime("%Y%m%d"),
                "strType": "C",
                "subcategory": -1,
            },
        )
        if not payload:
            continue
        if isinstance(payload, dict):
            if payload.get("Status") is False:
                log.warning("scrip %s window %s..%s rejected: %s",
                            scrip_code, win_start, win_end, payload.get("Message"))
                continue
            out.extend(payload.get("Table") or [])
    return out


def select_companies(scrips: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Pick which companies to harvest.

    BSE group 'A' is the most-traded, largest-cap tier -- exactly the companies
    whose dividend and e-voting notices get impersonated. Falls back through
    B and then everything else if A is thin.
    """
    def has_isin(r: dict[str, Any]) -> bool:
        return bool(str(r.get("ISIN_NUMBER") or "").strip())

    ordered: list[dict[str, Any]] = []
    for group in ("A", "B", "T", "M", "MT", "X", "XT"):
        ordered.extend(
            r for r in scrips
            if str(r.get("GROUP") or "").strip().upper() == group and has_isin(r)
        )
    seen: set[str] = set()
    picked: list[dict[str, Any]] = []
    for row in ordered:
        code = str(row.get("SCRIP_CD") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        picked.append(row)
        if len(picked) >= limit:
            break
    return picked


def scrape(days: int = 90, companies: int = 250, refresh: bool = False) -> dict[str, Any]:
    """Harvest announcements. Idempotent: merges into the existing cache by NEWSID."""
    session = RateLimitedSession(headers=BSE_HEADERS)

    scrips = fetch_scrip_master(session, refresh=refresh)
    if not scrips:
        return {"ok": False, "error": "scrip master unavailable", "filings": 0}

    targets = select_companies(scrips, companies)
    log.info("harvesting %d days of announcements for %d companies", days, len(targets))

    existing = read_cache(ANN_CACHE) or []
    by_id: dict[str, dict[str, Any]] = {
        str(r.get("NEWSID")): r for r in existing if r.get("NEWSID")
    }
    before = len(by_id)

    isin_by_code = {str(r.get("SCRIP_CD")): r.get("ISIN_NUMBER") for r in scrips}

    failures = 0
    for idx, row in enumerate(targets, 1):
        code = str(row.get("SCRIP_CD"))
        name = row.get("Scrip_Name")
        try:
            anns = fetch_announcements_for_scrip(session, code, days=days)
        except Exception as exc:  # noqa: BLE001 - one bad scrip must not kill the run
            log.warning("scrip %s (%s) failed: %s", code, name, exc)
            failures += 1
            continue

        for ann in anns:
            news_id = str(ann.get("NEWSID") or "")
            if not news_id:
                continue
            # Attach identity the announcement payload does not carry.
            ann["_ISIN"] = isin_by_code.get(code)
            ann["_SCRIP_CD"] = code
            ann.setdefault("SLONGNAME", name)
            by_id[news_id] = ann

        if idx % 25 == 0 or idx == len(targets):
            log.info("  [%d/%d] %s -> %d announcements cached", idx, len(targets), name, len(by_id))
            write_cache(ANN_CACHE, list(by_id.values()))

    merged = list(by_id.values())
    write_cache(ANN_CACHE, merged)

    result = {
        "ok": True,
        "companies_queried": len(targets),
        "failures": failures,
        "filings_before": before,
        "filings_after": len(merged),
        "new": len(merged) - before,
        "days": days,
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }
    log.info("BSE scrape complete: %s", result)
    return result


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Scrape BSE corporate announcements")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--companies", type=int, default=250)
    p.add_argument("--refresh", action="store_true", help="re-fetch the scrip master")
    args = p.parse_args()
    scrape(days=args.days, companies=args.companies, refresh=args.refresh)
