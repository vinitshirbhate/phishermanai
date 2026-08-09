
import os
import sys
import json
from unittest import result
import requests


FIRECRAWL_API_KEY="fc-cd6353d1f44f49859f853bdd9de00363"

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


def check_firecrawl_key():
    try:
        resp = requests.post(
            FIRECRAWL_SCRAPE_URL,
            headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"},
            json={"url": "https://example.com", "formats": ["markdown"]},
            timeout=30,
        )
        if resp.status_code == 401:
            return False, "Firecrawl key rejected (401) — check FIRECRAWL_API_KEY."
        return True, None
    except requests.RequestException as e:
        return False, f"Firecrawl connection failed: {e}"

def firecrawl_scrape(source_url: str):
    payload = {
        "url": source_url,
        "formats": [{"type": "json", "prompt": SCRAPE_PROMPT, "schema": NEWS_SCHEMA}],
        "onlyMainContent": True,
        "blockAds": True,
    }
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
    try:
        resp = requests.post(FIRECRAWL_SCRAPE_URL, headers=headers, json=payload, timeout=90)
        if resp.ok:
            items = resp.json().get("data", {}).get("json", {}).get("news", [])
            for item in items:
                item.setdefault("official", True)
            return items, None
        return [], {"source": source_url, "status": resp.status_code, "error": resp.text}
    except requests.RequestException as e:
        return [], {"source": source_url, "status": None, "error": str(e)}


def firecrawl_search_twitter(query: str, limit: int = 8):
    payload = {
        "query": query,
        "limit": limit,
        "sources": ["web"],
        "includeDomains": ["twitter.com", "x.com"],
        "tbs": "qdr:d",  # last 24h
    }
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
    try:
        resp = requests.post(FIRECRAWL_SEARCH_URL, headers=headers, json=payload, timeout=60)
        if resp.ok:
            results = resp.json().get("data", {}).get("web", []) or resp.json().get("data", [])
            items = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                items.append(
                    {
                        "company": "",
                        "headline": r.get("title", ""),
                        "summary": (r.get("description", "") or r.get("snippet", "") or "")[:200],
                        "source": "Twitter/X",
                        "url": r.get("url", ""),
                        "official": False,
                        "impact": "Medium",
                        "matched_query": query,
                    }
                )
            return items, None
        return [], {"source": f"twitter-search:{query}", "status": resp.status_code, "error": resp.text}
    except requests.RequestException as e:
        return [], {"source": f"twitter-search:{query}", "status": None, "error": str(e)}


def dedupe_by_url(items):
    seen = set()
    out = []
    for item in items:
        u = item.get("url", "")
        if u and u in seen:
            continue
        if u:
            seen.add(u)
        out.append(item)
    return out


def main():
    if not FIRECRAWL_API_KEY:
        sys.exit("Missing environment variable: FIRECRAWL_API_KEY")

    print("Checking Firecrawl key...", file=sys.stderr)
    ok, msg = check_firecrawl_key()
    print(f"  Firecrawl: {'OK' if ok else 'FAILED - ' + msg}", file=sys.stderr)
    if not ok:
        sys.exit(f"Stopping: {msg}")

    errors = []
    official_items = []
    twitter_items = []

    print("Scraping official sources via Firecrawl...", file=sys.stderr)
    for src in OFFICIAL_SOURCES:
        items, err = firecrawl_scrape(src)
        official_items.extend(items)
        if err:
            errors.append(err)
        print(f"  {src}: {len(items)} item(s)" + (" (error)" if err else ""), file=sys.stderr)

    print("Searching X/Twitter via Firecrawl search...", file=sys.stderr)
    for query in TWITTER_QUERIES:
        items, err = firecrawl_search_twitter(query)
        twitter_items.extend(items)
        if err:
            errors.append(err)
        print(f"  '{query}': {len(items)} item(s)" + (" (error)" if err else ""), file=sys.stderr)

    official_items = dedupe_by_url(official_items)
    twitter_items = dedupe_by_url(twitter_items)
    result = {
        "official_news": official_items,
        "twitter_news": twitter_items,
        "counts": {
            "official": len(official_items),
            "twitter": len(twitter_items),
            "total": len(official_items) + len(twitter_items),
        },
        "errors": errors,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()