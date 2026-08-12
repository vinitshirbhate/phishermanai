"""Claude-backed content analyst.

Deliberately scoped: this module does NOT score phishing. The external classifier at
PHISHING_API_URL owns that verdict, and having two components score the same thing would
let them disagree with no tie-breaker. Claude does the two jobs the classifier cannot:

1. Entity extraction -- who does this claim to be from, which tickers does it mention.
   Those feed the trust registry and market-correlation engines, so extraction quality
   directly drives two other signals.
2. The final plain-language explanation, written once every signal is in, for an
   investor who will not read a JSON blob of probabilities.

Optional throughout: with no ANTHROPIC_API_KEY the app degrades to a templated
explanation and empty entities. Every other signal keeps working.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import httpx

from ..config import get_settings
from ..schemas import ExtractedEntities, Verdict

MODEL = "claude-opus-5"
OPENROUTER_MODEL = "gpt-4o-mini"

_ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "claimed_issuer": {
            "type": ["string", "null"],
            "description": "Organisation the content claims to originate from "
                           "(e.g. 'SEBI', 'NSE', 'Reliance Industries'), or null.",
        },
        "companies": {"type": "array", "items": {"type": "string"}},
        "tickers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "NSE/BSE trading symbols, uppercase, no exchange suffix.",
        },
        "urgency_cues": {"type": "array", "items": {"type": "string"}},
        "requested_actions": {"type": "array", "items": {"type": "string"}},
        "impersonation_markers": {"type": "array", "items": {"type": "string"}},
        "links": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "claimed_issuer", "companies", "tickers", "urgency_cues",
        "requested_actions", "impersonation_markers", "links",
    ],
    "additionalProperties": False,
}

_EXTRACT_SYSTEM = """You extract structured facts from messages circulating among Indian \
retail investors. You are not judging whether the content is a scam -- a separate \
classifier does that. Report only what the text actually says.

- claimed_issuer: who the message presents itself as being from. Null if it does not \
claim an institutional sender.
- tickers: NSE/BSE symbols only, uppercase, no .NS suffix. Include a symbol when a \
company is clearly identified even if the symbol itself is not written out.
- urgency_cues: verbatim phrases creating time pressure.
- requested_actions: what the reader is being told to do.
- impersonation_markers: concrete signals of impersonation present in the text -- \
lookalike domains, mismatched sender, forged reference numbers, misused logos.
- links: every URL, verbatim."""

_EXPLAIN_SYSTEM = """You write one short verdict explanation for an Indian retail \
investor checking whether a message, video, or call is genuine.

