"""Forwarded messages as a first-class input.

FORWARDING IS THE PRIMARY USE CASE. Users do not paste suspicious mail into a
web form; they forward it. Getting this wrong means analysing the wrong sender,
and we did exactly that -- a genuine bank notice forwarded from a user's Gmail
fired INSTITUTIONAL_CLAIM_FROM_FREEMAIL against the user's own address.

Three shapes:

  ATTACHED  a message/rfc822 part is present. The original headers survive
            intact, including Authentication-Results, so the verdict is as good
            as for a directly received message.

  INLINE    the client quoted the original into the body under a
            "---------- Forwarded message ----------" marker. The original
            DKIM/SPF/DMARC results are GONE -- not failed, GONE. We recover the
            quoted From/Date/Subject and body, and mark authentication
            UNAVAILABLE. Reporting it as FAILED would be a lie about evidence
            we never had.

  DIRECT    neither.

On any forward, every rule that evaluates the OUTER envelope sender is
suppressed. The forwarder is the person asking us for help; they are not the
suspect.
"""

from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

ATTACHED = "ATTACHED"
INLINE = "INLINE"
DIRECT = "DIRECT"

MAX_UNWRAP_DEPTH = 5

# Body markers used by Gmail, Outlook, Apple Mail and Thunderbird.
INLINE_MARKERS = [
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}\s*$", re.I | re.M),
    re.compile(r"^Begin forwarded message:\s*$", re.I | re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}\s*$", re.I | re.M),
    re.compile(r"^_{5,}\s*$", re.M),          # Outlook's divider
]

SUBJECT_PREFIX = re.compile(r"^\s*(?:(?:Fwd?|FW|FWD|Wg|Rv|TR)\s*:\s*)+", re.I)

# A quoted header block inside the body. Leading '>' is tolerated because some
# clients quote the forwarded headers.
QUOTED_HEADER = re.compile(
    r"^\s*>*\s*(From|Sent|Date|To|Subject|Reply-To|Cc)\s*:\s*(.+)$", re.I | re.M
)

EMAIL_IN_TEXT = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass
class ForwardInfo:
    """What kind of forward this is, and what the original said."""

    forward_type: str = DIRECT
    depth: int = 0
    original_from: str | None = None
    original_from_domain: str | None = None
    original_subject: str | None = None
    original_date: str | None = None
    original_body: str = ""
    original_message: EmailMessage | None = None
    auth_available: bool = True
    forwarder_address: str | None = None
    forwarder_domain: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_forward(self) -> bool:
        return self.forward_type != DIRECT

    def to_dict(self) -> dict[str, Any]:
        return {
            "forward_type": self.forward_type,
            "depth": self.depth,
            "original_from": self.original_from,
            "original_from_domain": self.original_from_domain,
            "original_subject": self.original_subject,
            "original_date": self.original_date,
            "auth_available": self.auth_available,
            "forwarder_address": self.forwarder_address,
            "forwarder_domain": self.forwarder_domain,
            "notes": self.notes,
        }

    def user_message(self) -> str | None:
        """What to tell the user about verdict quality."""
        if not self.is_forward:
            return None
        target = self.original_from_domain or self.original_from or "the original sender"
        if self.forward_type == ATTACHED:
            return (
                f"You forwarded this as an attachment. We analysed the original message "
                f"from {target}, including its original security headers, so this verdict "
                "is as strong as if you had received the message directly."
            )
        return (
            f"You forwarded this. We analysed the original sender: {target}. "
            "Inline forwarding removes the original security headers, so we could not "
            "verify DKIM/SPF for that sender. For a stronger verdict, forward as an "
            "attachment (Gmail: three-dot menu -> Forward as attachment)."
        )


def _address_domain(address: str | None) -> str | None:
    if not address:
        return None
    from email.utils import parseaddr

    from core.textnorm import normalise_domain

    _, addr = parseaddr(address)
    if "@" not in addr:
        found = EMAIL_IN_TEXT.search(address)
        if not found:
            return None
        addr = found.group(0)
    return normalise_domain(addr.split("@")[-1]) or None


def _find_attached_rfc822(message: EmailMessage) -> EmailMessage | None:
    for part in message.walk():
        if part.get_content_type() == "message/rfc822":
            payload = part.get_payload()
            if isinstance(payload, list) and payload:
                inner = payload[0]
                if isinstance(inner, EmailMessage):
                    return inner
            raw = part.get_payload(decode=True)
            if raw:
                return email.message_from_bytes(raw, policy=email.policy.default)
    return None


