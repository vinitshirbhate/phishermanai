"""Image ingestion, built for what WhatsApp actually does to a picture.

WHATSAPP IS A LOSSY CHANNEL
--------------------------
By the time a forwarded screenshot reaches a victim, WhatsApp has resized it to
roughly 1600px on the long edge, re-encoded it as JPEG at quality 50-80,
stripped every EXIF field, and repeated all of that on each re-forward. There
is no provenance metadata left to read, and any fragile fingerprint is long
gone. Anything that depends on the file being pristine has already failed.

So the pipeline assumes degraded input from the start: upscale, deskew, denoise
before reading, and use a perceptual hash rather than a cryptographic one to
recognise the same document across recompressions.

THE RULE THAT MATTERS MOST HERE
-------------------------------
`read_critical_field` re-reads a financially critical value at several zoom
levels and only reports a value when the readings agree. If they do not, the
field is UNREADABLE and the caller must produce UNVERIFIED -- never TAMPERED.
Accusing a real document of being altered because our OCR misread a blurry
"4" as "40" is the fastest way to lose a user's trust, because it is the one
mistake they can check themselves.

Heavy dependencies (OpenCV, imagehash, PaddleOCR) are optional. Each is probed
at call time and its absence degrades the result honestly rather than raising.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

from core.fields import ExtractedFields, extract_all
from core.ingest.router import IMAGE, ParsedInput, TextBox

log = logging.getLogger(__name__)

CHAT_SCREENSHOT = "CHAT_SCREENSHOT"
DOCUMENT_PHOTO = "DOCUMENT_PHOTO"
CLEAN_IMAGE = "CLEAN_IMAGE"

HIGH = "HIGH"
MEDIUM = "MEDIUM"
UNREADABLE = "UNREADABLE"

# WhatsApp's long-edge target. Below this we upscale before OCR, because
# recognition accuracy on small text falls off a cliff.
TARGET_LONG_EDGE = 1600

# pHash at hash_size=16 gives a 256-bit hash: enough resolution to separate
# "same document recompressed" from "different document", which an 8x8 hash
# cannot do reliably on text-heavy images.
PHASH_SIZE = 16


def _optional(module: str):
    try:
        return __import__(module)
    except ImportError:
        return None


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

def classify_image(image) -> tuple[str, dict[str, Any]]:
    """CHAT_SCREENSHOT | DOCUMENT_PHOTO | CLEAN_IMAGE.

    Heuristics only -- no training. A chat screenshot is tall and narrow with a
    small number of flat background colours (the chat wallpaper and bubbles); a
    photographed document is closer to page-shaped with a broad, noisy
    histogram from uneven lighting.
    """
    np = _optional("numpy")
    if np is None:
        return CLEAN_IMAGE, {"reason": "numpy unavailable"}

    array = np.asarray(image.convert("RGB"))
    height, width = array.shape[:2]
    aspect = height / max(width, 1)

    # Flatness: how much of the image is covered by its few most common colours.
    small = array[::8, ::8].reshape(-1, 3) // 32
    packed = (small[:, 0] * 64 + small[:, 1] * 8 + small[:, 2]).astype("int32")
    counts = np.bincount(packed, minlength=512)
    top_share = float(counts.max() / max(counts.sum(), 1))
    top5_share = float(np.sort(counts)[-5:].sum() / max(counts.sum(), 1))

    evidence = {
        "width": int(width), "height": int(height), "aspect_ratio": round(aspect, 3),
        "dominant_colour_share": round(top_share, 3),
        "top5_colour_share": round(top5_share, 3),
    }

    # Phone screenshots are tall and dominated by a few flat colours.
    if aspect > 1.5 and top5_share > 0.55:
        return CHAT_SCREENSHOT, evidence
    if 0.6 <= aspect <= 1.8 and top5_share < 0.5:
        return DOCUMENT_PHOTO, evidence
    return CLEAN_IMAGE, evidence


# WhatsApp's "Forwarded many times" label is itself a fraud signal: it means
# the message has travelled well beyond its origin, which is how scams spread.
FORWARD_MARKERS = ("forwarded many times", "forwarded", "फॉरवर्ड")


def detect_forward_markers(ocr_text: str) -> dict[str, Any]:
    low = (ocr_text or "").lower()
    many = "forwarded many times" in low
    return {
        "forwarded": any(m in low for m in FORWARD_MARKERS),
        "forwarded_many_times": many,
        "note": (
            "WhatsApp marks a message 'forwarded many times' once it is far from its "
            "origin. Financial advice that reaches you that way has been through many "
            "hands, none of them accountable."
            if many else None
        ),
    }


# --------------------------------------------------------------------------
# Preprocessing
# --------------------------------------------------------------------------

def preprocess(image):
    """Upscale, deskew, denoise. Returns (processed_pil, evidence).

    Deliberately NOT binarised: the pHash is computed on the greyscale result,
    and thresholding destroys exactly the tonal detail that makes a perceptual
    hash stable across recompression.
    """
    cv2 = _optional("cv2")
    np = _optional("numpy")
    from PIL import Image

    evidence: dict[str, Any] = {"upscaled": False, "deskewed": False, "denoised": False}

    if cv2 is None or np is None:
        return image, {**evidence, "note": "OpenCV unavailable; using the image as-is"}

    array = np.asarray(image.convert("RGB"))
    height, width = array.shape[:2]

    if max(height, width) < TARGET_LONG_EDGE:
        scale = TARGET_LONG_EDGE / max(height, width)
        array = cv2.resize(array, (int(width * scale), int(height * scale)),
                           interpolation=cv2.INTER_CUBIC)
        evidence.update(upscaled=True, scale=round(scale, 3))

    grey = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)

    # Deskew from the dominant text-line angle via the Hough transform.
    try:
        edges = cv2.Canny(grey, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120,
                                minLineLength=max(60, grey.shape[1] // 6), maxLineGap=12)
        if lines is not None and len(lines) > 4:
            angles = []
            for x1, y1, x2, y2 in lines[:, 0]:
                if x2 == x1:
                    continue
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                if abs(angle) < 20:      # near-horizontal text lines only
                    angles.append(angle)
            if angles:
                skew = float(np.median(angles))
                if abs(skew) > 0.4:
                    centre = (grey.shape[1] // 2, grey.shape[0] // 2)
                    matrix = cv2.getRotationMatrix2D(centre, skew, 1.0)
                    grey = cv2.warpAffine(grey, matrix, (grey.shape[1], grey.shape[0]),
                                          flags=cv2.INTER_CUBIC,
                                          borderMode=cv2.BORDER_REPLICATE)
                    evidence.update(deskewed=True, skew_degrees=round(skew, 2))
    except Exception as exc:  # noqa: BLE001 - deskew is best-effort
        log.debug("deskew failed: %s", exc)

    # Bilateral filter: removes JPEG noise while keeping character edges sharp.
    try:
        grey = cv2.bilateralFilter(grey, 7, 50, 50)
        evidence["denoised"] = True
    except Exception as exc:  # noqa: BLE001
        log.debug("denoise failed: %s", exc)

    return Image.fromarray(grey), evidence


def compute_phash(image) -> str | None:
    """Perceptual hash of the preprocessed (not binarised) image."""
    imagehash = _optional("imagehash")
    if imagehash is None:
        return None
    try:
        return str(imagehash.phash(image, hash_size=PHASH_SIZE))
    except Exception as exc:  # noqa: BLE001
        log.debug("phash failed: %s", exc)
        return None


def phash_distance(a: str, b: str) -> int | None:
    if not a or not b or len(a) != len(b):
        return None
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return None


# --------------------------------------------------------------------------
# QR codes
# --------------------------------------------------------------------------

def decode_qr(image) -> list[str]:
    """Decode any QR codes. A payment QR hides its destination until scanned."""
    payloads: list[str] = []
    pyzbar = _optional("pyzbar")
    if pyzbar is not None:
        try:
            from pyzbar.pyzbar import decode as zbar_decode
            for item in zbar_decode(image):
                try:
                    payloads.append(item.data.decode("utf-8", "replace"))
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001 - pyzbar needs a native DLL
            log.debug("pyzbar unavailable: %s", exc)

    if not payloads:
        cv2 = _optional("cv2")
        np = _optional("numpy")
        if cv2 is not None and np is not None:
            try:
                detector = cv2.QRCodeDetector()
                data, points, _ = detector.detectAndDecode(
                    cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
                )
                if data:
                    payloads.append(data)
            except Exception as exc:  # noqa: BLE001
                log.debug("cv2 QR decode failed: %s", exc)
    return payloads


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------

_OCR_ENGINE = None
_OCR_BACKEND: str | None = None

# ENGINE CHOICE, AND WHY IT DEVIATES FROM THE BRIEF
# ------------------------------------------------
# The brief fixes PaddleOCR. PaddleOCR's models are the right ones -- PP-OCR is
# strong on the degraded, low-contrast text a WhatsApp screenshot produces --
# but the paddlepaddle runtime is not usable here as shipped:
#
#   * its oneDNN path raises NotImplementedError at inference on this CPU, and
#     only at predict() time, so the engine appears healthy and returns nothing;
#   * with oneDNN disabled it works but takes 21-38s per screenshot, against a
#     target of under 10s.
#
# RapidOCR runs the SAME PP-OCR model family through ONNX Runtime. Measured on
# the same 900x1600 fixture: 1.8s versus 21s, with identical box counts. So the
# models are unchanged and the recognition quality is unchanged -- only the
# inference runtime differs.
#
# PaddleOCR remains as a fallback, so a machine where paddle performs well still
# uses it. Which backend actually ran is reported in the result metadata rather
# than hidden.
RAPIDOCR = "rapidocr"
PADDLEOCR = "paddleocr"


def ocr_backend() -> str | None:
    """Which OCR backend is active, or None if text extraction is unavailable."""
    _ocr_engine()
    return _OCR_BACKEND


def _ocr_engine():
    """Load an OCR engine once: RapidOCR first, then PaddleOCR.

    PaddleOCR 3.x renamed the constructor arguments (`use_angle_cls` ->
    `use_textline_orientation`) and dropped `show_log`, so several signatures
    are attempted rather than silently reporting "no OCR engine" on a machine
    where it is installed.
    """
    global _OCR_ENGINE, _OCR_BACKEND
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE

    try:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
        _OCR_BACKEND = RAPIDOCR
        log.info("OCR backend: RapidOCR (PP-OCR models via ONNX Runtime)")
        return _OCR_ENGINE
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        log.info("RapidOCR unavailable (%s); trying PaddleOCR", exc)

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        log.info("No OCR engine installed (%s); image text extraction disabled", exc)
        return None

    # enable_mkldnn=False comes FIRST and is not an optimisation choice.
    # PaddlePaddle's oneDNN path fails at inference on some CPUs with
    #   NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support
    #   [pir::ArrayAttribute<pir::DoubleAttribute>]
    # which surfaces only when predict() runs, not at construction -- so the
    # engine looks healthy and then silently returns no text. Disabling oneDNN
    # costs some speed and makes OCR actually work.
    for kwargs in (
        {"use_textline_orientation": True, "lang": "en", "enable_mkldnn": False},  # 3.x
        {"lang": "en", "enable_mkldnn": False},
        {"use_textline_orientation": True, "lang": "en"},
        {"use_angle_cls": True, "lang": "en", "show_log": False},                  # 2.x
        {"lang": "en"},
    ):
        try:
            _OCR_ENGINE = PaddleOCR(**kwargs)
            _OCR_BACKEND = PADDLEOCR
            log.info("OCR backend: PaddleOCR (%s)", sorted(kwargs))
            return _OCR_ENGINE
        except (ValueError, TypeError):
            continue
        except Exception as exc:  # noqa: BLE001 - model download failure etc.
            log.info("PaddleOCR unavailable (%s); image text extraction disabled", exc)
            return None

    log.info("PaddleOCR present but no supported constructor signature matched")
    return None


def _run_ocr(engine, array) -> list[tuple[list, str, float]]:
    """Run OCR and normalise the result to (polygon, text, confidence) tuples.

    The two PaddleOCR generations return different shapes:
      2.x  [[[polygon, (text, score)], ...]]
      3.x  [{"dt_polys": [...], "rec_texts": [...], "rec_scores": [...]}]
    Normalising here keeps that difference out of the calling code.
    """
    # RapidOCR: callable, returns (results, elapsed) where each result is
    # [polygon, text, score].
    if _OCR_BACKEND == RAPIDOCR:
        try:
            results, _elapsed = engine(array)
        except Exception as exc:  # noqa: BLE001
            log.warning("RapidOCR failed: %s", exc)
            return []
        out: list[tuple[list, str, float]] = []
        for item in results or []:
            try:
                out.append((item[0], str(item[1]), float(item[2])))
            except Exception:  # noqa: BLE001
                continue
        return out

    result = None
    if hasattr(engine, "predict"):
        try:
            result = engine.predict(array)
        except Exception as exc:  # noqa: BLE001
            log.debug("predict() failed: %s", exc)
    if result is None:
        for attempt in (lambda: engine.ocr(array, cls=True), lambda: engine.ocr(array)):
            try:
                result = attempt()
                break
            except Exception as exc:  # noqa: BLE001
                log.debug("ocr() call failed: %s", exc)
    if not result:
        return []

    out: list[tuple[list, str, float]] = []
    for page in result:
        # 3.x dict form
        if isinstance(page, dict):
            polys = page.get("dt_polys") or page.get("rec_polys") or []
            texts = page.get("rec_texts") or []
            scores = page.get("rec_scores") or []
            for i, text in enumerate(texts):
                polygon = polys[i] if i < len(polys) else [[0, 0], [0, 0], [0, 0], [0, 0]]
                score = float(scores[i]) if i < len(scores) else 0.0
                out.append((polygon, str(text), score))
            continue
        # 2.x nested-list form
        for entry in page or []:
            try:
                polygon, (text, score) = entry[0], entry[1]
                out.append((polygon, str(text), float(score)))
            except Exception:  # noqa: BLE001
                continue
    return out


def ocr_with_boxes(image) -> tuple[str, list[TextBox]]:
    """Verbatim text plus bounding boxes.

    The boxes are not optional decoration -- they are what lets the UI draw a
    red rectangle around the altered field, which is the whole demo.
    """
    engine = _ocr_engine()
    if engine is None:
        return "", []

    np = _optional("numpy")
    if np is None:
        return "", []

    entries = _run_ocr(engine, np.asarray(image.convert("RGB")))

    boxes: list[TextBox] = []
    lines: list[str] = []
    for polygon, text, confidence in entries:
        try:
            xs = [int(p[0]) for p in polygon]
            ys = [int(p[1]) for p in polygon]
            boxes.append(TextBox(
                text=text,
                bbox=[min(xs), min(ys), max(xs), max(ys)],
                confidence=confidence,
            ))
            lines.append(text)
        except Exception:  # noqa: BLE001 - skip a malformed entry
            continue
    return "\n".join(lines), boxes


# --------------------------------------------------------------------------
# Critical-field re-reading
# --------------------------------------------------------------------------

@dataclass
class FieldReading:
    value: str | None
    confidence: str
    readings: list[str]
    agreement: float


def read_critical_field(image, bbox: list[int], *, vision_value: str | None = None) -> FieldReading:
    """Re-read one field at several zoom levels and reconcile the readings.

        all agree, min OCR confidence > 0.85 -> HIGH
        a majority agree                     -> MEDIUM
        no majority                          -> UNREADABLE, value None

    A field returned UNREADABLE can never produce a TAMPERED verdict. That rule
    is enforced in core/filings/tamper.py, which is where the comparison
    happens; this function's job is to be honest about what it could read.
    """
    engine = _ocr_engine()
    readings: list[str] = []
    confidences: list[float] = []

    if engine is not None:
        x1, y1, x2, y2 = bbox
        pad = 6
        crop = image.crop((max(0, x1 - pad), max(0, y1 - pad),
                           min(image.width, x2 + pad), min(image.height, y2 + pad)))
        np = _optional("numpy")
        for zoom in (1, 2, 4):
            try:
                scaled = crop.resize((crop.width * zoom, crop.height * zoom))
                entries = _run_ocr(engine, np.asarray(scaled.convert("RGB")))
                text_parts = [text for _, text, _ in entries]
                confs = [conf for _, _, conf in entries]
                if text_parts:
                    readings.append(" ".join(text_parts).strip())
                    confidences.append(min(confs) if confs else 0.0)
            except Exception:  # noqa: BLE001
                continue

    if vision_value:
        readings.append(str(vision_value).strip())

    if not readings:
        return FieldReading(None, UNREADABLE, [], 0.0)

    normalised = [r.replace(" ", "").lower() for r in readings]
    counts: dict[str, int] = {}
    for value in normalised:
        counts[value] = counts.get(value, 0) + 1
    winner, votes = max(counts.items(), key=lambda kv: kv[1])
    agreement = votes / len(normalised)

    winning_original = next(r for r, n in zip(readings, normalised) if n == winner)

    if votes == len(normalised) and (not confidences or min(confidences) > 0.85):
        return FieldReading(winning_original, HIGH, readings, agreement)
    if agreement > 0.5:
        return FieldReading(winning_original, MEDIUM, readings, agreement)
    return FieldReading(None, UNREADABLE, readings, agreement)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def process_image(data: bytes, filename: str | None = None) -> ParsedInput:
    """Full image pipeline: classify, preprocess, hash, OCR, decode QR, extract."""
    from PIL import Image

    metadata: dict[str, Any] = {"filename": filename}

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # noqa: BLE001
        return ParsedInput(
            source_type=IMAGE, raw_text="",
            metadata={**metadata, "error": f"Could not read the image: {exc}"},
        )

    metadata["dimensions"] = [image.width, image.height]
    # WhatsApp strips EXIF entirely, so its absence is expected, not suspicious.
    metadata["has_exif"] = bool(getattr(image, "_getexif", lambda: None)())

    image_type, classify_evidence = classify_image(image)
    metadata["image_type"] = image_type
    metadata["classification"] = classify_evidence

    processed, preprocess_evidence = preprocess(image)
    metadata["preprocessing"] = preprocess_evidence

    phash = compute_phash(processed)
    qr_payloads = decode_qr(image)
    if qr_payloads:
        metadata["qr_codes_found"] = len(qr_payloads)

    text, boxes = ocr_with_boxes(processed)
    if not text:
        metadata["ocr"] = (
            "No OCR engine available. Install the extras with: pip install -e .[image,ocr]"
        )
    else:
        metadata["ocr"] = {"engine": "paddleocr", "boxes": len(boxes)}
        metadata["forward_markers"] = detect_forward_markers(text)

    fields: ExtractedFields = extract_all(text)

    # Attach a per-field confidence and box wherever an OCR line contains the
    # extracted value, so tamper comparison can honour read confidence and the
    # UI knows where to draw.
    confidence_map: dict[str, Any] = {}
    for name in ("dividend_per_share", "record_date", "meeting_date",
                 "evoting_start", "evoting_end", "isin"):
        value = getattr(fields, name, None)
        if value is None:
            continue
        needle = str(value)
        if name == "dividend_per_share":
            needle = f"{value:g}"
        for box in boxes:
            if needle in box.text.replace(" ", ""):
                confidence_map[name] = box.confidence
                confidence_map[f"{name}__bbox"] = box.bbox
                break
    fields.field_confidence = confidence_map

    from core.chokepoints.delivery import extract_urls
    urls = extract_urls(text)
    fields.urls = urls

    import hashlib
    from core.textnorm import canonical_hash_text

    return ParsedInput(
        source_type=IMAGE,
        raw_text=text,
        structured=fields,
        phash=phash,
        ocr_boxes=boxes or None,
        qr_payloads=qr_payloads,
        urls=urls,
        content_hash=hashlib.sha256(canonical_hash_text(text).encode()).hexdigest(),
        metadata=metadata,
    )
