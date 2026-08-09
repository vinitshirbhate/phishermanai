"""SEBI registered-intermediary scraper.

Retrieved: 2026-08-06 / 2026-08-07.

SEBI publishes each intermediary category at

    /sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=<N>

but that view is paginated 25 rows at a time behind a Struts form, which makes
it painful to harvest. The page's own "export to excel" control calls

    /sebiweb/other/IntmExportAction.do?intmId=<N>

which returns the COMPLETE category as a legacy BIFF .xls. We use that: one
request per category instead of hundreds of paginated POSTs, and it is the
site's own supported export path.

Why this matters for detection
------------------------------
This gives us real registration numbers paired with the real registered NAME.
That pairing is what makes the REG_NO_NAME_MISMATCH check meaningful: a
fraudster who pastes a genuine INZ/INA number belonging to somebody else is
caught, which a pure format check could never do.

The registered e-mail addresses also yield legitimate sending domains, which
feed the domain map.
"""

from __future__ import annotations

import argparse
import html
import logging
import re
from datetime import datetime
from typing import Any

import requests
import urllib3
import xlrd

from data.scrapers.http import BROWSER_UA, read_cache, write_cache

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)

LIST_URL = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do"
EXPORT_URL = "https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do"

CACHE = "sebi_intermediaries.json"

# intmId -> (our EntityType, human label). Discovered by enumerating intmId and
# reading the category title each export writes into row 0.
# AIF/VCF/FVCI categories exist too but are institutional funds, not entities a
# retail investor gets impersonated messages from, so they are omitted.
CATEGORIES: dict[int, tuple[str, str]] = {
    2: ("BROKER", "Stock Brokers"),
    5: ("BANKER_TO_ISSUE", "Bankers to an Issue"),
    6: ("DEBENTURE_TRUSTEE", "Debenture Trustees"),
    7: ("CREDIT_RATING_AGENCY", "Credit Rating Agencies"),
    8: ("KRA", "KYC Registration Agencies"),
    9: ("MERCHANT_BANKER", "Merchant Bankers"),
    10: ("RTA", "Registrars to an Issue / Share Transfer Agents"),
    13: ("RIA", "Investment Advisers"),
    14: ("RESEARCH_ANALYST", "Research Analysts"),
    18: ("DEPOSITORY_PARTICIPANT", "Depository Participants - NSDL"),
    19: ("DEPOSITORY_PARTICIPANT", "Depository Participants - CDSL"),
    23: ("MUTUAL_FUND", "Mutual Funds"),
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Referer": "https://www.sebi.gov.in/intermediaries.html",
    })
    return s


def _parse_workbook(content: bytes) -> tuple[str, list[dict[str, Any]]]:
    """Parse a SEBI export .xls.

    Layout: row 0 is the category title, rows 1-2 are a two-level header
    (row 1 groups columns under 'Address'/'Correspondence Address'/'Validity',
    row 2 holds the real column names), data starts at row 3.
    """
    wb = xlrd.open_workbook(file_contents=content)
    sheet = wb.sheet_by_index(0)
    if sheet.nrows < 4:
        return "", []

    title = str(sheet.cell_value(0, 0)).strip()
    headers = [str(c).strip() for c in sheet.row_values(2)]

    # The two 'Address'/'Email-Id'/... blocks repeat, so disambiguate by first
    # occurrence -- we only want the primary (registered) address block.
    seen: dict[str, int] = {}
    keys: list[str] = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            keys.append(f"{h}__corr")
        else:
            seen[h] = 1
            keys.append(h)

    rows: list[dict[str, Any]] = []
    for r in range(3, sheet.nrows):
        values = sheet.row_values(r)
        rec = {}
        for k, v in zip(keys, values):
            if not k:
                continue
            if isinstance(v, float) and v.is_integer():
                v = str(int(v))
            rec[k] = str(v).strip()
        if rec.get("Name"):
            rows.append(rec)
    return title, rows


def fetch_category(session: requests.Session, intm_id: int) -> tuple[str, list[dict[str, Any]]]:
    # Visit the list page first so the session carries a jsessionid; the export
    # action rejects a cold request.
    session.get(LIST_URL, params={"doRecognisedFpi": "yes", "intmId": str(intm_id)},
                timeout=45, verify=False)
    resp = session.get(EXPORT_URL, params={"intmId": str(intm_id)}, timeout=120, verify=False)
    if resp.status_code != 200 or len(resp.content) < 5000:
        log.warning("intmId=%s export failed (status=%s len=%s)", intm_id, resp.status_code, len(resp.content))
        return "", []
    try:
        return _parse_workbook(resp.content)
    except Exception as exc:  # noqa: BLE001 - a malformed export must not abort the run
        log.warning("intmId=%s parse failed: %s", intm_id, exc)
        return "", []


