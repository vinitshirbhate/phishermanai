"""Per-modality analysis endpoints, plus the unified /verify entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import pipeline
from ..ingest import store
from ..schemas import TextAnalysisRequest, Verdict

router = APIRouter(prefix="/api/v1", tags=["analysis"])

_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _kind_for(filename: str, content_type: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in _AUDIO_SUFFIXES:
        return "audio"
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    # Extension is authoritative when present; fall back to the browser-supplied type.
    mime = (content_type or "").lower()
    for prefix, kind in (("audio/", "audio"), ("video/", "video"), ("image/", "image")):
        if mime.startswith(prefix):
            return kind
    return "unknown"


@router.post("/analyze/text", response_model=Verdict)
async def analyze_text(payload: TextAnalysisRequest) -> Verdict:
    """Score a message, email, or social post for scam/propaganda indicators."""
    source = payload.source_url or payload.sender
    verdict, entities = await pipeline.analyze_text(payload.text, source=source)
    store.record_analysis(
        "text", verdict, claimed_issuer=entities.claimed_issuer or "",
        tickers=entities.tickers, source=source or "",
    )
    return verdict


@router.post("/analyze/audio", response_model=Verdict)
async def analyze_audio(
    file: UploadFile = File(..., description="Audio clip to check"),
    source: str | None = Form(None),
    caption: str = Form("", description="Accompanying message text, if any"),
) -> Verdict:
    """Detect synthetic speech and analyse the transcript in the same pass."""
    audio_path = await pipeline.save_upload(file.filename or "audio.wav", await file.read())
    verdict, entities = await pipeline.analyze_audio(
        audio_path, source=source, caption=caption
    )
    store.record_analysis(
        "audio", verdict, claimed_issuer=entities.claimed_issuer or "",
        tickers=entities.tickers, source=source or "",
    )
    return verdict


@router.post("/analyze/video", response_model=Verdict)
async def analyze_video(
    file: UploadFile = File(..., description="Video clip to check"),
    caption: str = Form("", description="Accompanying post text, if any"),
    source: str | None = Form(None),
) -> Verdict:
    """Detect facial manipulation and analyse the audio track in the same pass."""
    video_path = await pipeline.save_upload(file.filename or "video.mp4", await file.read())
    verdict, entities = await pipeline.analyze_video(
        video_path, caption=caption, source=source
    )
    store.record_analysis(
        "video", verdict, claimed_issuer=entities.claimed_issuer or "",
        tickers=entities.tickers, source=source or "",
    )
    return verdict


@router.post("/verify", response_model=Verdict)
async def verify(
    text: str = Form("", description="Message text or post caption"),
    file: UploadFile | None = File(None, description="Audio, video, or image to check"),
    source: str | None = Form(None, description="URL, sender address, or @handle"),
    include_coordination: bool = Form(
        True, description="Fold in campaign analysis over ingested social chatter"
    ),
) -> Verdict:
    """One-click check. Accepts any combination of text and a media file, routes by type,
    and returns a single fused verdict with per-signal evidence."""
    if not text.strip() and file is None:
        raise HTTPException(400, "Provide text, a file, or both.")

    if file is None:
        verdict, entities = await pipeline.analyze_text(text, source=source)
        kind = "text"
    else:
        data = await file.read()
        if not data:
            raise HTTPException(400, "Uploaded file is empty.")
        path = await pipeline.save_upload(file.filename or "upload.bin", data)
        kind = _kind_for(file.filename or "", file.content_type)

        if kind == "audio":
            verdict, entities = await pipeline.analyze_audio(
                path, source=source, caption=text
            )
        elif kind == "video":
            verdict, entities = await pipeline.analyze_video(
                path, caption=text, source=source
            )
        elif kind == "image":
            verdict, entities = await pipeline.analyze_image(
                path, caption=text, source=source
            )
        else:
            raise HTTPException(
                415,
                f"Unsupported file type '{file.filename}'. Supported: audio "
                f"({', '.join(sorted(_AUDIO_SUFFIXES))}), video "
                f"({', '.join(sorted(_VIDEO_SUFFIXES))}), image "
                f"({', '.join(sorted(_IMAGE_SUFFIXES))}).",
            )

    if include_coordination:
        verdict = await pipeline.add_coordination_signal(verdict, content_excerpt=text)

    store.record_analysis(
        kind, verdict, claimed_issuer=entities.claimed_issuer or "",
        tickers=entities.tickers, source=source or "",
    )
    return verdict
