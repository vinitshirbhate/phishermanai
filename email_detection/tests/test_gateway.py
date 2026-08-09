"""Tests for the SMTP verification gateway.

The behaviour these exist to protect, in order of importance:

  1. MAIL IS NEVER LOST. Engine down, engine timeout, engine returning
     nonsense, message unparseable -- the message is still delivered, marked
     UNVERIFIED. Three tests cover this and they are the ones to keep working.
  2. VERDICT HEADERS CANNOT BE FORGED. An inbound X-...-Verdict: GENUINE is
     stripped and replaced with ours.
  3. THE GATEWAY IS NOT AN OPEN RELAY. Non-allowlisted recipients get 550.

Tests run against a real aiosmtpd instance on an ephemeral port, with the
verification engine stubbed at the HTTP boundary. Stubbing there rather than
mocking internals means the gateway's real request/response handling is
exercised -- including its failure paths.
"""

from __future__ import annotations

import email
import email.policy
import smtplib
import socket
import tempfile
import time
from email.header import Header
from email.message import EmailMessage
from pathlib import Path

import pytest

from gateway.config import load_config
from gateway.relay import _ensure_maildir, read_maildir
from gateway.send_fixtures import to_crlf
from gateway.smtp_server import RateLimiter, build
from gateway.stamping import (
    SUBJECT_TAGS,
    decode_subject,
    get_message_id,
    parse_message,
    stamp,
    strip_verdict_headers,
    synthesise_message_id,
    tag_subject,
)
from gateway.verify_client import GatewayVerdict, verify_raw_email

FIXTURES = Path(__file__).resolve().parent.parent / "eval" / "fixtures"


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class StubEngine:
    """Stands in for POST /verify/email at the HTTP boundary."""

    def __init__(self, verdict="GENUINE", confidence=90, behaviour="ok"):
        self.verdict = verdict
        self.confidence = confidence
        self.behaviour = behaviour        # ok | timeout | unreachable | http500 | garbage
        self.calls = 0

    def __call__(self, url, files=None, data=None, timeout=None, **kwargs):
        import requests

        self.calls += 1
        if self.behaviour == "timeout":
            raise requests.Timeout("stub timeout")
        if self.behaviour == "unreachable":
            raise requests.ConnectionError("stub connection refused")

        class Response:
            pass

        response = Response()
        if self.behaviour == "http500":
            response.status_code = 500
            response.json = lambda: {}
            return response
        if self.behaviour == "garbage":
            response.status_code = 200
            def _boom():
                raise ValueError("not json")
            response.json = _boom
            return response

        response.status_code = 200
        response.json = lambda: {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "summary": "stub summary",
            "reasons": [
                {"code": "REASON_ONE", "severity": 5},
                {"code": "REASON_TWO", "severity": 4},
            ],
            "checks": {
                "MONEY": {"passed": True}, "ENTITY": {"passed": True},
                "CLAIM": {"passed": False}, "DELIVERY": {"passed": None},
            },
            "matched_filing": {"filing_id": 42, "exchange": "BSE",
                               "filing_date": "2026-07-10T00:00:00", "tier": "STRUCTURED"},
            "verification_id": "777",
            "content_hash": "abc123",
        }
        return response


@pytest.fixture
def gateway(monkeypatch, tmp_path):
    """A running gateway with a stubbed engine. Yields (send, handler, stub, maildir)."""
    stub = StubEngine()
    monkeypatch.setattr("gateway.verify_client.requests.post", stub)
    # Dedup must not leak between tests via the shared database.
    monkeypatch.setattr("gateway.store.cached_verdict", lambda mid: None)
    monkeypatch.setattr("gateway.store.record", lambda *a, **k: 1)

    port = _free_port()
    maildir = tmp_path / "maildir"
    config = load_config(
        host="127.0.0.1", port=port, relay_mode="maildir",
        maildir_path=str(maildir),
        recipient_allowlist=["@example.com", "demo@local"],
    )
    controller, handler = build(config)
    controller.start()

    def send(raw: bytes, to="investor@example.com", frm="sender@example.net"):
        with smtplib.SMTP("127.0.0.1", port, timeout=20) as client:
            return client.sendmail(frm, [to], to_crlf(raw))

    try:
        yield send, handler, stub, maildir, config
    finally:
        controller.stop()


