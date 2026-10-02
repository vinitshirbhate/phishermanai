"""ffmpeg helpers shared by the video and audio paths.

The binary comes from the `imageio-ffmpeg` wheel rather than from the host. That
removes the last non-pip install step: a deployment target no longer needs
ffmpeg on PATH, an apt-get layer, or a hand-set FFMPEG_PATH -- `pip install -r
requirements.txt` is the whole setup. Set FFMPEG_PATH anyway to override it.

One thing the wheel does not ship is ffprobe, so duration is read by parsing
ffmpeg's own header output instead. See probe_duration.
"""

from __future__ import annotations

import asyncio
import functools
import re
import shutil
import subprocess
from pathlib import Path

from ..config import get_settings

# "  Duration: 00:01:02.90, start: 0.000000, bitrate: 129 kb/s"
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


@functools.lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    """Path to the ffmpeg binary, resolved once.

    Explicit config wins, then the wheel's bundled static build, then whatever is
    on PATH. The bundled build is the one that makes this work on a bare
    container, so it is preferred over PATH rather than the other way round --
    a host ffmpeg is likelier to be an unknown version than the pinned wheel.
    """
    configured = (get_settings().ffmpeg_path or "").strip()
    if configured and configured.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        if Path(configured).exists():
            return configured

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - fall through to PATH
        pass

    return shutil.which("ffmpeg") or "ffmpeg"


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out, err
    except NotImplementedError:
        # Windows' Proactor loop is not always available under the worker model
        # uvicorn picks; fall back to a threaded subprocess rather than failing.
        proc = await asyncio.to_thread(
            subprocess.run, args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return proc.returncode or 0, proc.stdout, proc.stderr


async def probe_duration(path: str | Path) -> float | None:
    """Duration in seconds, or None if ffmpeg can't read the file.

    Parsed out of ffmpeg's banner rather than asked of ffprobe, which the
    imageio-ffmpeg wheel does not ship. `ffmpeg -i FILE` with no output file
    prints the container header and exits non-zero ("At least one output file
    must be specified") -- that non-zero exit is the normal path here, so the
    return code is deliberately ignored and only the parse decides.
    """
    _, _, err = await _run(ffmpeg_exe(), "-hide_banner", "-i", str(path))
    match = _DURATION_RE.search(err.decode("utf-8", "replace"))
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


async def extract_audio(video_path: str | Path, out_path: str | Path) -> str | None:
    """Extract a video's audio track to 16kHz mono WAV. Returns an error string,
    or None on success.

    A video with no audio track is a normal case (silent clip), not a failure, so the
    caller degrades to video-only analysis rather than erroring.
    """
    code, _, err = await _run(
        ffmpeg_exe(),
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
        ffmpeg_exe(),
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