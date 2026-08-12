"""What the user should do next, and the artefacts that help them do it.

Three deliverables:

  1. IMMEDIATE GUIDANCE -- what not to do, plus the verified official contact
     for the organisation the message claims to be, taken from our entities
     table. This detail matters more than it looks: a worried investor who is
     told "contact the company" will search for a helpline and land on a fake
     one, because fraudulent support numbers are seeded into search results for
     exactly that moment. Handing them the registered contact closes that loop.

  2. SHAREABLE WARNING CARD -- a PNG the user can forward straight back into the
     WhatsApp group the message came from. Fraud spreads by forwarding, so the
     correction has to travel the same way, in the same format, or it does not
     travel at all.

  3. PREFILLED REPORTS -- routed by type, because sending a report to the wrong
     body wastes the only report most people will ever file:
        registered intermediary  -> SEBI SCORES
        unregistered / content   -> SEBI takedown
        money actually lost      -> cybercrime.gov.in / helpline 1930
"""

from __future__ import annotations

import hashlib
import io
import textwrap
from datetime import datetime
from typing import Any

from sqlalchemy import select

from core.db import session_scope
from core.models import Entity
from core.scoring import FRAUDULENT, GENUINE, TAMPERED, UNVERIFIED, Verdict

# Verdict presentation. Colours are RGB for the PNG card; the UI uses its own.
VERDICT_STYLE = {
    GENUINE: {"colour": (22, 138, 74), "label": "GENUINE", "icon": "OK"},
    TAMPERED: {"colour": (194, 120, 3), "label": "TAMPERED", "icon": "!"},
    # The card shows the display wording, not the internal code: "UNVERIFIED"
    # reads as an accusation, which is the opposite of what this verdict means.
    UNVERIFIED: {"colour": (90, 98, 112), "label": "NO RISK FOUND", "icon": "?"},
    FRAUDULENT: {"colour": (185, 28, 28), "label": "FRAUDULENT", "icon": "X"},
}

OFFICIAL_CHANNELS = {
    "cybercrime": {
        "name": "National Cyber Crime Reporting Portal",
        "url": "https://cybercrime.gov.in",
        "helpline": "1930",
        "use_when": "You have already lost money. Report within 24 hours -- the "
                    "golden-hour window gives the best chance of freezing the transfer.",
    },
    "scores": {
        "name": "SEBI SCORES",
        "url": "https://scores.sebi.gov.in",
        "use_when": "Your complaint is against a SEBI-registered intermediary.",
    },
    "sebi_takedown": {
        "name": "SEBI investor complaint / unregistered entity report",
        "url": "https://www.sebi.gov.in",
        "use_when": "The entity is not SEBI-registered, or the content should be taken down.",
    },
    "smartodr": {
        "name": "SMART ODR portal",
        "url": "https://smartodr.in",
        "use_when": "A dispute with a registered intermediary needs resolution.",
    },
}


def official_contact_for(entity_name: str | None) -> dict[str, Any] | None:
    """The registered contact details for an entity, from SEBI's own register."""
    if not entity_name:
        return None
    from core.textnorm import normalise_company_name

    target = normalise_company_name(entity_name)
    if not target:
        return None

    try:
        with session_scope() as session:
            rows = session.execute(
                select(Entity.name, Entity.entity_type, Entity.sebi_reg_no,
                       Entity.official_domains, Entity.official_contact)
                .where(Entity.normalised_name == target)
            ).all()
            if not rows:
                rows = session.execute(
                    select(Entity.name, Entity.entity_type, Entity.sebi_reg_no,
                           Entity.official_domains, Entity.official_contact)
                    .where(Entity.normalised_name.like(f"%{target}%"))
                    .limit(1)
                ).all()
    except Exception:  # noqa: BLE001
        return None

    if not rows:
        return None

    # Prefer a record that actually carries contact details.
    best = max(rows, key=lambda r: (bool(r[4]), bool(r[3]), bool(r[2])))
    name, entity_type, reg_no, domains, contact = best
    return {
        "entity": name,
        "entity_type": entity_type,
        "sebi_registration": reg_no,
        "official_domains": domains or [],
        "registered_email": (contact or {}).get("email"),
        "registered_phone": (contact or {}).get("phone"),
        "city": (contact or {}).get("city"),
        "source": "SEBI registered intermediary register",
        "caution": (
            "Use only these details. Do not search for a helpline number -- fraudulent "
            "customer-care numbers are deliberately placed in search results."
        ),
    }