Write 2-4 sentences of plain language. Lead with what this is and what they should do. \
Reference only the detector findings you are given -- never invent evidence, and never \
restate a numeric score the reader was not shown. If findings conflict or several \
detectors were unavailable, say the result is inconclusive rather than projecting \
confidence. No preamble, no markdown, no bullet points."""


def _openrouter_url() -> str:
    return f"{get_settings().openrouter_base_url.rstrip('/')}/api/v1/chat/completions"


def _openrouter_text(response_json: dict[str, Any]) -> str:
    if not isinstance(response_json, dict):
        return ""
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, dict):
        text = content.get("text") or content.get("content") or ""
        if isinstance(text, str):
            return text
        if isinstance(text, list):
            return "".join(item.get("text", "") for item in text if isinstance(item, dict))
    if isinstance(content, str):
        return content
    if isinstance(choices[0].get("text"), str):
        return choices[0]["text"]
    return ""


async def _openrouter_request(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {get_settings().openrouter_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_openrouter_url(), json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


async def _anthropic_request(messages: list[dict[str, str]], max_tokens: int) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    response = await client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=messages[0]["content"],
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
        messages=[messages[1]],
    )
    return _first_text(response)


def is_enabled() -> bool:
    return bool(get_settings().openrouter_api_key or get_settings().anthropic_api_key)


def _first_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


async def _send_llm_request(messages: list[dict[str, str]], max_tokens: int) -> str:
    if get_settings().openrouter_api_key:
        payload = {
            "model": get_settings().openrouter_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        return _openrouter_text(await _openrouter_request(payload))

    if get_settings().anthropic_api_key:
        return await _anthropic_request(messages, max_tokens)

    raise RuntimeError("no LLM API key set")


async def extract_entities(text: str) -> tuple[ExtractedEntities, str | None]:
    """Pull issuer/tickers/cues out of content. Returns (entities, error)."""
    if not is_enabled():
        return ExtractedEntities(), "OPENROUTER_API_KEY not set"
    if not (text or "").strip():
        return ExtractedEntities(), "no text supplied"

    prompt = (
        _EXTRACT_SYSTEM + "\n\nRespond with only a single JSON object. "
        "Do not include markdown, commentary, or extra keys. "
        "Match the schema exactly and use null or empty arrays for missing fields.\n"
        f"Schema: {json.dumps(_ENTITY_SCHEMA, ensure_ascii=False)}\n\n"
        f"Text: {text[:20000]}"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Extract the entities from the text above."},
    ]

    try:
        raw_text = await _send_llm_request(messages, max_tokens=2048)
    except Exception as exc:  # noqa: BLE001 - network/auth/rate-limit all degrade alike
        return ExtractedEntities(), f"{type(exc).__name__}: {exc}"

    try:
        return ExtractedEntities.model_validate_json(raw_text), None
    except (ValueError, json.JSONDecodeError) as exc:
        return ExtractedEntities(), f"could not parse extraction: {exc}"


def _fallback_explanation(verdict: Verdict) -> str:
    """Used when the LLM is disabled or errors. Deterministic, never misleading."""
    available = [s for s in verdict.signals if s.available]
    if not available:
        return (
            "No detector was able to evaluate this content, so no conclusion can be "
            "drawn. Verify through official channels before acting on it."
        )
    findings = "; ".join(s.summary for s in available if s.summary)
    advice = (
        "Do not act on this content. Verify through official SEBI or exchange channels."
        if verdict.band in ("High", "Critical")
        else "Treat with normal caution and confirm through official channels."
    )
    return f"{verdict.headline}. Detector findings: {findings}. {advice}"


async def explain(verdict: Verdict, content_excerpt: str = "") -> tuple[str, str | None]:
    """Write the investor-facing explanation. Returns (explanation, error)."""
    if not is_enabled():
        return _fallback_explanation(verdict), "OPENROUTER_API_KEY not set"

    findings = [
        {"detector": s.name, "finding": s.summary, "available": s.available,
         "error": s.error}
        for s in verdict.signals
    ]
    briefing = {
        "overall_band": verdict.band,
        "override_applied": verdict.override_applied,
        "detector_findings": findings,
        "content_excerpt": (content_excerpt or "")[:2000],
        "transcript_excerpt": (verdict.transcript or "")[:2000],
    }

    messages = [
        {"role": "system", "content": _EXPLAIN_SYSTEM},
        {"role": "user", "content": json.dumps(briefing, ensure_ascii=False)},
    ]
    try:
        raw_text = await _send_llm_request(messages, max_tokens=1024)
    except Exception as exc:  # noqa: BLE001
        return _fallback_explanation(verdict), f"{type(exc).__name__}: {exc}"

    if raw_text.strip().lower().startswith("i'm sorry"):
        return _fallback_explanation(verdict), "model declined to write an explanation"

    return (raw_text or _fallback_explanation(verdict)), None


async def health() -> str:
    if not is_enabled():
        return "disabled (no OPENROUTER_API_KEY or ANTHROPIC_API_KEY)"
    try:
        await _send_llm_request(
            [{"role": "system", "content": _EXPLAIN_SYSTEM},
             {"role": "user", "content": "ok"}],
            max_tokens=1,
        )
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {type(exc).__name__}"
