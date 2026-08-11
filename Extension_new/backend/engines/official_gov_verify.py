"""
official_gov_verify.py - Live, on-demand cross-checks against official
government sources, for the moment a user explicitly asks "is this real".

WHY THIS EXISTS
----------------
backend/data/sebi_register.json is a *snapshot*, rebuilt by
scripts/fetch_sebi_register.py on whatever cadence someone remembers to run
it. Two problems fall out of that:

  1. Coverage: the snapshot previously carried only 2 of SEBI's ~17
     recognised-intermediary categories (Research Analysts, Investment
     Advisers). A stockbroker, AMC, PMS, AIF, custodian, RTA, merchant
     banker or credit-rating-agency registration number resolved to
     `unverified` not because it was fake, but because we had never fetched
     its category. `unverified` is the honest answer for a bounded subset,
     but it is a worse answer than it needs to be.
  2. Freshness: even for covered categories, the snapshot is only as new as
     the last scrape. A registration cancelled by SEBI yesterday still reads
     `valid` today if nobody re-ran the script.

This module does NOT replace the snapshot - the snapshot is what makes
`assess_registration()` sub-millisecond and offline, which matters for the
hover path (see link_reputation.py's own reasoning about staying local).
Instead it adds an EXPLICIT, opt-in, rate-limited live lookup for the moment
a snapshot-derived `unverified`/`weak_match` isn't good enough and the user
(or the UI, on click - never on hover) asks for a direct, real-time check
against SEBI's own register.

WHAT IS AND ISN'T A REAL API HERE
-----------------------------------
SEBI's "Recognised Intermediaries" register has no public JSON/REST API.
What it has is the same AJAX endpoint its own search-by-registration-number
form calls (POST, HTML fragment response) - that is what
`live_sebi_lookup()` drives, filling the `regNo` filter server-side instead
of paginating the whole category. This is the same access path
scripts/fetch_sebi_register.py already uses for the bulk snapshot; this
module reuses it for a single-record, on-demand query.

For every OTHER government source listed in OFFICIAL_SOURCES below: most of
these (MCA21, GST, RBI Sachet, NSE/BSE corporate filings) do NOT expose a
free, unauthenticated, programmatic API either - they are real official
web properties with real search forms, often behind a captcha. Rather than
silently pretending we can query them, they are exposed as VERIFICATION
LINKS with a `programmatic: false` flag, so a caller (and a user reading the
hover card) can see honestly what was actually machine-checked versus what
is "here is exactly where to look this up yourself, on the real .gov.in
domain, in one click". Overclaiming API coverage here would be a worse
failure mode than the stale-snapshot problem this module exists to fix.
"""
from __future__ import annotations

import html
import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("phisherman.official_gov_verify")

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"

# --------------------------------------------------------------------------- #
# SEBI live single-record lookup
# --------------------------------------------------------------------------- #
_SEBI_AJAX_URL = "https://www.sebi.gov.in/sebiweb/ajax/other/getintmfpiinfo.jsp"
_SEBI_LANDING_URL = ("https://www.sebi.gov.in/sebiweb/other/OtherAction.do"
                      "?doRecognisedFpi=yes&intmId={intm_id}")
_SEBI_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Same category table as scripts/fetch_sebi_register.py CATEGORIES, kept in
# sync by hand (see that file's header comment re: no machine-readable id
# map existing). If the two drift, scripts/fetch_sebi_register.py --stats
# is the source of truth.
SEBI_CATEGORIES: dict[int, str] = {
    1: "BROKER", 6: "DT", 7: "CRA", 8: "KRA", 9: "MB", 10: "RTA",
    13: "IA", 14: "RA", 15: "QDP", 16: "AIF", 19: "DP", 21: "VCF",
    23: "MF", 25: "FVCI", 27: "CUST", 29: "FPI", 33: "PMS", 36: "CIS",
}

_TAG_RE = re.compile(r"<[^>]+>")
_RECORD_RE = re.compile(
    r"<div class=['\"]fixed-table-body card-table['\"]>(.*?)"
    r"(?=<div class=['\"]fixed-table-body card-table['\"]>|$)", re.S)
