#!/usr/bin/env python3
"""
fetch_sebi_register.py - builds backend/data/sebi_register.json from SEBI's
public "Recognised Intermediaries" register.

Produces the ground-truth snapshot that F-B1 (registration identity
verification) resolves against.

--------------------------------------------------------------------------
ACCESS PATH - determined by inspection, not assumption (task STEP 0)
--------------------------------------------------------------------------
The register pages carry three candidate bulk affordances. All three were
inspected before a scraper was written:

  * "Download" button  - wired to `javascript: void(0);`. There is NO download
    handler anywhere in https://www.sebi.gov.in/sebiweb/js/other.js (grep for
    /[Dd]ownload/ returns nothing). The button is dead markup. No CSV exists.

  * searchAllIntm() ("Show All Records") - does NOT return all records. It
    clears the filter inputs and then calls searchFormFpi('s','-1'), i.e. it
    resets to page 1. Verified empirically: the response is
    "1 to 25 of 2149 records". It is a filter reset, not a bulk export.

  * searchFormFpi(v, v1) - POSTs to /sebiweb/ajax/other/getintmfpiinfo.jsp and
    returns an HTML fragment of 25 records. `doDirect` is a 0-based page index.

So: no bulk endpoint exists and the paginating scraper is required. We drive
the same AJAX endpoint the page's own pagination uses, which is cheaper and
more stable than re-rendering the full Struts page per request.

--------------------------------------------------------------------------
DATA MINIMISATION (DPDPA) - see docs/SECURITY_AND_LEGAL_CONTROL_MATRIX.md
--------------------------------------------------------------------------
SEBI publishes postal addresses, telephone/fax numbers and contact-person
names for every registrant, many of whom are individual proprietors for whom
this is a home address and a personal mobile. Raw HTML is cached locally for
parser iteration, but ONLY these fields are written to the shipped JSON:

    reg_number, reg_prefix, registered_name, name_normalised, category,
    email_domain, validity_start, validity_end, as_on_date

Address, telephone, fax, contact person and full e-mail addresses are parsed
and then deliberately DROPPED. Bundling ~3,000 individuals' home addresses and
personal phone numbers inside a distributed Chrome extension is indefensible
even though the source is public.

Usage:
    python scripts/fetch_sebi_register.py                # cache-first build
    python scripts/fetch_sebi_register.py --refresh      # re-hit SEBI
    python scripts/fetch_sebi_register.py --categories 14,13,30
    python scripts/fetch_sebi_register.py --verify       # print meta, no write
    python scripts/fetch_sebi_register.py --stats        # parsed-data profile
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "data" / "sebi_register.json"
CACHE = Path(__file__).resolve().parent / ".cache"

INDEX_URL = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes"
LANDING_URL = ("https://www.sebi.gov.in/sebiweb/other/OtherAction.do"
               "?doRecognisedFpi=yes&intmId={intm_id}")
AJAX_URL = "https://www.sebi.gov.in/sebiweb/ajax/other/getintmfpiinfo.jsp"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

PAGE_SIZE = 25
MIN_DELAY, MAX_DELAY = 0.6, 1.0          # ~1-1.6 req/s
MAX_RETRIES = 4

# intmId -> (our category code, SEBI's own label, expected reg prefix family)
# The prefix column is documentation only; the actual matcher is DERIVED from
# the fetched reg_number column (see build_prefix_shapes).
CATEGORIES = {
    14: ("RA", "Research Analyst"),
    13: ("IA", "Investment Adviser"),
    30: ("broker", "Stock Brokers"),
}

# Free/consumer mail providers. An email domain here is NOT an identity anchor:
# treating "gmail.com" as a registrant's domain would let any gmail sender
# short-circuit to `valid`. Recorded, but never used for domain matching.
FREE_MAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.in",
    "hotmail.com", "outlook.com", "live.com", "rediffmail.com", "rediff.com",
    "ymail.com", "icloud.com", "protonmail.com", "aol.com", "msn.com",
    "yandex.com", "zoho.com", "zohomail.com", "mail.com", "gmx.com",
}

_SUFFIX_RE = re.compile(r"\b(private|pvt|limited|ltd|llp|and|&)\b", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

_RECORD_RE = re.compile(
    r"<div class=['\"]fixed-table-body card-table['\"]>(.*?)"
    r"(?=<div class=['\"]fixed-table-body card-table['\"]>|$)", re.S)
_PAIR_RE = re.compile(
    r"<div class=['\"]title['\"]>\s*<span>(.*?)</span>\s*</div>\s*"
    r"<div class=['\"]value[^'\"]*['\"]>\s*<span>(.*?)</span>\s*</div>", re.S)
_COUNT_RE = re.compile(r"(\d+)\s*to\s*(\d+)\s*of\s*(\d+)\s*records", re.I)
_ASON_RE = re.compile(r"Registered intermediaries as on date\s*([A-Za-z]{3,}\s+\d{1,2},\s*\d{4})", re.I)


# --------------------------------------------------------------------------- #
# Fetch layer - cache first, always
# --------------------------------------------------------------------------- #
def _clean(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment or "")).replace("\xa0", " ").strip()


def _http(url: str, data: bytes | None = None, referer: str | None = None) -> str:
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Requested-With"] = "XMLHttpRequest"
    if referer:
        headers["Referer"] = referer
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:                       # noqa: BLE001 - retry all
            last = exc
            backoff = (2 ** attempt) + random.uniform(0, 0.75)
            print(f"    retry {attempt + 1}/{MAX_RETRIES} after {backoff:.1f}s "
                  f"({type(exc).__name__})", file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(f"GET/POST failed after {MAX_RETRIES} attempts: {url}") from last


def _cached(name: str, produce, refresh: bool) -> str:
    """Cache raw HTML BEFORE parsing so parser iteration never re-hits SEBI."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")
    body = produce()
    path.write_text(body, encoding="utf-8")
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    return body


