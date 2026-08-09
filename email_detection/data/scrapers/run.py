"""Scraper CLI.

    python -m data.scrapers.run --source bse --days 90
    python -m data.scrapers.run --source nse --days 90
    python -m data.scrapers.run --source all --days 90

Run once during development. The demo path reads only data/cache/.
"""

from __future__ import annotations

import argparse
import json
import logging

from data.scrapers import bse, nse


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    p = argparse.ArgumentParser(description="PhishermanAI data scrapers")
    p.add_argument("--source", choices=["bse", "nse", "all"], default="all")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--companies", type=int, default=250, help="BSE only: how many scrips to harvest")
    p.add_argument("--refresh", action="store_true", help="BSE only: re-fetch the scrip master")
    args = p.parse_args()

    results = {}
    if args.source in ("bse", "all"):
        results["bse"] = bse.scrape(days=args.days, companies=args.companies, refresh=args.refresh)
    if args.source in ("nse", "all"):
        results["nse"] = nse.scrape(days=args.days)

    print(json.dumps(results, indent=2))

    if results.get("nse") and not results["nse"].get("ok"):
        print("\nNOTE: NSE was blocked (%s). BSE data is sufficient ground truth; "
              "this limitation is documented in data/README.md." % results["nse"].get("reason"))


if __name__ == "__main__":  # pragma: no cover
    main()
