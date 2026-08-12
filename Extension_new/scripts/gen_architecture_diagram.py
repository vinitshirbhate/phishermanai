#!/usr/bin/env python3
"""Generate docs/architecture.excalidraw - one diagram, readable by both audiences.

Layout is computed rather than hand-placed so boxes line up and arrows land on
edges. Text elements are standalone (not container-bound): simpler, and it
renders identically.
"""
import json
from pathlib import Path

OUT = Path(r"f:\chetana-browser\docs\architecture.excalidraw")

els = []
_seed = [1000]


def _nonce():
    _seed[0] += 1
    return _seed[0] * 7919 % 2147483647


def base(t, x, y, w, h, **kw):
    return {
        "id": f"e{len(els)}_{_nonce()}",
        "type": t,
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": kw.get("stroke", "#1e1e1e"),
        "backgroundColor": kw.get("bg", "transparent"),
        "fillStyle": kw.get("fill", "solid"),
        "strokeWidth": kw.get("sw", 2),
        "strokeStyle": kw.get("ss", "solid"),
        "roughness": kw.get("rough", 1),
        "opacity": kw.get("opacity", 100),
        "groupIds": [],
        "frameId": None,
        "roundness": kw.get("roundness", {"type": 3}),
        "seed": _nonce(),
        "version": 1,
        "versionNonce": _nonce(),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }


def rect(x, y, w, h, **kw):
    e = base("rectangle", x, y, w, h, **kw)
    els.append(e)
    return e


CHAR_W = {11: 5.7, 12: 6.2, 13: 6.7, 14: 7.2, 16: 8.2, 20: 10.4, 36: 18.6}


def text(s, x, y, size=16, color="#1e1e1e", family=1, align="left", w=None):
    lines = s.split("\n")
    cw = CHAR_W.get(size, size * 0.52)
    width = w if w else max(len(l) for l in lines) * cw
    height = len(lines) * size * 1.25
    e = base("text", x, y, width, height, stroke=color, roundness=None)
    e.update({
        "text": s, "fontSize": size, "fontFamily": family,
        "textAlign": align, "verticalAlign": "top",
        "containerId": None, "originalText": s, "lineHeight": 1.25,
        "baseline": int(size * 0.9),
    })
    els.append(e)
    return e


def centered(s, box, size=16, color="#1e1e1e", family=1, dy=None):
    lines = s.split("\n")
    cw = CHAR_W.get(size, size * 0.52)
    w = max(len(l) for l in lines) * cw
    h = len(lines) * size * 1.25
    x = box["x"] + (box["width"] - w) / 2
    y = box["y"] + ((box["height"] - h) / 2 if dy is None else dy)
    return text(s, x, y, size, color, family, "center", w=w)


def arrow(x1, y1, x2, y2, color="#343a40", dashed=False):
    e = base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1),
             stroke=color, ss="dashed" if dashed else "solid",
             roundness={"type": 2})
    e.update({
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow",
    })
    els.append(e)
    return e


# ── palette ───────────────────────────────────────────────────────────────
BLUE_S, BLUE_B = "#1971c2", "#a5d8ff"
GREEN_S = "#2f9e44"
RED_S, RED_B = "#e03131", "#ffc9c9"
AMBER_S, AMBER_B = "#f08c00", "#ffec99"
VIO_S, VIO_B = "#6741d9", "#d0bfff"
GREY_S, GREY_B = "#495057", "#e9ecef"
INK = "#1e1e1e"
MUTE = "#5c5f66"

# ── title ─────────────────────────────────────────────────────────────────
text("Phisherman AI \u2014 System Architecture", 60, 40, 36, INK)
text("Securities-fraud warnings for Indian retail investors  \u00b7  SEBI TechSprint PS-01\n"
     "Chrome MV3 extension + optional local backend  \u00b7  works fully offline",
     62, 92, 16, MUTE)

# ═════════ 1. SURFACES ════════════════════════════════════════════════════
Y1 = 190
text("1 \u00b7  WHERE WE WATCH", 60, Y1 - 34, 20, BLUE_S)
text("the four places a scam actually reaches the user", 320, Y1 - 30, 14, MUTE)

surfaces = [
    ("Link hover", "any page,\nbefore the click"),
    ("Web page", "the page\nbeing viewed"),
    ("WhatsApp Web", "incoming\nmessages"),
    ("Gmail / webmail", "the open\nmessage"),
]
SW_W, SW_H, GAP = 250, 92, 28
CS_W = 4 * SW_W + 3 * GAP          # 1084
for i, (title, sub) in enumerate(surfaces):
    x = 60 + i * (SW_W + GAP)
    b = rect(x, Y1, SW_W, SW_H, stroke=BLUE_S, bg=BLUE_B)
    centered(title, b, 20, INK, dy=14)
    centered(sub, b, 12, MUTE, dy=46)

