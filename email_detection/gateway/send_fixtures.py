"""Pipe the evaluation fixtures through the gateway and print the results.

    python -m gateway.send_fixtures

This is the demo driver. It starts a gateway on an ephemeral port, sends every
fixture .eml through it over real SMTP, and prints what came out the other side.
It runs fully offline against the local Maildir -- the only network call is to
the verification engine on 127.0.0.1, and if that is down every message still
arrives, marked UNVERIFIED, which is itself worth demonstrating.
"""

from __future__ import annotations

import argparse
import json
import smtplib
import statistics
import sys
import tempfile
import time
from pathlib import Path

from gateway.config import load_config
from gateway.smtp_server import build

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "eval" / "fixtures"

EXPECTED = {
    "genuine": "GENUINE",
    "tampered": "TAMPERED",
    "fraud": "FRAUDULENT",
    "edge": "UNVERIFIED",
    "inst": "UNVERIFIED",
}


def to_crlf(raw: bytes) -> bytes:
    """Normalise line endings to CRLF before handing bytes to SMTP.

    SMTP is a CRLF protocol (RFC 5321). `smtplib.sendmail` silently fixes bare
    LF endings for a `str` payload but does NOT for `bytes` -- and .eml files on
    disk are LF-terminated. Sending them raw means the server sees no line
    terminators at all and rejects the whole message as one oversized line:
    "500 Line too long (see RFC5321 4.5.3.1.6)". A real MTA does this conversion
    on the wire; here we do it explicitly.
    """
    return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def _expected_for(name: str) -> str | None:
    for prefix, verdict in EXPECTED.items():
        if name.startswith(prefix):
            return verdict
    return None


def collect_fixtures(include_institutional: bool = False) -> list[Path]:
    files = sorted(FIXTURE_DIR.glob("*.eml"))
    if include_institutional:
        files += sorted((FIXTURE_DIR / "institutional").glob("*.eml"))
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send fixtures through the gateway")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--institutional", action="store_true",
                        help="also send the 20 genuine institutional emails")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    fixtures = collect_fixtures(args.institutional)
    if not fixtures:
        print("No fixtures found. Run: python -m eval.make_fixtures", file=sys.stderr)
        return 1

    port = args.port or _free_port()
    maildir = Path(tempfile.mkdtemp(prefix="phai-gw-"))

    config = load_config(
        port=port,
        host="127.0.0.1",
        relay_mode="maildir",
        maildir_path=str(maildir),
        # Fixtures are addressed to investor@example.com; allow the domain so
        # the run does not depend on the shipped allowlist.
        recipient_allowlist=["@example.com", "demo@local", "@local"],
    )

    from core.db import init_db
    init_db()

    controller, handler = build(config)
    controller.start()

    rows = []
    try:
        for path in fixtures:
            raw = to_crlf(path.read_bytes())
            started = time.perf_counter()
            try:
                with smtplib.SMTP("127.0.0.1", port, timeout=30) as client:
                    client.sendmail("sender@example.net", ["investor@example.com"], raw)
                wall_ms = int((time.perf_counter() - started) * 1000)
                result = handler.results[-1] if handler.results else {}
                rows.append({
                    "file": path.name,
                    "expected": _expected_for(path.name),
                    "verdict": result.get("verdict_name"),
                    "confidence": result.get("confidence"),
                    "latency_ms": result.get("latency_ms"),
                    "wall_ms": wall_ms,
                    "error": result.get("error"),
                    "cached": result.get("cached", False),
                })
            except Exception as exc:  # noqa: BLE001
                rows.append({
                    "file": path.name, "expected": _expected_for(path.name),
                    "verdict": "SEND_FAILED", "error": f"{type(exc).__name__}: {exc}",
                })
    finally:
        controller.stop()

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    _print_table(rows, maildir)
    return 0


def _print_table(rows: list[dict], maildir: Path) -> None:
    print()
    print(f"{'FIXTURE':<36}{'EXPECTED':<12}{'VERDICT':<12}{'CONF':>5}{'ms':>7}  NOTE")
    print("-" * 92)
    correct = 0
    comparable = 0
    for row in rows:
        expected = row.get("expected") or "-"
        verdict = row.get("verdict") or "-"
        if row.get("expected"):
            comparable += 1
            if expected == verdict:
                correct += 1
        note = row.get("error") or ("cache hit" if row.get("cached") else "")
        mark = "" if expected in ("-", verdict) else "  <-- MISMATCH"
        print(f"{row['file']:<36}{expected:<12}{verdict:<12}"
              f"{str(row.get('confidence') or ''):>5}{str(row.get('latency_ms') or ''):>7}  {note}{mark}")

    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    print("-" * 92)
    if comparable:
        print(f"  matched expected verdict : {correct}/{comparable}")
    if latencies:
        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
        print(f"  gateway latency          : p50 {p50:.0f} ms | p95 {p95:.0f} ms | max {max(latencies)} ms")
    print(f"  delivered to             : {maildir}")
    print()


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
