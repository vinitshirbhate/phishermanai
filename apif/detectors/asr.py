"""Whisper transcription. Bridges audio/video into the text-phishing path: a vishing
call becomes a transcript, and the transcript goes to the same classifier that scores
emails and social posts.

Model is openai/whisper-small, already present in the local HF cache. torch here is a
CPU build, so the model is loaded lazily (never at import) and every inference runs in a
worker thread -- a 30s forward pass on the event loop would stall the whole service.
"""

from __future__ import annotations

import functools
from pathlib import Path

import anyio

from . import warm_imports
from ..config import get_settings


@functools.lru_cache(maxsize=1)
def _pipeline():
    """Lazy singleton. First call pays the model load (~10-20s on CPU); later calls are
    free. Kept out of module scope so importing this file stays instant."""
    warm_imports()
    from transformers import pipeline  # imported late: heavy, and needs compat applied

    settings = get_settings()
    return pipeline(
        "automatic-speech-recognition",
        model=settings.whisper_model,
        # Whisper's encoder has a hard 30s receptive field. Without chunking, audio past
        # the first 30s is silently dropped -- the model returns a confident transcript
        # of the opening only, which is worse than an error.
        chunk_length_s=30,
        stride_length_s=5,
    )


def _transcribe_sync(path: str) -> dict:
    return _pipeline()(path, return_timestamps=False)


async def transcribe(audio_path: str | Path) -> tuple[str, str | None]:
    """Transcribe an audio file.

    Returns (transcript, error). On failure the transcript is "" and error explains why,
    so callers can degrade instead of failing the whole request.
    """
    path = Path(audio_path)
    if not path.exists():
        return "", f"audio file not found: {path.name}"

    try:
        result = await anyio.to_thread.run_sync(_transcribe_sync, str(path))
    except Exception as exc:  # noqa: BLE001 - transformers raises a wide variety
        return "", f"transcription failed ({type(exc).__name__}: {exc})"

    text = (result.get("text") or "").strip() if isinstance(result, dict) else str(result)
    if not text:
        return "", "no speech detected"
    return text, None
