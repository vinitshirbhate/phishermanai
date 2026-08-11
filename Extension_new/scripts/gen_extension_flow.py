#!/usr/bin/env python3
"""docs/architecture-extension.excalidraw - the extension, left-to-right, dark.

Styled to match the reference flow diagram: near-black canvas, thin light
strokes, one teal accent box, grouped containers with a small label chip, and
short labels on the arrows.

Deliberately simple: inputs -> pick the unit -> four checks -> merge -> verdict.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "architecture-extension.excalidraw"

els = []
_s = [900]


def _n():
    _s[0] += 1
    return _s[0] * 7919 % 2147483647


def base(t, x, y, w, h, **k):
    return {"id": f"x{len(els)}_{_n()}", "type": t, "x": x, "y": y,
            "width": w, "height": h, "angle": 0,
            "strokeColor": k.get("stroke", LINE),
            "backgroundColor": k.get("bg", "transparent"),
            "fillStyle": "solid", "strokeWidth": k.get("sw", 1),
            "strokeStyle": k.get("ss", "solid"), "roughness": 0, "opacity": 100,
            "groupIds": [], "frameId": None,
            "roundness": k.get("roundness", {"type": 3}),
            "seed": _n(), "version": 1, "versionNonce": _n(),
            "isDeleted": False, "boundElements": None, "updated": 1,
            "link": None, "locked": False}


# ── dark palette, taken from the reference ───────────────────────────────
BG = "#0f0f0f"
LINE = "#d6d6d6"          # box + arrow stroke
DIM = "#5a5a5a"           # group container stroke
TXT = "#ffffff"
MUT = "#9ca3af"
TEAL = "#14b8a6"
INK = "#0b1f1c"           # text on the teal fill


def rect(x, y, w, h, **k):
    e = base("rectangle", x, y, w, h, **k)
    els.append(e)
    return e


CW = {9: 4.7, 10: 5.2, 11: 5.7, 12: 6.2, 13: 6.7, 16: 8.2, 24: 12.4}


def text(s, x, y, size=11, color=TXT, family=2, align="left", w=None):
    lines = s.split("\n")
    cw = CW.get(size, size * 0.52)
    width = w if w else max(len(l) for l in lines) * cw
    e = base("text", x, y, width, len(lines) * size * 1.25, stroke=color,
             roundness=None)
    e.update({"text": s, "fontSize": size, "fontFamily": family,
              "textAlign": align, "verticalAlign": "top", "containerId": None,
              "originalText": s, "lineHeight": 1.25, "baseline": int(size * 0.9)})
    els.append(e)
    return e


def node(x, y, w, h, label, sub=None, fill=None, stroke=LINE, tcol=TXT):
    """A box with centred label, optionally a second muted line."""
    rect(x, y, w, h, stroke=stroke, bg=fill or "transparent")
    lines = label.split("\n")
    fs = 11
    th = len(lines) * fs * 1.25 + (12 if sub else 0)
    ty = y + (h - th) / 2
    tw = max(len(l) for l in lines) * CW[fs]
    text(label, x + (w - tw) / 2, ty, fs, tcol, align="center", w=tw)
    if sub:
        sw_ = len(sub) * CW[9]
        text(sub, x + (w - sw_) / 2, ty + len(lines) * fs * 1.25 + 2, 9,
             MUT if not fill else INK, align="center", w=sw_)
    return {"x": x, "y": y, "w": w, "h": h}


def group(x, y, w, h, label):
    rect(x, y, w, h, stroke=DIM, roundness=None)
    chip_w = len(label) * CW[9] + 12
    rect(x, y - 15, chip_w, 15, stroke=DIM, bg="#262626", roundness=None)
    text(label, x + 6, y - 12, 9, MUT)


def arrow(x1, y1, x2, y2, label=None, color=LINE, above=True):
    e = base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), stroke=color,
             roundness={"type": 2})
    e.update({"points": [[0, 0], [x2 - x1, y2 - y1]], "lastCommittedPoint": None,
              "startBinding": None, "endBinding": None,
              "startArrowhead": None, "endArrowhead": "arrow"})
    els.append(e)
    if label:
        lw = len(label) * CW[9]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        text(label, mx - lw / 2, my - (14 if above else -5), 9, MUT, w=lw,
             align="center")


def elbow(x1, y1, x2, y2, label=None, color=LINE):
    """Right-angle connector: across, then down/up, then into the target."""
    midx = x1 + (x2 - x1) * 0.5
    e = base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), stroke=color,
             roundness={"type": 2})
    e.update({"points": [[0, 0], [midx - x1, 0], [midx - x1, y2 - y1],
                         [x2 - x1, y2 - y1]],
              "lastCommittedPoint": None, "startBinding": None,
              "endBinding": None, "startArrowhead": None, "endArrowhead": "arrow"})
    els.append(e)
    if label:
        lw = len(label) * CW[9]
        text(label, x1 + 14, y1 - 14, 9, MUT, w=lw)


# ═════════════════════════════════════════════════════════════════════════
text("Phisherman AI — extension flow", 40, 24, 16, TXT)
text("everything below the dashed line runs on the user's device", 40, 48, 9, MUT)

# ── client group ─────────────────────────────────────────────────────────
GX, GY = 40, 90
group(GX, GY, 168, 300, "Client")
inputs = [("News sites / web", None), ("WhatsApp Web", None),
          ("Gmail / webmail", None), ("Any link (hover)", None)]
for i, (lbl, sub) in enumerate(inputs):
    node(GX + 18, GY + 22 + i * 68, 132, 46, lbl, sub)

# ── pick the unit ────────────────────────────────────────────────────────
PX = 268
pick = node(PX, GY + 116, 122, 60, "Pick the unit", "message, not page")
for i in range(4):
    y = GY + 22 + i * 68 + 23
    elbow(GX + 150 + 6, y, PX - 6, GY + 146)

# ── four checks ──────────────────────────────────────────────────────────
CX = 452
checks = [
    ("Link check", "PSL · homoglyph", "link"),
    ("Identity check", "SEBI register", "text"),
    ("Behaviour check", "timing · ladders", "chat"),
    ("File check", "APK filename", "file"),
]
cy0 = GY - 6
boxes = []
for i, (lbl, sub, tag) in enumerate(checks):
    b = node(CX, cy0 + i * 84, 148, 58, lbl, sub)
    boxes.append(b)
    elbow(PX + 122 + 6, GY + 146, CX - 6, cy0 + i * 84 + 29, tag if i == 0 else None)
    if i:
        lw = len(checks[i][2]) * CW[9]
        text(checks[i][2], PX + 132, cy0 + i * 84 + 14, 9, MUT, w=lw)

# ── knowledge base ───────────────────────────────────────────────────────
KX, KY = 452, 424          # clears the last check box AND its group label chip
group(KX, KY, 322, 96, "Bundled snapshots — offline, dated")
node(KX + 14, KY + 16, 138, 30, "SEBI register", "3,179 real")
node(KX + 168, KY + 16, 140, 30, "Blocklists", "820,000 domains")
text("local backend  ·  127.0.0.1  ·  optional", KX + 14, KY + 58, 9, MUT)
arrow(KX + 160, KY - 6, KX + 160, cy0 + 3 * 84 + 62, None)
text("data", KX + 168, KY - 22, 9, MUT)

# ── merge (teal accent) ──────────────────────────────────────────────────
MX = 660
merge = node(MX, GY + 108, 130, 76, "Merge signals", "risk vs protective",
             fill=TEAL, stroke=TEAL, tcol=INK)
for i in range(4):
    elbow(CX + 148 + 6, cy0 + i * 84 + 29, MX - 6, GY + 146)

# ── verdict ──────────────────────────────────────────────────────────────
VX = 838
verdict = node(VX, GY + 108, 132, 76, "Verdict", "+ why, + sources")
arrow(MX + 130 + 6, GY + 146, VX - 6, GY + 146)

# ── never-cry-wolf gate ──────────────────────────────────────────────────
GX2 = VX
node(GX2, GY + 232, 132, 54, "Blocked claims", "never “safe”", stroke="#ef4444",
     tcol="#ef4444")
# label=None, colour="#ef4444" - passing the hex positionally put it in the
# label slot and rendered "#ef4444" as the arrow's caption.
arrow(VX + 66, GY + 184 + 6, VX + 66, GY + 232 - 6, None, "#ef4444")

# ── output ───────────────────────────────────────────────────────────────
OX = 1018
group(OX, GY + 78, 168, 138, "What the user sees")
outs = ["Hover card", "Badge on message", "Side panel"]
for i, o in enumerate(outs):
    node(OX + 16, GY + 96 + i * 42, 136, 32, o)
arrow(VX + 132 + 6, GY + 146, OX + 10, GY + 146)

# ── footer ───────────────────────────────────────────────────────────────
FY = KY + 118
text("No page content, message text, or payment identifier ever leaves the device on the default path.",
     40, FY, 10, MUT)
text("Badge appears only when there is evidence. Nothing is ever blocked, sent, or replied to on the user's behalf.",
     40, FY + 18, 10, MUT)

doc = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
       "elements": els,
       "appState": {"gridSize": None, "viewBackgroundColor": BG},
       "files": {}}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT}  ({len(els)} elements, {OUT.stat().st_size:,} bytes)")
