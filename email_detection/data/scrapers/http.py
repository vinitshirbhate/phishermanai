"""Shared HTTP client for the one-time scrapers.

Rate limited to 1 request/second with exponential backoff, per the hard
constraint in the project brief. These scrapers run ONCE during development and
write JSON to data/cache/. Nothing in the demo request path imports this module.
"""

from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / "cache"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

MIN_INTERVAL_SEC = 1.0


class RateLimitedSession:
    """requests.Session with a floor on inter-request delay and retry/backoff."""

    def __init__(self, headers: dict[str, str] | None = None, min_interval: float = MIN_INTERVAL_SEC):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})
        if headers:
            self.session.headers.update(headers)
        self.min_interval = min_interval
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        retries: int = 3,
        timeout: int = 45,
    ) -> Any | None:
        """GET and parse JSON. Returns None after exhausting retries.

        Returning None rather than raising is deliberate: a single blocked scrip
        must not abort a 700-request harvest.
        """
        last_err: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                if resp.status_code == 200:
                    text = resp.text.strip()
                    if not text:
                        return None
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        log.warning("non-JSON response from %s: %.120s", url, text)
                        return None
                if resp.status_code in (403, 401):
                    log.warning("blocked (%s) on %s", resp.status_code, url)
                    return None
                last_err = RuntimeError(f"HTTP {resp.status_code}")
            except requests.RequestException as exc:
                last_err = exc

            backoff = (2**attempt) + random.uniform(0, 0.5)
            log.debug("retry %s/%s after %.1fs (%s)", attempt + 1, retries, backoff, last_err)
            time.sleep(backoff)

        log.warning("giving up on %s: %s", url, last_err)
        return None

    def get_bytes(self, url: str, *, timeout: int = 60) -> bytes | None:
        """GET raw bytes (PDF attachments). Returns None on any non-200."""
        self._throttle()
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.content
            log.debug("HTTP %s for %s", resp.status_code, url)
        except requests.RequestException as exc:
            log.debug("request failed for %s: %s", url, exc)
        return None

    def get_text(self, url: str, *, timeout: int = 45) -> str | None:
        self._throttle()
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            log.warning("HTTP %s on %s", resp.status_code, url)
        except requests.RequestException as exc:
            log.warning("request failed for %s: %s", url, exc)
        return None


def cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def write_cache(name: str, payload: Any) -> Path:
    path = cache_path(name)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("wrote %s (%.1f KB)", path.name, path.stat().st_size / 1024)
    return path


def read_cache(name: str) -> Any | None:
    path = cache_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("corrupt cache file %s", path)
        return None