def fetch_landing(intm_id: int, refresh: bool) -> str:
    url = LANDING_URL.format(intm_id=intm_id)
    return _cached(f"intm{intm_id}_landing.html", lambda: _http(url), refresh)


def fetch_page(intm_id: int, page_index: int, refresh: bool) -> str:
    """page_index is 0-based; it is the `doDirect` value the site's own JS sends."""
    body = urllib.parse.urlencode({
        "nextValue": "1", "next": "n", "intmId": str(intm_id),
        "contPer": "", "name": "", "regNo": "", "email": "", "location": "",
        "exchange": "", "affiliate": "", "alp": "", "language": "2",
        "model": "", "esgCategory": "", "doDirect": str(page_index), "intmIds": "",
    }).encode()
    return _cached(
        f"intm{intm_id}_p{page_index:04d}.html",
        lambda: _http(AJAX_URL, data=body, referer=LANDING_URL.format(intm_id=intm_id)),
        refresh)


# --------------------------------------------------------------------------- #
# Parse layer
# --------------------------------------------------------------------------- #
def parse_as_on_date(landing_html: str) -> str | None:
    """'Registered intermediaries as on date Aug 06, 2026' -> '2026-08-06'.

    Captured PER CATEGORY, never globally - some SEBI categories are years
    staler than others and a single global date would misreport them.
    """
    m = _ASON_RE.search(_clean(landing_html))
    if not m:
        return None
    raw = re.sub(r"\s+", " ", m.group(1)).strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_total(fragment: str) -> int | None:
    m = _COUNT_RE.search(_clean(fragment))
    return int(m.group(3)) if m else None


def parse_records(fragment: str) -> list[dict]:
    """Extract the label/value card structure into raw dicts (all fields)."""
    out = []
    for block in _RECORD_RE.findall(fragment):
        fields = {}
        for label, value in _PAIR_RE.findall(block):
            fields[_clean(label).rstrip(":").strip()] = _clean(value)
        if fields.get("Registration No."):
            out.append(fields)
    return out


def parse_validity(value: str) -> tuple[str | None, str | None]:
    """'Apr 13, 2026 - Perpetual' -> ('2026-04-13', 'perpetual')."""
    if not value:
        return None, None
    parts = [p.strip() for p in re.split(r"\s+-\s+", value, maxsplit=1)]

    def one(tok: str) -> str | None:
        if not tok:
            return None
        if re.search(r"perpetual", tok, re.I):
            return "perpetual"
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(tok, fmt).date().isoformat()
            except ValueError:
                continue
        return tok or None

    start = one(parts[0]) if parts else None
    end = one(parts[1]) if len(parts) > 1 else None
    return start, end


def email_domain_of(value: str) -> str | None:
    """First e-mail's DOMAIN only. The local part is PII and is discarded here."""
    if not value:
        return None
    m = re.search(r"@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})", value)
    if not m:
        return None
    dom = m.group(1).lower().strip(".")
    return dom or None


