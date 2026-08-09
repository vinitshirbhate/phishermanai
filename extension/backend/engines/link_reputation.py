"""
Domain reputation with provenance.

Serves the link hover card. The card previously said "no signals" on almost
every link, which is true and useless: most links are fine, and a warning that
is silent 95% of the time trains people to ignore it.

The answer is not to invent signals but to report what was checked. `checked` is
populated on every call, hit or miss, and carries each list's name, entry count
and refresh date, so a clean result is falsifiable rather than a shrug.

Everything runs against snapshots on the user's own machine. Live third-party
lookups stay in threat_feeds.py: explicit, rate-limited, off the hover path.
Only moderate, domain-level lists are loaded; the large malware/DNS feeds are
excluded for memory and are simply absent from `checked`, so reported coverage
matches actual coverage.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from . import domain_intel
from .scamgate import load_domain_set

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FEEDS_DIR = DATA_DIR / "feeds"

# (filename, human label, what it covers). Deliberately a short list: these are
# domain-level, moderate in size, and independently sourced. Large malware/DNS
# feeds are excluded for memory, and their exclusion is visible to the user
# because they simply do not appear in `checked`.
DOMAIN_LISTS = [
    ("phishing_domains_active.txt", "Phishing.Database (active)", "phishing"),
    ("blocklistproject_phishing.txt", "The Blocklist Project — phishing", "phishing"),
    ("scam_blocklist_domains.txt", "Scam domain blocklist", "scam"),
]

_manifest_cache: Optional[dict] = None


def _manifest() -> dict:
    global _manifest_cache
    if _manifest_cache is None:
        p = FEEDS_DIR / "_refresh_manifest.json"
        try:
            _manifest_cache = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _manifest_cache = {}
    return _manifest_cache


def feeds_as_of() -> Optional[str]:
    """Date the bundled feeds were last refreshed, ISO, or None if unknown."""
    raw = _manifest().get("last_refresh")
    if not raw:
        return None
    try:
        return datetime.strptime(raw.split(" UTC")[0], "%Y-%m-%d %H:%M:%S").date().isoformat()
    except Exception:
        return raw.split(" ")[0] if isinstance(raw, str) else None


def _describe(filename: str) -> dict:
    for r in _manifest().get("results", []) or []:
        if r.get("filename") == filename:
            return {"description": r.get("description") or "", "source": r.get("url") or ""}
    return {"description": "", "source": ""}


def _host_variants(host: str) -> list[str]:
    """A domain and its parents: blocklists list `evil.com`, the link is `a.b.evil.com`."""
    host = (host or "").lower().strip(".")
    parts = host.split(".")
    return [".".join(parts[i:]) for i in range(len(parts) - 1)] or ([host] if host else [])


def inspect(url: str) -> dict:
    """
    Reputation for one URL, with provenance.

    Returns `checked` on every call - the list of sources actually consulted and
    how big each was - so a clean result is evidence rather than a shrug.
    """
    raw = (url or "").strip()
    if not raw:
        return {"error": "empty url", "checked": [], "listed": []}
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw

    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        return {"error": "no host", "checked": [], "listed": []}

    variants = _host_variants(host)
    checked: list[dict] = []
    listed: list[dict] = []

    for filename, label, kind in DOMAIN_LISTS:
        entries = load_domain_set(filename)
        if not entries:
            continue                      # absent file: not claimed as checked
        meta = _describe(filename)
        checked.append({
            "list": label,
            "entries": len(entries),
            "kind": kind,
            "description": meta["description"],
            "source": meta["source"],
        })
        for v in variants:
            if v in entries:
                listed.append({"list": label, "kind": kind, "matched": v})
                break

    # domain_intel.analyze() - NOT verify_domain(), which does not exist here.
    # A hasattr() guard silently returned {} and the card lost the whitelist,
    # TLD and typosquat findings without anything reporting a failure.
    intel = {}
    try:
        di = domain_intel.analyze(raw)
        intel = {
            "whitelisted": bool(di.is_whitelisted),
            "https": bool(di.is_https),
            "tld_risk": di.tld_risk,
            "subdomain_depth": di.subdomain_depth,
            "typosquat_target": di.typosquat_target or None,
            "signals": list(di.signals or []),
        }
    except Exception as exc:                      # noqa: BLE001
        intel = {"error": f"domain intel unavailable: {exc}"}

    total = sum(c["entries"] for c in checked)
    return {
        "host": host,
        "listed": listed,
        "checked": checked,
        "lists_checked": len(checked),
        "entries_checked": total,
        "as_of": feeds_as_of(),
        "intel": intel,
        # The honest bound on what a clean result means. The card shows this
        # verbatim rather than paraphrasing it into reassurance.
        "coverage_note": (
            "Not listed on "
            + (f"{len(checked)} blocklist{'s' if len(checked) != 1 else ''} "
               f"covering {total:,} domains" if checked else "any bundled blocklist")
            + (f", as of {feeds_as_of()}." if feeds_as_of() else ".")
            + " A domain registered since then would not appear."
        ) if not listed else None,
    }