def scrape(only: list[int] | None = None) -> dict[str, Any]:
    session = _session()
    targets = only or list(CATEGORIES)

    existing = read_cache(CACHE) or {}
    records: dict[str, dict[str, Any]] = {
        r["registration_no"]: r
        for r in existing.get("records", [])
        if r.get("registration_no")
    }
    unregistered_kept = [r for r in existing.get("records", []) if not r.get("registration_no")]

    per_category: dict[str, int] = {}
    for intm_id in targets:
        entity_type, label = CATEGORIES.get(intm_id, ("OTHER_INTERMEDIARY", f"intmId={intm_id}"))
        log.info("fetching SEBI category %s (intmId=%s) ...", label, intm_id)
        title, rows = fetch_category(session, intm_id)
        if not rows:
            per_category[label] = 0
            continue

        kept = 0
        for row in rows:
            reg = (row.get("Registration No.") or "").strip()
            rec = {
                "name": row.get("Name", "").strip(),
                "registration_no": reg,
                "entity_type": entity_type,
                "category_label": label,
                "source_title": title,
                "email": (row.get("Email-Id") or "").strip().lower(),
                "telephone": (row.get("Telephone") or "").strip(),
                "city": (row.get("City") or "").strip(),
                "state": (row.get("State") or "").strip(),
                "valid_from": (row.get("From") or "").strip(),
                "valid_to": (row.get("To") or "").strip(),
                "intm_id": intm_id,
            }
            if reg:
                records[reg] = rec
            else:
                unregistered_kept.append(rec)
            kept += 1
        per_category[label] = kept
        log.info("  %s -> %d rows", label, kept)

    payload = {
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
        "source": "https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do",
        "per_category": per_category,
        "records": list(records.values()) + unregistered_kept,
    }
    write_cache(CACHE, payload)
    log.info("SEBI scrape complete: %d intermediaries across %d categories",
             len(payload["records"]), len(per_category))
    return {"ok": True, "total": len(payload["records"]), "per_category": per_category}


# --------------------------------------------------------------------------
# Live single-entity verification
# --------------------------------------------------------------------------
#
# The bulk export above is our primary read path: offline, fast, deterministic.
# But SEBI's search form also accepts a registration number and returns just
# that entity in about a second, which makes a targeted live confirmation
# practical where a live bulk sync would not be.
#
# The division of labour:
#
#   cached register  -> every verification, always available, no network
#   live lookup      -> optional confirmation of ONE registration number,
#                       triggered explicitly, with a hard timeout and silent
#                       fallback to cache
#
# It is never on the demo path. A registration can be suspended or cancelled
# between refreshes, so when a user wants certainty about a specific number,
# this closes that gap without making every verification depend on SEBI being
# reachable.

NAME_RE = re.compile(
    r'<div class="title"><span>Name</span></div><div class="value[^"]*"><span>(.*?)</span>', re.S
)
REG_RE = re.compile(
    r'<div class="title"><span>Registration No\.</span></div><div class="value[^"]*"><span>(.*?)</span>', re.S
)
COUNT_RE = re.compile(r"(\d+)\s*to\s*(\d+)\s*of\s*(\d+)\s*records")

# Registration-number prefix -> the intmId whose register to search.
REG_PREFIX_TO_INTM: list[tuple[str, int]] = [
    ("INZ", 2), ("INB", 2), ("INF", 2),
    ("INBI", 5), ("IND", 6),
    ("IN/CRA", 7), ("IN/KRA", 8),
    ("INM", 9), ("INR", 10), ("INA", 13), ("INH", 14),
    ("IN-DP", 18), ("MF/", 23),
]


def intm_id_for_registration(reg_no: str) -> int | None:
    reg = (reg_no or "").strip().upper()
    for prefix, intm_id in sorted(REG_PREFIX_TO_INTM, key=lambda p: -len(p[0])):
        if reg.startswith(prefix):
            return intm_id
    return None


def lookup_registration_live(reg_no: str, *, timeout: float = 6.0) -> dict[str, Any]:
    """Confirm one registration number against SEBI's live register.

    Returns a dict that always includes `ok`. On any failure -- network down,
    SEBI slow, unexpected markup -- `ok` is False and the caller falls back to
    the cached register. It never raises.
    """
    result: dict[str, Any] = {
        "ok": False,
        "registration_no": reg_no,
        "found": False,
        "registered_names": [],
        "source": "sebi_live",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "error": None,
    }

    intm_id = intm_id_for_registration(reg_no)
    if intm_id is None:
        result["error"] = "unrecognised_registration_prefix"
        return result

    try:
        session = _session()
        session.get(LIST_URL, params={"doRecognisedFpi": "yes", "intmId": str(intm_id)},
                    timeout=timeout, verify=False)
        resp = session.post(
            LIST_URL,
            data={
                "doRecognisedFpi": "yes", "intmId": str(intm_id), "regNo": reg_no.strip(),
                "name": "", "contPer": "", "email": "", "location": "",
                "curr_alp": "", "nextValue": "1",
            },
            timeout=timeout, verify=False,
        )
        if resp.status_code != 200:
            result["error"] = f"http_{resp.status_code}"
            return result

        names = [html.unescape(n).strip() for n in NAME_RE.findall(resp.text)]
        regs = [r.strip().upper() for r in REG_RE.findall(resp.text)]
        target = reg_no.strip().upper()

        matched = sorted({n for n, r in zip(names, regs) if r == target})
        result["ok"] = True
        result["found"] = bool(matched)
        result["registered_names"] = matched
        count = COUNT_RE.search(resp.text)
        result["record_count"] = int(count.group(3)) if count else len(matched)
    except Exception as exc:  # noqa: BLE001 - live check must never break a verdict
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Scrape SEBI registered intermediaries")
    p.add_argument("--only", type=int, nargs="*", help="specific intmId values")
    p.add_argument("--lookup", help="live-verify a single registration number and exit")
    args = p.parse_args()
    if args.lookup:
        import json as _json
        print(_json.dumps(lookup_registration_live(args.lookup), indent=2))
    else:
        scrape(only=args.only)