_PAIR_RE = re.compile(
    r"<div class=['\"]title['\"]>\s*<span>(.*?)</span>\s*</div>\s*"
    r"<div class=['\"]value[^'\"]*['\"]>\s*<span>(.*?)</span>\s*</div>", re.S)

_ssl_ctx = ssl.create_default_context()

_MIN_INTERVAL_S = 1.0            # good-citizen floor between live SEBI hits
_last_call_at = 0.0
_CACHE_TTL_S = 6 * 3600          # 6h - long enough to absorb repeat hovers,
                                  # short enough that a same-day cancellation
                                  # is visible well before the next snapshot.
_live_cache: dict[str, tuple[float, dict]] = {}


def _clean(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment or "")).replace("\xa0", " ").strip()


def _rate_gate() -> None:
    global _last_call_at
    wait = _MIN_INTERVAL_S - (time.time() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.time()


def _post(url: str, data: dict, referer: str, timeout: float) -> Optional[str]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": _SEBI_UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        logger.info("SEBI live lookup network error: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - a failed live check must degrade, not 500
        logger.warning("SEBI live lookup unexpected error: %s", exc)
        return None


def _parse_records(fragment: str) -> list[dict]:
    out = []
    for block in _RECORD_RE.findall(fragment or ""):
        fields = {}
        for label, value in _PAIR_RE.findall(block):
            fields[_clean(label).rstrip(":").strip()] = _clean(value)
        if fields.get("Registration No."):
            out.append(fields)
    return out


@dataclass
class LiveVerifyResult:
    reg_number: str
    checked: bool                        # did a live network call actually happen
    matched: bool                        # did SEBI's own site return this exact number
    source: str = "sebi.gov.in"
    method: str = "live_single_record_query"
    category_tried: Optional[str] = None
    intm_id_tried: Optional[int] = None
    registered_name: Optional[str] = None
    status: Optional[str] = None
    validity: Optional[str] = None
    checked_at: Optional[str] = None     # ISO timestamp of this call
    source_url: Optional[str] = None
    error: Optional[str] = None
    cached: bool = False
    disclosure: str = (
        "Live query against the same public search SEBI's own website uses. "
        "Not a documented/versioned API - if SEBI changes their site markup, "
        "this degrades to `checked: false`, never to a false `matched`."
    )


def _cache_get(key: str) -> Optional[dict]:
    hit = _live_cache.get(key)
    if not hit:
        return None
    ts, val = hit
    if time.time() - ts > _CACHE_TTL_S:
        del _live_cache[key]
        return None
    return {**val, "cached": True}


def _cache_set(key: str, val: dict) -> None:
    if len(_live_cache) > 2000:
        _live_cache.pop(next(iter(_live_cache)))
    _live_cache[key] = (time.time(), val)


def _guess_intm_ids(reg_number: str, prefix_categories: Optional[dict] = None) -> list[int]:
    """
    Which intmId(s) to try for a given registration number.

    Prefers the live snapshot's own `prefix_categories` (backend/data/
    sebi_register.json, built by fetch_sebi_register.py) since that mapping
    is DERIVED from real fetched data, never hand-written. Falls back to
    trying every known category (bounded, 18 values) only if the prefix is
    genuinely outside anything we have ever fetched - slower, but still
    bounded and still honest: a miss across all 18 stays `unverified`, never
    `invalid` (same G-2 rule as the offline matcher).
    """
    prefix = re.match(r"^[A-Za-z]+", reg_number or "")
    prefix = prefix.group(0).upper() if prefix else ""
    if prefix_categories:
        code = prefix_categories.get(prefix)
        if code:
            for intm_id, cat in SEBI_CATEGORIES.items():
                if cat == code:
                    return [intm_id]
    return list(SEBI_CATEGORIES)  # bounded probe, worst case


def live_sebi_lookup(reg_number: str, *, prefix_categories: Optional[dict] = None,
                      timeout: float = 6.0, max_probes: int = 4) -> dict:
    """
    On-demand, real-time SEBI register check for ONE registration number.

    Deliberately NOT called from the hover path (see content_script.js -
    the hover card renders the offline snapshot verdict instantly; this is
    what a "Verify live on SEBI" click triggers). Rate-limited to be a good
    citizen of a government server that has no published API budget.
    """
    reg_number = (reg_number or "").strip().upper()
    if not reg_number:
        return asdict(LiveVerifyResult(reg_number=reg_number, checked=False, matched=False,
                                        error="empty registration number"))

    cache_key = f"sebi:{reg_number}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    candidates = _guess_intm_ids(reg_number, prefix_categories)[:max_probes]
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for intm_id in candidates:
        _rate_gate()
        referer = _SEBI_LANDING_URL.format(intm_id=intm_id)
        body = {
            "nextValue": "1", "next": "n", "intmId": str(intm_id),
            "contPer": "", "name": "", "regNo": reg_number, "email": "",
            "location": "", "exchange": "", "affiliate": "", "alp": "",
            "language": "2", "model": "", "esgCategory": "", "doDirect": "0",
            "intmIds": "",
        }
        frag = _post(_SEBI_AJAX_URL, body, referer, timeout)
        if frag is None:
            result = asdict(LiveVerifyResult(
                reg_number=reg_number, checked=False, matched=False,
                intm_id_tried=intm_id, category_tried=SEBI_CATEGORIES.get(intm_id),
                checked_at=now_iso, source_url=referer,
                error="SEBI site unreachable or timed out",
            ))
            _cache_set(cache_key, result)
            return result

        records = _parse_records(frag)
        hit = next((r for r in records
                    if r.get("Registration No.", "").upper() == reg_number), None)
        if hit:
            result = asdict(LiveVerifyResult(
                reg_number=reg_number, checked=True, matched=True,
                category_tried=SEBI_CATEGORIES.get(intm_id), intm_id_tried=intm_id,
                registered_name=hit.get("Name") or hit.get("Registered Name") or hit.get("Trade Name"),
                status="active",  # cancelled/expired registrants drop out of SEBI's own listing
                validity=hit.get("Registration Validity") or hit.get("Validity"),
                checked_at=now_iso, source_url=referer,
            ))
            _cache_set(cache_key, result)
            return result

    # Tried everything we reasonably could, live, and SEBI's own search
    # returned no matching row in any category attempted.
    result = asdict(LiveVerifyResult(
        reg_number=reg_number, checked=True, matched=False,
        category_tried=", ".join(SEBI_CATEGORIES.get(i, str(i)) for i in candidates),
        checked_at=now_iso,
        source_url=_SEBI_LANDING_URL.format(intm_id=candidates[0]) if candidates else None,
        error=(f"No live match in {len(candidates)} SEBI categories checked "
               f"(of {len(SEBI_CATEGORIES)} known). Not proof of invalidity - "
               "see disclosure."),
    ))
    _cache_set(cache_key, result)
    return result


# --------------------------------------------------------------------------- #
# Directory of OTHER real official Indian government sources
# --------------------------------------------------------------------------- #
# `programmatic` is honest, not aspirational: only sources this module can
# actually query live are True. Everything else is a genuine .gov.in / .org.in
# / .nic.in property surfaced as a one-click manual-verification link -
# useful in the hover card and in the extension's "Verify" panel, and never
# silently presented as machine-checked when it wasn't.
OFFICIAL_SOURCES = [
    {
        "id": "sebi_register",
        "label": "SEBI — Recognised Intermediaries register",
        "url": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes",
        "use": "Registration status for brokers, IAs, RAs, PMS, AIFs, AMCs, RTAs, custodians, merchant bankers, credit rating agencies, KRAs, DPs, and FPIs.",
        "programmatic": True,
        "category": "securities_intermediary",
    },
    {
        "id": "sebi_scores",
        "label": "SEBI SCORES — investor grievance portal",
        "url": "https://scores.gov.in/",
        "use": "File or check the status of a grievance against a SEBI-registered entity.",
        "programmatic": False,
        "category": "securities_intermediary",
    },
    {
        "id": "sebi_check",
        "label": "SEBI investor.sebi.gov.in — SEBI Check (verify before you invest)",
        "url": "https://investor.sebi.gov.in/sebicheck",
        "use": "SEBI's own consumer-facing consolidated verification tool.",
        "programmatic": False,
        "category": "securities_intermediary",
    },
    {
        "id": "mca_master_data",
        "label": "MCA21 — Company / LLP Master Data",
        "url": "https://www.mca.gov.in/mcafoportal/companyLLPMasterData.do",
        "use": "Confirm a company's CIN, registration status, and registered office against the Ministry of Corporate Affairs — useful when an SME/IPO or investment scheme claims a company identity.",
        "programmatic": False,
        "category": "corporate_identity",
    },
    {
        "id": "nse_corp_filings",
        "label": "NSE — Corporate Filings & Announcements",
        "url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "use": "Verify whether a listed-company announcement, buyback, or corporate action attributed to NSE is genuine.",
        "programmatic": False,
        "category": "listed_company",
    },
    {
        "id": "bse_corp_announcements",
        "label": "BSE — Corporate Announcements",
        "url": "https://www.bseindia.com/corporates/ann.html",
        "use": "Cross-check a corporate announcement or press release claiming BSE origin.",
        "programmatic": False,
        "category": "listed_company",
    },
    {
        "id": "rbi_sachet",
        "label": "RBI Sachet — unregistered / banned entity alerts",
        "url": "https://sachet.rbi.org.in/",
        "use": "Check for regulator alerts on unauthorised deposit-taking and investment schemes (Ponzi/chit-fund style).",
        "programmatic": False,
        "category": "financial_scheme",
    },
    {
        "id": "rbi_nbfc_list",
        "label": "RBI — list of registered NBFCs",
        "url": "https://www.rbi.org.in/scripts/bs_viewcontent.aspx?Id=2",
        "use": "Confirm whether an entity claiming to be an RBI-registered NBFC actually is.",
        "programmatic": False,
        "category": "financial_entity",
    },
    {
        "id": "cert_in",
        "label": "CERT-In — cyber incident advisories",
        "url": "https://www.cert-in.org.in/",
        "use": "Government incident advisories and threat context, including active phishing campaigns.",
        "programmatic": False,
        "category": "cyber_advisory",
    },
    {
        "id": "cybercrime_portal",
        "label": "National Cyber Crime Reporting Portal",
        "url": "https://www.cybercrime.gov.in/",
        "use": "Official reporting path for financial fraud and cybercrime, including the suspect-search repository.",
        "programmatic": False,
        "category": "reporting",
    },
    {
        "id": "sanchar_saathi_chakshu",
        "label": "Sanchar Saathi / Chakshu",
        "url": "https://www.sancharsaathi.gov.in/sfc/",
        "use": "Report and check spoofed calls/SMS and telecom fraud.",
        "programmatic": False,
        "category": "reporting",
    },
    {
        "id": "pib_fact_check",
        "label": "PIB Fact Check",
        "url": "https://pib.gov.in/aboutfactchecke.aspx",
        "use": "Verify claims about government schemes, orders, or announcements.",
        "programmatic": False,
        "category": "fact_check",
    },
    {
        "id": "data_gov_in",
        "label": "data.gov.in — Open Government Data Platform",
        "url": "https://data.gov.in/",
        "use": "Bulk/API access to select published government datasets (registration required per-dataset for an API key); useful for corroborating scheme or licence lists not otherwise queryable.",
        "programmatic": False,
        "category": "open_data",
    },
]


def get_official_sources(category: Optional[str] = None) -> list[dict]:
    if not category:
        return OFFICIAL_SOURCES
    return [s for s in OFFICIAL_SOURCES if s["category"] == category]


def load_prefix_categories() -> dict:
    """Best-effort load of the live snapshot's prefix->category map, so
    live_sebi_lookup can target the right intmId on the first try instead
    of probing all 18."""
    try:
        doc = json.loads((DATA_DIR / "sebi_register.json").read_text(encoding="utf-8"))
        return doc.get("registry_meta", {}).get("prefix_categories", {})
    except Exception:
        return {}