# ═════════ 2. CONTENT SCRIPT ══════════════════════════════════════════════
Y2 = Y1 + SW_H + 74
for i in range(4):
    x = 60 + i * (SW_W + GAP) + SW_W / 2
    arrow(x, Y1 + SW_H + 8, x, Y2 - 10, BLUE_S)

cs = rect(60, Y2, CS_W, 96, stroke=GREY_S, bg=GREY_B)
centered("content_script.js   +   whatsapp/   +   mail extractor", cs, 20, INK, dy=14)
centered("Picks the RIGHT UNIT to judge \u2014 the one message, not the whole page.\n"
         "If it cannot isolate the message on a mail site, it scans nothing and says so.",
         cs, 14, MUTE, dy=48)

# ═════════ 3. SERVICE WORKER ══════════════════════════════════════════════
Y3 = Y2 + 96 + 76
arrow(60 + CS_W / 2, Y2 + 96 + 8, 60 + CS_W / 2, Y3 - 12, GREY_S)
text("snapshot", 60 + CS_W / 2 + 12, Y2 + 112, 14, MUTE)

SWK_H = 396
rect(60, Y3, CS_W, SWK_H, stroke=GREEN_S, bg="#ebfbee")
text("2 \u00b7  ON-DEVICE BRAIN   \u2014   background.js (service worker)", 84, Y3 + 20, 20, GREEN_S)
text("Everything below runs on the user's laptop. No network. No account. Nothing leaves the device.",
     84, Y3 + 50, 14, MUTE)

lanes = [
    (BLUE_S, BLUE_B, "LINKS", "preflight/",
     "Is this domain really\nwho it claims to be?",
     "\u2022 Public Suffix List\n\u2022 homoglyph / punycode\n\u2022 IP & redirect tricks\n\u2192 verdict L0\u2013L5"),
    (VIO_S, VIO_B, "ADVISORS", "securities_identity",
     "Is that SEBI\nregistration real?",
     "\u2022 3,179 real registrants\n\u2022 pattern derived from data\n\u2022 registered to SOMEONE ELSE\n\u2192 the valuable catch"),
    (AMBER_S, AMBER_B, "CHATS", "whatsapp/",
     "Does this chat\nbehave like a scam?",
     "\u2022 reply-timing uniformity\n\u2022 money asks escalating\n\u2022 template reuse (hashes)\n\u2192 verdict W0\u2013W6"),
    (RED_S, RED_B, "FILES", "shared/apk_check",
     "Should you install\nthat APK?",
     "\u2022 filename + delivery\n\u2022 'Premium Mod' claims\n\u2022 broker-brand lookalikes\n\u2192 never says 'virus'"),
]
LN_W = (CS_W - 5 * 24) / 4
LN_Y = Y3 + 84
for i, (s, bgc, cap, mod, q, bullets) in enumerate(lanes):
    x = 60 + 24 + i * (LN_W + 24)
    b = rect(x, LN_Y, LN_W, 250, stroke=s, bg=bgc)
    centered(cap, b, 20, INK, dy=14)
    centered(mod, b, 12, s, family=3, dy=42)
    centered(q, b, 14, INK, dy=72)
    text(bullets, x + 14, LN_Y + 130, 13, MUTE)

text("shared/ :   normalise (lookalike letters)  \u00b7  signal_polarity (a good sign is never painted red)  \u00b7  overlay  \u00b7  ml_scorer",
     84, Y3 + SWK_H - 44, 13, MUTE)

# ═════════ 4. BACKEND + OUTPUT ════════════════════════════════════════════
Y4 = Y3 + SWK_H + 72
BE_W = 640
arrow(60 + BE_W / 2, Y3 + SWK_H + 8, 60 + BE_W / 2, Y4 - 12, GREY_S, dashed=True)
text("optional  \u00b7  localhost only  \u00b7  never required",
     60 + BE_W / 2 + 14, Y3 + SWK_H + 20, 13, MUTE)

rect(60, Y4, BE_W, 186, stroke=GREY_S, bg="#f8f9fa", ss="dashed")
text("3 \u00b7  LOCAL BACKEND  (FastAPI, 127.0.0.1:8799)", 84, Y4 + 18, 20, GREY_S)
text("Makes it smarter. Pull the network cable and it still works.", 84, Y4 + 46, 14, MUTE)
text("\u2022  820,000 known-bad domains  (3 blocklists, dated)\n"
     "\u2022  3,179 SEBI registrants \u00b7 whitelist \u00b7 typosquat check\n"
     "\u2022  17 engines \u2014 scamgate L0/L1/L2, behaviour, campaigns",
     84, Y4 + 76, 14, INK)
