"""Onward delivery after verification.

Three modes:

  MAILDIR   write into a local Maildir. The default, and the one the demo uses:
            no network, no downstream MTA, works with the cable unplugged.
  SMTP      hand off to a downstream host:port -- the real deployment shape,
            where this gateway sits in front of an existing mail server.
  DISCARD   verify and log only. For load testing without filling a disk.

Delivery failures are reported, never swallowed, but they also never raise into
the SMTP handler: the handler decides what to tell the sending client.
"""

from __future__ import annotations

import logging
import mailbox
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from gateway.config import RELAY_DISCARD, RELAY_MAILDIR, RELAY_SMTP, GatewayConfig

log = logging.getLogger("phishermanai.gateway.relay")


def _ensure_maildir(path: Path) -> None:
    """Create the maildir and its tmp/new/cur subdirectories.

    `mailbox.Maildir(create=True)` only creates the subdirectories when the root
    does NOT already exist -- it takes an existing directory as an already-valid
    maildir and creates nothing. Anything that makes the directory first (a
    mkdir, tempfile.mkdtemp, a mounted volume, a git checkout) therefore yields
    a maildir with no tmp/, and every delivery fails with FileNotFoundError on
    a path inside it.

    Creating all three explicitly is correct whether or not the root exists.
    """
    path.mkdir(parents=True, exist_ok=True)
    for sub in ("tmp", "new", "cur"):
        (path / sub).mkdir(exist_ok=True)


@dataclass
class RelayResult:
    ok: bool
    mode: str
    destination: str | None = None
    error: str | None = None


def deliver(
    message: EmailMessage,
    raw: bytes,
    config: GatewayConfig,
    *,
    mail_from: str = "",
    rcpt_tos: list[str] | None = None,
) -> RelayResult:
    mode = config.relay_mode

    if mode == RELAY_DISCARD:
        return RelayResult(ok=True, mode=mode, destination=None)

    if mode == RELAY_MAILDIR:
        try:
            path = config.maildir_abspath
            _ensure_maildir(path)
            box = mailbox.Maildir(str(path), create=True)
            key = box.add(raw)
            box.close()
            return RelayResult(ok=True, mode=mode, destination=f"{path}/{key}")
        except Exception as exc:  # noqa: BLE001
            log.error("maildir delivery failed: %s", exc)
            return RelayResult(ok=False, mode=mode, error=f"{type(exc).__name__}: {exc}")

    if mode == RELAY_SMTP:
        try:
            with smtplib.SMTP(config.relay_host, config.relay_port, timeout=15) as client:
                client.sendmail(mail_from or "", rcpt_tos or [], raw)
            return RelayResult(
                ok=True, mode=mode,
                destination=f"{config.relay_host}:{config.relay_port}",
            )
        except Exception as exc:  # noqa: BLE001
            log.error("smtp relay failed: %s", exc)
            return RelayResult(ok=False, mode=mode, error=f"{type(exc).__name__}: {exc}")

    return RelayResult(ok=False, mode=mode, error=f"unknown relay mode {mode!r}")


def read_maildir(config: GatewayConfig, limit: int = 50) -> list[dict]:
    """Read back delivered messages. Used by send_fixtures and the tests."""
    path = config.maildir_abspath
    if not path.exists():
        return []
    box = mailbox.Maildir(str(path), create=False)
    out = []
    for key in list(box.keys())[-limit:]:
        msg = box[key]
        out.append({
            "key": key,
            "subject": msg.get("Subject"),
            "from": msg.get("From"),
            "to": msg.get("To"),
            "message_id": msg.get("Message-ID"),
            "headers": {k: v for k, v in msg.items() if k.lower().startswith("x-")},
        })
    box.close()
    return out