def recommended_actions(
    verdict: Verdict,
    *,
    claimed_entity: str | None = None,
    money_sent: bool = False,
) -> list[dict[str, Any]]:
    """Ordered, concrete next steps for this verdict."""
    actions: list[dict[str, Any]] = []
    kind = verdict.verdict

    if kind == FRAUDULENT:
        actions.append({
            "priority": "IMMEDIATE", "type": "DO_NOT",
            "title": "Do not pay, click, or reply",
            "detail": (
                "Do not send money, do not open any link in this message, do not share an "
                "OTP or PIN, and do not install anything it asks you to install. Replying "
                "at all confirms your number is active."
            ),
        })
    elif kind == TAMPERED:
        altered = [c for c in verdict.field_comparisons if c.get("match") is False]
        names = ", ".join(c["field"].replace("_", " ") for c in altered) or "a key field"
        actions.append({
            "priority": "IMMEDIATE", "type": "DO_NOT",
            "title": "Do not act on this document",
            "detail": (
                f"This document is based on a real filing, but the {names} does not match "
                "what the company filed with the exchange. Treat every instruction in it "
                "as unreliable, including any bank or payment details."
            ),
        })
    elif kind == UNVERIFIED:
        actions.append({
            "priority": "IMMEDIATE", "type": "VERIFY",
            "title": "Verify independently before acting",
            "detail": (
                "We found no authoritative record to check this against, and no clear fraud "
                "indicators either. Confirm through the organisation's own app or website "
                "before you act on it -- not through any link in the message."
            ),
        })
    else:
        actions.append({
            "priority": "INFO", "type": "SAFE_TO_READ",
            "title": "This matches the official filing",
            "detail": (
                "Every check passed and the content matches what the company filed with the "
                "exchange. Note that genuine corporate notices never ask you to pay anything."
            ),
        })

    contact = official_contact_for(claimed_entity)
    if contact:
        actions.append({
            "priority": "HIGH", "type": "OFFICIAL_CONTACT",
            "title": f"Verified contact for {contact['entity']}",
            "detail": contact["caution"],
            "contact": contact,
        })

    if kind in (FRAUDULENT, TAMPERED):
        if money_sent:
            actions.append({
                "priority": "IMMEDIATE", "type": "REPORT",
                "title": "Report the loss now -- call 1930",
                "detail": OFFICIAL_CHANNELS["cybercrime"]["use_when"],
                "channel": OFFICIAL_CHANNELS["cybercrime"],
            })
        registered = bool(contact and contact.get("sebi_registration"))
        channel = OFFICIAL_CHANNELS["scores"] if registered else OFFICIAL_CHANNELS["sebi_takedown"]
        actions.append({
            "priority": "HIGH", "type": "REPORT",
            "title": f"Report to {channel['name']}",
            "detail": channel["use_when"],
            "channel": channel,
        })
        actions.append({
            "priority": "MEDIUM", "type": "SHARE",
            "title": "Warn the group this came from",
            "detail": (
                "Download the warning card and forward it to whoever sent you this. "
                "Fraud spreads by forwarding; the correction has to as well."
            ),
        })

    return actions


# --------------------------------------------------------------------------
# Prefilled reports
# --------------------------------------------------------------------------

def build_reports(
    verdict: Verdict,
    *,
    content_hash: str,
    claimed_entity: str | None = None,
    sender: str | None = None,
    domains: list[str] | None = None,
    upi_ids: list[str] | None = None,
    received_at: str | None = None,
) -> dict[str, Any]:
    """Prefilled report text, routed to the right destination."""
    now = received_at or datetime.now().isoformat(timespec="seconds")
    top = [r for r in verdict.reasons if r["severity"] >= 4][:6]
    evidence_lines = [f"  - [{r['severity']}] {r['code']}: {r['message']}" for r in top]

    body = textwrap.dedent(f"""\
        SUBJECT: Report of suspected securities-market fraud

        Verdict from automated verification: {verdict.verdict} (evidence score {verdict.confidence}/100)
        Assessed at: {now}
        Content fingerprint (SHA-256): {content_hash}

        Claimed sender / entity : {claimed_entity or 'not stated'}
        Sender address          : {sender or 'not available'}
        Domains referenced      : {', '.join(domains or []) or 'none'}
        Payment addresses       : {', '.join(upi_ids or []) or 'none'}

        Findings:
        {chr(10).join(evidence_lines) if evidence_lines else '  - No high-severity findings recorded.'}

        Summary: {verdict.summary}

        This report was generated by PhishermanAI. The content fingerprint allows this
        submission to be linked with other reports of the same material.
        """)

    registered = bool(official_contact_for(claimed_entity) or {})
    if verdict.verdict in (FRAUDULENT, TAMPERED):
        route = "scores" if registered else "sebi_takedown"
    else:
        route = "sebi_takedown"

    return {
        "recommended_route": route,
        "routes": {
            key: {**channel, "prefilled_text": body}
            for key, channel in OFFICIAL_CHANNELS.items()
        },
        "prefilled_text": body,
        "content_hash": content_hash,
    }


