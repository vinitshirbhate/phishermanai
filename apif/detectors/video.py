"""Video deepfake detection, run locally on an ONNX EfficientNet-B0.

Replaces the remote Hugging Face Space this used to call. The Space was a free
one -- cold starts, queueing and outright downtime were the normal case, and a
verdict that depends on someone else's free tier being awake is not a verdict
you can demo. This runs in-process in about a second per clip with no network
at all.

The graph is `apif/data/models/ffpp_efficientnet_b0.onnx`, exported from the
FaceForensics++ checkpoint by deepfake_detection/video_detection/export_onnx.py
(that script needs torch; this module does not, which is the point -- torch's
CPU wheel does not fit in a small container and onnxruntime does).

    frames -> largest face per frame -> 224x224, ImageNet norm -> P(fake) each
           -> top-quarter mean -> Signal

TWO THINGS THAT DECIDE WHETHER THE NUMBERS MEAN ANYTHING
--------------------------------------------------------
The model was trained on face crops. Fed whole frames it is out of distribution
and reads almost everything as real -- both known deepfakes in the sample set
score ~0.3 uncropped and ~0.9 cropped. So: no face found, no verdict. The
Signal comes back unavailable rather than confidently clean, because "we could
not look" and "we looked and it is fine" must not render the same way.

And per-frame scores are aggregated by top-quarter mean, not by mean. Only some
frames of a manipulated clip carry visible artefacts; averaging over the clean
ones buries the signal (one sample: mean 0.50, top-quarter 0.88).
"""

from __future__ import annotations

import functools
from pathlib import Path

import anyio
import cv2
import numpy as np
import onnxruntime as ort

from ..config import get_settings
from ..schemas import SIGNAL_VIDEO_DEEPFAKE, Signal

# These are imported at module scope on purpose, not lazily inside the functions
# that use them.
#
# cv2's __init__ reassigns sys.modules["cv2"] partway through its own bootstrap.
# A thread that imports cv2 while another is mid-bootstrap finds a populated
# sys.modules entry, returns immediately, and gets the half-built module -- which
# presents as `AttributeError: module 'cv2' has no attribute 'CascadeClassifier'`
# from whichever thread lost the race. Scoring runs in a worker thread via
# anyio.to_thread, and /verify-link overlaps it with Firecrawl and coordination
# work, so a lazy import here is genuinely reachable and was observed in
# production. Importing at module scope means it happens once, during app import,
# before any request thread exists. It costs ~0.3s of startup and removes the
# failure mode entirely.

IMG_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# Longest side a frame is downscaled to before face detection. A head is a head
# at 960px, and detecting on a 4K frame costs several times the time to find it.
_DETECT_MAX_SIDE = 960

# Up to this many frames, sample by walking the file; past it, seek instead.
# Walking with grab() measured ~4.7x faster than seeking to each index, because
# every seek makes the decoder restart from the preceding keyframe.
_SEQUENTIAL_SCAN_LIMIT = 3000

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@functools.lru_cache(maxsize=1)
def _session():
    """Lazy singleton for the *session* only -- the 16MB graph is loaded on first
    use, while onnxruntime itself is imported at module scope above."""
    settings = get_settings()
    path = Path(settings.video_model_path)
    if not path.exists():
        raise FileNotFoundError(
            f"video model not found: {path}. Build it with "
            f"`python deepfake_detection/video_detection/export_onnx.py`."
        )

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = settings.onnx_intra_op_threads
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # The arena allocator holds freed blocks to save allocation time. On a small
    # container scoring a handful of frames per request that roughly doubles
    # steady-state RSS to save a few milliseconds -- the wrong trade here.
    opts.enable_cpu_mem_arena = False

    available = set(ort.get_available_providers())
    providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in available]
    return ort.InferenceSession(str(path), opts, providers=providers or ["CPUExecutionProvider"])


@functools.lru_cache(maxsize=1)
def _cascade():
    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        raise RuntimeError(f"could not load Haar cascade from {path}")
    return cascade


def _largest_face(frame):
    """(x, y, w, h) of the biggest usable face in a BGR frame, or None."""
    h_img, w_img = frame.shape[:2]
    scale = min(1.0, _DETECT_MAX_SIDE / max(h_img, w_img))
    small = (cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
             if scale < 1.0 else frame)

    min_side = int(min(small.shape[:2]) * get_settings().video_min_face_ratio)
    grey = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    boxes = [
        tuple(map(int, b))
        for b in _cascade().detectMultiScale(
            grey, scaleFactor=1.1, minNeighbors=5,
            minSize=(max(min_side, 30), max(min_side, 30)),
        )
    ]
    boxes = [b for b in boxes if b[2] >= min_side and b[3] >= min_side]
    if not boxes:
        return None

    x, y, w, h = max(boxes, key=lambda b: b[2] * b[3])
    if scale < 1.0:
        x, y, w, h = (int(v / scale) for v in (x, y, w, h))
    return x, y, w, h