def normalise_name(name: str) -> str:
    n = _SUFFIX_RE.sub(" ", (name or "").lower())
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def derive_prefix(reg_number: str) -> str:
    """Leading non-digit run, derived from the value itself. Never hand-written.

    'INH000004017' -> 'INH'   -   'INAIFSC10001' -> 'INAIFSC'
    'ARN-123456'   -> 'ARN'   -   'IN-DP-NSDL-321-2024' -> 'IN-DP'
    """
    rn = (reg_number or "").strip().upper()
    if rn.startswith("IN-DP-"):
        return "IN-DP"
    m = re.match(r"^([A-Z]+)-", rn)          # scheme-tagged, e.g. ARN-123456
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z]+)", rn)           # letters run, e.g. INA / INAIFSC
    return m.group(1) if m else rn


def build_prefix_shapes(records: list[dict]) -> list[dict]:
    """
    DERIVE the registration-number shape family from the fetched data (D3).

    For every distinct prefix we record the observed digit-length range, so the
    matcher generated at load time covers exactly what the register contains -
    including INAIFSC10001, whose 5 trailing digits a hand-written INA\\d{9}
    silently fails.
    """
    shapes: dict[str, dict] = {}
    for r in records:
        rn = r["reg_number"]
        prefix = r["reg_prefix"]
        tail = rn[len(prefix):].lstrip("-")
        sh = shapes.setdefault(prefix, {
            "prefix": prefix, "tail_kind": None,
            "min_digits": 10 ** 6, "max_digits": 0, "count": 0,
            "examples": [], "total_len_min": 10 ** 6, "total_len_max": 0,
        })
        sh["count"] += 1
        sh["total_len_min"] = min(sh["total_len_min"], len(rn))
        sh["total_len_max"] = max(sh["total_len_max"], len(rn))
        if len(sh["examples"]) < 3:
            sh["examples"].append(rn)
        if tail.isdigit():
            kind = "digits"
            sh["min_digits"] = min(sh["min_digits"], len(tail))
            sh["max_digits"] = max(sh["max_digits"], len(tail))
        else:
            kind = "mixed"
        sh["tail_kind"] = kind if sh["tail_kind"] in (None, kind) else "mixed"
    for sh in shapes.values():
        if sh["min_digits"] == 10 ** 6:
            sh["min_digits"] = sh["max_digits"] = 0
    return sorted(shapes.values(), key=lambda s: (-len(s["prefix"]), s["prefix"]))


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def harvest_category(intm_id: int, refresh: bool, limit_pages: int | None) -> dict:
    code, label = CATEGORIES[intm_id]
    print(f"[{code}] intmId={intm_id} ({label})")

    landing = fetch_landing(intm_id, refresh)
    as_on = parse_as_on_date(landing)
    print(f"    as-on date : {as_on or 'NOT FOUND'}")

    first = fetch_page(intm_id, 0, refresh)
    total = parse_total(first)
    if total is None:
        raise RuntimeError(f"intmId={intm_id}: could not read the record count")
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if limit_pages:
        pages = min(pages, limit_pages)
    print(f"    records    : {total}  ({pages} pages)")

    raw: list[dict] = []
    raw.extend(parse_records(first))
    for p in range(1, pages):
        frag = fetch_page(intm_id, p, refresh)
        got = parse_records(frag)
        if not got:
            print(f"    WARNING page {p} parsed 0 records", file=sys.stderr)
        raw.extend(got)
        if p % 20 == 0 or p == pages - 1:
            print(f"      page {p + 1}/{pages}  cumulative {len(raw)}")

    return {"intm_id": intm_id, "code": code, "label": label,
            "as_on_date": as_on, "reported_total": total, "raw": raw}


