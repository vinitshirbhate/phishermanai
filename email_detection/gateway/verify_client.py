"""Client for the existing verification engine.

REUSE, NOT REIMPLEMENTATION
---------------------------
This module contains no detection logic. It POSTs raw RFC822 bytes to the
engine's existing `POST /verify/email` endpoint and parses the response. Every
chokepoint, extraction, filings match and scoring rule runs in `core/`, exactly
as it does for the web UI and the browser extension. If you find yourself adding
a rule here, it belongs in `core/`.

Raw bytes are posted UNCHANGED. That matters: the upstream provider's
`Authentication-Results` header is our DKIM/SPF/DMARC evidence, and rebuilding
the message before verifying would risk reordering or re-encoding it away.

NEVER FAIL CLOSED
-----------------
Every failure path here returns a GatewayVerdict with `ok=False` and verdict
UNVERIFIED. It never raises. A mail gateway that drops or holds messages when
its scanner is unhappy is worse than no gateway: the operator loses mail and
does not know why. We would rather deliver an unverified message with an honest
X-...-Error header than lose a real one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

log = logging.getLogger("phishermanai.gateway.verify")

UNVERIFIED = "UNVERIFIED"


@dataclass
class GatewayVerdict:
    """A verdict plus how we got it (or failed to)."""

    verdict: str = UNVERIFIED
    confidence: int = 0
    summary: str = ""
    reason_codes: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)
    matched_filing: dict[str, Any] | None = None
    verification_id: str | None = None
    content_hash: str | None = None
    latency_ms: int = 0
    ok: bool = True
    error: str | None = None
    cached: bool = False

    @property
    def checks_header(self) -> str:
        """Render as MONEY=pass;ENTITY=pass;CLAIM=pass;DELIVERY=na"""
        parts = []
        for name in ("MONEY", "ENTITY", "CLAIM", "DELIVERY"):
            check = (self.checks or {}).get(name)
            if not check:
                parts.append(f"{name}=na")
                continue
            passed = check.get("passed")
            state = "pass" if passed is True else "fail" if passed is False else "na"
            parts.append(f"{name}={state}")
        return ";".join(parts)

    @property
    def filing_header(self) -> str | None:
        f = self.matched_filing
        if not f or not f.get("filing_id"):
            return None
        bits = [f"id={f.get('filing_id')}"]
        if f.get("exchange"):
            bits.append(str(f["exchange"]))
        if f.get("filing_date"):
            bits.append(str(f["filing_date"])[:10])
        if f.get("tier"):
            bits.append(f"tier={f['tier']}")
        return " ".join(bits)


def _failure(reason: str, latency_ms: int = 0) -> GatewayVerdict:
    return GatewayVerdict(
        verdict=UNVERIFIED,
        confidence=0,
        summary="The verification engine could not be reached, so this message was not checked.",
        reason_codes=["ENGINE_UNAVAILABLE"],
        ok=False,
        error=reason,
        latency_ms=latency_ms,
    )


def verify_raw_email(
    raw: bytes,
    *,
    endpoint: str,
    timeout: float = 8.0,
    filename: str = "message.eml",
) -> GatewayVerdict:
    """Verify raw RFC822 bytes. Never raises; never returns None."""
    import time

    started = time.perf_counter()
    try:
        response = requests.post(
            endpoint,
            files={"file": (filename, raw, "message/rfc822")},
            data={"channel": "GATEWAY"},
            timeout=timeout,
        )
    except requests.Timeout:
        elapsed = int((time.perf_counter() - started) * 1000)
        log.warning("engine timeout after %sms - delivering unverified", elapsed)
        return _failure(f"engine_timeout_after_{timeout}s", elapsed)
    except requests.RequestException as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        log.warning("engine unreachable (%s) - delivering unverified", type(exc).__name__)
        return _failure(f"engine_unreachable:{type(exc).__name__}", elapsed)

    elapsed = int((time.perf_counter() - started) * 1000)

    if response.status_code != 200:
        log.warning("engine returned HTTP %s - delivering unverified", response.status_code)
        return _failure(f"engine_http_{response.status_code}", elapsed)

    try:
        payload = response.json()
    except ValueError:
        return _failure("engine_invalid_json", elapsed)

    try:
        return GatewayVerdict(
            verdict=str(payload.get("verdict") or UNVERIFIED),
            confidence=int(payload.get("confidence") or 0),
            summary=str(payload.get("summary") or ""),
            reason_codes=[
                str(r.get("code")) for r in (payload.get("reasons") or []) if r.get("code")
            ],
            checks=payload.get("checks") or {},
            matched_filing=payload.get("matched_filing"),
            verification_id=str(payload.get("verification_id") or "") or None,
            content_hash=str(payload.get("content_hash") or "") or None,
            latency_ms=elapsed,
            ok=True,
        )
    except Exception as exc:  # noqa: BLE001 - unexpected shape must not lose the mail
        log.warning("engine response unparseable (%s) - delivering unverified", exc)
        return _failure(f"engine_response_unparseable:{type(exc).__name__}", elapsed)
