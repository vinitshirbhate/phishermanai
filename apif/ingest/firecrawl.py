"""Firecrawl ingestion of official market sources and X/Twitter chatter.

Refactored from fake_propaganda/main.py. The source list, queries, extraction schema and
prompt are carried over unchanged -- they are well tuned and produce good output.

Two substantive changes:
  - The API key comes from settings instead of being hardcoded in the module.
  - Sources are fetched concurrently. The original looped serially over 7 sources and 6
    queries with timeouts of 90s and 60s, so a slow run could approach 15 minutes; as a
    request-triggered background job that is unusable. asyncio.gather makes it bounded
    by the slowest single source.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"

OFFICIAL_SOURCES = [
    "https://www.moneycontrol.com",
    "https://economictimes.indiatimes.com/markets",
    "https://www.business-standard.com/markets",
    "https://www.livemint.com/market",
    "https://www.nseindia.com",
    "https://www.bseindia.com",
    "https://www.sebi.gov.in",
]

TWITTER_QUERIES = [
    "Indian stock market earnings results today",
    "NSE BSE listed company acquisition OR merger",
    "SEBI order OR action against company",
    "Indian stock block deal OR bulk deal today",
    "listed company fraud OR scam OR deepfake India",
    "Nifty Sensex breaking news today",
]

NEWS_SCHEMA = {
    "type": "object",
    "properties": {
        "news": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "source": {"type": "string"},
                    "url": {"type": "string"},
                    "official": {"type": "boolean"},
                    "impact": {"type": "string", "enum": ["High", "Medium", "Low"]},
                },
                "required": ["headline", "summary", "source", "url", "official", "impact"],
            },
        }
    },
    "required": ["news"],
}

SCRAPE_PROMPT = """
Extract news items from this page that could move a stock price:
earnings, M&A, CEO/CFO changes, government/SEBI policy or action,
fundraising, large orders, fraud, deepfake/phishing scams targeting
a listed company, market manipulation, block deals, bankruptcy.

