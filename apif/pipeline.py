"""Orchestration: routes content to the applicable detectors, runs them concurrently,
and fuses the results into one Verdict.

Ordering matters here and is not arbitrary:
  1. Media is reduced to text first (ASR), because the transcript is what the
     phishing classifier consumes -- a vishing call and a phishing email then travel the
     same path.
  2. Entity extraction runs before the registry and market engines, because it supplies
     their inputs (claimed_issuer, tickers). Those two cannot start earlier.
  3. Everything that has its inputs runs concurrently. Transcription and the spoof check
     are both remote calls of a few seconds each, so overlapping them rather than
     chaining them is most of the latency budget.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings
from .detectors import asr, llm_analyst, media, text_phishing, video as video_detector, voice
from .engines import coordination, fusion, market, trust_registry
from .ingest import store
from .schemas import ExtractedEntities, Signal, Verdict


class MediaTooLongError(Exception):
    """Raised when an upload exceeds the duration cap.

    Deliberately an exception rather than an unavailable Signal: fusing a lone
    unavailable signal yields band "Low" with score 0.0, which a client rendering only
    the band would show as green. Returning "safe" for content that was never examined
    is the worst possible failure mode for a scam-detection tool, so the request is
    rejected outright instead.
    """


async def _staging_dir() -> Path:
    path = get_settings().upload_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_upload(filename: str, data: bytes) -> Path:
    """Persist an uploaded file under a collision-proof name."""
    staging = await _staging_dir()
    suffix = Path(filename or "upload").suffix or ".bin"
    path = staging / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(data)
    return path


async def _duration_guard(path: Path) -> None:
    """Reject media long enough to stall a CPU-only deployment, with a clear reason."""
    duration = await media.probe_duration(path)
    limit = get_settings().max_media_seconds
    if duration is not None and duration > limit:
        raise MediaTooLongError(
            f"Media is {duration:.0f}s long; the limit is {limit:.0f}s on this "
            f"CPU-only deployment. Trim the clip to under {limit:.0f}s and retry."
        )


async def analyze_text(
    text: str,
    source: str | None = None,
    at: datetime | None = None,
    known_entities: ExtractedEntities | None = None,
) -> tuple[Verdict, ExtractedEntities]:
    """Full text pipeline: classify, extract entities, then corroborate against the
    registry and the market."""
    at = at or datetime.now(timezone.utc)

    # Phishing classification and entity extraction are independent -- overlap them.
    phishing_task = asyncio.create_task(text_phishing.detect(text))
    if known_entities is not None:
        entities, entity_error = known_entities, None
    else:
        entities, entity_error = await llm_analyst.extract_entities(text)
    phishing = await phishing_task

    # These two depend on the extracted entities, so they start only now.
    registry_signal, market_signal = await asyncio.gather(
        asyncio.to_thread(
            trust_registry.analyze, source, entities.claimed_issuer, None
        ),
        market.analyze(entities.tickers, at=at),
    )

    signals = [phishing, registry_signal, market_signal]
    verdict = fusion.fuse(signals)
    verdict.explanation, _ = await llm_analyst.explain(verdict, content_excerpt=text)
    if entity_error:
        verdict.signals.append(
            Signal.unavailable("entity_extraction", entity_error)
        )
    return verdict, entities


def _combine_text(caption: str, transcript: str) -> str:
    """Merge the accompanying post text with what was actually said.

    Both must reach the classifier. In a fabricated executive video the scam usually
    lives in the caption ("guaranteed 300% returns, deposit here") while the audio is
    innocuous B-roll -- scoring only the transcript would clear the post entirely.
    """
    parts = [p.strip() for p in (caption, transcript) if p and p.strip()]
    return "\n\n".join(parts)


async def analyze_audio(
    audio_path: str | Path,
    source: str | None = None,
    caption: str = "",
) -> tuple[Verdict, ExtractedEntities]:
    """Audio pipeline: transcribe, then run the transcript (plus any accompanying
    caption) through the text path while the spoof check runs in parallel."""
    path = Path(audio_path)
    await _duration_guard(path)

    voice_task = asyncio.create_task(voice.analyze(path))
    transcript, transcript_error = await asr.transcribe(path)

    combined = _combine_text(caption, transcript)
    entities = ExtractedEntities()
    text_signals: list[Signal] = []
    if combined:
        entities, _ = await llm_analyst.extract_entities(combined)
        phishing_task = asyncio.create_task(text_phishing.detect(combined))
        registry_signal, market_signal = await asyncio.gather(
            asyncio.to_thread(
                trust_registry.analyze, source, entities.claimed_issuer, None
            ),
            market.analyze(entities.tickers),
        )
        text_signals = [await phishing_task, registry_signal, market_signal]
    else:
        text_signals = [Signal.unavailable("text_phishing", transcript_error or "no speech")]
        if source:
            text_signals.append(
                await asyncio.to_thread(trust_registry.analyze, source, None, None)
            )

    voice_signal = await voice_task
    verdict = fusion.fuse([voice_signal, *text_signals])
    verdict.transcript = transcript or None
    verdict.explanation, _ = await llm_analyst.explain(verdict, content_excerpt=combined)
    return verdict, entities


async def analyze_video(
    video_path: str | Path,
    caption: str = "",
    source: str | None = None,
) -> tuple[Verdict, ExtractedEntities]:
    """Video pipeline: frame-level deepfake detection plus the full audio-track pipeline.

    A fabricated executive video usually fails on both channels; checking only the frames
    misses a real face dubbed with a synthetic voice.
    """
    path = Path(video_path)
    await _duration_guard(path)

    video_task = asyncio.create_task(video_detector.analyze(path))

    staging = await _staging_dir()
    audio_path = staging / f"{path.stem}_audio.wav"
    audio_error = await media.extract_audio(path, audio_path)

    entities = ExtractedEntities()
    other_signals: list[Signal] = []
    transcript: str | None = None

    if audio_error:
        # Silent clip, or no audio stream: still analyse the caption on its own.
        other_signals.append(Signal.unavailable("voice_spoof", audio_error))
        if caption:
            caption_verdict, entities = await analyze_text(caption, source=source)
            other_signals.extend(caption_verdict.signals)
    else:
        # The caption travels with the transcript so both are classified together.
        audio_verdict, entities = await analyze_audio(
            audio_path, source=source, caption=caption
        )
        transcript = audio_verdict.transcript
        other_signals.extend(audio_verdict.signals)

    video_signal = await video_task
    verdict = fusion.fuse([video_signal, *other_signals])
    verdict.transcript = transcript
    verdict.explanation, _ = await llm_analyst.explain(
        verdict, content_excerpt=transcript or caption
    )
    return verdict, entities


async def analyze_image(
    image_path: str | Path, caption: str = "", source: str | None = None
) -> tuple[Verdict, ExtractedEntities]:
    """Still images go straight to the deepfake detector.

    This used to wrap the image in a 1-second H.264 clip so the remote Space
    would accept it. The local detector scores a single frame natively, so that
    round trip through ffmpeg -- and the re-encoding artefacts it introduced
    into the very pixels being judged -- is gone.
    """
    video_task = asyncio.create_task(video_detector.analyze(Path(image_path)))

    entities = ExtractedEntities()
    other_signals: list[Signal] = []
    if caption:
        caption_verdict, entities = await analyze_text(caption, source=source)
        other_signals.extend(caption_verdict.signals)
    elif source:
        other_signals.append(
            await asyncio.to_thread(trust_registry.analyze, source, None, None)
        )

    video_signal = await video_task
    verdict = fusion.fuse([video_signal, *other_signals])
    verdict.explanation, _ = await llm_analyst.explain(verdict, content_excerpt=caption)
    return verdict, entities


async def add_coordination_signal(verdict: Verdict, content_excerpt: str = "") -> Verdict:
    """Fold stored social chatter into an existing verdict and re-fuse.

    Coordination is a property of a *campaign*, not of one artefact, so it is computed
    against everything ingested rather than the submitted content alone.
    """
    posts = await asyncio.to_thread(store.social_posts_for_graph)
    signal = await asyncio.to_thread(coordination.analyze, posts)
    signals = [s for s in verdict.signals if s.name != signal.name] + [signal]

    updated = fusion.fuse(signals)
    updated.transcript = verdict.transcript
    # The explanation must be rewritten, not carried over: re-fusing can move the band,
    # and the previous text quotes the old one. Reusing it produces a response whose
    # explanation contradicts its own headline.
    updated.explanation, _ = await llm_analyst.explain(
        updated, content_excerpt=content_excerpt or verdict.transcript or ""
    )
    return updated
