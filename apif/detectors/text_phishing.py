"""Client for the external text-phishing classifier.

Contract (verified live against http://127.0.0.1:8080/openapi.json, no auth):

    POST /detect  {"text": str}
               -> {"text": str, "label": str, "confidence": float,
                   "is_phishing": bool, "message": str}
    GET  /health

This service is the *only* phishing classifier. The LLM analyst never re-scores text --
it extracts entities and writes explanations, so the two never disagree on the verdict.
"""

from __future__ import annotations

import httpx

from ..config import get_settings
from ..schemas import SIGNAL_TEXT_PHISHING, Signal

# The classifier is a local CPU model; generous but bounded so a hung service can't
# stall a /verify request that has other signals to report.
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


async def health() -> str:
    """Returns 'ok' or a short failure reason. Used by the app's own /health."""
    url = f"{get_settings().phishing_api_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            resp = await client.get(url)
        return "ok" if resp.status_code == 200 else f"http {resp.status_code}"
    except httpx.HTTPError as exc:
        return f"unreachable: {type(exc).__name__}"


async def detect(text: str) -> Signal:
    """Score text for phishing. Never raises -- a downstream failure returns an
    unavailable Signal so the rest of the pipeline still produces a verdict."""
    text = (text or "").strip()
    if not text:
        return Signal.unavailable(SIGNAL_TEXT_PHISHING, "no text supplied")

    url = f"{get_settings().phishing_api_url.rstrip('/')}/detect"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"text": text})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        return Signal.unavailable(
            SIGNAL_TEXT_PHISHING, f"classifier returned HTTP {exc.response.status_code}"
        )
    except httpx.HTTPError as exc:
        return Signal.unavailable(
            SIGNAL_TEXT_PHISHING, f"classifier unreachable ({type(exc).__name__})"
        )
    except ValueError:
        return Signal.unavailable(SIGNAL_TEXT_PHISHING, "classifier returned non-JSON")

    is_phishing = bool(data.get("is_phishing", False))
    confidence = float(data.get("confidence", 0.0))
    # The service reports confidence in its *own* label, not in "phishing". A confident
    # benign call must map to a low risk score, not a high one.
    score = confidence if is_phishing else 1.0 - confidence

    label = str(data.get("label", "unknown"))
    return Signal(
        name=SIGNAL_TEXT_PHISHING,
        score=max(0.0, min(1.0, score)),
        available=True,
        summary=f"Classifier: {label} ({confidence:.1%} confidence)",
        evidence={
            "label": label,
            "confidence": confidence,
            "is_phishing": is_phishing,
            "message": data.get("message", ""),
        },
    )