def _body_text(message: EmailMessage) -> str:
    from core.ingest.email_parser import _decode_body

    text, _html = _decode_body(message)
    return text


def _parse_inline(body: str) -> tuple[dict[str, str], str] | None:
    """Recover quoted headers and the quoted body from an inline forward."""
    marker_pos = None
    for marker in INLINE_MARKERS:
        found = marker.search(body)
        if found and (marker_pos is None or found.start() < marker_pos):
            marker_pos = found.end()

    region = body[marker_pos:] if marker_pos is not None else body

    headers: dict[str, str] = {}
    last_header_end = 0
    for match in QUOTED_HEADER.finditer(region[:4000]):
        key = match.group(1).strip().lower()
        if key not in headers:
            headers[key] = match.group(2).strip()
        last_header_end = match.end()

    if "from" not in headers:
        return None

    return headers, region[last_header_end:].strip()


def detect(message: EmailMessage, *, depth: int = 0) -> ForwardInfo:
    """Classify a message and recover the original if it is a forward."""
    from email.utils import parseaddr

    info = ForwardInfo(depth=depth)
    _, forwarder = parseaddr(str(message.get("From", "") or ""))
    info.forwarder_address = forwarder or None
    info.forwarder_domain = _address_domain(forwarder)

    # --- ATTACHED: the strong case.
    inner = _find_attached_rfc822(message)
    if inner is not None and depth < MAX_UNWRAP_DEPTH:
        nested = detect(inner, depth=depth + 1)
        if nested.is_forward and nested.original_message is not None:
            # Recursively unwrapped to the innermost original.
            nested.forwarder_address = info.forwarder_address
            nested.forwarder_domain = info.forwarder_domain
            nested.notes.append(f"unwrapped {nested.depth} nested forward(s)")
            return nested

        _, original_from = parseaddr(str(inner.get("From", "") or ""))
        info.forward_type = ATTACHED
        info.original_message = inner
        info.original_from = original_from or None
        info.original_from_domain = _address_domain(original_from)
        info.original_subject = str(inner.get("Subject", "") or "")
        info.original_date = str(inner.get("Date", "") or "") or None
        info.original_body = _body_text(inner)
        # Original headers survived, so authentication is genuinely available.
        info.auth_available = bool(inner.get_all("Authentication-Results"))
        if not info.auth_available:
            info.notes.append("attached original carried no Authentication-Results header")
        return info

    # --- INLINE
    body = _body_text(message)
    subject = str(message.get("Subject", "") or "")
    has_marker = any(m.search(body) for m in INLINE_MARKERS)
    has_prefix = bool(SUBJECT_PREFIX.match(subject))

    if has_marker or has_prefix:
        parsed = _parse_inline(body)
        if parsed is not None:
            headers, quoted_body = parsed
            info.forward_type = INLINE
            info.original_from = headers.get("from")
            info.original_from_domain = _address_domain(headers.get("from"))
            info.original_subject = headers.get("subject") or SUBJECT_PREFIX.sub("", subject).strip()
            info.original_date = headers.get("date") or headers.get("sent")
            info.original_body = quoted_body or body
            # THE IMPORTANT LINE: the original's DKIM/SPF/DMARC are gone, not failed.
            info.auth_available = False
            info.notes.append("inline forward: original authentication headers not preserved")
            return info

        if has_prefix:
            # Subject says Fwd: but we could not find a quoted header block.
            info.forward_type = INLINE
            info.original_subject = SUBJECT_PREFIX.sub("", subject).strip()
            info.original_body = body
            info.auth_available = False
            info.notes.append("forward detected from subject prefix; original headers not recoverable")
            return info

    return info


def detect_raw(raw: bytes | str) -> ForwardInfo:
    """Detect forwarding from raw RFC822 bytes.

    The pipeline holds a parsed `ParsedEmail` dataclass rather than the
    stdlib `EmailMessage` this module needs, so it re-parses here. Cheap, and
    it keeps `ParsedEmail` free of a stdlib object it has no other use for.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    try:
        message = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception:  # noqa: BLE001 - unparseable input is simply not a forward
        return ForwardInfo()
    return detect(message)


def analysis_text(info: ForwardInfo, fallback: str) -> str:
    """The text that should actually be analysed."""
    if info.is_forward and info.original_body:
        header_line = " ".join(
            part for part in (info.original_from, info.original_subject) if part
        )
        return f"{header_line}\n\n{info.original_body}".strip()
    return fallback
