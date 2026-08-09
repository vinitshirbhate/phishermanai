"""Generate the Excalidraw architecture diagrams.

    python -m docs.make_excalidraw

Writes:
    docs/system-overview.excalidraw  how a verification runs (start here)
    docs/architecture.excalidraw     the verification pipeline, vertical
    docs/data-refresh.excalidraw     how the local data stays current

Open either at excalidraw.com (menu -> Open). Every box, arrow and label is a
normal Excalidraw object, so they can be rearranged, retyped and exported to
PNG/SVG for slides.

These mirror docs/architecture.mmd and docs/data-refresh.mmd exactly -- same
boxes, same wording, same colours. The Mermaid files stay the canonical source
for anything that renders Mermaid (GitHub, Notion, the architecture page); these
exist so the diagrams can be *edited* by hand without a conversion step.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

DOCS = Path(__file__).resolve().parent

INK = "#1e1e1e"
# Same palette as the Mermaid classDefs, so the two renderings match.
PREP_BG, PREP_LINE = "#a5d8ff", "#1971c2"
GATE_BG, GATE_LINE = "#ffec99", "#f08c00"
STORE_BG, STORE_LINE = "#d0bfff", "#6741d9"
INPUT_BG, INPUT_LINE = "#f1f3f5", "#868e96"
OK_BG, OK_LINE = "#b2f2bb", "#2f9e44"
QUIET_BG, QUIET_LINE = "#e9ecef", "#868e96"
WARN_BG, WARN_LINE = "#ffd8a8", "#e8590c"
BAD_BG, BAD_LINE = "#ffc9c9", "#e03131"

FONT_HAND = 1          # Virgil, the Excalidraw signature face
LINE_HEIGHT = 1.25

_rng = random.Random(20260809)
_n = [0]


def _uid() -> str:
    _n[0] += 1
    return f"pha{_n[0]:04d}"


def _seed() -> int:
    return _rng.randint(1, 2**31)


def _el(kind: str, x: float, y: float, w: float, h: float, **extra: Any) -> dict:
    base = {
        "id": _uid(), "type": kind, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": INK, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 3}, "seed": _seed(), "version": 1,
        "versionNonce": _seed(), "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
    }
    base.update(extra)
    return base


def _text(content: str, x: float, y: float, size: int, *, container: str | None = None,
          colour: str = INK, align: str = "center", w: float | None = None,
          h: float | None = None) -> dict:
    lines = content.split("\n")
    width = w if w is not None else max(len(l) for l in lines) * size * 0.58
    height = h if h is not None else len(lines) * size * LINE_HEIGHT
    return _el("text", x, y, width, height,
               text=content, originalText=content, fontSize=size,
               fontFamily=FONT_HAND, textAlign=align,
               verticalAlign="middle" if container else "top",
               containerId=container, lineHeight=LINE_HEIGHT,
               strokeColor=colour, baseline=int(size * 0.8))


def box(x, y, w, h, label, *, bg, line, size=17, ellipse=False, diamond=False):
    kind = "ellipse" if ellipse else "diamond" if diamond else "rectangle"
    shape = _el(kind, x, y, w, h, backgroundColor=bg, strokeColor=line,
                roundness={"type": 2} if kind != "rectangle" else {"type": 3})
    pad = 60 if diamond else 18
    label_el = _text(label, x, y, size, container=shape["id"],
                     w=w - pad, h=len(label.split("\n")) * size * LINE_HEIGHT)
    shape["boundElements"] = [{"id": label_el["id"], "type": "text"}]
    return shape, label_el


def _anchor(el: dict, side: str) -> tuple[float, float]:
    x, y, w, h = el["x"], el["y"], el["width"], el["height"]
    return {
        "top": (x + w / 2, y), "bottom": (x + w / 2, y + h),
        "left": (x, y + h / 2), "right": (x + w, y + h / 2),
    }[side]


def link(a: dict, b: dict, *, from_side="bottom", to_side="top", label=None,
         colour=INK, dashed=False, waypoints: list[tuple[float, float]] | None = None,
         size=13):
    """Arrow between two shapes. `waypoints` are absolute points for an elbow."""
    x1, y1 = _anchor(a, from_side)
    x2, y2 = _anchor(b, to_side)

    absolute = [(x1, y1), *(waypoints or []), (x2, y2)]
    points = [[px - x1, py - y1] for px, py in absolute]

    arrow = _el("arrow", x1, y1, x2 - x1, y2 - y1,
                strokeColor=colour, backgroundColor="transparent",
                roundness={"type": 2}, strokeStyle="dashed" if dashed else "solid",
                points=points, lastCommittedPoint=None,
                startBinding={"elementId": a["id"], "focus": 0, "gap": 4},
                endBinding={"elementId": b["id"], "focus": 0, "gap": 4},
                startArrowhead=None, endArrowhead="arrow")
    a.setdefault("boundElements", []).append({"id": arrow["id"], "type": "arrow"})
    b.setdefault("boundElements", []).append({"id": arrow["id"], "type": "arrow"})

    out = [arrow]
    if label:
        # Place the label beside the arrow's midpoint.
        mid = absolute[len(absolute) // 2] if len(absolute) > 2 else \
            ((x1 + x2) / 2, (y1 + y2) / 2)
        out.append(_text(label, mid[0] + 10, mid[1] - 9, size, colour=colour, align="left"))
    return out


def _document(elements: list[dict]) -> dict:
    return {
        "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }


# ==========================================================================
# Diagram 1 — the verification pipeline
# ==========================================================================

def build_pipeline() -> dict:
    els: list[dict] = []
    add = els.extend

    add([_text("How PhishermanAI verifies a message", 330, 0, 28, align="left"),
         _text("proven senders exit early · everything else is checked against real filings",
               330, 40, 15, colour="#5c6773", align="left")])

    CX, CW = 380, 330          # main column

    inp, t = box(CX, 100, CW, 58, "Email · WhatsApp · Screenshot",
                 bg=INPUT_BG, line=INPUT_LINE, size=16); add([inp, t])
    prep, t = box(CX, 208, CW, 76,
                  "Prepare\nparse · mask demat/PAN/phone · unwrap forwards",
                  bg=PREP_BG, line=PREP_LINE, size=15); add([prep, t])
    gate, t = box(CX - 45, 334, CW + 90, 150,
                  "Signed by an\nauthorised domain?",
                  bg=GATE_BG, line=GATE_LINE, size=17, diamond=True); add([gate, t])
    checks, t = box(CX, 540, CW, 76,
                    "Four chokepoints\nEntity · Money · Claim · Delivery",
                    bg=PREP_BG, line=PREP_LINE, size=15); add([checks, t])
    filing, t = box(CX, 668, CW, 76,
                    "Cross-check the real filing\ncompare field by field",
                    bg=PREP_BG, line=PREP_LINE, size=15); add([filing, t])
    decide, t = box(CX - 25, 796, CW + 50, 130, "Weigh the findings",
                    bg=GATE_BG, line=GATE_LINE, size=17, diamond=True); add([decide, t])

    # verdict row
    VY, VW, VH, gap = 1000, 226, 72, 22
    x0 = 40
    verified, t = box(x0, VY, VW, VH, "VERIFIED", bg=OK_BG, line=OK_LINE, size=19, ellipse=True); add([verified, t])
    norisk, t = box(x0 + (VW + gap), VY, VW, VH, "NO RISK FOUND", bg=QUIET_BG, line=QUIET_LINE, size=17, ellipse=True); add([norisk, t])
    tampered, t = box(x0 + 2 * (VW + gap), VY, VW, VH, "TAMPERED", bg=WARN_BG, line=WARN_LINE, size=19, ellipse=True); add([tampered, t])
    fraud, t = box(x0 + 3 * (VW + gap), VY, VW, VH, "FRAUDULENT", bg=BAD_BG, line=BAD_LINE, size=19, ellipse=True); add([fraud, t])

    # local data, to the right so the fast path can run down the left
    data, t = box(800, 560, 290, 128,
                  "Local reference data\n8,434 exchange filings\n5,442 SEBI registrations\nno network at request time",
                  bg=STORE_BG, line=STORE_LINE, size=14); add([data, t])

    # main spine
    add(link(inp, prep))
    add(link(prep, gate))
    add(link(gate, checks, label="no"))
    add(link(checks, filing))
    add(link(filing, decide))

    # the fast path: down the left margin to VERIFIED
    add(link(gate, verified, from_side="left", to_side="top",
             colour=OK_LINE, label="yes — proven sender",
             waypoints=[(150, 409), (150, 980)]))

    # decision fan-out
    for target, colour in ((verified, OK_LINE), (norisk, QUIET_LINE),
                           (tampered, WARN_LINE), (fraud, BAD_LINE)):
        add(link(decide, target, colour=colour))

    # lookups
    add(link(data, checks, from_side="left", to_side="right", colour=STORE_LINE, dashed=True))
    add(link(data, filing, from_side="left", to_side="right", colour=STORE_LINE, dashed=True))

    add([
        _text("Runs before any rule, so a 16-digit\ndemat ID is never read as a bank account.",
              740, 214, 13, colour="#5c6773", align="left"),
        _text("DKIM already proves the content is\nunaltered — 83% of genuine mail\nexits here in 10 ms.",
              740, 372, 13, colour="#8a6100", align="left"),
        _text("The differentiator: is what this says\nwhat the company actually filed?",
              740, 700, 13, colour="#5c6773", align="left"),
        _text("Dashed = lookup against local data. Nothing leaves the machine.",
              40, 1110, 13, colour="#5c6773", align="left"),
    ])
    return _document(els)


# ==========================================================================
# Diagram 2 — keeping the data current
# ==========================================================================

def build_refresh() -> dict:
    els: list[dict] = []
    add = els.extend

    add([_text("Keeping the local data current", 40, 0, 26, align="left"),
         _text("stale data fails safe — it can make us less certain, never falsely confident",
               40, 36, 15, colour="#5c6773", align="left")])

    SX, SW = 40, 250
    bse, t = box(SX, 110, SW, 70, "BSE announcements\nstale in hours", bg=STORE_BG, line=STORE_LINE, size=14); add([bse, t])
    sebi, t = box(SX, 210, SW, 70, "SEBI registers\nstale in weeks", bg=STORE_BG, line=STORE_LINE, size=14); add([sebi, t])
    master, t = box(SX, 310, SW, 70, "Scrip master\nstale in months", bg=STORE_BG, line=STORE_LINE, size=14); add([master, t])

    JX, JW = 350, 200
    j1, t = box(JX, 110, JW, 70, "Twice daily\nincremental", bg=PREP_BG, line=PREP_LINE, size=14); add([j1, t])
    j2, t = box(JX, 210, JW, 70, "Weekly", bg=PREP_BG, line=PREP_LINE, size=14); add([j2, t])
    j3, t = box(JX, 310, JW, 70, "Monthly", bg=PREP_BG, line=PREP_LINE, size=14); add([j3, t])

    corpus, t = box(620, 190, 250, 110,
                    "Local corpus\nper-source\ndata_as_of stamp",
                    bg=GATE_BG, line=GATE_LINE, size=15); add([corpus, t])

    stamp, t = box(950, 80, 290, 80,
                   "Every verdict states it\n“as of 8 Aug 2026, 18:30”",
                   bg=OK_BG, line=OK_LINE, size=14); add([stamp, t])
    age, t = box(960, 210, 270, 120, "Older than\n3 days?",
                 bg=GATE_BG, line=GATE_LINE, size=16, diamond=True); add([age, t])
    loud, t = box(1310, 190, 250, 70, "Show staleness banner",
                  bg=WARN_BG, line=WARN_LINE, size=14); add([loud, t])
    okbox, t = box(1310, 290, 250, 62, "Normal operation",
                   bg=QUIET_BG, line=QUIET_LINE, size=14); add([okbox, t])

    guard, t = box(560, 380, 380, 96,
                   "Newer document, or amended filing\n→ NO RISK FOUND, never TAMPERED",
                   bg=OK_BG, line=OK_LINE, size=14); add([guard, t])

    dom, t = box(40, 430, 400, 84,
                 "New domain candidate\nDNS/MX check → human review → merge",
                 bg=BAD_BG, line=BAD_LINE, size=14); add([dom, t])

    for src, job in ((bse, j1), (sebi, j2), (master, j3)):
        add(link(src, job, from_side="right", to_side="left"))
    for job in (j1, j2, j3):
        add(link(job, corpus, from_side="right", to_side="left"))

    add(link(corpus, stamp, from_side="right", to_side="left", colour=OK_LINE))
    add(link(corpus, age, from_side="right", to_side="left"))
    add(link(age, loud, from_side="right", to_side="left", colour=WARN_LINE, label="yes"))
    add(link(age, okbox, from_side="bottom", to_side="left", colour=QUIET_LINE, label="no"))
    add(link(corpus, guard, from_side="bottom", to_side="top", colour=OK_LINE, dashed=True))
    add(link(dom, corpus, from_side="right", to_side="bottom", colour=BAD_LINE,
             dashed=True, label="never auto-inserted"))

    add([_text("Only the first source is urgent. The others move in weeks or months.",
               40, 560, 13, colour="#5c6773", align="left")])
    return _document(els)


# ==========================================================================
# Diagram 3 — system workflow (horizontal)
# ==========================================================================
#
# Shows HOW A REQUEST RUNS, not merely what the parts are. Two rows:
#
#   TOP     the journey of one message, an unbroken left-to-right line, 1..6
#   BOTTOM  the local data it reads, and the jobs that refill that data
#
# Splitting them is the whole point. The earlier version put the data store
# inline between the engine and the sources, which made a lookup look like a
# step in the journey. Nothing on the bottom row happens during a request, so a
# reader can follow the top line end to end and have the complete story.

def layer(x, y, w, h, title, *, line):
    """A dashed grouping band with a title above it."""
    frame = _el("rectangle", x, y, w, h,
                backgroundColor="transparent", strokeColor=line,
                strokeStyle="dashed", strokeWidth=1, roundness={"type": 3})
    heading = _text(title, x + 2, y - 26, 14, colour=line, align="left")
    return frame, heading


def badge(n, x, y, *, line="#1971c2"):
    """A small numbered circle, so the running order cannot be misread."""
    circle = _el("ellipse", x, y, 36, 36, backgroundColor="#ffffff",
                 strokeColor=line, strokeWidth=2, roundness={"type": 2})
    label = _text(str(n), x, y, 17, container=circle["id"], colour=line, w=24, h=21)
    circle["boundElements"] = [{"id": label["id"], "type": "text"}]
    return circle, label


def build_system() -> dict:
    els = []
    add = els.extend

    add([_text("PhishermanAI - how a verification runs", 40, 0, 27, align="left"),
         _text("follow the numbered line: message in, answer out. Everything below it is local data being read.",
               40, 38, 15, colour="#5c6773", align="left")])

    # ================================================= TOP ROW: the journey
    f, t = layer(40, 120, 240, 300, "WAYS IN", line="#868e96"); add([f, t])
    ext, t = box(60, 150, 200, 74, "WhatsApp Web\nextension - 200 ms",
                 bg=INPUT_BG, line=INPUT_LINE, size=13); add([ext, t])
    web, t = box(60, 236, 200, 74, "Web app\ndrop .eml - paste - image",
                 bg=INPUT_BG, line=INPUT_LINE, size=13); add([web, t])
    smtp, t = box(60, 322, 200, 80, "SMTP gateway\nchecks mail on arrival",
                  bg=INPUT_BG, line=INPUT_LINE, size=13); add([smtp, t])

    api, t = box(330, 215, 170, 110, "API\nFastAPI\n/verify",
                 bg=PREP_BG, line=PREP_LINE, size=14); add([api, t])
    n, t = badge(1, 340, 190); add([n, t])

    f, t = layer(550, 120, 880, 300, "VERIFICATION ENGINE", line="#1971c2"); add([f, t])

    prep, t = box(575, 200, 180, 110,
                  "Read & clean\nparse - strip hidden text\nmask demat / PAN / phone",
                  bg=GATE_BG, line=GATE_LINE, size=13); add([prep, t])
    n, t = badge(2, 585, 175, line=GATE_LINE); add([n, t])

    gate, t = box(790, 175, 210, 160, "Sender proven?\nvalid signature +\nknown domain",
                  bg=GATE_BG, line=GATE_LINE, size=14, diamond=True); add([gate, t])
    n, t = badge(3, 800, 150, line=GATE_LINE); add([n, t])

    checks, t = box(1035, 200, 175, 110, "Four checks\nEntity - Money\nClaim - Delivery",
                    bg=PREP_BG, line=PREP_LINE, size=13); add([checks, t])
    n, t = badge(4, 1045, 175); add([n, t])

    filing, t = box(1245, 200, 165, 110, "Compare to the\nreal filing\nfield by field",
                    bg=PREP_BG, line=PREP_LINE, size=13); add([filing, t])
    n, t = badge(5, 1255, 175); add([n, t])

    decide, t = box(1480, 215, 155, 110, "Weigh it up\n\n40 ms total",
                    bg=OK_BG, line=OK_LINE, size=14); add([decide, t])
    n, t = badge(6, 1490, 190, line=OK_LINE); add([n, t])

    f, t = layer(1690, 120, 250, 320, "ANSWER", line="#2f9e44"); add([f, t])
    VX, VW = 1710, 210
    verified, t = box(VX, 150, VW, 62, "VERIFIED", bg=OK_BG, line=OK_LINE, size=17, ellipse=True); add([verified, t])
    norisk, t = box(VX, 224, VW, 62, "NO RISK FOUND", bg=QUIET_BG, line=QUIET_LINE, size=15, ellipse=True); add([norisk, t])
    tampered, t = box(VX, 298, VW, 62, "TAMPERED", bg=WARN_BG, line=WARN_LINE, size=17, ellipse=True); add([tampered, t])
    fraud, t = box(VX, 372, VW, 62, "FRAUDULENT", bg=BAD_BG, line=BAD_LINE, size=17, ellipse=True); add([fraud, t])

    # =========================================== BOTTOM ROW: what it reads
    f, t = layer(560, 520, 560, 210, "LOCAL DATA  -  read during every check", line="#6741d9")
    add([f, t])
    d1, t = box(580, 560, 250, 100,
                "8,434 exchange filings\n10,367 entities\n114 verified domains",
                bg=STORE_BG, line=STORE_LINE, size=13); add([d1, t])
    d2, t = box(850, 560, 250, 100,
                "28 rules\nSEBI registrations\nUPI handles - IFSC",
                bg=STORE_BG, line=STORE_LINE, size=13); add([d2, t])

    f, t = layer(1180, 520, 500, 210,
                 "REFILLED OUT OF BAND  -  never during a request", line="#e8590c")
    add([f, t])
    s1, t = box(1200, 560, 220, 100, "BSE filings\ntwice daily",
                bg=WARN_BG, line=WARN_LINE, size=13); add([s1, t])
    s2, t = box(1440, 560, 220, 100, "SEBI registers\nweekly",
                bg=WARN_BG, line=WARN_LINE, size=13); add([s2, t])

    # ------------------------------------------------------------ wiring
    for channel in (ext, web, smtp):
        add(link(channel, api, from_side="right", to_side="left"))
    add(link(api, prep, from_side="right", to_side="left"))
    add(link(prep, gate, from_side="right", to_side="left"))
    add(link(gate, checks, from_side="right", to_side="left", label="no"))
    add(link(checks, filing, from_side="right", to_side="left"))
    add(link(filing, decide, from_side="right", to_side="left"))

    add(link(decide, verified, from_side="right", to_side="left", colour=OK_LINE))
    add(link(decide, norisk, from_side="right", to_side="left", colour=QUIET_LINE))
    add(link(decide, tampered, from_side="right", to_side="left", colour=WARN_LINE))
    add(link(decide, fraud, from_side="right", to_side="left", colour=BAD_LINE))

    # The fast path, routed clear above the row so it reads as a bypass rather
    # than another step.
    add(link(gate, verified, from_side="top", to_side="top", colour=OK_LINE,
             label="yes - 83% of genuine mail, 10 ms",
             waypoints=[(895, 70), (1815, 70)]))

    # Lookups rise from the data row into the two stages that consult it.
    add(link(d1, checks, from_side="top", to_side="bottom", colour=STORE_LINE, dashed=True))
    add(link(d1, filing, from_side="top", to_side="bottom", colour=STORE_LINE, dashed=True))
    add(link(d2, checks, from_side="top", to_side="bottom", colour=STORE_LINE, dashed=True))

    add(link(s1, d1, from_side="left", to_side="right", colour=WARN_LINE, dashed=True))
    add(link(s2, d2, from_side="left", to_side="right", colour=WARN_LINE, dashed=True))

    add([
        _text("Solid line = the journey of one message.     Dashed = reading local data.",
              40, 470, 14, colour="#5c6773", align="left"),
        _text("A screenshot takes the same path but about 3 s, because the text must be read off the image first.",
              40, 762, 13, colour="#5c6773", align="left"),
        _text("No step on the top line touches the internet. The whole journey runs with the cable unplugged.",
              40, 792, 13, colour="#6741d9", align="left"),
    ])
    return _document(els)


if __name__ == "__main__":  # pragma: no cover
    for name, builder in (("architecture", build_pipeline),
                          ("data-refresh", build_refresh),
                          ("system-overview", build_system)):
        doc = builder()
        path = DOCS / f"{name}.excalidraw"
        path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        kinds: dict[str, int] = {}
        for element in doc["elements"]:
            kinds[element["type"]] = kinds.get(element["type"], 0) + 1
        print(f"wrote {path.name}: {len(doc['elements'])} elements {kinds}")
