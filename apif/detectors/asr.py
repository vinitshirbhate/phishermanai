"""Speech-to-text via AssemblyAI. Bridges audio/video into the text-phishing path:
a vishing call becomes a transcript, and the transcript goes to the same classifier
that scores emails and social posts.

Replaces a local openai/whisper-small running under transformers. That model was
the single reason torch, transformers and librosa were installed at all -- roughly
2GB of wheels and a 10-20s load on the first request, to do a job a hosted API does
in a few seconds. Removing it is what lets the service fit in a small container.

    POST /v2/upload      raw bytes            -> {"upload_url": ...}
    POST /v2/transcript  {"audio_url": ...}   -> {"id": ..., "status": "queued"}
    GET  /v2/transcript/{id}                  -> poll until completed | error

WHAT LEAVES THE MACHINE
-----------------------
The audio is uploaded to a third party. That is a real change from the local
model, where nothing left the box. AssemblyAI's upload endpoint stores the file
only for the life of the transcription job, but if a deployment handles audio
that cannot go to a processor, this detector is the piece to reconsider -- the
rest of the pipeline stays local.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from ..config import get_settings

_BASE = "https://api.assemblyai.com/v2"

# Upload of a capped clip plus a transcription job that runs faster than real
# time. The pipeline's own duration guard has already rejected anything long.
_UPLOAD_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_POLL_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Polling cadence. Short clips finish in a few seconds, so a tight first interval
# keeps the common case fast; the ceiling stops a stuck job from spinning.
_POLL_INTERVAL = 2.0
_MAX_POLL_SECONDS = 300.0


async def health() -> str:
    """'ok' or a short failure reason. Used by the app's own /health."""
    settings = get_settings()
    if not settings.assemblyai_api_key:
        return "disabled (no ASSEMBLYAI_API_KEY)"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            # Asking for a transcript that cannot exist is the cheapest
            # authenticated round trip: 401 proves the key is wrong, 404 proves
            # the key is good and the service is up.
            resp = await client.get(
                f"{_BASE}/transcript/nonexistent",
                headers={"authorization": settings.assemblyai_api_key},
            )
        if resp.status_code == 401:
            return "rejected the API key"
        return "ok"
    except httpx.HTTPError as exc:
        return f"unreachable: {type(exc).__name__}"


async def _upload(client: httpx.AsyncClient, path: Path, key: str) -> tuple[str, str | None]:
    """Upload the audio, returning (upload_url, error)."""
    try:
        resp = await client.post(
            f"{_BASE}/upload",
            headers={"authorization": key},
            content=path.read_bytes(),
            timeout=_UPLOAD_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        return "", f"upload failed ({type(exc).__name__})"

    if resp.status_code == 401:
        return "", "AssemblyAI rejected the API key"
    if resp.status_code != 200:
        return "", f"upload returned HTTP {resp.status_code}: {(resp.text or '')[:160]}"
    try:
        return resp.json()["upload_url"], None
    except (ValueError, KeyError):
        return "", "upload returned no upload_url"


async def _submit(client: httpx.AsyncClient, audio_url: str, key: str) -> tuple[str, str | None]:
    """Queue the transcription job, returning (transcript_id, error)."""
    try:
        resp = await client.post(
            f"{_BASE}/transcript",
            headers={"authorization": key},
            json={"audio_url": audio_url, "language_detection": True},
            timeout=_POLL_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        return "", f"transcription request failed ({type(exc).__name__})"

    if resp.status_code not in (200, 201):
        return "", f"transcription returned HTTP {resp.status_code}: {(resp.text or '')[:160]}"
    try:
        return resp.json()["id"], None
    except (ValueError, KeyError):
        return "", "transcription returned no job id"


async def _poll(client: httpx.AsyncClient, job_id: str, key: str) -> tuple[str, str | None]:
    """Wait for the job, returning (text, error)."""
    waited = 0.0
    while waited < _MAX_POLL_SECONDS:
        try:
            resp = await client.get(
                f"{_BASE}/transcript/{job_id}",
                headers={"authorization": key},
                timeout=_POLL_TIMEOUT,
            )
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return "", f"polling failed ({type(exc).__name__})"

        status = data.get("status")
        if status == "completed":
            return (data.get("text") or "").strip(), None
        if status == "error":
            return "", f"transcription failed: {data.get('error') or 'unknown error'}"

        await asyncio.sleep(_POLL_INTERVAL)
        waited += _POLL_INTERVAL

    return "", f"transcription timed out after {_MAX_POLL_SECONDS:.0f}s"


async def transcribe(audio_path: str | Path) -> tuple[str, str | None]:
    """Transcribe an audio file.

    Returns (transcript, error). On failure the transcript is "" and error explains why,
    so callers can degrade instead of failing the whole request.
    """
    path = Path(audio_path)
    if not path.exists():
        return "", f"audio file not found: {path.name}"

    key = get_settings().assemblyai_api_key
    if not key:
        return "", "ASSEMBLYAI_API_KEY not set"

    async with httpx.AsyncClient() as client:
        upload_url, error = await _upload(client, path, key)
        if error:
            return "", error

        job_id, error = await _submit(client, upload_url, key)
        if error:
            return "", error

        text, error = await _poll(client, job_id, key)
        if error:
            return "", error

    if not text:
        return "", "no speech detected"
    return text, None