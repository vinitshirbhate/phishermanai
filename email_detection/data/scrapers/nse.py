"""NSE corporate filings scraper.

NSE rejects bare requests with HTTP 403. The documented workaround is a cookie
handshake: GET nseindia.com with a browser User-Agent to receive the bot-guard
cookies, then reuse that session for the API call.

This is implemented faithfully below. If NSE still blocks us -- which it does
from some networks and datacentre IPs regardless of headers -- we log the
failure loudly and return ok=False. The loader then proceeds with BSE only.

We do NOT fabricate NSE data to fill the gap. BSE alone provides sufficient
ground truth (see data/README.md for actual counts), and a silently faked
corpus would invalidate every number in the evaluation harness.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta
from typing import Any

from data.scrapers.http import RateLimitedSession, read_cache, write_cache

log = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com"
NSE_ANN_URL = "https://www.nseindia.com/api/corporate-announcements"

NSE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

ANN_CACHE = "nse_announcements.json"
STATUS_CACHE = "nse_status.json"


def _handshake(session: RateLimitedSession) -> bool:
    """Prime the session with NSE's bot-guard cookies."""
    log.info("NSE handshake: GET %s", NSE_HOME)
    html = session.get_text(NSE_HOME)
    if html is None:
        log.error("NSE handshake failed -- homepage did not return 200")
        return False
    cookies = session.session.cookies.get_dict()
    log.info("NSE handshake got %d cookies: %s", len(cookies), sorted(cookies)[:6])
    return bool(cookies)


def scrape(days: int = 90) -> dict[str, Any]:
    session = RateLimitedSession(headers=NSE_HEADERS)

    status: dict[str, Any] = {
        "source": "NSE",
        "attempted_at": datetime.now().isoformat(timespec="seconds"),
        "ok": False,
        "reason": None,
        "filings": 0,
    }

    if not _handshake(session):
        status["reason"] = "handshake_failed_403_or_no_cookies"
        write_cache(STATUS_CACHE, status)
        log.error("NSE BLOCKED at handshake. Proceeding with BSE only. "
                  "This is a network-level block, not a code defect.")
        return status

    end = date.today()
    start = end - timedelta(days=days)
    payload = session.get_json(
        NSE_ANN_URL,
        params={
            "index": "equities",
            "from_date": start.strftime("%d-%m-%Y"),
            "to_date": end.strftime("%d-%m-%Y"),
        },
    )

    if not payload:
        status["reason"] = "api_blocked_or_empty_after_handshake"
        write_cache(STATUS_CACHE, status)
        log.error("NSE handshake succeeded but the announcements API returned nothing. "
                  "Proceeding with BSE only.")
        return status

    rows = payload if isinstance(payload, list) else payload.get("data") or []
    existing = read_cache(ANN_CACHE) or []
    by_key = {f"{r.get('symbol')}|{r.get('an_dt')}|{r.get('desc')}": r for r in existing}
    for row in rows:
        by_key[f"{row.get('symbol')}|{row.get('an_dt')}|{row.get('desc')}"] = row

    merged = list(by_key.values())
    write_cache(ANN_CACHE, merged)

    status.update(ok=True, filings=len(merged), reason=None)
    write_cache(STATUS_CACHE, status)
    log.info("NSE scrape complete: %d filings", len(merged))
    return status


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Scrape NSE corporate announcements")
    p.add_argument("--days", type=int, default=90)
    args = p.parse_args()
    scrape(days=args.days)
