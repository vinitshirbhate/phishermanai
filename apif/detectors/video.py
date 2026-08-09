"""Video deepfake detection via a remote Hugging Face Space (MS-EffGCViT, frame-by-frame
with 6 domain-specific models).

Refactored from deepfake_detection/video_detection/main.py. Two changes matter:

- The gradio_client is constructed per request, not at import. Building it at import
  would make a remote HTTP call during `uvicorn` startup and hang the service if the
  Space is asleep.
- Every failure returns an unavailable Signal. This is a *free* Space: cold starts,
  queueing, and outright downtime are the normal case, not the exception. A demo where
  the video detector is briefly unavailable should still produce a verdict from the
  audio, text, and registry signals -- not a 500.
"""

from __future__ import annotations

from pathlib import Path

import anyio

from ..config import get_settings
from ..schemas import SIGNAL_VIDEO_DEEPFAKE, Signal

# Space defaults, carried over from the original script.
VARIANT = "fast"        # "fast" (b0, 8.7M params) or "pro" (b5, 50.3M, slower)
DATASET = "ff++"        # "kodf" (East Asian), "celeb-df-v2" (celebrity), "ff++" (Western)
NUM_FRAMES = 5
MARGIN_RATIO = 0.2
CONF_THRES = 0.5
MIN_FACE_RATIO = 0.01
TTA_HFLIP = 0.0
AGG_MODE = "conf"       # "conf" (heuristic, recommended), "mean", or "vote"


def _predict_sync(video_path: str) -> dict:
    from gradio_client import Client, file

    settings = get_settings()
    client = Client(settings.video_space_id)
    class_probabilities, result, _frame_table_html = client.predict(
        video_path=file(video_path),
        variant=VARIANT,
        dataset=DATASET,
        num_frames=NUM_FRAMES,
        margin_ratio=MARGIN_RATIO,
        conf_thres=CONF_THRES,
        min_face_ratio=MIN_FACE_RATIO,
        tta_hflip=TTA_HFLIP,
        agg_mode=AGG_MODE,
        api_name="/predict",
    )
    return {"class_probabilities": class_probabilities, "result": result}


def _fake_probability(class_probabilities: dict) -> float | None:
    """Pull the FAKE confidence out of the Space's gradio Label payload.

    The label text carries an emoji and varies in case, so match on a substring rather
    than an exact key -- and treat REAL as the complement when only REAL is present.
    """
    confidences = (class_probabilities or {}).get("confidences") or []
    real_conf: float | None = None
    for entry in confidences:
        label = str(entry.get("label", "")).upper()
        conf = entry.get("confidence")
        if conf is None:
            continue
        if "FAKE" in label:
            return float(conf)
        if "REAL" in label:
            real_conf = float(conf)
    return 1.0 - real_conf if real_conf is not None else None


async def analyze(video_path: str | Path) -> Signal:
    """Score a video for facial manipulation. Never raises."""
    path = Path(video_path)
    if not path.exists():
        return Signal.unavailable(SIGNAL_VIDEO_DEEPFAKE, f"video not found: {path.name}")

    settings = get_settings()
    try:
        with anyio.fail_after(settings.video_space_timeout):
            payload = await anyio.to_thread.run_sync(_predict_sync, str(path))
    except TimeoutError:
        return Signal.unavailable(
            SIGNAL_VIDEO_DEEPFAKE,
            f"detection Space timed out after {settings.video_space_timeout:.0f}s "
            "(free Space may be queued or asleep)",
        )
    except Exception as exc:  # noqa: BLE001 - gradio_client raises broadly
        return Signal.unavailable(
            SIGNAL_VIDEO_DEEPFAKE, f"detection Space unavailable ({type(exc).__name__}: {exc})"
        )

    score = _fake_probability(payload["class_probabilities"])
    if score is None:
        return Signal.unavailable(
            SIGNAL_VIDEO_DEEPFAKE, "no face detected in sampled frames"
        )

    result_text = str(payload.get("result", "")).strip()
    return Signal(
        name=SIGNAL_VIDEO_DEEPFAKE,
        score=max(0.0, min(1.0, score)),
        available=True,
        summary=f"Video: {score:.1%} manipulated-face probability across {NUM_FRAMES} frames",
        evidence={
            "fake_probability": round(score, 4),
            "space_verdict": result_text,
            "variant": VARIANT,
            "dataset": DATASET,
            "frames_sampled": NUM_FRAMES,
            "class_probabilities": payload["class_probabilities"],
        },
    )
