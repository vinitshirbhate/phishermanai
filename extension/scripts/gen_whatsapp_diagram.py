#!/usr/bin/env python3
"""docs/architecture-whatsapp.excalidraw - WhatsApp lane, DETAILED walkthrough.

The companion overview lives in scripts/gen_whatsapp_overview.py and renders
docs/architecture-whatsapp-2.excalidraw - one row, six boxes, for a slide.
This one is the top-to-bottom version with the evidence spelled out.

Layout is computed rather than hand-placed, so it regenerates cleanly when a
status changes.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "architecture-whatsapp.excalidraw"

els = []
_seed = [500]


def _nonce():
    _seed[0] += 1
    return _seed[0] * 7919 % 2147483647


def base(t, x, y, w, h, **kw):
    return {
        "id": f"w{len(els)}_{_nonce()}", "type": t,
        "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": kw.get("stroke", "#1e1e1e"),
        "backgroundColor": kw.get("bg", "transparent"),
        "fillStyle": "solid", "strokeWidth": kw.get("sw", 2),
        "strokeStyle": kw.get("ss", "solid"), "roughness": 1,
        "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": kw.get("roundness", {"type": 3}),
        "seed": _nonce(), "version": 1, "versionNonce": _nonce(),
        "isDeleted": False, "boundElements": None, "updated": 1,
        "link": None, "locked": False,
    }


def rect(x, y, w, h, **kw):
    e = base("rectangle", x, y, w, h, **kw)
    els.append(e)
    return e


CW = {11: 5.7, 12: 6.2, 13: 6.7, 14: 7.2, 16: 8.2, 18: 9.3, 20: 10.4, 24: 12.4, 34: 17.6}


def text(s, x, y, size=16, color="#1e1e1e", family=1, align="left", w=None):
    lines = s.split("\n")
    cw = CW.get(size, size * 0.52)
    width = w if w else max(len(l) for l in lines) * cw
    e = base("text", x, y, width, len(lines) * size * 1.25, stroke=color, roundness=None)
    e.update({"text": s, "fontSize": size, "fontFamily": family, "textAlign": align,
              "verticalAlign": "top", "containerId": None, "originalText": s,
              "lineHeight": 1.25, "baseline": int(size * 0.9)})
    els.append(e)
    return e


def centered(s, box, size=16, color="#1e1e1e", family=1, dy=None):
    lines = s.split("\n")
    cw = CW.get(size, size * 0.52)
    w = max(len(l) for l in lines) * cw
    h = len(lines) * size * 1.25
    return text(s, box["x"] + (box["width"] - w) / 2,
                box["y"] + ((box["height"] - h) / 2 if dy is None else dy),
                size, color, family, "center", w=w)


def arrow(x1, y1, x2, y2, color="#343a40", dashed=False):
    e = base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), stroke=color,
             ss="dashed" if dashed else "solid", roundness={"type": 2})
    e.update({"points": [[0, 0], [x2 - x1, y2 - y1]], "lastCommittedPoint": None,
              "startBinding": None, "endBinding": None,
              "startArrowhead": None, "endArrowhead": "arrow"})
    els.append(e)
    return e


GREEN_S, GREEN_B = "#2f9e44", "#b2f2bb"
BLUE_S, BLUE_B = "#1971c2", "#a5d8ff"
AMBER_S, AMBER_B = "#f08c00", "#ffec99"
RED_S, RED_B = "#e03131", "#ffc9c9"
VIO_S, VIO_B = "#6741d9", "#d0bfff"
GREY_S, GREY_B = "#495057", "#e9ecef"
INK, MUTE = "#1e1e1e", "#5c5f66"

W, L = 1000, 60
CX = L + W / 2

text("WhatsApp Lane — how it works", L, 40, 34, INK)
text("Catches investment-scam messages on WhatsApp Web, entirely on the user's device.\n"
     "Nothing typed, read, or received ever leaves the laptop.", L + 2, 88, 16, MUTE)

Y, STEP_H = 165, 118


def step(n, title, plain, tech, y, s, b, h=STEP_H):
    box = rect(L, y, W, h, stroke=s, bg=b)
    text(f"{n}", L + 22, y + 16, 24, s)
    text(title, L + 62, y + 16, 20, INK)
    text(plain, L + 62, y + 46, 14, INK)
    text(tech, L + 62, y + h - 30, 12, MUTE, family=3)
    return box


step(1, "A message arrives",
     "Someone opens a chat, or a new message lands.",
     "whatsapp/adapter_mv3.js  ·  MutationObserver (childList+subtree)  ·  150 ms debounce",
     Y, GREY_S, GREY_B)
arrow(CX, Y + STEP_H + 6, CX, Y + STEP_H + 40, GREY_S)

Y2 = Y + STEP_H + 48
step(2, "Can we actually see the page?",
     "WhatsApp changes its design often. If we can no longer find messages reliably,\n"
     "we STOP scanning and say so — rather than guess and get it wrong.",
     "whatsapp/health.js  ·  HEALTHY / DEGRADED / BLIND  ·  re-checked on a timer",
     Y2, BLUE_S, BLUE_B, 130)
text("BLIND → “Not scanning.\nWhatsApp's page structure\nchanged.”",
     L + W + 24, Y2 + 26, 12, BLUE_S)
arrow(CX, Y2 + 136, CX, Y2 + 170, BLUE_S)

Y3 = Y2 + 178
step(3, "Read ONE message",
     "Who sent it, when, was it forwarded — and what is inside it.",
     "whatsapp/selectors.js (attribute-only, 3 fallback tiers)  +  whatsapp/extract.js",
     Y3, GREEN_S, GREEN_B, 178)
items = ["UPI IDs", "links", "phone numbers", "money amounts",
         "SEBI reg. numbers", ".apk files"]
IW = (W - 60 - 5 * 12) / 6
for i, it in enumerate(items):
    x = L + 30 + i * (IW + 12)
    bb = rect(x, Y3 + 78, IW, 34, stroke=GREEN_S, bg="#ffffff")
    centered(it, bb, 12, INK)
text("Privacy: message text is NEVER stored — only a one-way fingerprint.   "
     "“View once” media is flagged but never opened.",
     L + 62, Y3 + 122, 13, GREEN_S)
arrow(CX, Y3 + 184, CX, Y3 + 218, GREEN_S)

Y4 = Y3 + 226
step(4, "Read the CHAT it arrived in",
     "How the conversation behaves — not what it says. Works without reading content.",
     "whatsapp/context.js  ·  reply-latency CV  ·  monotonic amount ladder  ·  FNV-1a hashes",
     Y4, AMBER_S, AMBER_B, 150)
beh = [("Replies too evenly timed", "a bot, not a person"),
       ("Money asks climbing", "₹5,000 → ₹50,000 → ₹2 lakh"),
       ("Same text in other groups", "a campaign, not advice")]
BW = (W - 60 - 2 * 14) / 3
for i, (t_, s_) in enumerate(beh):
    x = L + 30 + i * (BW + 14)
    bb = rect(x, Y4 + 76, BW, 52, stroke=AMBER_S, bg="#ffffff")
    centered(t_, bb, 13, INK, dy=10)
    centered(s_, bb, 11, MUTE, dy=30)
arrow(CX, Y4 + 156, CX, Y4 + 190, AMBER_S)

Y5 = Y4 + 198
step(5, "Decide — and say WHY",
     "Seven outcomes. A badge only appears from W1 upward; W0 stays silent.",
     "whatsapp/verdict.js  ·  every code carries its evidence and which truth it speaks to",
     Y5, VIO_S, VIO_B, 196)
codes = [
    ("W0", "nothing found", "#adb5bd"),
    ("W1", "unsolicited context", VIO_S),
    ("W2", "advice, no SEBI disclosure", VIO_S),
    ("W3", "matches a SEBI typology", VIO_S),
    ("W4", "asks for money  /  unsafe app", RED_S),
    ("W5", "reg. number belongs to SOMEONE ELSE", RED_S),
    ("W6", "same identifiers seen elsewhere", RED_S),
]
for i, (c, d, col) in enumerate(codes):
    y = Y5 + 72 + i * 17
    text(c, L + 62, y, 12, col, family=3)
    text(d, L + 108, y, 12, INK if col != "#adb5bd" else MUTE)
text("W5 is the one to demo:\n“Registration INA000... is\nregistered to <X>, not to\nthis sender.”\n\n"
     "It accuses the CREDENTIAL,\nnever the person.",
     L + 560, Y5 + 66, 13, RED_S)
arrow(CX, Y5 + 202, CX, Y5 + 236, VIO_S)

Y6 = Y5 + 244
step(6, "Show it — without touching the chat",
     "A small badge beside the message. Never inside it, never blocking, always dismissible.",
     "shared/overlay.js  ·  one shadow root, sibling of the scroll container",
     Y6, GREY_S, GREY_B, 108)
text("We never send, reply, react, forward,\nor leave a group on the user's behalf.",
     L + W + 24, Y6 + 30, 12, GREY_S)

# ── status band ──────────────────────────────────────────────────────────
Y7 = Y6 + 116 + 54
text("WHAT IS ACTUALLY IMPLEMENTED", L, Y7, 20, INK)
text("This is the honest state, not the plan.", L + 400, Y7 + 4, 14, MUTE)

cols = [
    (GREEN_S, "#ebfbee", "BUILT  &  TESTED",
     "All 6 modules above.\n13 pure-logic tests +\nAPK tests, all passing.\n"
     "Verdicts W0–W6 produce\ncorrect output from a\nmessage record."),
    (AMBER_S, "#fff9db", "BUILT,  NOT  RUNNING",
     "adapter.start() has NO\nCALLER. The files load\non web.whatsapp.com but\n"
     "nothing starts the lane,\nso no badge appears in\na real browser yet."),
    (RED_S, "#fff5f5", "NOT  YET  VERIFIED",
     "The selectors have never\nrun against real WhatsApp\nmarkup — needs 5 human-\n"
     "captured screenshots.\nFixtures we write would\nmatch our own code."),
]
SW_ = (W - 2 * 20) / 3
for i, (s, bgc, t_, body) in enumerate(cols):
    x = L + i * (SW_ + 20)
    rect(x, Y7 + 36, SW_, 168, stroke=s, bg=bgc)
    text(t_, x + 18, Y7 + 52, 16, s)
    text(body, x + 18, Y7 + 80, 12, INK)

Y8 = Y7 + 36 + 168 + 40
text("Also OFF by default:  chat context is not fed into the SEBI-disclosure rule. "
     "enable_chat_context() refuses\nunless explicitly confirmed — shipping it because "
     "the code exists is how a demo becomes a false claim.",
     L, Y8, 13, MUTE)
text("READ IT TWO WAYS   —   non-technical: follow 1→6 and read the large type.   "
     "technical: the small grey line in each step is the module and the method.",
     L, Y8 + 46, 13, INK)

doc = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
       "elements": els,
       "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"}, "files": {}}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT}  ({len(els)} elements, {OUT.stat().st_size:,} bytes)")
