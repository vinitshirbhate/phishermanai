"""Video deepfake detection. Everything the detector needs is in this file.

    python test.py                          # samples/fake.mp4
    python test.py path/to/video.mp4
    python test.py video.mp4 --json         # machine-readable
    python test.py video.mp4 --frames 32 --agg max
    python test.py samples/photo.jpeg       # stills work too

Runs on onnxruntime and OpenCV. No torch, no timm, no network -- which is what
makes a 512 MB free-tier box viable; see export_onnx.py for how the graph was
produced, and the measured figures in config.py for how much headroom is left
(enough for one request at a time, not two).

    video -> sample N frames -> crop the largest face -> 224x224, ImageNet norm
          -> EfficientNet-B0 -> P(fake) per frame -> aggregate -> verdict

WHAT THIS MODEL CAN AND CANNOT TELL YOU
---------------------------------------
It was trained on FaceForensics++, so it judges *faces*. Three consequences
worth knowing before you trust a number it gives you:

  - No face, no verdict. Whole frames are out of distribution and the model
    reads them as real almost regardless of content, so a clip where no face is
    found returns UNKNOWN rather than a confident REAL. Silence beats a
    confident wrong answer.
  - It detects face manipulation, not lies. A genuine face saying false things
    is REAL to this model. That is a different problem from the one the rest of
    this repo solves.
  - It has seen FF++ manipulations. A generator it has not seen may not trip it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

import config

log = logging.getLogger("deepfake.video")

_MEAN = np.array(config.IMAGENET_MEAN, dtype=np.float32)
_STD = np.array(config.IMAGENET_STD, dtype=np.float32)
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# Longest side a frame is downscaled to before face detection runs on it.
_DETECT_MAX_SIDE = 960

# Up to this many frames, sample by walking the file; past it, seek instead.
_SEQUENTIAL_SCAN_LIMIT = 3000

_session: ort.InferenceSession | None = None
_detector: "FaceDetector | None" = None


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def get_session() -> ort.InferenceSession:
    """The ONNX session, built once and reused.

    Loading the graph costs a few hundred milliseconds. On a free tier that
    spins down between requests you pay it on every cold start anyway, so there
    is no reason to pay it twice.
    """
    global _session
    if _session is not None:
        return _session

    if not config.MODEL_PATH.exists():
        raise FileNotFoundError(
            f"model not found: {config.MODEL_PATH}\n"
            f"Build it once with:  python export_onnx.py"
        )

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = config.INTRA_OP_THREADS
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # The arena allocator trades memory for speed by holding on to freed blocks.
    # That is the wrong trade on a 512 MB box scoring a handful of frames per
    # request -- it roughly doubles steady-state RSS to save a few ms.
    opts.enable_cpu_mem_arena = False

    available = set(ort.get_available_providers())
    providers = [p for p in config.PROVIDERS if p in available] or ["CPUExecutionProvider"]

    _session = ort.InferenceSession(str(config.MODEL_PATH), opts, providers=providers)
    log.info("loaded %s via %s", config.MODEL_PATH.name, _session.get_providers()[0])
    return _session


# ---------------------------------------------------------------------------
# Face detection
# ---------------------------------------------------------------------------

class FaceDetector:
    """Largest-face detector, YuNet when available and Haar otherwise.

    Haar is the default because OpenCV bundles it -- no download, no extra file
    in the image, works offline. It is also visibly weaker on turned heads, so
    if face_detection_yunet_2023mar.onnx is present it wins.
    """

    def __init__(self) -> None:
        self.yunet = None
        self.cascade = None

        if config.YUNET_PATH.exists():
            try:
                self.yunet = cv2.FaceDetectorYN.create(str(config.YUNET_PATH), "", (320, 320))
                log.info("face detector: YuNet")
                return
            except Exception as exc:  # noqa: BLE001 - fall back rather than fail
                log.warning("YuNet load failed (%s), falling back to Haar", exc)

        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.cascade = cv2.CascadeClassifier(path)
        if self.cascade.empty():
            raise RuntimeError(f"could not load Haar cascade from {path}")
        log.info("face detector: Haar")

    def largest_face(self, frame: np.ndarray) -> tuple[int, int, int, int] | None:
        """Return (x, y, w, h) of the biggest usable face, or None.

        Detection runs on a downscaled copy and the box is scaled back up, so
        the crop still comes out of the full-resolution frame. Detecting on a
        4K frame directly costs several times the time and memory to find the
        same face -- a head is a head at 960 px wide.
        """
        h_img, w_img = frame.shape[:2]
        scale = min(1.0, _DETECT_MAX_SIDE / max(h_img, w_img))
        small = (cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                 if scale < 1.0 else frame)
        h_det, w_det = small.shape[:2]
        min_side = int(min(h_det, w_det) * config.MIN_FACE_RATIO)

        if self.yunet is not None:
            self.yunet.setInputSize((w_det, h_det))
            _, faces = self.yunet.detect(small)
            boxes = [] if faces is None else [tuple(map(int, f[:4])) for f in faces]
        else:
            grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            # equalizeHist buys a little robustness on dark or flat footage,
            # which is common in forwarded/re-encoded video.
            grey = cv2.equalizeHist(grey)
            boxes = [
                tuple(map(int, b))
                for b in self.cascade.detectMultiScale(
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


def get_detector() -> FaceDetector:
    global _detector
    if _detector is None:
        _detector = FaceDetector()
    return _detector


def crop_face(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    mx, my = int(w * config.FACE_MARGIN), int(h * config.FACE_MARGIN)
    h_img, w_img = frame.shape[:2]
    return frame[max(0, y - my):min(h_img, y + h + my),
                 max(0, x - mx):min(w_img, x + w + mx)]


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

def iter_frames(path: Path, count: int) -> "Iterator[np.ndarray]":
    """Yield evenly spaced frames across the whole clip, one at a time.

    Spread rather than the first N: manipulation is not always present from the
    first second, and consecutive frames are nearly identical anyway, so N
    neighbours tell you roughly what one frame would have.

    A generator, not a list, and on the 1920x1920 sample that alone took peak
    memory from 604 MB to 471 MB -- sixteen frames of it held at once are
    ~180 MB of uint8 before anything is done with them, whereas yielded one at
    a time only the 224x224 crops survive the loop.

    It does not make the process resolution-independent: FFmpeg's own decode
    buffers still scale with the frame size and are not ours to free. See the
    measurements against MAX_DECODE_PIXELS in config.py.
    """
    if path.suffix.lower() in _IMAGE_SUFFIXES:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"could not read image: {path}")
        yield img
        return

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"could not open video: {path}")

    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        yielded = 0

        if 0 < total <= _SEQUENTIAL_SCAN_LIMIT:
            # Walk the file once, decoding past the frames we do not want with
            # grab() -- which advances the decoder without materialising a
            # frame -- and only calling retrieve() on the ones we do. Measured
            # 4.7x faster than seeking to each index on the 1920x1920 sample
            # (0.45s vs 2.10s), because every cap.set() makes the decoder
            # restart from the preceding keyframe.
            wanted = set(np.linspace(0, total - 1, min(count, total)).astype(int).tolist())
            last = max(wanted)
            for idx in range(last + 1):
                if idx in wanted:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    yielded += 1
                    yield frame
                elif not cap.grab():
                    break

        elif total > 0:
            # Long file: walking every frame to reach the end would cost more
            # than the seeks do, so pay for the keyframe restarts instead.
            for idx in np.linspace(0, total - 1, min(count, total)).astype(int):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
                ok, frame = cap.read()
                if ok:
                    yielded += 1
                    yield frame

        # Some containers report no frame count, and seeking on them silently
        # fails. Read from the top rather than yielding nothing.
        if yielded == 0:
            cap.release()
            cap = cv2.VideoCapture(str(path))
            while yielded < count:
                ok, frame = cap.read()
                if not ok:
                    break
                yielded += 1
                yield frame

        if yielded == 0:
            raise ValueError(f"no readable frames in {path}")
    finally:
        cap.release()


def preprocess(image: np.ndarray) -> np.ndarray:
    """BGR uint8 -> normalised CHW float32, exactly as in training."""
    resized = cv2.resize(image, (config.IMG_SIZE, config.IMG_SIZE), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return ((rgb - _MEAN) / _STD).transpose(2, 0, 1)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_batch(tensors: list[np.ndarray]) -> np.ndarray:
    """P(fake) per input, in chunks so peak memory stays flat."""
    session = get_session()
    out: list[np.ndarray] = []
    for i in range(0, len(tensors), config.BATCH_SIZE):
        batch = np.stack(tensors[i:i + config.BATCH_SIZE]).astype(np.float32)
        out.append(session.run(["prob_fake"], {"frames": batch})[0].reshape(-1))
    return np.concatenate(out) if out else np.array([], dtype=np.float32)


def aggregate(probs: np.ndarray, mode: str | None = None) -> float:
    """Per-frame probabilities -> one score for the clip.

    See config.AGGREGATION for why the default is not the mean.
    """
    mode = mode or config.AGGREGATION
    if probs.size == 0:
        raise ValueError("nothing to aggregate")
    if mode == "mean":
        return float(probs.mean())
    if mode == "max":
        return float(probs.max())
    if mode == "topk":
        k = max(config.TOPK_MIN, int(round(probs.size * config.TOPK_FRACTION)))
        return float(np.sort(probs)[-min(k, probs.size):].mean())
    raise ValueError(f"unknown aggregation: {mode!r} (use topk, mean or max)")


def detect(
    video_path: str | Path,
    frames: int | None = None,
    aggregation: str | None = None,
    use_face_crop: bool | None = None,
) -> dict[str, Any]:
    """Classify one clip.

    Returns prediction REAL / FAKE / UNKNOWN, plus enough detail to argue with
    the result: the per-frame scores, how many frames had a detectable face, and
    which knobs produced the number.
    """
    started = time.perf_counter()
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"no such file: {path}")

    frames = frames or config.FRAMES_PER_CLIP
    crop = config.USE_FACE_CROP if use_face_crop is None else use_face_crop

    # Consume the generator frame by frame and keep only the 224x224 crops, so
    # that what this loop holds scales with the number of frames scored rather
    # than with the resolution of the video.
    detector = get_detector() if crop else None
    tensors: list[np.ndarray] = []
    faces_found = 0
    sampled_count = 0
    frame_pixels = 0

    for frame in iter_frames(path, frames):
        if sampled_count == 0:
            h, w = frame.shape[:2]
            frame_pixels = h * w
            if frame_pixels > config.MAX_DECODE_PIXELS:
                # Not fatal here -- a CLI run on a workstation is fine. It is
                # the deployment that needs to care, so say so loudly and hand
                # the number back in the result for callers that enforce it.
                log.warning(
                    "%dx%d (%.1f MP) exceeds MAX_DECODE_PIXELS (%.1f MP); decode buffers "
                    "scale with resolution and may exhaust a small container",
                    w, h, frame_pixels / 1e6, config.MAX_DECODE_PIXELS / 1e6,
                )
        sampled_count += 1

        if detector is None:
            tensors.append(preprocess(frame))
            continue
        box = detector.largest_face(frame)
        if box is None:
            continue            # scoring a faceless frame would only add noise
        faces_found += 1
        tensors.append(preprocess(crop_face(frame, box)))

    elapsed = lambda: round((time.perf_counter() - started) * 1000, 1)  # noqa: E731

    if not tensors:
        # The honest answer. This model only knows faces; with none found it has
        # nothing to say, and its whole-frame bias is towards REAL, so a verdict
        # here would be confidently wrong more often than right.
        return {
            "prediction": "UNKNOWN",
            "confidence": 0.0,
            "prob_fake": None,
            "reason": "No face detected in any sampled frame; this model only judges faces.",
            "frames_sampled": sampled_count,
        "frame_pixels": frame_pixels,
        "oversized": frame_pixels > config.MAX_DECODE_PIXELS,
            "frames_scored": 0,
            "faces_found": 0,
            "face_crop": crop,
            "aggregation": aggregation or config.AGGREGATION,
            "per_frame": [],
            "latency_ms": elapsed(),
            "file": str(path),
        }

    probs = score_batch(tensors)
    score = aggregate(probs, aggregation)
    is_fake = score >= config.PREDICTION_THRESHOLD

    return {
        "prediction": "FAKE" if is_fake else "REAL",
        # Distance from the threshold, expressed as a probability of the class
        # actually being reported -- so a 0.51 FAKE reads as 51% confident,
        # not 51% confident it is real.
        "confidence": float(score if is_fake else 1.0 - score),
        "prob_fake": round(float(score), 4),
        "threshold": config.PREDICTION_THRESHOLD,
        "frames_sampled": sampled_count,
        "frame_pixels": frame_pixels,
        "oversized": frame_pixels > config.MAX_DECODE_PIXELS,
        "frames_scored": len(tensors),
        "faces_found": faces_found if crop else None,
        "face_crop": crop,
        "aggregation": aggregation or config.AGGREGATION,
        "per_frame": [round(float(p), 4) for p in probs],
        "latency_ms": elapsed(),
        "file": str(path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect face manipulation in a video or image.")
    parser.add_argument("video", nargs="?", default=str(Path(__file__).parent / "samples" / "fake.mp4"))
    parser.add_argument("--frames", type=int, default=config.FRAMES_PER_CLIP,
                        help=f"frames to sample (default {config.FRAMES_PER_CLIP})")
    parser.add_argument("--agg", choices=["topk", "mean", "max"], default=config.AGGREGATION,
                        help=f"how per-frame scores combine (default {config.AGGREGATION})")
    parser.add_argument("--no-face", action="store_true",
                        help="skip face cropping (diagnostic only -- scores become unreliable)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else config.LOG_LEVEL,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        result = detect(args.video, frames=args.frames, aggregation=args.agg,
                        use_face_crop=not args.no_face)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"File:       {result['file']}")
    print(f"Prediction: {result['prediction']}")
    if result["prob_fake"] is None:
        print(f"Reason:     {result['reason']}")
    else:
        print(f"Confidence: {result['confidence']:.2%}")
        print(f"P(fake):    {result['prob_fake']:.4f}  (threshold {result['threshold']})")
        print(f"Frames:     {result['frames_scored']} scored of {result['frames_sampled']} sampled"
              + (f", {result['faces_found']} with a face" if result["face_crop"] else " (no face crop)"))
        print(f"Aggregated: {result['aggregation']}")
        if args.verbose:
            print(f"Per frame:  {result['per_frame']}")
    print(f"Latency:    {result['latency_ms']} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())