Ignore memes, opinion pieces, duplicate stories, and pure promotions.
For each item return: company, headline, one-line summary (<=40 words),
source, url, whether it's an official source (true/false), and impact
(High/Medium/Low).
"""


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().firecrawl_api_key}",
        "Content-Type": "application/json",
    }


def dedupe_by_url(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        u = item.get("url", "")
        if u and u in seen:
            continue
        if u:
            seen.add(u)
        out.append(item)
    return out


async def _scrape(client: httpx.AsyncClient, source_url: str):
    payload = {
        "url": source_url,
        "formats": [{"type": "json", "prompt": SCRAPE_PROMPT, "schema": NEWS_SCHEMA}],
        "onlyMainContent": True,
        "blockAds": True,
    }
    try:
        resp = await client.post(FIRECRAWL_SCRAPE_URL, headers=_headers(), json=payload,
                                 timeout=90)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("json", {}).get("news", [])
            for item in items:
                item.setdefault("official", True)
            return items, None
        return [], {"source": source_url, "status": resp.status_code, "error": resp.text[:500]}
    except httpx.HTTPError as exc:
        return [], {"source": source_url, "status": None, "error": str(exc)}


async def _search_twitter(client: httpx.AsyncClient, query: str, limit: int = 8):
    payload = {
        "query": query,
        "limit": limit,
        "sources": ["web"],
        "includeDomains": ["twitter.com", "x.com"],
        "tbs": "qdr:d",  # last 24h
    }
    try:
        resp = await client.post(FIRECRAWL_SEARCH_URL, headers=_headers(), json=payload,
                                 timeout=60)
        if resp.status_code != 200:
            return [], {"source": f"twitter-search:{query}", "status": resp.status_code,
                        "error": resp.text[:500]}
        body = resp.json()
        results = body.get("data", {}).get("web", []) or body.get("data", [])
        items = []
        for r in results:
            if not isinstance(r, dict):
                continue
            items.append({
                "company": "",
                "headline": r.get("title", ""),
                "summary": (r.get("description", "") or r.get("snippet", "") or "")[:200],
                "source": "Twitter/X",
                "url": r.get("url", ""),
                "official": False,
                "impact": "Medium",
                "matched_query": query,
            })
        return items, None
    except httpx.HTTPError as exc:
        return [], {"source": f"twitter-search:{query}", "status": None, "error": str(exc)}


LINK_PREVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "text": {"type": "string"},
        "source_name": {"type": "string"},
        "media": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["video", "audio", "image"]},
                    "url": {"type": "string", "format": "uri"},
                    "description": {"type": "string"},
                },
                "required": ["type", "url"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "summary", "text", "media"],
}

LINK_PREVIEW_PROMPT = """
Extract the content from this web page. Return a JSON object with:
- title: page title or headline
- summary: one short summary sentence
- text: the main post text or article body
- source_name: the site or author name if available
- media: an array of found media items, each with type audio, video, or image, a public URL, and a short description
Return only JSON matching the schema.
"""


def _normalize_preview(raw: dict[str, Any], url: str) -> dict[str, Any]:
    preview = {
        "url": url,
        "title": raw.get("title", ""),
        "summary": raw.get("summary", ""),
        "text": raw.get("text", ""),
        "source_name": raw.get("source_name"),
        "media": [],
    }
    for item in raw.get("media", []) or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        item_url = item.get("url")
        if item_type not in {"video", "audio", "image"} or not item_url:
            continue
        preview["media"].append({
            "type": item_type,
            "url": item_url,
            "description": item.get("description", ""),
        })
    return preview


async def preview_link(client: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    payload = {
        "url": page_url,
        "formats": [
            {"type": "json", "prompt": LINK_PREVIEW_PROMPT, "schema": LINK_PREVIEW_SCHEMA}
        ],
        "onlyMainContent": True,
        "blockAds": True,
    }
    resp = await client.post(FIRECRAWL_SCRAPE_URL, headers=_headers(), json=payload, timeout=90)
    if resp.status_code != 200:
        raise httpx.HTTPStatusError("Firecrawl preview failed", request=resp.request, response=resp)
    body = resp.json()
    raw = body.get("data", {}).get("json", {})
    return _normalize_preview(raw, page_url)


async def download_media(url: str, out_path: Path) -> None:
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)


async def check_key() -> tuple[bool, str | None]:
    if not get_settings().firecrawl_api_key:
        return False, "FIRECRAWL_API_KEY not set"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                FIRECRAWL_SCRAPE_URL, headers=_headers(),
                json={"url": "https://example.com", "formats": ["markdown"]}, timeout=30,
            )
        if resp.status_code == 401:
            return False, "Firecrawl key rejected (401)"
        return True, None
    except httpx.HTTPError as exc:
        return False, f"Firecrawl connection failed: {exc}"


async def run_ingestion() -> dict[str, Any]:
    """Scrape official sources and search X/Twitter concurrently, then persist."""
    from . import store

    settings = get_settings()
    if not settings.firecrawl_api_key:
        return {"error": "FIRECRAWL_API_KEY not set", "official": 0, "twitter": 0}

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_scrape(client, src) for src in OFFICIAL_SOURCES],
            *[_search_twitter(client, q) for q in TWITTER_QUERIES],
            return_exceptions=True,
        )

    official: list[dict[str, Any]] = []
    twitter: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    split = len(OFFICIAL_SOURCES)

    for idx, outcome in enumerate(results):
        if isinstance(outcome, BaseException):
            errors.append({"source": "unknown", "error": str(outcome)})
            continue
        items, err = outcome
        (official if idx < split else twitter).extend(items)
        if err:
            errors.append(err)

    official = dedupe_by_url(official)
    twitter = dedupe_by_url(twitter)

    new_official = store.upsert_content(official, channel="web")
    new_twitter = store.upsert_content(twitter, channel="twitter")

    return {
        "official": len(official),
        "twitter": len(twitter),
        "new_official": new_official,
        "new_twitter": new_twitter,
        "errors": errors,
    }
