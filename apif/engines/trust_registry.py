"""Source-trust registry: the "verify the genuine article" half of the product.

Investors currently have no reliable way to confirm that a SEBI/exchange message is real.
This engine answers that with three independent checks:

  1. Registry match  -- is this domain / @handle / email domain a known official source?
  2. Lookalike check -- is it a near-miss of one? `sebi-gov.in` and `nseindla.com` must
     be flagged as impersonation, not merely "unknown". This is the check that catches
     real phishing, because attackers register plausible neighbours rather than
     unrelated domains.
  3. Signature check -- SEBI mandates DSC on filings, so a "SEBI circular" PDF with no
     signature field is itself evidence, independent of its wording.

A registry hit plus a valid signature is what triggers fusion's cap-at-Low override.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import Levenshtein

from ..config import get_settings
from ..schemas import SIGNAL_SOURCE_UNTRUSTED, RegistryLookupResult, Signal

# Distance at which a domain is treated as impersonating a trusted one. 2 catches
# character swaps, single insertions/deletions, and most homoglyph substitutions
# (nseindla/nseindia) without flagging genuinely unrelated short domains.
_LOOKALIKE_MAX_DISTANCE = 2

# Characters attackers substitute to build visually identical domains.
_HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "5": "s", "3": "e", "@": "a", "$": "s"})


@lru_cache(maxsize=1)
def _registry() -> list[dict[str, Any]]:
    path = get_settings().trusted_sources_path
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("organisations", [])


def reload_registry() -> None:
    """Drop the cache after the exchange feeds add listed companies."""
    _registry.cache_clear()


def _normalise_domain(value: str) -> str:
    """Reduce a URL, email, or bare domain to a comparable registrable host."""
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "@" in value and "://" not in value:
        value = value.rsplit("@", 1)[-1]        # email -> domain
    if "://" in value:
        value = urlparse(value).netloc or value
    value = value.split("/")[0].split(":")[0]
    return value[4:] if value.startswith("www.") else value


def _skeleton(domain: str) -> str:
    """Homoglyph- and separator-normalised form, so `sebi-gov.in` and `sebi.gov.in`
    compare as near-identical rather than as different strings."""
    return domain.translate(_HOMOGLYPHS).replace("-", "").replace(".", "")


def lookup(query: str) -> RegistryLookupResult:
    """Classify a domain, URL, email address, or @handle against the registry."""
    raw = (query or "").strip()
    if not raw:
        return RegistryLookupResult(query=query, matched=False,
                                    notes=["empty query"])

    handle = raw.lstrip("@").lower() if raw.startswith("@") else None
    domain = _normalise_domain(raw)
    email_domain = raw.rsplit("@", 1)[-1].lower() if "@" in raw and "://" not in raw else None

    for org in _registry():
        if handle and handle in {h.lower() for h in org.get("x_handles", [])}:
            return RegistryLookupResult(
                query=query, matched=True, organisation=org["name"], match_type="handle"
            )
        if email_domain and email_domain in {d.lower() for d in org.get("email_domains", [])}:
            return RegistryLookupResult(
                query=query, matched=True, organisation=org["name"],
                match_type="email_domain",
            )
        if domain and domain in {_normalise_domain(d) for d in org.get("domains", [])}:
            return RegistryLookupResult(
                query=query, matched=True, organisation=org["name"], match_type="domain"
            )

    # No exact match. Before calling it merely "unknown", check whether it is a
    # near-miss of a trusted domain -- that is impersonation, a much stronger finding.
    if domain:
        skeleton = _skeleton(domain)
        for org in _registry():
            for trusted in org.get("domains", []):
                trusted_norm = _normalise_domain(trusted)
                if not trusted_norm or trusted_norm == domain:
                    continue
                if (
                    Levenshtein.distance(domain, trusted_norm) <= _LOOKALIKE_MAX_DISTANCE
                    or _skeleton(trusted_norm) == skeleton
                ):
                    return RegistryLookupResult(
                        query=query, matched=False, organisation=org["name"],
                        lookalike_of=trusted_norm,
                        notes=[f"'{domain}' closely imitates '{trusted_norm}' ({org['name']})"],
                    )

    return RegistryLookupResult(
        query=query, matched=False, notes=["not found in the trusted-source registry"]
    )


def find_organisation(name: str) -> dict[str, Any] | None:
    """Resolve a claimed issuer string (from the LLM analyst) to a registry entry."""
    needle = (name or "").strip().lower()
    if not needle:
        return None
    for org in _registry():
        candidates = {org["name"].lower(), org.get("short_name", "").lower()}
        candidates |= {t.lower() for t in org.get("tickers", [])}
        if needle in candidates or any(c and c in needle for c in candidates if len(c) > 3):
            return org
    return None


def check_pdf_signature(pdf_path: str | Path) -> dict[str, Any]:
    """Report whether a PDF carries a digital signature field.

    Presence of a signature is NOT cryptographic validation -- verifying the certificate
    chain against India's CCA trust store is out of scope here. Absence on a document
    claiming to be a SEBI/exchange circular is the actionable finding, since those are
    mandated to be signed.
    """
    path = Path(pdf_path)
    if not path.exists():
        return {"signed": False, "error": "file not found"}
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        fields = reader.get_fields() or {}
        signature_fields = [
            name for name, field in fields.items()
            if str(field.get("/FT", "")) == "/Sig"
        ]
        return {
            "signed": bool(signature_fields),
            "signature_fields": signature_fields,
            "note": "signature field present (certificate chain not validated)"
            if signature_fields
            else "no digital signature field found",
        }
    except Exception as exc:  # noqa: BLE001 - pypdf raises broadly on malformed files
        return {"signed": False, "error": f"{type(exc).__name__}: {exc}"}


def analyze(
    source: str | None = None,
    claimed_issuer: str | None = None,
    pdf_path: str | Path | None = None,
) -> Signal:
    """Score how trustworthy the origin of this content is.

    `source` is the observable origin (URL, sender address, @handle); `claimed_issuer` is
    who the content *says* it is from. The gap between the two is the whole point: a
    message claiming to be SEBI arriving from an unrelated domain is the classic fake.
    """
    if not source and not claimed_issuer:
        return Signal.unavailable(SIGNAL_SOURCE_UNTRUSTED, "no source or issuer supplied")

    evidence: dict[str, Any] = {"registry_matched": False, "signature_valid": False}
    notes: list[str] = []
    score = 0.5  # unknown origin: neither trusted nor proven malicious

    result = lookup(source) if source else None
    if result is not None:
        evidence["source_lookup"] = result.model_dump()
        if result.matched:
            evidence["registry_matched"] = True
            score = 0.0
            notes.append(f"Source is the registered domain of {result.organisation}")
        elif result.lookalike_of:
            score = 0.95
            notes.append(
                f"Source impersonates {result.lookalike_of} ({result.organisation})"
            )
        else:
            notes.append("Source is not a registered official channel")

    if claimed_issuer:
        org = find_organisation(claimed_issuer)
        evidence["claimed_issuer"] = claimed_issuer
        evidence["claimed_issuer_known"] = org is not None
        if org and result is not None:
            # Does the observable origin belong to the org it claims to be?
            claims_match = result.matched and result.organisation == org["name"]
            evidence["issuer_matches_source"] = claims_match
            if not claims_match:
                score = max(score, 0.9)
                notes.append(
                    f"Content claims to be from {org['name']} but the source does not "
                    "belong to that organisation"
                )
            if org.get("requires_digital_signature") and pdf_path is None:
                notes.append(
                    f"{org['short_name']} communications are digitally signed; "
                    "no signed document was provided to verify"
                )

    if pdf_path is not None:
        sig = check_pdf_signature(pdf_path)
        evidence["signature"] = sig
        if sig.get("signed"):
            evidence["signature_valid"] = True
            score = min(score, 0.1)
            notes.append("Document carries a digital signature field")
        else:
            score = max(score, 0.7)
            notes.append("Document claiming official status has no digital signature")

    return Signal(
        name=SIGNAL_SOURCE_UNTRUSTED,
        score=max(0.0, min(1.0, score)),
        available=True,
        summary="; ".join(notes) or "Source could not be corroborated",
        evidence=evidence,
    )
