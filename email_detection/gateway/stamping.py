"""Write the verdict into the message, without disturbing anything else.

Two things here are security-relevant rather than cosmetic.

1. INBOUND VERDICT HEADERS ARE STRIPPED FIRST.
   Anyone can put `X-PhishermanAI-Verdict: GENUINE` in a message they send.
   If we only ever appended, a downstream Gmail filter keying on that header
   would trust the attacker's copy -- the message would arrive carrying both a
   forged GENUINE and our real FRAUDULENT, and which one a client matches is
   undefined. So every header with our prefix is removed before ours is added.
   Both the current prefix and the legacy "X-SatyaCheck" prefix are stripped
   regardless of which one is configured, so changing `header_prefix` can never
   leave a stale prefix an attacker could forge into.

2. THE ORIGINAL MESSAGE IS PRESERVED BYTE-FOR-BYTE BELOW THE HEADERS.
   We parse with `email.policy.default`, mutate only headers, and re-serialise.
   MIME structure, attachments, encodings and the body are untouched, because
   re-encoding a signed or multipart message can invalidate it.
"""

from __future__ import annotations

import email
import email.policy
import hashlib
import re
from email.header import decode_header, make_header
from email.message import EmailMessage
from typing import Any

from gateway.verify_client import GatewayVerdict

HEADER_VERSION = "1.0"

# Always stripped, whatever prefix is configured. Order does not matter.
KNOWN_PREFIXES = ("x-phishermanai", "x-satyacheck")

SUBJECT_TAGS = {
    "FRAUDULENT": "[!! FRAUD] ",
    "TAMPERED": "[!! ALTERED] ",
    # "NOT VERIFIED" rather than "UNVERIFIED": the tag lands in the recipient's
    # inbox on ordinary mail from any sender outside our registry, which is most
    # legitimate senders. It should read as "we could not confirm this", not as
    # a mark against the sender.
    "UNVERIFIED": "[? NOT VERIFIED] ",
    "GENUINE": "",          # no tag: normal mail must stay uncluttered
}

MAX_REASONS_IN_HEADER = 5


def parse_message(raw: bytes) -> EmailMessage:
    """Parse raw bytes into an EmailMessage, tolerating malformed input."""
    return email.message_from_bytes(raw, policy=email.policy.default)


def strip_verdict_headers(message: EmailMessage) -> list[str]:
    """Remove every inbound header claiming to be one of ours.

    Returns the names removed, so the caller can log an attempted spoof.
    """
    removed: list[str] = []
    for name in list(message.keys()):
        lowered = name.lower()
        if any(lowered.startswith(prefix) for prefix in KNOWN_PREFIXES):
            removed.append(name)
    for name in removed:
        del message[name]
    return removed


def decode_subject(message: EmailMessage) -> str:
    """Decode an RFC 2047 subject to plain text. Never raises."""
    raw = message.get("Subject")
    if raw is None:
        return ""
    try:
        return str(make_header(decode_header(str(raw))))
    except Exception:  # noqa: BLE001 - a malformed subject must not lose the mail
        return str(raw)


def tag_subject(message: EmailMessage, verdict: str) -> tuple[str, str]:
    """Prepend a visible verdict tag. Returns (original, new).

    RFC 2047 matters here: a subject such as
    "=?utf-8?B?4KS44KWC4KSa4KSo4KS special?=" must be decoded before the tag is
    prepended and re-encoded afterwards, otherwise the tag lands inside the
    encoded word and the whole subject renders as mojibake.
    """
    original = decode_subject(message)
    tag = SUBJECT_TAGS.get(verdict, "")
    if not tag:
        return original, original

    tagged = f"{tag}{original}"
    del message["Subject"]
    # Assign the DECODED unicode string and let email.policy.default handle
    # RFC 2047 encoding and folding at serialisation time.
    #
    # The obvious alternative, `Header(tagged, "utf-8").encode()`, is wrong
    # here: it returns a header already folded across multiple lines, and
    # policy.default rejects any assigned value containing a newline
    # ("Header values may not contain linefeed or carriage return characters").
    # That crashed on long non-ASCII subjects -- exactly the ones that need
    # encoding most.
    message["Subject"] = tagged
    return original, tagged


def synthesise_message_id(raw: bytes, hostname: str = "phishermanai.gateway.local") -> str:
    """A stable Message-ID for mail that arrived without one.

    Content-derived rather than random, so a retransmission of the same bytes
    produces the same id and still hits the dedup cache.
    """
    digest = hashlib.sha256(raw).hexdigest()[:32]
    return f"<{digest}@{hostname}>"


def get_message_id(message: EmailMessage, raw: bytes, hostname: str) -> tuple[str, bool]:
    """(message_id, was_synthesised)."""
    existing = message.get("Message-ID")
    if existing:
        value = str(existing).strip()
        if value:
            return value, False
    return synthesise_message_id(raw, hostname), True


def stamp(
    message: EmailMessage,
    verdict: GatewayVerdict,
    *,
    prefix: str = "X-PhishermanAI",
    subject_tagging: bool = True,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Strip forged headers, add ours, optionally tag the subject.

    Mutates `message` in place. Returns a summary for logging.
    """
    forged = strip_verdict_headers(message)

    message[f"{prefix}-Verdict"] = verdict.verdict
    message[f"{prefix}-Confidence"] = str(verdict.confidence)

    if verdict.reason_codes:
        message[f"{prefix}-Reasons"] = ";".join(verdict.reason_codes[:MAX_REASONS_IN_HEADER])

    message[f"{prefix}-Checks"] = verdict.checks_header

    filing = verdict.filing_header
    if filing:
        message[f"{prefix}-Filing"] = filing

    if verdict.verification_id:
        message[f"{prefix}-Id"] = str(verdict.verification_id)
    elif message_id:
        message[f"{prefix}-Id"] = hashlib.sha256(message_id.encode()).hexdigest()[:16]

    message[f"{prefix}-Version"] = HEADER_VERSION

    if not verdict.ok and verdict.error:
        message[f"{prefix}-Error"] = verdict.error

    if forged:
        # Record the attempt rather than discarding it silently: an operator
        # seeing this header knows someone tried to forge a verdict.
        message[f"{prefix}-Stripped"] = ";".join(sorted(set(forged)))[:400]

    original_subject = decode_subject(message)
    tagged_subject = original_subject
    if subject_tagging:
        original_subject, tagged_subject = tag_subject(message, verdict.verdict)

    return {
        "forged_headers_removed": forged,
        "original_subject": original_subject,
        "tagged_subject": tagged_subject,
    }


def serialise(message: EmailMessage) -> bytes:
    """Back to bytes for relay, preserving structure."""
    try:
        return message.as_bytes()
    except Exception:  # noqa: BLE001 - fall back rather than lose the message
        return message.as_string().encode("utf-8", "replace")