def minimise(harvest: dict) -> list[dict]:
    """Raw parsed fields -> the shipped, field-minimised record (D2)."""
    out = []
    for f in harvest["raw"]:
        reg_number = (f.get("Registration No.") or "").strip().upper()
        name = (f.get("Name") or "").strip()
        if not reg_number or not name:
            continue
        start, end = parse_validity(f.get("Validity", ""))
        dom = email_domain_of(f.get("E-mail", ""))
        out.append({
            "reg_number": reg_number,
            "reg_prefix": derive_prefix(reg_number),
            "registered_name": name,
            "name_normalised": normalise_name(name),
            "category": harvest["code"],
            # `status`: SEBI publishes CURRENT registrants only - there is no
            # status column and a cancelled registration disappears from the
            # listing rather than showing as cancelled. Every listed row is
            # therefore active as of this category's as-on date.
            "status": "active",
            "email_domain": dom,
            # Only a NON-free domain may anchor identity. gmail.com et al. would
            # let any consumer-mail sender short-circuit to `valid`.
            "domain_anchor": dom if dom and dom not in FREE_MAIL else None,
            "validity_start": start,
            "validity_end": end,
            "as_on_date": harvest["as_on_date"],
        })
    return out


def build_document(harvests: list[dict]) -> dict:
    records: list[dict] = []
    for h in harvests:
        records.extend(minimise(h))

    # Dedupe on reg_number, keeping first occurrence (a firm can hold several
    # registrations; the same number never legitimately appears twice).
    seen, deduped = set(), []
    for r in records:
        if r["reg_number"] in seen:
            continue
        seen.add(r["reg_number"])
        deduped.append(r)
    deduped.sort(key=lambda r: r["reg_number"])

    shapes = build_prefix_shapes(deduped)
    payload = json.dumps(deduped, ensure_ascii=True, sort_keys=True).encode("utf-8")

    per_cat = {h["code"]: h["as_on_date"] for h in harvests}
    prefix_categories: dict[str, str] = {}
    for r in deduped:
        prefix_categories.setdefault(r["reg_prefix"], r["category"])

    return {
        "registry_meta": {
            "source": "sebi_register",
            "source_url": INDEX_URL,
            "category_urls": {CATEGORIES[h["intm_id"]][0]:
                              LANDING_URL.format(intm_id=h["intm_id"]) for h in harvests},
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "per_category_as_on_dates": per_cat,
            "covered_categories": sorted(per_cat),
            # Which prefix families this snapshot can speak to. A number whose
            # prefix is NOT here must never be called `invalid` - we simply did
            # not fetch its category (G-2).
            "covered_prefixes": sorted(prefix_categories),
            "prefix_categories": prefix_categories,
            "record_count": len(deduped),
            "per_category_counts": {h["code"]: h["reported_total"] for h in harvests},
            "licence": "Public register published by SEBI (www.sebi.gov.in).",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "synthetic_subset": False,
            "authoritative": True,
            "field_minimised": True,
            "dropped_fields": ["address", "correspondence_address", "telephone",
                               "fax", "contact_person", "email_local_part"],
            "disclosure": (
                "Real SEBI register data, field-minimised under DPDPA data-"
                "minimisation (see docs/SECURITY_AND_LEGAL_CONTROL_MATRIX.md). "
                "Covers the categories listed in covered_categories only; a "
                "registration number outside those categories resolves to "
                "`unverified`, never `invalid`."
            ),
        },
        "prefixes": sorted({r["reg_prefix"] for r in deduped}),
        "prefix_shapes": shapes,
        "intermediaries": deduped,
    }


