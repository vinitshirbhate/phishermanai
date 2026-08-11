"""ffmpeg helpers shared by the video and audio paths."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from ..config import get_settings


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out, err
    except NotImplementedError:
        proc = await asyncio.to_thread(
            subprocess.run,
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc.returncode or 0, proc.stdout, proc.stderr


async def probe_duration(path: str | Path) -> float | None:
    """Duration in seconds, or None if ffprobe can't read the file."""
    settings = get_settings()
    # ffprobe sits next to ffmpeg; derive rather than adding a second config key.
    ffprobe = str(Path(settings.ffmpeg_path).with_name("ffprobe.exe"))
    if not Path(ffprobe).exists():
        ffprobe = "ffprobe"

    code, out, _ = await _run(
        ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(path)
    )
    if code != 0:
        return None
    try:
        return float(json.loads(out)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None


async def extract_audio(video_path: str | Path, out_path: str | Path) -> str | None:
    """Extract a video's audio track to 16kHz mono WAV -- the format both Whisper and
    the ASVspoof model expect. Returns an error string, or None on success.

    A video with no audio track is a normal case (silent clip), not a failure, so the
    caller degrades to video-only analysis rather than erroring.
    """
    code, _, err = await _run(
        get_settings().ffmpeg_path,
        "-y", "-i", str(video_path),
        "-vn",                 # drop video
        "-ac", "1",            # mono
        "-ar", "16000",        # 16kHz
        "-f", "wav",
        str(out_path),
    )
    if code != 0:
        detail = err.decode("utf-8", "replace").strip().splitlines()
        tail = detail[-1] if detail else "unknown ffmpeg error"
        if "does not contain any stream" in tail or "Output file #0 does not contain" in tail:
            return "video has no audio track"
        return f"audio extraction failed: {tail}"
    if not Path(out_path).exists() or Path(out_path).stat().st_size == 0:
        return "video has no audio track"
    return None


async def to_compact_audio(
    src_path: str | Path, out_path: str | Path, bitrate: str = "48k"
) -> str | None:
    """Transcode to 16kHz mono MP3 for upload to a size-capped API.

    The spoof service rejects anything over 5MB, which a raw WAV blows past quickly --
    a 10-minute 16kHz mono WAV is ~19MB. At 48kbps the same clip is ~3.6MB and the
    service scores it identically, since it resamples to a speech band regardless.
    Returns an error string, or None on success.
    """
    code, _, err = await _run(
        get_settings().ffmpeg_path,
        "-y", "-i", str(src_path),
        "-vn",                  # drop video if handed a container
        "-ac", "1",             # mono
        "-ar", "16000",         # 16kHz
        "-b:a", bitrate,
        str(out_path),
    )
    if code != 0:
        detail = err.decode("utf-8", "replace").strip().splitlines()
        return f"audio transcode failed: {detail[-1] if detail else 'unknown'}"
    if not Path(out_path).exists() or Path(out_path).stat().st_size == 0:
        return "audio transcode produced an empty file"
    return None


async def image_to_clip(image_path: str | Path, out_path: str | Path) -> str | None:
    """Wrap a still image into a 1-second video so the frame-based deepfake Space can
    score it. Returns an error string, or None on success."""
    code, _, err = await _run(
        get_settings().ffmpeg_path,
        "-y", "-loop", "1", "-i", str(image_path),
        "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p",
        # The detector crops faces; keep dimensions even for yuv420p.
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        str(out_path),
    )
    if code != 0:
        detail = err.decode("utf-8", "replace").strip().splitlines()
        return f"image conversion failed: {detail[-1] if detail else 'unknown'}"
    return None