# --------------------------------------------------------------------------
# Shareable warning card
# --------------------------------------------------------------------------

CARD_W, CARD_H = 1080, 1080


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def build_warning_card(
    verdict: Verdict,
    *,
    claimed_entity: str | None = None,
    max_reasons: int = 3,
) -> bytes:
    """Render a square PNG summarising the verdict, sized for chat forwarding."""
    from PIL import Image, ImageDraw

    style = VERDICT_STYLE.get(verdict.verdict, VERDICT_STYLE[UNVERIFIED])
    colour = style["colour"]

    img = Image.new("RGB", (CARD_W, CARD_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Header band carrying the verdict colour.
    draw.rectangle([0, 0, CARD_W, 300], fill=colour)
    draw.text((60, 70), "PhishermanAI", font=_font(38), fill=(255, 255, 255))
    draw.text((60, 130), style["label"], font=_font(96, bold=True), fill=(255, 255, 255))
    draw.text((60, 240), f"Evidence score {verdict.confidence}/100",
              font=_font(30), fill=(255, 255, 255))

    y = 350
    if claimed_entity:
        draw.text((60, y), f"Claimed sender: {claimed_entity}"[:60],
                  font=_font(30, bold=True), fill=(30, 33, 40))
        y += 56

    for line in textwrap.wrap(verdict.summary, width=52)[:5]:
        draw.text((60, y), line, font=_font(34), fill=(30, 33, 40))
        y += 48

    y += 20
    draw.line([60, y, CARD_W - 60, y], fill=(220, 223, 230), width=2)
    y += 30

    draw.text((60, y), "WHY", font=_font(26, bold=True), fill=(110, 116, 130))
    y += 44

    # Measure each block BEFORE drawing it. Checking the cursor first and then
    # drawing up to three lines let the last reason overflow into the footer
    # band and get visually clipped mid-sentence.
    LINE_H = 38
    BLOCK_GAP = 22
    FOOTER_TOP = CARD_H - 190
    shown = 0

    for reason in verdict.reasons:
        if shown >= max_reasons:
            break
        if reason["severity"] < 3:
            continue

        lines = textwrap.wrap(reason["message"], width=46)[:3]
        if not lines:
            continue
        # Ellipsise rather than truncate silently, so a shortened reason reads
        # as shortened instead of as a sentence that stops for no reason.
        if len(textwrap.wrap(reason["message"], width=46)) > 3:
            lines[-1] = lines[-1].rstrip(" .,") + " ..."

        block_height = LINE_H * len(lines)
        if y + block_height > FOOTER_TOP - 20:
            break

        draw.ellipse([60, y + 10, 76, y + 26], fill=colour)
        for i, line in enumerate(lines):
            draw.text((94, y + (i * LINE_H)), line, font=_font(28), fill=(55, 60, 70))
        y += block_height + BLOCK_GAP
        shown += 1

    if shown == 0:
        draw.text((94, y), "No fraud indicators were found.", font=_font(28), fill=(55, 60, 70))

    # Footer: the action line and the honesty line.
    footer_y = CARD_H - 190
    draw.rectangle([0, footer_y, CARD_W, CARD_H], fill=(244, 246, 249))
    if verdict.verdict in (FRAUDULENT, TAMPERED):
        draw.text((60, footer_y + 32), "Do not pay. Do not click. Forward this warning.",
                  font=_font(30, bold=True), fill=(185, 28, 28))
    elif verdict.verdict == UNVERIFIED:
        draw.text((60, footer_y + 32), "Not confirmed either way -- verify before acting.",
                  font=_font(30, bold=True), fill=(90, 98, 112))
    else:
        draw.text((60, footer_y + 32), "Checks passed. Notices never ask you to pay.",
                  font=_font(30, bold=True), fill=(22, 138, 74))

    draw.text((60, footer_y + 84),
              "Report fraud: cybercrime.gov.in or call 1930",
              font=_font(26), fill=(90, 98, 112))
    draw.text((60, footer_y + 126),
              datetime.now().strftime("Checked %d %b %Y, %H:%M"),
              font=_font(22), fill=(140, 146, 158))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def content_fingerprint(text: str) -> str:
    from core.textnorm import canonical_hash_text
    return hashlib.sha256(canonical_hash_text(text).encode()).hexdigest()
