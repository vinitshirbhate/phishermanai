"""Render the e-mail fixtures as WhatsApp-style screenshots.

    python -m eval.make_screenshots

Produces, for each genuine and tampered fixture, a chat-screenshot-looking PNG
pushed through the same degradation WhatsApp applies: resize to a 1600px long
edge and JPEG re-encode at quality 55. That is not decoration -- OCR accuracy
and pHash stability both depend on it, so testing against pristine renders
would tell us nothing about the channel we actually run in.
"""

from __future__ import annotations

import io
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core.ingest.email_parser import parse_email

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SHOT_DIR = FIXTURE_DIR / "screenshots"

WIDTH, HEIGHT = 1080, 1920
WHATSAPP_LONG_EDGE = 1600
WHATSAPP_QUALITY = 55


def _font(size: int, bold: bool = False):
    paths = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
        if bold else
        ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
    )
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render_chat_screenshot(subject: str, body: str, sender: str) -> Image.Image:
    """A plausible WhatsApp chat containing a forwarded corporate notice."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (233, 226, 218))   # chat wallpaper
    draw = ImageDraw.Draw(img)

    # Header bar
    draw.rectangle([0, 0, WIDTH, 120], fill=(0, 92, 75))
    draw.ellipse([28, 28, 92, 92], fill=(200, 210, 205))
    draw.text((112, 38), "Investor Group - NSE/BSE", font=_font(34, bold=True), fill=(255, 255, 255))
    draw.text((112, 78), "24 members", font=_font(24), fill=(215, 230, 225))

    # Message bubble
    x0, y0 = 40, 170
    bubble_w = WIDTH - 130
    lines: list[str] = ["Forwarded many times", ""]
    lines += textwrap.wrap(subject, width=44)
    lines.append("")
    for para in body.split("\n"):
        if not para.strip():
            lines.append("")
        else:
            lines.extend(textwrap.wrap(para.strip(), width=46))
    lines = lines[:44]

    bubble_h = 60 + len(lines) * 38
    draw.rounded_rectangle([x0, y0, x0 + bubble_w, y0 + bubble_h], radius=22, fill=(255, 255, 255))

    y = y0 + 24
    draw.text((x0 + 26, y), "Forwarded many times", font=_font(24), fill=(140, 148, 155))
    y += 46
    draw.text((x0 + 26, y), sender[:44], font=_font(26, bold=True), fill=(0, 130, 100))
    y += 44

    for line in lines[2:]:
        draw.text((x0 + 26, y), line, font=_font(28), fill=(20, 24, 28))
        y += 38

    draw.text((x0 + bubble_w - 130, y0 + bubble_h - 34), "11:42 AM",
              font=_font(22), fill=(150, 158, 165))
    return img


def whatsapp_degrade(img: Image.Image, generations: int = 1) -> Image.Image:
    """Apply WhatsApp-style resize + JPEG recompression, `generations` times."""
    out = img
    for _ in range(generations):
        width, height = out.size
        if max(width, height) > WHATSAPP_LONG_EDGE:
            scale = WHATSAPP_LONG_EDGE / max(width, height)
            out = out.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
        buffer = io.BytesIO()
        out.convert("RGB").save(buffer, format="JPEG", quality=WHATSAPP_QUALITY, optimize=True)
        buffer.seek(0)
        out = Image.open(buffer)
        out.load()
    return out


def main() -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    written = []

    for item in manifest:
        if item["label"] not in ("GENUINE", "TAMPERED"):
            continue
        parsed = parse_email((FIXTURE_DIR / item["file"]).read_bytes())
        img = render_chat_screenshot(
            parsed.subject, parsed.body_text, parsed.from_display_name or parsed.from_address
        )
        degraded = whatsapp_degrade(img, generations=1)

        name = item["file"].replace(".eml", "_whatsapp.png")
        path = SHOT_DIR / name
        degraded.convert("RGB").save(path, format="PNG")
        written.append({
            "file": f"screenshots/{name}",
            "label": item["label"],
            "source_eml": item["file"],
            "filing_id": item.get("filing_id"),
            "company": item.get("company"),
            "tampered_field": item.get("tampered_field"),
            "original_value": item.get("original_value"),
            "altered_value": item.get("altered_value"),
        })

    (SHOT_DIR / "manifest.json").write_text(json.dumps(written, indent=2), encoding="utf-8")
    print(f"wrote {len(written)} WhatsApp-style screenshots to {SHOT_DIR}")
    for item in written:
        print(f"  {item['label']:<10} {item['file']}")


if __name__ == "__main__":  # pragma: no cover
    main()
