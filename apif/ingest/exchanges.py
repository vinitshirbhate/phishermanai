"""NSE/BSE official feeds — corporate announcements and the listed-company universe
used to grow the trust registry.

NSE actively blocks programmatic clients: a bare request returns 401 or hangs. The
workaround is to prime a session against the public site first so the WAF issues cookies,
then reuse them for the API call with browser-like headers. This is fragile by nature and
can break whenever NSE changes its edge configuration, so every function here degrades to
an empty result rather than raising -- yfinance carries the demo-critical market path.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import httpx

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

NSE_BASE = "https://www.nseindia.com"
NSE_ANNOUNCEMENTS = f"{NSE_BASE}/api/corporate-announcements?index=equities"
BSE_ANNOUNCEMENTS_TEMPLATE = (
    "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"
    "?strCat=-1&strPrevDate={prev}&strScrip=&strSearch=P&strToDate={today}"
    "&strType=C&pageno=1"
)


def _bse_url(days_back: int = 5) -> str:
    """BSE returns nothing for an empty date range, so always supply one."""
    today = date.today()
    return BSE_ANNOUNCEMENTS_TEMPLATE.format(
        prev=(today - timedelta(days=days_back)).strftime("%Y%m%d"),
        today=today.strftime("%Y%m%d"),
    )


async def _nse_client() -> httpx.AsyncClient:
    """Client with NSE's WAF cookies already primed."""
    client = httpx.AsyncClient(headers=_BROWSER_HEADERS, timeout=20.0, follow_redirects=True)
    try:
        # This GET exists only to collect cookies; its body is discarded.
        await client.get(NSE_BASE)
    except httpx.HTTPError:
        pass
    return client


async def nse_announcements(limit: int = 50) -> tuple[list[dict[str, Any]], str | None]:
    """Recent NSE corporate announcements. Returns (items, error)."""
    client = await _nse_client()
    try:
        resp = await client.get(NSE_ANNOUNCEMENTS)
        if resp.status_code != 200:
            return [], f"NSE returned HTTP {resp.status_code}"
        payload = resp.json()
    except httpx.HTTPError as exc:
        return [], f"NSE unreachable ({type(exc).__name__})"
    except ValueError:
        return [], "NSE returned non-JSON (likely a WAF challenge page)"
    finally:
        await client.aclose()

    rows = payload if isinstance(payload, list) else payload.get("data", [])
    items = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        items.append({
            "company": row.get("sm_name") or row.get("symbol", ""),
            "headline": row.get("desc") or row.get("attchmntText", ""),
            "summary": (row.get("attchmntText") or "")[:200],
            "source": "NSE",
            "url": row.get("attchmntFile", "") or NSE_BASE,
            "official": True,
            "impact": "Medium",
        })
    return items, None


async def bse_announcements(limit: int = 50) -> tuple[list[dict[str, Any]], str | None]:
    """Recent BSE corporate announcements. Returns (items, error)."""
    # follow_redirects is required: BSE answers this path with a 301 to its canonical
    # host, and httpx does not follow redirects by default.
    try:
        async with httpx.AsyncClient(
            headers={**_BROWSER_HEADERS, "Referer": "https://www.bseindia.com/"},
            timeout=20.0, follow_redirects=True,
        ) as client:
            resp = await client.get(_bse_url())
            if resp.status_code != 200:
                return [], f"BSE returned HTTP {resp.status_code}"
            payload = resp.json()
    except httpx.HTTPError as exc:
        return [], f"BSE unreachable ({type(exc).__name__})"
    except ValueError:
        return [], "BSE returned non-JSON"

    # BSE double-encodes: the JSON body is itself a JSON *string*. It also answers a
    # no-results query with the bare sentinel "No Record Found!", which is not JSON at
    # all -- decoding that blindly raises and looks like a transport failure.
    if isinstance(payload, str):
        if "No Record Found" in payload:
            return [], "BSE reported no announcements for the requested window"
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return [], f"BSE returned an unexpected payload: {payload[:80]!r}"

    rows = payload.get("Table", []) if isinstance(payload, dict) else []
    items = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        items.append({
            "company": row.get("SLONGNAME", ""),
            "headline": row.get("NEWSSUB", ""),
            "summary": (row.get("HEADLINE") or "")[:200],
            "source": "BSE",
            "url": row.get("NSURL", "") or "https://www.bseindia.com",
            "official": True,
            "impact": "Medium",
        })
    return items, None


async def run_exchange_ingestion() -> dict[str, Any]:
    """Pull both exchanges into the content store. Partial success is normal."""
    from . import store

    nse_items, nse_err = await nse_announcements()
    bse_items, bse_err = await bse_announcements()

    new_rows = store.upsert_content(nse_items + bse_items, channel="web")
    errors = [e for e in (nse_err, bse_err) if e]
    return {
        "nse": len(nse_items),
        "bse": len(bse_items),
        "new_rows": new_rows,
        "errors": errors,
    }