text("Answers with PROVENANCE, not a verdict:\n"
     "\u201cNot listed on 3 blocklists covering 819,572\n"
     "domains, as of 2026-03-23.\u201d",
     84, Y4 + 132, 12, GREEN_S)

OUT_X = 60 + BE_W + 40
OUT_W = CS_W - BE_W - 40
text("4 \u00b7  WHAT THE USER SEES", OUT_X, Y4 - 34, 20, AMBER_S)
outs = [
    ("Hover card", "the real domain, what was checked,\nand what it cannot see"),
    ("Trust island", "score + top signals, shadow DOM,\ndismissible, never blocks"),
    ("Side panel", "full evidence \u2014 every signal,\nits source and its date"),
]
for i, (t_, s_) in enumerate(outs):
    y = Y4 + i * 64
    rect(OUT_X, y, OUT_W, 56, stroke=AMBER_S, bg=AMBER_B)
    text(t_, OUT_X + 16, y + 8, 16, INK)
    text(s_, OUT_X + 16, y + 30, 11, MUTE)

# ═════════ 5. THE RULE ════════════════════════════════════════════════════
Y6 = Y4 + 186 + 64
rect(60, Y6, CS_W, 152, stroke=RED_S, bg="#fff5f5")
text("5 \u00b7  THE ONE RULE  \u2014  NEVER CRY WOLF", 84, Y6 + 18, 20, RED_S)
text("A tool that flags your real bank is uninstalled by Tuesday. Enforced by machines, not by good intentions.",
     84, Y6 + 46, 14, MUTE)

gates = [
    ("GATE G-2", "false accusations counted\non every run \u2192 currently 0"),
    ("BLOCKED CLAIMS", "\u201csafe\u201d, \u201cverified safe\u201d,\n\u201cthis is a deepfake\u201d \u2192 build FAILS"),
    ("PARITY GATE", "JS and Python must agree\nto \u00b10.02 \u2192 or CI fails"),
    ("PROVENANCE", "every answer names its sources\n+ dates \u2192 checkable, not trusted"),
]
GW = (CS_W - 5 * 22) / 4
for i, (t_, s_) in enumerate(gates):
    x = 60 + 22 + i * (GW + 22)
    rect(x, Y6 + 76, GW, 60, stroke=RED_S, bg=RED_B)
    text(t_, x + 12, Y6 + 84, 14, INK)
    text(s_, x + 12, Y6 + 104, 11, MUTE)

# ═════════ 6. NUMBERS ═════════════════════════════════════════════════════
Y7 = Y6 + 152 + 56
rect(60, Y7, CS_W, 158, stroke=VIO_S, bg="#f8f0fc")
text("6 \u00b7  THE HONEST NUMBERS", 84, Y7 + 18, 20, VIO_S)
text("MCC  0.6646  (CI .6597-.6697)    >= 0.55   MET\n"
     "Recall @ FPR<=1%   0.6112        >= 0.85   NOT MET\n"
     "Brier  0.1317                    <= 0.12   NOT MET",
     84, Y7 + 52, 13, INK, family=3)
text("164 tests  \u00b7  5 CI gates  \u00b7  G-2 false accusations: 0", 84, Y7 + 116, 14, GREEN_S)

text("The standard public phishing dataset's famous 99% accuracy is a\n"
     "COLLECTION ARTEFACT: 100% of its \u201clegitimate\u201d URLs are tidy\n"
     "https://www.domain homepages. Train on that and you score 0.99\n"
     "while flagging SEBI's own website. We ship the honest 0.66.",
     600, Y7 + 50, 13, MUTE)

# ═════════ LEGEND ═════════════════════════════════════════════════════════
Y8 = Y7 + 158 + 46
text("READ IT TWO WAYS", 60, Y8, 16, INK)
text("Non-technical  \u2014  follow the numbers 1 \u2192 6, top to bottom. Ignore the small grey type.\n"
     "Technical      \u2014  the small grey type is the module names and the actual techniques used.\n"
     "Solid arrow = always happens.   Dashed arrow / dashed box = optional, degrades safely if absent.",
     60, Y8 + 26, 14, MUTE)

# ── write ─────────────────────────────────────────────────────────────────
doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": els,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {OUT}  ({len(els)} elements, {OUT.stat().st_size:,} bytes)")
