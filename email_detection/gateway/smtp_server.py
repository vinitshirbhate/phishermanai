"""The receiving SMTP gateway.

    sender -> [this gateway] -> verify -> stamp headers -> relay -> mailbox

This is a RECEIVING server, not a client: mail is delivered TO us, we verify it
and hand it onward. Deployed by a broker, listed company or RTA in front of
their existing mail infrastructure, so investors get the check automatically
with no action of their own.

FAILURE POLICY -- the single most important behaviour here
----------------------------------------------------------
Mail is delivered even when verification fails. Engine down, engine timeout,
malformed message, storage error: the message still goes to the mailbox, marked
UNVERIFIED with an X-...-Error explaining why. The only things we refuse
outright are abuse controls -- a recipient we do not serve (550), an oversized
message (552), or a flood (421) -- and those are refusals at RCPT/DATA time, so
the sending server retries or reports rather than silently losing the mail.

A security tool that eats mail gets switched off, and then it protects nobody.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from email.utils import parseaddr
from typing import Any

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Envelope, Session

from gateway import store
from gateway.config import GatewayConfig, load_config
from gateway.relay import deliver
from gateway.stamping import get_message_id, parse_message, serialise, stamp
from gateway.verify_client import verify_raw_email

log = logging.getLogger("phishermanai.gateway")


class RateLimiter:
    """Sliding-window limit per connecting IP."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, ip: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        window = self._hits[ip]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        return True


class VerifyingHandler:
    """aiosmtpd handler: verify, stamp, relay."""

    def __init__(self, config: GatewayConfig):
        self.config = config
        self.limiter = RateLimiter(config.rate_limit_per_min)
        self.processed = 0
        self.results: list[dict[str, Any]] = []

    # -- RCPT: allowlist ---------------------------------------------------
    async def handle_RCPT(
        self, server: SMTP, session: Session, envelope: Envelope,
        address: str, rcpt_options: list[str],
    ) -> str:
        if not self.config.recipient_allowed(address):
            # Refusing unknown recipients is what stops this being an open
            # relay. Without it, anyone could use the gateway to send mail
            # anywhere and our IP would carry the blame.
            log.warning("rejected RCPT for non-allowlisted recipient %s", address)
            return "550 5.7.1 Recipient not served by this gateway"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    # -- DATA: the work ----------------------------------------------------
    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:
        started = time.perf_counter()

        peer_ip = (session.peer[0] if session.peer else "unknown")
        if not self.limiter.allow(peer_ip):
            log.warning("rate limit exceeded for %s", peer_ip)
            return "421 4.7.0 Too many messages, slow down"

        # envelope.content is the RAW RFC822 bytes exactly as received. We pass
        # these to the engine unchanged, because the upstream provider's
        # Authentication-Results header is our DKIM/SPF/DMARC evidence and
        # rebuilding the message could reorder or drop it.
        raw: bytes = envelope.content or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")

        if len(raw) > self.config.max_size_bytes:
            log.warning("rejected oversized message (%d bytes) from %s", len(raw), peer_ip)
            return f"552 5.3.4 Message exceeds {self.config.max_size_mb} MB limit"

        mail_from = envelope.mail_from or ""
        rcpt_tos = list(envelope.rcpt_tos or [])

        try:
            message = parse_message(raw)
        except Exception as exc:  # noqa: BLE001
            # A message we cannot even parse is still delivered. Refusing it
            # would lose mail on our own parser's shortcomings.
            log.warning("unparseable message from %s (%s) - delivering as-is", peer_ip, exc)
            deliver_result = deliver(None, raw, self.config, mail_from=mail_from, rcpt_tos=rcpt_tos)
            self._record_result(
                message_id="<unparseable>", mail_from=mail_from, rcpt_tos=rcpt_tos,
                verdict_name="UNVERIFIED", confidence=0, subject="",
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"unparseable:{type(exc).__name__}", relayed=deliver_result.ok,
            )
            return "250 Message accepted (unverified: could not parse)"

        message_id, synthesised = get_message_id(message, raw, self.config.hostname)

        # Dedup: an SMTP retry or a second allowlisted recipient must not cause
        # a second verification.
        verdict = store.cached_verdict(message_id)
        if verdict is not None:
            log.info("cache hit for %s", message_id)
        else:
            verdict = await asyncio.to_thread(
                verify_raw_email,
                raw,
                endpoint=self.config.verify_endpoint,
                timeout=self.config.engine_timeout,
            )

        stamped = stamp(
            message, verdict,
            prefix=self.config.header_prefix,
            subject_tagging=self.config.subject_tagging,
            message_id=message_id,
        )

        if stamped["forged_headers_removed"]:
            log.warning(
                "stripped forged verdict headers %s from %s",
                stamped["forged_headers_removed"], message_id,
            )

        outgoing = serialise(message)
        relay_result = deliver(
            message, outgoing, self.config, mail_from=mail_from, rcpt_tos=rcpt_tos,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)

        if not verdict.cached:
            store.record(
                verdict,
                message_id=message_id,
                from_addr=parseaddr(str(message.get("From", "")))[1] or mail_from,
                to_addr=",".join(rcpt_tos),
                subject_original=stamped["original_subject"],
                content_hash=verdict.content_hash or "",
                latency_ms=latency_ms,
            )

        self._record_result(
            message_id=message_id, mail_from=mail_from, rcpt_tos=rcpt_tos,
            verdict_name=verdict.verdict, confidence=verdict.confidence,
            subject=stamped["original_subject"], latency_ms=latency_ms,
            error=verdict.error, relayed=relay_result.ok, cached=verdict.cached,
            synthesised_id=synthesised,
        )

        # Structured log line. Never the body -- envelope and verdict only.
        log.info(
            "verdict=%s confidence=%s msgid=%s from=%s to=%s latency=%sms "
            "relay=%s cached=%s%s",
            verdict.verdict, verdict.confidence, message_id, mail_from,
            ",".join(rcpt_tos), latency_ms, relay_result.mode, verdict.cached,
            f" error={verdict.error}" if verdict.error else "",
        )

        self.processed += 1
        if not relay_result.ok:
            # We verified but could not hand off. Tell the sender to retry
            # rather than pretend we delivered it.
            return f"451 4.3.0 Verified but delivery failed: {relay_result.error}"
        return "250 Message accepted for delivery"

    def _record_result(self, **kwargs: Any) -> None:
        """In-memory trace, used by send_fixtures and the tests."""
        self.results.append(kwargs)
        if len(self.results) > 500:
            self.results = self.results[-500:]


class GatewayController(Controller):
    """Controller pinned to the configured host/port."""

    def __init__(self, handler: VerifyingHandler, config: GatewayConfig):
        super().__init__(
            handler,
            hostname=config.host,
            port=config.port,
            data_size_limit=config.max_size_bytes,
        )
        self.config = config


def build(config: GatewayConfig | None = None) -> tuple[GatewayController, VerifyingHandler]:
    config = config or load_config()
    handler = VerifyingHandler(config)
    return GatewayController(handler, config), handler
