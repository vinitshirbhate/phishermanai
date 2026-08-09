"""Authorised-sender resolution and BIMI verification.

WHAT AUTHORITY MEANS HERE
-------------------------
A domain is "authorised" for a claim type when we hold positive evidence that it
belongs to an organisation entitled to make that claim: an exchange, a
depository, a regulator, a bank, an RTA, a broker, or a listed company speaking
about its own corporate actions.

Two sources of evidence, in order of strength:

  1. RBI-RESTRICTED TLDs. `.bank.in` and `.fin.in` are not open registrations.
     The Institute for Development and Research in Banking Technology allots
     `.bank.in` only to RBI-licensed banks, and `.fin.in` only to regulated
     non-bank financial entities. Membership of the TLD IS the credential, so
     the whole TLD is treated as authorised and no per-domain listing is needed.

  2. THE CURATED DOMAIN MAP, with a claim-type column.

Subdomains inherit their parent's authority: `alerts.sbi.co.in` resolves to
`sbi.co.in`. Organisations send from subdomains constantly and enumerating them
is hopeless.

WHAT THIS IS NOT
----------------
Authority is not a verdict. It answers "is this domain entitled to speak?" and
nothing else. It becomes a verdict only when combined with cryptographic proof
that the domain actually sent the message -- see `try_short_circuit`.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("phishermanai.authority")

REPO_ROOT = Path(__file__).resolve().parent.parent
BIMI_CACHE_PATH = REPO_ROOT / "data" / "cache" / "bimi_records.json"

# TLDs whose registration is itself a regulatory credential.
RESTRICTED_TLDS = {
    "bank.in": ("BANKING", "RBI-licensed bank (.bank.in is allotted by IDRBT on RBI authorisation)"),
    "fin.in": ("NBFC", "Regulated non-bank financial entity (.fin.in, IDRBT-allotted)"),
}

# Government and regulator domains.
GOV_SUFFIXES = {
    "gov.in": ("REGULATOR", "Government of India domain"),
    "nic.in": ("REGULATOR", "National Informatics Centre domain"),
    "rbi.org.in": ("REGULATOR", "Reserve Bank of India"),
}


@dataclass
class Authority:
    domain: str                 # the matched authorised domain
    entity_name: str
    claim_type: str             # EXCHANGE | DEPOSITORY | REGULATOR | BANKING | ...
    source: str
    matched_via: str            # EXACT | SUBDOMAIN | RESTRICTED_TLD | GOV_SUFFIX

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain, "entity_name": self.entity_name,
            "claim_type": self.claim_type, "source": self.source,
            "matched_via": self.matched_via,
        }


@functools.lru_cache(maxsize=1)
def _authorised_domains() -> dict[str, tuple[str, str, str]]:
    """domain -> (entity_name, claim_type, source), from the domain map."""
    from sqlalchemy import select

    from core.db import session_scope
    from core.models import DomainMap

    out: dict[str, tuple[str, str, str]] = {}
    try:
        with session_scope() as session:
            rows = session.execute(
                select(DomainMap.domain, DomainMap.entity_name,
                       DomainMap.entity_type, DomainMap.verified_source)
            ).all()
    except Exception:  # noqa: BLE001 - no DB: fall back to TLD rules only
        return out

    # The claim type is derived from entity_type. The CSV carries an explicit
    # `authority` column too, but the DomainMap table predates it, so the
    # mapping is repeated here rather than requiring a schema change.
    claim_by_type = {
        "EXCHANGE": "EXCHANGE", "DEPOSITORY": "DEPOSITORY", "REGULATOR": "REGULATOR",
        "RTA": "RTA", "BROKER": "BROKER", "MUTUAL_FUND": "MUTUAL_FUND",
        "LISTED_COMPANY": "CORPORATE_ACTION",
    }
    for domain, entity_name, entity_type, source in rows:
        if not domain:
            continue
        out[domain.lower()] = (
            entity_name or domain,
            claim_by_type.get(entity_type or "", "GENERAL"),
            source or "domain_map",
        )
    return out


def reset_authority_cache() -> None:
    _authorised_domains.cache_clear()


def resolve_authority(domain: str) -> Authority | None:
    """Is this domain authorised to speak as a financial institution?

    Returns None when we hold no positive evidence -- which is the common case
    and must never be read as suspicion.
    """
    if not domain:
        return None
    domain = domain.strip().lower().rstrip(".")
    if not domain:
        return None

    # 1. RBI-restricted TLDs: membership is the credential.
    for suffix, (claim_type, description) in RESTRICTED_TLDS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return Authority(
                domain=domain, entity_name=domain.rsplit("." + suffix, 1)[0] or domain,
                claim_type=claim_type, source=description, matched_via="RESTRICTED_TLD",
            )

    registry = _authorised_domains()

    # 2. Exact match.
    if domain in registry:
        entity_name, claim_type, source = registry[domain]
        return Authority(domain=domain, entity_name=entity_name,
                         claim_type=claim_type, source=source, matched_via="EXACT")

    # 3. Subdomain of a listed domain. Longest suffix wins, so a specific entry
    #    for evoting.nsdl.com beats the generic nsdl.com.
    best: tuple[str, tuple[str, str, str]] | None = None
    for known, payload in registry.items():
        if domain.endswith("." + known):
            if best is None or len(known) > len(best[0]):
                best = (known, payload)
    if best is not None:
        entity_name, claim_type, source = best[1]
        return Authority(domain=best[0], entity_name=entity_name, claim_type=claim_type,
                         source=source, matched_via="SUBDOMAIN")

    # 4. Government suffixes.
    for suffix, (claim_type, description) in GOV_SUFFIXES.items():
        if domain == suffix or domain.endswith("." + suffix):
            return Authority(domain=domain, entity_name=domain, claim_type=claim_type,
                             source=description, matched_via="GOV_SUFFIX")

    return None


# --------------------------------------------------------------------------
# BIMI
# --------------------------------------------------------------------------
#
# BIMI is what renders the verified logo ("blue tick") in a mail client. The
# indicator itself is NOT in the .eml -- the client draws it after checking DNS
# -- so it cannot be read from the message. It can be verified independently:
#
#     default._bimi.<domain>  TXT  ->  v=BIMI1; l=<logo SVG>; a=<VMC URL>
#
# An `a=` tag means a Verified Mark Certificate exists, which requires a
# registered trademark and an audited issuance process. That is strong positive
# evidence.
#
# ABSENCE MEANS NOTHING. BIMI adoption is under 1%, so a missing record is the
# overwhelmingly common case for legitimate senders and must never be penalised.

BIMI_SELECTOR = "default._bimi"


@dataclass
class BimiRecord:
    domain: str
    found: bool = False
    has_vmc: bool = False
    logo_url: str | None = None
    vmc_url: str | None = None
    raw: str | None = None
    checked_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain, "found": self.found, "has_vmc": self.has_vmc,
            "logo_url": self.logo_url, "vmc_url": self.vmc_url,
            "checked_at": self.checked_at, "error": self.error,
        }


def _load_bimi_cache() -> dict[str, Any]:
    if not BIMI_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(BIMI_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_bimi_cache(cache: dict[str, Any]) -> None:
    try:
        BIMI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BIMI_CACHE_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    except OSError as exc:  # pragma: no cover
        log.debug("could not persist BIMI cache: %s", exc)


def check_bimi(domain: str, *, allow_live: bool = False, timeout: float = 4.0) -> BimiRecord:
    """Look up a domain's BIMI record.

    Disk cache first. `allow_live` is False by default so the demo path never
    blocks on DNS -- a cache miss returns found=False, which is treated as "no
    information", not as a negative signal.
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return BimiRecord(domain="", found=False)

    cache = _load_bimi_cache()
    if domain in cache:
        entry = dict(cache[domain])
        entry.pop("_", None)
        return BimiRecord(**{k: v for k, v in entry.items() if k in BimiRecord.__annotations__})

    if not allow_live:
        return BimiRecord(domain=domain, found=False, error="not_in_cache_and_live_disabled")

    record = BimiRecord(domain=domain, checked_at=datetime.now().isoformat(timespec="seconds"))
    try:
        import dns.resolver

        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        answers = resolver.resolve(f"{BIMI_SELECTOR}.{domain}", "TXT")
        for answer in answers:
            raw = b"".join(answer.strings).decode("utf-8", "replace") if hasattr(answer, "strings") \
                else str(answer).strip('"')
            if "v=BIMI1" not in raw.upper().replace(" ", "").replace("V=BIMI1", "v=BIMI1"):
                if "bimi" not in raw.lower():
                    continue
            record.found = True
            record.raw = raw[:500]
            logo = re.search(r"\bl\s*=\s*([^;]+)", raw)
            vmc = re.search(r"\ba\s*=\s*([^;]+)", raw)
            if logo:
                record.logo_url = logo.group(1).strip()
            if vmc and vmc.group(1).strip():
                record.vmc_url = vmc.group(1).strip()
                record.has_vmc = True
            break
    except Exception as exc:  # noqa: BLE001 - DNS failure is not a signal
        record.error = f"{type(exc).__name__}"

    cache[domain] = record.to_dict()
    _save_bimi_cache(cache)
    return record
