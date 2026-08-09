"""Voice deepfake (spoof) detection via the Aurigin API.

Contract (verified live against https://api.aurigin.ai/v1/predict):

    POST /predict   multipart file=<audio>, header x-api-key
                 -> {"prediction_id": str,
                     "global":   {"result": "bonafide"|"spoofed",
                                  "score": float,        # spoof probability
                                  "confidence": float,
                                  "reason": str|null},
                     "segments": [{"start": s, "end": s, "result": str,
                                   "confidence": float, "scores": [float, ...]}],
                     "model": str, "audio_duration": float,
                     "processing_time": float, "warnings": [str]}

This replaced a local ASVspoof-style checkpoint that was never calibrated: it scored
genuine recordings as 100% spoof and saturated at 1.000 on every clip, so its output
carried no usable signal. The hosted model is calibrated and verified on the bundled
samples -- a genuine recording scores 0.020, a known fake 0.822, and a real
voice-conversion deepfake 0.973.

Two things the service handles that the local model did not, so this wrapper no longer
implements either: the score is calibrated (no label-polarity flag to get wrong), and
segmentation is server-side (no manual windowing -- `segments` locates *where* in the
clip the synthetic audio is).

There is deliberately no fallback to the old local checkpoint. Falling back to an
uncalibrated model that reports everything as spoof would be worse than reporting the
signal unavailable and letting fusion renormalize around it.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from ..config import get_settings
from ..schemas import SIGNAL_VOICE_SPOOF, Signal
from . import media

VERDICT_SYNTHETIC = "SYNTHETIC"
VERDICT_AUTHENTIC = "NO_SYNTHETIC_ARTEFACTS"

_SPOOFED = "spoofed"

# Formats the service accepts directly, so they upload without re-encoding.
_MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg"}

# Inference is remote and runs roughly real-time on long clips; bounded so a hung
# service cannot stall a /verify request that has other signals to report.
_TIMEOUT = httpx.Timeout(180.0, connect=10.0)


async def health() -> str:
    """Returns 'ok' or a short failure reason. Used by the app's own /health.

    The service documents no health route, so this is a reachability check only: any
    HTTP response proves DNS, TLS, and routing work. It deliberately does not probe
    /health and report that status -- an unrouted path returns 503 even while /predict
    is serving normally, which would report the detector down when it is not.
    """
    settings = get_settings()
    if not settings.aurigin_api_key:
        return "disabled (no AURIGIN_API_KEY)"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            await client.get(settings.aurigin_base_url.rstrip("/"))
        return "ok"
    except httpx.HTTPError as exc:
        return f"unreachable: {type(exc).__name__}"


async def _fit_bitrate(path: Path, cap_mb: float) -> str:
    """Highest MP3 bitrate whose output still fits under the upload cap.

    Falls back to a conservative 48k when the duration is unreadable -- that fits ten
    minutes of speech, past which the pipeline's own duration guard has already rejected
    the upload.
    """
    duration = await media.probe_duration(path)
    if not duration or duration <= 0:
        return "48k"
    kbps = int((cap_mb * 8_000 / duration) * 0.9)  # 10% headroom for container overhead
    return f"{max(32, min(128, kbps))}k"


def _worst_segment(segments: list[dict]) -> dict | None:
    """The most confidently-spoofed segment, else the most suspicious one.

    Segments carry a per-window `confidence` in their own label, so ranking spoofed
    segments by confidence surfaces the strongest evidence rather than an arbitrary one.
    """
    spoofed = [s for s in segments if s.get("result") == _SPOOFED]
    pool = spoofed or segments
    if not pool:
        return None
    return max(pool, key=lambda s: float(s.get("confidence") or 0.0))


async def analyze(audio_path: str | Path) -> Signal:
    """Score audio for synthetic-speech artefacts. Never raises."""
    path = Path(audio_path)
    if not path.exists():
        return Signal.unavailable(SIGNAL_VOICE_SPOOF, f"audio not found: {path.name}")

    settings = get_settings()
    if not settings.aurigin_api_key:
        return Signal.unavailable(SIGNAL_VOICE_SPOOF, "AURIGIN_API_KEY not set")

    cap_mb = settings.aurigin_max_upload_mb
    upload, mime, compact = path, _MIME.get(path.suffix.lower(), "audio/mpeg"), None
    try:
        # Send the original untouched when it already fits and is in a format the service
        # accepts. Lossy re-encoding measurably moves the score (a 12.9s sample read 0.822
        # as WAV and 0.705 after a 48kbps pass), so only pay that cost when the upload cap
        # forces it.
        if path.suffix.lower() not in _MIME or path.stat().st_size / 1e6 > cap_mb:
            staging = settings.upload_dir
            staging.mkdir(parents=True, exist_ok=True)
            compact = staging / f"{uuid.uuid4().hex}_spoof.mp3"

            transcode_error = await media.to_compact_audio(
                path, compact, bitrate=await _fit_bitrate(path, cap_mb)
            )
            if transcode_error:
                return Signal.unavailable(SIGNAL_VOICE_SPOOF, transcode_error)

            size_mb = compact.stat().st_size / 1e6
            if size_mb > cap_mb:
                return Signal.unavailable(
                    SIGNAL_VOICE_SPOOF,
                    f"audio too long for the spoof service ({size_mb:.1f}MB compressed, "
                    f"limit {cap_mb:.0f}MB)",
                )
            upload, mime = compact, "audio/mpeg"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                with upload.open("rb") as fh:
                    resp = await client.post(
                        f"{settings.aurigin_base_url.rstrip('/')}/predict",
                        headers={"x-api-key": settings.aurigin_api_key},
                        files={"file": (upload.name, fh, mime)},
                    )
            if resp.status_code == 401:
                return Signal.unavailable(SIGNAL_VOICE_SPOOF, "spoof service rejected the API key")
            if resp.status_code != 200:
                detail = (resp.text or "")[:160]
                return Signal.unavailable(
                    SIGNAL_VOICE_SPOOF, f"spoof service returned HTTP {resp.status_code}: {detail}"
                )
            data = resp.json()
        except httpx.HTTPError as exc:
            return Signal.unavailable(
                SIGNAL_VOICE_SPOOF, f"spoof service unreachable ({type(exc).__name__})"
            )
        except ValueError:
            return Signal.unavailable(SIGNAL_VOICE_SPOOF, "spoof service returned non-JSON")
    finally:
        if compact is not None:
            compact.unlink(missing_ok=True)

    overall = data.get("global") or {}
    if "result" not in overall:
        return Signal.unavailable(SIGNAL_VOICE_SPOOF, "spoof service returned no verdict")

    is_spoof = overall.get("result") == _SPOOFED
    score = float(overall.get("score") or 0.0)
    confidence = float(overall.get("confidence") or 0.0)
    segments = data.get("segments") or []
    worst = _worst_segment(segments)

    evidence = {
        "spoof_probability": score,
        "is_spoof": is_spoof,
        "result": overall.get("result"),
        "confidence": confidence,
        "reason": overall.get("reason"),
        "duration_seconds": data.get("audio_duration"),
        "segments_analysed": len(segments),
        "spoofed_segments": sum(1 for s in segments if s.get("result") == _SPOOFED),
        "model": data.get("model"),
        "prediction_id": data.get("prediction_id"),
        "warnings": data.get("warnings") or [],
        "segments": [
            {
                "start": s.get("start"),
                "end": s.get("end"),
                "result": s.get("result"),
                "confidence": s.get("confidence"),
            }
            for s in segments
        ],
    }
    if worst is not None:
        evidence["worst_window"] = [worst.get("start"), worst.get("end")]

    window_note = ""
    if worst is not None and len(segments) > 1:
        window_note = (
            f", strongest at {worst.get('start'):.0f}-{worst.get('end'):.0f}s "
            f"of {len(segments)} segments"
        )

    evidence["voice_verdict"] = VERDICT_SYNTHETIC if is_spoof else VERDICT_AUTHENTIC
    return Signal(
        name=SIGNAL_VOICE_SPOOF,
        score=max(0.0, min(1.0, score)),
        available=True,
        summary=(
            f"{'Synthetic' if is_spoof else 'Authentic'} audio "
            f"({score:.1%} spoof probability, {confidence:.0%} confidence{window_note})"
        ),
        evidence=evidence,
    )
