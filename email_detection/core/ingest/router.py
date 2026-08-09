"""Input router: turn anything a user submits into one normalised object.

Accepts a .eml file, raw text, an image, a PDF, or a bare URL, detects which it
is, and dispatches to the right parser. Everything downstream -- the four
chokepoints, the filings matcher, the tamper detector -- consumes `ParsedInput`
and never needs to know what the user actually uploaded.

The image path is optional. It needs opencv/imagehash/PaddleOCR, which are
heavy, so the email path installs and runs without them; asking for an image
without those extras returns a clear message rather than an import traceback.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from typing import Any

from core.fields import ExtractedFields, extract_all
from core.ingest.email_parser import EmailAuth, ParsedEmail, parse_email
from core.textnorm import canonical_hash_text

EMAIL = "EMAIL"
TEXT = "TEXT"
IMAGE = "IMAGE"
PDF = "PDF"
URL = "URL"

IMAGE_MAGIC = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",
    b"BM": "bmp",
}


@dataclass
class TextBox:
    """One OCR-detected text region. `bbox` is [x1, y1, x2, y2] in pixels.

    These are what let the UI draw a red box around an altered field, so they
    are carried end to end even though the email path does not produce them.
    """

    text: str
    bbox: list[int]
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "bbox": self.bbox, "confidence": round(self.confidence, 3)}


@dataclass
class ParsedInput:
    source_type: str
    raw_text: str = ""
    structured: ExtractedFields | None = None
    auth_results: EmailAuth | None = None
    email: ParsedEmail | None = None
    phash: str | None = None
    ocr_boxes: list[TextBox] | None = None
    qr_payloads: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "raw_text": self.raw_text,
            "structured": self.structured.to_dict() if self.structured else None,
            "auth_results": self.auth_results.to_dict() if self.auth_results else None,
            "email": self.email.to_dict() if self.email else None,
            "phash": self.phash,
            "ocr_boxes": [b.to_dict() for b in self.ocr_boxes] if self.ocr_boxes else None,
            "qr_payloads": self.qr_payloads,
            "urls": self.urls,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
        }


def _content_hash(text: str) -> str:
    return hashlib.sha256(canonical_hash_text(text).encode("utf-8")).hexdigest()


def detect_type(data: bytes | str, filename: str | None = None) -> str:
    """Identify the input type from magic bytes, filename, then content shape."""
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.lower().startswith(("http://", "https://", "www.")) and len(stripped.split()) == 1:
            return URL
        # A pasted raw email still has headers even without a .eml extension.
        head = stripped[:2000].lower()
        if ("\nfrom:" in head or head.startswith("from:")) and \
           ("subject:" in head or "received:" in head or "return-path:" in head):
            return EMAIL
        return TEXT

    name = (filename or "").lower()
    if data.startswith(b"%PDF"):
        return PDF
    for magic in IMAGE_MAGIC:
        if data.startswith(magic):
            return IMAGE
    if name.endswith(".eml") or name.endswith(".msg"):
        return EMAIL
    if name.endswith(".pdf"):
        return PDF
    if name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
        return IMAGE

    head = data[:2000].decode("utf-8", "replace").lower()
    if ("\nfrom:" in head or head.startswith("from:")) and \
       ("subject:" in head or "received:" in head or "return-path:" in head):
        return EMAIL
    return TEXT


def _extract_pdf_text(data: bytes) -> tuple[str, dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", {"error": "pypdf not installed; run: pip install pypdf"}
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages[:15]]
        text = "\n".join(pages).strip()
        return text, {
            "page_count": len(reader.pages),
            "pages_read": len(pages),
            # A PDF with no extractable text is a scan. Say so, rather than
            # silently returning nothing and letting it look like an empty file.
            "text_layer": bool(text),
            "note": None if text else "No text layer; this looks like a scanned document.",
        }
    except Exception as exc:  # noqa: BLE001
        return "", {"error": f"{type(exc).__name__}: {exc}"}


def route(
    data: bytes | str,
    filename: str | None = None,
    *,
    source_type: str | None = None,
) -> ParsedInput:
    """Parse any supported input into a ParsedInput."""
    kind = source_type or detect_type(data, filename)

    if kind == EMAIL:
        parsed_email = parse_email(data)
        text = parsed_email.full_text
        result = ParsedInput(
            source_type=EMAIL,
            raw_text=text,
            email=parsed_email,
            auth_results=parsed_email.auth,
            urls=parsed_email.urls,
            metadata={
                "filename": filename,
                "subject": parsed_email.subject,
                "from": parsed_email.from_address,
                "attachments": parsed_email.attachments,
                "received_hops": len(parsed_email.received_chain),
            },
        )

    elif kind == PDF:
        raw = data if isinstance(data, bytes) else data.encode()
        text, meta = _extract_pdf_text(raw)
        result = ParsedInput(
            source_type=PDF, raw_text=text,
            metadata={"filename": filename, **meta},
        )

    elif kind == IMAGE:
        raw = data if isinstance(data, bytes) else data.encode()
        try:
            from core.ingest.image_pipeline import process_image
        except ImportError as exc:
            return ParsedInput(
                source_type=IMAGE,
                raw_text="",
                metadata={
                    "filename": filename,
                    "error": "image_support_unavailable",
                    "detail": (
                        "Image input needs the optional extras. Install with: "
                        "pip install -e .[image,ocr]"
                    ),
                    "import_error": str(exc),
                },
            )
        result = process_image(raw, filename=filename)

    elif kind == URL:
        url = data.strip() if isinstance(data, str) else data.decode("utf-8", "replace").strip()
        result = ParsedInput(
            source_type=URL, raw_text=url, urls=[url],
            metadata={"submitted_url": url},
        )

    else:
        text = data if isinstance(data, str) else data.decode("utf-8", "replace")
        result = ParsedInput(source_type=TEXT, raw_text=text, metadata={"filename": filename})

    if result.structured is None:
        result.structured = extract_all(result.raw_text, urls=result.urls)
    if not result.urls and result.structured:
        from core.chokepoints.delivery import extract_urls
        result.urls = extract_urls(result.raw_text)
        result.structured.urls = result.urls
    if not result.content_hash:
        result.content_hash = _content_hash(result.raw_text)

    return result
