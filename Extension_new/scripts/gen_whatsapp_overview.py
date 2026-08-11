#!/usr/bin/env python3
"""docs/architecture-whatsapp-2.excalidraw - WhatsApp lane, left-to-right overview.

Mermaid-flowchart style: one row of boxes, one arrow between each, one branch.
Deliberately thin on detail - the point is the shape and the honest status.
"""
import json
from pathlib import Path

OUT = Path(r"f:\chetana-browser\docs\architecture-whatsapp-2.excalidraw")
els = []
_s = [500]


def _n():
    _s[0] += 1
    return _s[0] * 7919 % 2147483647


def base(t, x, y, w, h, **k):
    return {"id": f"w{len(els)}_{_n()}", "type": t, "x": x, "y": y,
            "width": w, "height": h, "angle": 0,
            "strokeColor": k.get("stroke", "#1e1e1e"),
            "backgroundColor": k.get("bg", "transparent"),
            "fillStyle": "solid", "strokeWidth": k.get("sw", 2),
            "strokeStyle": k.get("ss", "solid"), "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None,
            "roundness": k.get("roundness", {"type": 3}),
            "seed": _n(), "version": 1, "versionNonce": _n(),
            "isDeleted": False, "boundElements": None, "updated": 1,
            "link": None, "locked": False}


def rect(x, y, w, h, **k):
    e = base("rectangle", x, y, w, h, **k); els.append(e); return e


CW = {10: 5.2, 11: 5.7, 12: 6.2, 13: 6.7, 14: 7.2, 16: 8.2, 18: 9.3, 20: 10.4, 30: 15.5}


def text(s, x, y, size=14, color="#1e1e1e", family=1, align="left", w=None):
    lines = s.split("\n")
    cw = CW.get(size, size * 0.52)
    width = w if w else max(len(l) for l in lines) * cw
    e = base("text", x, y, width, len(lines) * size * 1.25, stroke=color, roundness=None)
    e.update({"text": s, "fontSize": size, "fontFamily": family, "textAlign": align,
              "verticalAlign": "top", "containerId": None, "originalText": s,
              "lineHeight": 1.25, "baseline": int(size * 0.9)})
    els.append(e); return e


def ctext(s, box, size=14, color="#1e1e1e", family=1, dy=0):
    lines = s.split("\n")
    cw = CW.get(size, size * 0.52)
    w = max(len(l) for l in lines) * cw
    return text(s, box["x"] + (box["width"] - w) / 2, box["y"] + dy,
                size, color, family, "center", w=w)


def arrow(x1, y1, x2, y2, color="#495057"):
    e = base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), stroke=color,
             roundness={"type": 2})
    e.update({"points": [[0, 0], [x2 - x1, y2 - y1]], "lastCommittedPoint": None,
              "startBinding": None, "endBinding": None,
              "startArrowhead": None, "endArrowhead": "arrow"})
    els.append(e); return e


GREY_S, GREY_B = "#495057", "#e9ecef"
BLUE_S, BLUE_B = "#1971c2", "#a5d8ff"
GREEN_S, GREEN_B = "#2f9e44", "#b2f2bb"
AMBER_S, AMBER_B = "#f08c00", "#ffec99"
VIO_S, VIO_B = "#6741d9", "#d0bfff"
RED_S, RED_B = "#e03131", "#ffc9c9"
INK, MUTE = "#1e1e1e", "#5c5f66"

L, TOP = 60, 40
BW, BH, GAP = 252, 132, 56

text("WhatsApp Lane", L, TOP, 30, INK)
text("Catches investment-scam messages on WhatsApp Web \u2014 entirely on the user's device.",
     L + 2, TOP + 44, 14, MUTE)

Y = TOP + 96

steps = [
    (GREY_S,  GREY_B,  "Message arrives", "a chat opens, or a\nnew message lands", "adapter_mv3.js"),
    (BLUE_S,  BLUE_B,  "Can we see?",     "HEALTHY \u00b7 DEGRADED\n\u00b7 BLIND",          "health.js"),
    (GREEN_S, GREEN_B, "Read the message", "links, UPI, amounts,\nSEBI reg no, .apk",  "extract.js"),
    (AMBER_S, AMBER_B, "Read the chat",   "reply timing, rising\nasks, reused text",   "context.js"),
    (VIO_S,   VIO_B,   "Decide",          "W0\u2013W6, each with\nits evidence",        "verdict.js"),
    (RED_S,   RED_B,   "Show a badge",    "beside the message,\nnever blocks",         "overlay.js"),
]

boxes = []
for i, (s, b, title, sub, mod) in enumerate(steps):
    x = L + i * (BW + GAP)
    bx = rect(x, Y, BW, BH, stroke=s, bg=b)
    boxes.append(bx)
    ctext(title, bx, 18, INK, dy=16)
    ctext(sub, bx, 13, INK, dy=48)
    ctext(mod, bx, 11, s, family=3, dy=100)
    if i:
        arrow(x - GAP + 8, Y + BH / 2, x - 8, Y + BH / 2)

# the one branch that matters
b2 = boxes[1]
BY = Y + BH + 62
arrow(b2["x"] + BW / 2, Y + BH + 6, b2["x"] + BW / 2, BY - 8, BLUE_S)
stop = rect(b2["x"] - 34, BY, BW + 68, 62, stroke=BLUE_S, bg="#ffffff", ss="dashed")
ctext("if BLIND \u2192 stop scanning and say so", stop, 14, BLUE_S, dy=12)
ctext("a guess is worse than an honest silence", stop, 11, MUTE, dy=34)

# privacy note under the read step
b3 = boxes[2]
text("message text is never stored \u2014 only a\none-way fingerprint. \u201cView once\u201d never opened.",
     b3["x"], BY + 4, 11, GREEN_S)

# W5 callout under decide
b5 = boxes[4]
text("W5 \u2014 the one to demo: \u201cthis registration\nbelongs to someone else.\u201d Accuses the\ncredential, never the person.",
     b5["x"], BY + 4, 11, VIO_S)

# ── status strip ─────────────────────────────────────────────────────────
SY = BY + 62 + 66
text("WHAT IS IMPLEMENTED", L, SY, 18, INK)
text("the honest state, not the plan", L + 268, SY + 4, 13, MUTE)

chips = [
    (GREEN_S, "#ebfbee", "BUILT  &  TESTED",
     "all 6 modules \u00b7 13 tests passing"),
    (AMBER_S, "#fff9db", "BUILT,  NOT  RUNNING",
     "start() has no caller \u2014 no badge yet"),
    (RED_S,   "#fff5f5", "NOT  VERIFIED",
     "selectors never run on real WhatsApp"),
]
TOTAL = 6 * BW + 5 * GAP
CWD = (TOTAL - 2 * 24) / 3
for i, (s, bg, t, sub) in enumerate(chips):
    x = L + i * (CWD + 24)
    c = rect(x, SY + 36, CWD, 68, stroke=s, bg=bg)
    text(t, x + 20, SY + 50, 14, s)
    text(sub, x + 20, SY + 72, 12, INK)

text("Also off by default: chat context is not fed into the SEBI-disclosure rule until explicitly confirmed.",
     L, SY + 124, 12, MUTE)
text("Non-technical: read the big words left to right.      Technical: the small mono line is the module.",
     L, SY + 150, 12, INK)

doc = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
       "elements": els,
       "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"}, "files": {}}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT}  ({len(els)} elements, {OUT.stat().st_size:,} bytes)")