def _simple_message(subject="Test message", body="Hello", extra_headers=None) -> bytes:
    msg = EmailMessage()
    msg["From"] = "Sender <sender@example.net>"
    msg["To"] = "investor@example.com"
    msg["Subject"] = subject
    msg["Message-ID"] = "<test-001@example.net>"
    for k, v in (extra_headers or {}).items():
        msg[k] = v
    msg.set_content(body)
    return msg.as_bytes()


def _delivered(maildir: Path) -> list[EmailMessage]:
    out = []
    new_dir = maildir / "new"
    if not new_dir.exists():
        return out
    for path in sorted(new_dir.iterdir()):
        out.append(email.message_from_bytes(path.read_bytes(), policy=email.policy.default))
    return out


# ==========================================================================
# 1. Core verdict flow
# ==========================================================================

class TestVerdictFlow:
    def test_genuine_delivered_untagged_with_headers(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.verdict, stub.confidence = "GENUINE", 88
        send(_simple_message(subject="Dividend intimation"))

        messages = _delivered(maildir)
        assert len(messages) == 1
        msg = messages[0]
        assert msg["X-PhishermanAI-Verdict"] == "GENUINE"
        assert msg["X-PhishermanAI-Confidence"] == "88"
        assert msg["X-PhishermanAI-Version"] == "1.0"
        # GENUINE must not clutter the subject.
        assert decode_subject(msg) == "Dividend intimation"

    def test_fraudulent_is_tagged(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.verdict = "FRAUDULENT"
        send(_simple_message(subject="Claim your dividend"))
        msg = _delivered(maildir)[0]
        assert msg["X-PhishermanAI-Verdict"] == "FRAUDULENT"
        assert decode_subject(msg).startswith("[!! FRAUD] ")

    def test_tampered_is_tagged_and_carries_reasons(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.verdict = "TAMPERED"
        send(_simple_message())
        msg = _delivered(maildir)[0]
        assert decode_subject(msg).startswith("[!! ALTERED] ")
        assert "REASON_ONE" in msg["X-PhishermanAI-Reasons"]

    def test_checks_header_format(self, gateway):
        send, handler, stub, maildir, config = gateway
        send(_simple_message())
        msg = _delivered(maildir)[0]
        assert msg["X-PhishermanAI-Checks"] == "MONEY=pass;ENTITY=pass;CLAIM=fail;DELIVERY=na"

    def test_filing_header_present_when_matched(self, gateway):
        send, handler, stub, maildir, config = gateway
        send(_simple_message())
        msg = _delivered(maildir)[0]
        assert "id=42" in msg["X-PhishermanAI-Filing"]
        assert "BSE" in msg["X-PhishermanAI-Filing"]


# ==========================================================================
# 2. NEVER FAIL CLOSED  -- the most important tests here
# ==========================================================================

class TestNeverFailClosed:
    def test_engine_unreachable_still_delivers(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.behaviour = "unreachable"
        send(_simple_message(subject="Important notice"))

        messages = _delivered(maildir)
        assert len(messages) == 1, "message was LOST when the engine was down"
        msg = messages[0]
        assert msg["X-PhishermanAI-Verdict"] == "UNVERIFIED"
        assert "engine_unreachable" in msg["X-PhishermanAI-Error"]
        # Tag wording is asserted via SUBJECT_TAGS rather than a literal, so
        # rewording the label for users does not break the behavioural test.
        # What matters here is that the message was DELIVERED and visibly
        # marked, not the exact adjective.
        assert decode_subject(msg).startswith(SUBJECT_TAGS["UNVERIFIED"])

    def test_engine_timeout_still_delivers(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.behaviour = "timeout"
        send(_simple_message())

        messages = _delivered(maildir)
        assert len(messages) == 1, "message was LOST on engine timeout"
        assert messages[0]["X-PhishermanAI-Verdict"] == "UNVERIFIED"
        assert "timeout" in messages[0]["X-PhishermanAI-Error"]

    def test_engine_http_error_still_delivers(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.behaviour = "http500"
        send(_simple_message())
        messages = _delivered(maildir)
        assert len(messages) == 1
        assert messages[0]["X-PhishermanAI-Verdict"] == "UNVERIFIED"
        assert "engine_http_500" in messages[0]["X-PhishermanAI-Error"]

    def test_engine_garbage_response_still_delivers(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.behaviour = "garbage"
        send(_simple_message())
        assert len(_delivered(maildir)) == 1

    def test_malformed_message_still_delivered(self, gateway):
        send, handler, stub, maildir, config = gateway
        # Truncated headers, no body separator, bare 8-bit bytes.
        raw = b"From: broken@example.net\r\nSubject: truncated"
        send(raw)
        assert len(_delivered(maildir)) == 1, "malformed message was lost"

    def test_verify_client_never_raises(self):
        """Direct unit check on the client's contract."""
        verdict = verify_raw_email(
            b"From: a@b\r\n\r\nx",
            endpoint="http://127.0.0.1:9/nonexistent",   # port 9 = discard
            timeout=0.5,
        )
        assert isinstance(verdict, GatewayVerdict)
        assert verdict.ok is False
        assert verdict.verdict == "UNVERIFIED"


# ==========================================================================
# 3. Spoofing defence
# ==========================================================================

class TestForgedHeaders:
    def test_forged_verdict_header_is_stripped_and_replaced(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.verdict = "FRAUDULENT"
        raw = _simple_message(extra_headers={
            "X-PhishermanAI-Verdict": "GENUINE",
            "X-PhishermanAI-Confidence": "100",
        })
        send(raw)

        msg = _delivered(maildir)[0]
        verdicts = msg.get_all("X-PhishermanAI-Verdict")
        assert verdicts == ["FRAUDULENT"], f"forged header survived: {verdicts}"
        assert msg.get_all("X-PhishermanAI-Confidence") == ["0"] or \
               msg["X-PhishermanAI-Confidence"] != "100"
        assert "X-PhishermanAI-Verdict" in (msg["X-PhishermanAI-Stripped"] or "")

    def test_legacy_prefix_also_stripped(self):
        """Both prefixes go, whichever is configured, so a rename cannot open a gap."""
        msg = parse_message(_simple_message(extra_headers={
            "X-SatyaCheck-Verdict": "GENUINE",
            "X-PhishermanAI-Verdict": "GENUINE",
        }))
        removed = strip_verdict_headers(msg)
        assert len(removed) == 2
        assert msg["X-SatyaCheck-Verdict"] is None
        assert msg["X-PhishermanAI-Verdict"] is None


# ==========================================================================
# 4. Abuse controls
# ==========================================================================

class TestAbuseControls:
    def test_non_allowlisted_recipient_rejected_550(self, gateway):
        send, handler, stub, maildir, config = gateway
        with pytest.raises(smtplib.SMTPRecipientsRefused) as excinfo:
            send(_simple_message(), to="stranger@elsewhere.org")
        code = list(excinfo.value.recipients.values())[0][0]
        assert code == 550
        assert _delivered(maildir) == [], "message for a non-allowlisted recipient was relayed"

    def test_oversized_message_rejected_552(self, gateway, monkeypatch):
        send, handler, stub, maildir, config = gateway
        handler.config.max_size_mb = 0.001          # ~1 KB
        big = _simple_message(body="x" * 50_000)
        with pytest.raises(smtplib.SMTPResponseException) as excinfo:
            send(big)
        assert excinfo.value.smtp_code in (552, 500, 523)

    def test_rate_limiter_blocks_after_threshold(self):
        limiter = RateLimiter(per_minute=3)
        assert [limiter.allow("1.2.3.4") for _ in range(3)] == [True, True, True]
        assert limiter.allow("1.2.3.4") is False
        # A different peer is unaffected.
        assert limiter.allow("5.6.7.8") is True

    def test_rate_limiter_disabled_when_zero(self):
        limiter = RateLimiter(per_minute=0)
        assert all(limiter.allow("1.2.3.4") for _ in range(500))

    def test_empty_allowlist_denies_everything(self):
        config = load_config(recipient_allowlist=[])
        assert config.recipient_allowed("anyone@anywhere.com") is False

    def test_domain_allowlist_entry(self):
        config = load_config(recipient_allowlist=["@example.com"])
        assert config.recipient_allowed("a@example.com") is True
        assert config.recipient_allowed("a@notexample.com") is False


# ==========================================================================
# 5. Message identity and structure
# ==========================================================================

class TestMessageHandling:
    def test_rfc2047_subject_tagged_and_still_decodable(self, gateway):
        send, handler, stub, maildir, config = gateway
        stub.verdict = "FRAUDULENT"
        original = "सूचना: लाभांश भुगतान"          # Devanagari
        raw = _simple_message(subject=original)
        # Confirm we really are exercising the encoded-word path: policy.default
        # emits the subject as RFC 2047 on the wire.
        assert b"=?utf-8?" in raw

        send(raw)

        msg = _delivered(maildir)[0]
        decoded = decode_subject(msg)
        assert decoded.startswith("[!! FRAUD] ")
        assert original in decoded, f"non-ASCII subject was mangled: {decoded!r}"
        # And it must still be encoded on the wire, not emitted as raw 8-bit.
        delivered_raw = (maildir / "new").iterdir().__next__().read_bytes()
        assert b"=?utf-8?" in delivered_raw

    def test_multipart_structure_preserved(self, gateway):
        send, handler, stub, maildir, config = gateway
        msg = EmailMessage()
        msg["From"] = "sender@example.net"
        msg["To"] = "investor@example.com"
        msg["Subject"] = "With attachment"
        msg["Message-ID"] = "<mp-1@example.net>"
        msg.set_content("See attached.")
        payload = b"%PDF-1.4 fake pdf bytes \x00\x01\x02"
        msg.add_attachment(payload, maintype="application", subtype="pdf",
                           filename="notice.pdf")
        send(msg.as_bytes())

        delivered = _delivered(maildir)[0]
        assert delivered.is_multipart()
        parts = [p for p in delivered.walk()
                 if p.get_content_disposition() == "attachment"]
        assert len(parts) == 1
        assert parts[0].get_filename() == "notice.pdf"
        assert parts[0].get_payload(decode=True) == payload, "attachment bytes changed"

    def test_missing_message_id_is_synthesised_stably(self):
        raw = b"From: a@b.com\r\nSubject: no id\r\n\r\nbody\r\n"
        msg = parse_message(raw)
        first, synthesised = get_message_id(msg, raw, "gw.local")
        assert synthesised is True
        assert first.startswith("<") and first.endswith("@gw.local>")
        # Stable: same bytes, same id, so a retry still hits the dedup cache.
        assert get_message_id(parse_message(raw), raw, "gw.local")[0] == first
        assert synthesise_message_id(b"different", "gw.local") != first

    def test_existing_message_id_preserved(self):
        raw = _simple_message()
        msg = parse_message(raw)
        message_id, synthesised = get_message_id(msg, raw, "gw.local")
        assert synthesised is False
        assert message_id == "<test-001@example.net>"

    def test_original_headers_preserved(self, gateway):
        send, handler, stub, maildir, config = gateway
        raw = _simple_message(extra_headers={"X-Custom-Tracking": "keep-me",
                                             "Reply-To": "replies@example.net"})
        send(raw)
        msg = _delivered(maildir)[0]
        assert msg["X-Custom-Tracking"] == "keep-me"
        assert msg["Reply-To"] == "replies@example.net"
        assert msg["Message-ID"] == "<test-001@example.net>"


# ==========================================================================
# 6. Dedup
# ==========================================================================

class TestDedup:
    def test_duplicate_message_id_reuses_cached_verdict(self, monkeypatch, tmp_path):
        stub = StubEngine()
        monkeypatch.setattr("gateway.verify_client.requests.post", stub)

        cache: dict[str, GatewayVerdict] = {}
        monkeypatch.setattr("gateway.store.cached_verdict", lambda mid: cache.get(mid))

        def fake_record(verdict, *, message_id, **kwargs):
            cache[message_id] = GatewayVerdict(
                verdict=verdict.verdict, confidence=verdict.confidence, cached=True,
            )
            return 1
        monkeypatch.setattr("gateway.store.record", fake_record)

        port = _free_port()
        config = load_config(
            host="127.0.0.1", port=port, relay_mode="maildir",
            maildir_path=str(tmp_path / "md"),
            recipient_allowlist=["@example.com"],
        )
        controller, handler = build(config)
        controller.start()
        try:
            raw = to_crlf(_simple_message())
            for _ in range(3):
                with smtplib.SMTP("127.0.0.1", port, timeout=20) as client:
                    client.sendmail("s@example.net", ["investor@example.com"], raw)
        finally:
            controller.stop()

        assert stub.calls == 1, f"engine called {stub.calls} times for one Message-ID"
        assert len(_delivered(tmp_path / "md")) == 3, "dedup must not stop delivery"


# ==========================================================================
# 7. Units
# ==========================================================================

class TestUnits:
    def test_ensure_maildir_creates_subdirs_when_root_exists(self, tmp_path):
        """mailbox.Maildir(create=True) silently skips subdirs on an existing root."""
        root = tmp_path / "md"
        root.mkdir()
        _ensure_maildir(root)
        assert {p.name for p in root.iterdir()} == {"tmp", "new", "cur"}

    def test_to_crlf_normalises(self):
        assert to_crlf(b"a\nb\r\nc") == b"a\r\nb\r\nc"

    def test_tag_subject_leaves_genuine_alone(self):
        msg = parse_message(_simple_message(subject="Quarterly statement"))
        original, tagged = tag_subject(msg, "GENUINE")
        assert original == tagged == "Quarterly statement"

    def test_stamp_marks_error_when_engine_failed(self):
        msg = parse_message(_simple_message())
        verdict = GatewayVerdict(verdict="UNVERIFIED", ok=False, error="engine_timeout_after_8.0s")
        stamp(msg, verdict, prefix="X-PhishermanAI")
        assert msg["X-PhishermanAI-Error"] == "engine_timeout_after_8.0s"

    def test_checks_header_all_na_when_no_checks(self):
        verdict = GatewayVerdict()
        assert verdict.checks_header == "MONEY=na;ENTITY=na;CLAIM=na;DELIVERY=na"


# ==========================================================================
# 8. End to end against the real engine (skipped if it is not running)
# ==========================================================================

def _engine_up() -> bool:
    import requests
    try:
        return requests.get("http://127.0.0.1:8000/health", timeout=2).status_code == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _engine_up(), reason="verification engine not running on :8000")
class TestEndToEnd:
    @pytest.mark.parametrize("fixture,expected", [
        ("genuine_01.eml", "GENUINE"),
        ("tampered_01.eml", "TAMPERED"),
        ("fraud_02_guaranteed_returns.eml", "FRAUDULENT"),
        ("edge_01_unregistered_but_real.eml", "UNVERIFIED"),
    ])
    def test_fixture_verdict_through_gateway(self, fixture, expected, tmp_path):
        path = FIXTURES / fixture
        if not path.exists():
            pytest.skip(f"{fixture} not generated")

        port = _free_port()
        config = load_config(
            host="127.0.0.1", port=port, relay_mode="maildir",
            maildir_path=str(tmp_path / "md"),
            recipient_allowlist=["@example.com"],
        )
        controller, handler = build(config)
        controller.start()
        try:
            with smtplib.SMTP("127.0.0.1", port, timeout=30) as client:
                client.sendmail("s@example.net", ["investor@example.com"],
                                to_crlf(path.read_bytes()))
        finally:
            controller.stop()

        msg = _delivered(tmp_path / "md")[0]
        assert msg["X-PhishermanAI-Verdict"] == expected
