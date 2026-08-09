"""Start the gateway.

    python -m gateway.run
    python -m gateway.run --port 1025 --relay maildir --allowlist demo@local
    python -m gateway.run --relay smtp --relay-host 127.0.0.1 --relay-port 2525
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time

from gateway.config import RELAY_MODES, load_config
from gateway.smtp_server import build


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhishermanAI SMTP verification gateway")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--relay", dest="relay_mode", choices=RELAY_MODES)
    parser.add_argument("--relay-host", dest="relay_host")
    parser.add_argument("--relay-port", dest="relay_port", type=int)
    parser.add_argument("--maildir", dest="maildir_path")
    parser.add_argument("--engine-url", dest="engine_url")
    parser.add_argument("--engine-timeout", dest="engine_timeout", type=float)
    parser.add_argument(
        "--allowlist", dest="recipient_allowlist",
        help="comma-separated recipients or @domains",
    )
    parser.add_argument("--no-subject-tagging", action="store_true")
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    log = logging.getLogger("phishermanai.gateway")

    overrides = {
        k: v for k, v in vars(args).items()
        if k not in ("config", "verbose", "no_subject_tagging") and v is not None
    }
    if args.no_subject_tagging:
        overrides["subject_tagging"] = False

    try:
        config = load_config(args.config, **overrides)
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    # Ensure the schema is current before the first message arrives, rather than
    # failing on the first insert.
    from core.db import init_db
    init_db()

    if config.is_public_binding():
        log.warning(
            "BINDING PUBLICLY on %s. This build is NOT hardened for internet "
            "exposure -- no TLS, no authentication, no spam controls. "
            "See gateway/SECURITY.md.", config.host,
        )
    if not config.recipient_allowlist:
        log.warning("recipient allowlist is EMPTY; every recipient will be rejected with 550")

    controller, handler = build(config)
    controller.start()

    log.info(
        "gateway listening on %s:%s | relay=%s | engine=%s | allowlist=%s",
        config.host, config.port, config.relay_mode,
        config.verify_endpoint, config.recipient_allowlist,
    )
    if config.relay_mode == "maildir":
        log.info("delivering to maildir %s", config.maildir_abspath)

    stopping = False

    def _stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _stop)
    try:
        signal.signal(signal.SIGTERM, _stop)
    except (AttributeError, ValueError):  # pragma: no cover - platform dependent
        pass

    try:
        while not stopping:
            time.sleep(0.25)
    finally:
        controller.stop()
        log.info("gateway stopped after %d message(s)", handler.processed)
        print(json.dumps({"processed": handler.processed}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