def write_extension_snapshot(doc: dict) -> tuple[Path, int]:
    """
    D6 - emit extension/data/securities_snapshot.json from the SAME build, so the
    offline in-extension check (extension/securities_check.js) can never disagree
    with the backend about who is registered.

    Carries a further-reduced record: the extension needs identity resolution
    only, so validity dates and raw e-mail domains are dropped again here.
    """
    ns_path = ROOT / "backend" / "data" / "valid_upi_namespace.json"
    ns = json.loads(ns_path.read_text(encoding="utf-8"))
    meta = doc["registry_meta"]

    snapshot = {
        "meta": {
            "source": "sebi_register",
            "register_as_of": meta["fetched_at"],
            "per_category_as_on_dates": meta["per_category_as_on_dates"],
            "covered_categories": meta["covered_categories"],
            "covered_prefixes": meta["covered_prefixes"],
            "prefix_categories": meta["prefix_categories"],
            "category_urls": meta["category_urls"],
            "record_count": meta["record_count"],
            "sha256": meta["sha256"],
            "synthetic_subset": False,
            "authoritative": True,
            "note": ("Real SEBI register, field-minimised. Built by "
                     "scripts/fetch_sebi_register.py in the same run as "
                     "backend/data/sebi_register.json — the two are always in sync."),
        },
        "prefixes": doc["prefixes"],
        "prefix_shapes": doc["prefix_shapes"],
        "intermediaries": [{
            "reg_number": r["reg_number"],
            "registered_name": r["registered_name"],
            "name_normalised": r["name_normalised"],
            "category": r["category"],
            "status": r["status"],
            "domain_anchor": r["domain_anchor"],
        } for r in doc["intermediaries"]],
        "upi_suffixes": sorted(s["suffix"].lower() for s in ns.get("namespace_suffixes", [])),
        "sebi_check_url": ns.get("sebi_check_url", "https://investor.sebi.gov.in/sebicheck"),
    }
    out = ROOT / "extension" / "data" / "securities_snapshot.json"
    # Compact separators: this ships inside the extension bundle (2 MB budget).
    out.write_text(json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    return out, out.stat().st_size


def print_stats(doc: dict) -> None:
    recs = doc["intermediaries"]
    meta = doc["registry_meta"]
    print("\n--- profile -------------------------------------------------")
    print(f"records           : {len(recs)}")
    print(f"per-category      : {meta['per_category_counts']}")
    print(f"as-on dates       : {meta['per_category_as_on_dates']}")
    print(f"prefixes          : {doc['prefixes']}")
    print("\nprefix shapes (matcher is generated from these):")
    for s in doc["prefix_shapes"]:
        print(f"  {s['prefix']:<10} n={s['count']:<6} tail={s['tail_kind']:<7} "
              f"digits={s['min_digits']}-{s['max_digits']:<3} "
              f"len={s['total_len_min']}-{s['total_len_max']:<3} eg={s['examples'][0]}")
    with_dom = sum(1 for r in recs if r["email_domain"])
    anchors = sum(1 for r in recs if r["domain_anchor"])
    print(f"\nemail_domain present : {with_dom}/{len(recs)}")
    print(f"usable domain anchors: {anchors}/{len(recs)} "
          f"(free-mail domains excluded from identity matching)")
    ends = {}
    for r in recs:
        ends[r["validity_end"] or "none"] = ends.get(r["validity_end"] or "none", 0) + 1
    top = sorted(ends.items(), key=lambda kv: -kv[1])[:5]
    print(f"validity_end top     : {top}")
    dupes = len(recs) - len({r["name_normalised"] for r in recs})
    print(f"duplicate normalised names: {dupes}")
    print("-------------------------------------------------------------\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch SEBI's public intermediary register.")
    ap.add_argument("--categories", default="14,13",
                    help="comma-separated intmIds (default 14,13 = RA + IA)")
    ap.add_argument("--refresh", action="store_true", help="bypass scripts/.cache/")
    ap.add_argument("--verify", action="store_true", help="print meta and exit without writing")
    ap.add_argument("--stats", action="store_true", help="print a parsed-data profile")
    ap.add_argument("--limit-pages", type=int, default=None, help="debug: cap pages per category")
    args = ap.parse_args()

    ids = [int(x) for x in args.categories.split(",") if x.strip()]
    unknown = [i for i in ids if i not in CATEGORIES]
    if unknown:
        print(f"unknown intmId(s): {unknown}; known: {sorted(CATEGORIES)}", file=sys.stderr)
        return 2

    harvests = [harvest_category(i, args.refresh, args.limit_pages) for i in ids]
    doc = build_document(harvests)
    meta = doc["registry_meta"]

    for h in harvests:
        got = sum(1 for r in doc["intermediaries"] if r["category"] == h["code"])
        if got < h["reported_total"]:
            print(f"NOTE {h['code']}: parsed {got} of {h['reported_total']} reported "
                  f"(duplicates removed or pages capped)", file=sys.stderr)

    if args.stats:
        print_stats(doc)

    if args.verify:
        print(json.dumps(meta, indent=2))
        return 0

    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print(f"  records   : {meta['record_count']}")
    print(f"  categories: {meta['per_category_as_on_dates']}")
    print(f"  prefixes  : {doc['prefixes']}")
    print(f"  sha256    : {meta['sha256']}")

    snap, size = write_extension_snapshot(doc)
    budget = 2 * 1024 * 1024
    print(f"\nWrote {snap.relative_to(ROOT)}")
    print(f"  size      : {size / 1024:.0f} KiB of a {budget // 1024} KiB budget "
          f"({'OK' if size <= budget else 'OVER BUDGET'})")
    if size > budget:
        print("  Bundle exceeds 2 MB — ship RA + IA only and disclose the included "
              "categories in the UI.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