def _iter_frames(path: Path, count: int):
    """Yield evenly spaced frames one at a time.

    A generator, not a list: sixteen 1080p frames held at once are ~100MB of
    uint8 before anything is done with them, and only the 224x224 crops need to
    survive the loop.
    """
    if path.suffix.lower() in _IMAGE_SUFFIXES:
        image = cv2.imread(str(path))
        if image is not None:
            yield image
        return

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        yielded = 0

        if 0 < total <= _SEQUENTIAL_SCAN_LIMIT:
            wanted = set(np.linspace(0, total - 1, min(count, total)).astype(int).tolist())
            for idx in range(max(wanted) + 1):
                if idx in wanted:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    yielded += 1
                    yield frame
                elif not cap.grab():
                    break
        elif total > 0:
            for idx in np.linspace(0, total - 1, min(count, total)).astype(int):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
                ok, frame = cap.read()
                if ok:
                    yielded += 1
                    yield frame

        # Some containers report no frame count and silently fail to seek.
        if yielded == 0:
            cap.release()
            cap = cv2.VideoCapture(str(path))
            while yielded < count:
                ok, frame = cap.read()
                if not ok:
                    break
                yielded += 1
                yield frame
    finally:
        cap.release()


def _preprocess(image):
    """BGR uint8 -> normalised CHW float32, exactly as in training."""
    resized = cv2.resize(image, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    normed = (rgb - np.array(IMAGENET_MEAN, np.float32)) / np.array(IMAGENET_STD, np.float32)
    return normed.transpose(2, 0, 1)


def _score_sync(video_path: str) -> dict:
    """Blocking inference. Called in a worker thread, never on the event loop."""
    settings = get_settings()
    path = Path(video_path)

    tensors = []
    sampled = 0
    frame_pixels = 0
    for frame in _iter_frames(path, settings.video_frames_per_clip):
        if sampled == 0:
            frame_pixels = frame.shape[0] * frame.shape[1]
        sampled += 1
        box = _largest_face(frame)
        if box is not None:
            x, y, w, h = box
            tensors.append(_preprocess(frame[y:y + h, x:x + w]))

    if sampled == 0:
        return {"error": "no readable frames"}
    if not tensors:
        return {"error": "no face detected in sampled frames", "frames_sampled": sampled}

    session = _session()
    batch_size = settings.video_batch_size
    probs = np.concatenate([
        session.run(["prob_fake"], {"frames": np.stack(tensors[i:i + batch_size]).astype(np.float32)})[0].reshape(-1)
        for i in range(0, len(tensors), batch_size)
    ])

    k = max(3, int(round(probs.size * settings.video_topk_fraction)))
    score = float(np.sort(probs)[-min(k, probs.size):].mean())

    return {
        "score": score,
        "frames_sampled": sampled,
        "frames_scored": int(probs.size),
        "per_frame": [round(float(p), 4) for p in probs],
        "frame_pixels": frame_pixels,
    }


async def analyze(video_path: str | Path) -> Signal:
    """Score a video or image for facial manipulation. Never raises."""
    path = Path(video_path)
    if not path.exists():
        return Signal.unavailable(SIGNAL_VIDEO_DEEPFAKE, f"video not found: {path.name}")

    try:
        payload = await anyio.to_thread.run_sync(_score_sync, str(path))
    except FileNotFoundError as exc:
        return Signal.unavailable(SIGNAL_VIDEO_DEEPFAKE, str(exc))
    except Exception as exc:  # noqa: BLE001 - a detector must not fail the request
        return Signal.unavailable(
            SIGNAL_VIDEO_DEEPFAKE, f"video analysis failed ({type(exc).__name__}: {exc})"
        )

    if "error" in payload:
        # Notably includes "no face detected". The model only judges faces, and
        # its whole-frame bias runs towards real, so anything other than
        # unavailable here would be a confident answer about something it never
        # actually looked at.
        return Signal.unavailable(SIGNAL_VIDEO_DEEPFAKE, payload["error"])

    score = payload["score"]
    return Signal(
        name=SIGNAL_VIDEO_DEEPFAKE,
        score=max(0.0, min(1.0, score)),
        available=True,
        summary=(
            f"Video: {score:.1%} manipulated-face probability across "
            f"{payload['frames_scored']} frames with a detected face"
        ),
        evidence={
            "fake_probability": round(score, 4),
            "frames_sampled": payload["frames_sampled"],
            "frames_scored": payload["frames_scored"],
            "per_frame": payload["per_frame"],
            "model": "EfficientNet-B0 / FaceForensics++ (local ONNX)",
            "aggregation": "top-quarter mean",
        },
    )


async def health() -> str:
    """'ok', or a short reason. The model is on disk, so this is a load check."""
    try:
        await anyio.to_thread.run_sync(_session)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {type(exc).__name__}: {exc}"