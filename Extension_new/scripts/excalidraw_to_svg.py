#!/usr/bin/env python3
"""
scripts/excalidraw_to_svg.py - render a .excalidraw scene to a standalone SVG.

WHY: GitHub does not render .excalidraw files. A README that links to one shows
a broken preview, so the diagrams have to ship as SVG next to the source.

Scope is deliberately narrow - rectangles, text and (multi-point) arrows, which
is exactly what our generators emit. It is NOT a general Excalidraw renderer: no
freedraw, no ellipses, no bound-container text, no images. If a scene ever uses
those, this fails loudly rather than dropping them silently.

Usage:
    python scripts/excalidraw_to_svg.py docs/architecture.excalidraw [out.svg]
    python scripts/excalidraw_to_svg.py --all
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PAD = 28

SUPPORTED = {"rectangle", "text", "arrow", "line", "ellipse"}

# Excalidraw fontFamily ids -> a web-safe stack. 1/5 are the hand-drawn faces
# (Virgil / Excalifont); we substitute a clean sans so the SVG is legible
# everywhere without embedding a font file.
FONTS = {
    1: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    2: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    3: "'Cascadia Code', 'SF Mono', Consolas, ui-monospace, monospace",
    5: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    6: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    8: "'Cascadia Code', Consolas, ui-monospace, monospace",
}


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def bounds(els):
    xs, ys, xe, ye = [], [], [], []
    for e in els:
        x, y = _f(e.get("x")), _f(e.get("y"))
        w, h = _f(e.get("width")), _f(e.get("height"))
        if e.get("type") in ("arrow", "line"):
            pts = e.get("points") or [[0, 0]]
            for px, py in pts:
                xs.append(x + _f(px)); ys.append(y + _f(py))
                xe.append(x + _f(px)); ye.append(y + _f(py))
        else:
            xs.append(x); ys.append(y); xe.append(x + w); ye.append(y + h)
    return min(xs), min(ys), max(xe), max(ye)


def _rect(e):
    x, y = _f(e["x"]), _f(e["y"])
    w, h = _f(e["width"]), _f(e["height"])
    r = 12 if e.get("roundness") else 0
    r = min(r, w / 2, h / 2) if w and h else 0
    bg = e.get("backgroundColor") or "transparent"
    fill = "none" if bg in ("transparent", "", None) else bg
    dash = ' stroke-dasharray="8 6"' if e.get("strokeStyle") == "dashed" else ""
    if e.get("strokeStyle") == "dotted":
        dash = ' stroke-dasharray="2 5"'
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{r:.1f}" fill="{fill}" stroke="{e.get("strokeColor", "#000")}" '
            f'stroke-width="{_f(e.get("strokeWidth"), 1):.1f}"{dash}/>')


def _ellipse(e):
    x, y = _f(e["x"]), _f(e["y"])
    w, h = _f(e["width"]), _f(e["height"])
    bg = e.get("backgroundColor") or "transparent"
    fill = "none" if bg in ("transparent", "", None) else bg
    return (f'<ellipse cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" '
            f'rx="{w / 2:.1f}" ry="{h / 2:.1f}" fill="{fill}" '
            f'stroke="{e.get("strokeColor", "#000")}" '
            f'stroke-width="{_f(e.get("strokeWidth"), 1):.1f}"/>')


def _text(e):
    x, y = _f(e["x"]), _f(e["y"])
    w = _f(e["width"])
    size = _f(e.get("fontSize"), 16)
    lh = _f(e.get("lineHeight"), 1.25)
    fam = FONTS.get(e.get("fontFamily"), FONTS[2])
    align = e.get("textAlign", "left")
    anchor = {"center": "middle", "right": "end"}.get(align, "start")
    tx = x + (w / 2 if align == "center" else (w if align == "right" else 0))
    fill = e.get("strokeColor", "#000")
    lines = str(e.get("text", "")).split("\n")
    # Excalidraw y is the TOP of the text block; SVG y is a baseline.
    first = y + size * 0.82
    out = [f'<text x="{tx:.1f}" y="{first:.1f}" font-family="{fam}" '
           f'font-size="{size:.1f}" fill="{fill}" text-anchor="{anchor}" '
           f'xml:space="preserve">']
    for i, ln in enumerate(lines):
        dy = 0 if i == 0 else size * lh
        out.append(f'<tspan x="{tx:.1f}" dy="{dy:.1f}">{escape(ln)}</tspan>')
    out.append("</text>")
    return "".join(out)


def _arrow(e):
    x, y = _f(e["x"]), _f(e["y"])
    pts = [(x + _f(px), y + _f(py)) for px, py in (e.get("points") or [[0, 0]])]
    if len(pts) < 2:
        return ""
    col = e.get("strokeColor", "#000")
    sw = _f(e.get("strokeWidth"), 1)
    dash = ' stroke-dasharray="8 6"' if e.get("strokeStyle") == "dashed" else ""
    d = "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in pts)
    parts = [f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw:.1f}" '
             f'stroke-linecap="round" stroke-linejoin="round"{dash}/>']
    if e.get("endArrowhead") == "arrow":
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        dx, dy = x2 - x1, y2 - y1
        ln = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / ln, dy / ln
        size = max(9.0, sw * 4.5)
        # two barbs, 25 degrees off the shaft
        for sign in (1, -1):
            ang = 0.44 * sign
            cos_a, sin_a = __import__("math").cos(ang), __import__("math").sin(ang)
            bx = x2 - size * (ux * cos_a - uy * sin_a)
            by = y2 - size * (ux * sin_a + uy * cos_a)
            parts.append(f'<path d="M {x2:.1f} {y2:.1f} L {bx:.1f} {by:.1f}" '
                         f'fill="none" stroke="{col}" stroke-width="{sw:.1f}" '
                         f'stroke-linecap="round"/>')
    return "".join(parts)


RENDER = {"rectangle": _rect, "ellipse": _ellipse, "text": _text,
          "arrow": _arrow, "line": _arrow}


def convert(src: Path, dst: Path) -> tuple[int, int, int]:
    doc = json.loads(src.read_text(encoding="utf-8"))
    els = [e for e in doc.get("elements", []) if not e.get("isDeleted")]
    if not els:
        raise SystemExit(f"{src}: no elements")

    unsupported = sorted({e["type"] for e in els if e["type"] not in SUPPORTED})
    if unsupported:
        raise SystemExit(
            f"{src}: unsupported element type(s) {unsupported}. This renderer "
            f"covers rectangle/ellipse/text/arrow/line only — rather than drop "
            f"them silently and ship a diagram missing pieces, it stops here.")

    x0, y0, x1, y1 = bounds(els)
    w, h = (x1 - x0) + PAD * 2, (y1 - y0) + PAD * 2
    bg = (doc.get("appState") or {}).get("viewBackgroundColor") or "#ffffff"

    body = "".join(RENDER[e["type"]](e) for e in els)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
        f'viewBox="0 0 {w:.0f} {h:.0f}" role="img">'
        f'<rect width="100%" height="100%" fill="{bg}"/>'
        f'<g transform="translate({PAD - x0:.1f},{PAD - y0:.1f})">{body}</g>'
        f'</svg>\n'
    )
    dst.write_text(svg, encoding="utf-8")
    return len(els), int(w), int(h)


def main(argv):
    if not argv or argv[0] == "--all":
        targets = sorted((ROOT / "docs").glob("*.excalidraw"))
    else:
        targets = [Path(argv[0])]
    out_override = Path(argv[1]) if len(argv) > 1 and argv[0] != "--all" else None

    for src in targets:
        dst = out_override or src.with_suffix(".svg")
        n, w, h = convert(src, dst)
        print(f"{src.name:42} -> {dst.name:38} {n:>3} els  {w}x{h}")


if __name__ == "__main__":
    main(sys.argv[1:])
