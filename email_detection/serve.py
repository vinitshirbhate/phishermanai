"""Container entrypoint: make sure the corpus is there, then serve the API.

    python serve.py

Deliberately not a shell script. This repo is developed on Windows, where a
checked-out `.sh` has neither the exec bit nor LF endings, and both failures
surface only inside the built image as an unhelpful "exec format error".

Configuration is all environment, because that is what a PaaS gives you:

    PORT                 port to bind          (default 8000)
    HOST                 interface to bind     (default 0.0.0.0)
    WEB_CONCURRENCY      uvicorn worker count  (default 1 -- see the note below)
    PHISHERMANAI_SKIP_LOAD=1   never attempt the corpus load
"""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("phishermanai.serve")


def corpus_is_loaded() -> bool:
    """True when the database already has filings in it.

    The image bakes the database in at build time, so normally this is a cheap
    yes. It comes back no in the two cases that would otherwise serve an empty
    corpus and quietly mark everything UNVERIFIED: a volume mounted over
    `data/`, and a `DATABASE_URL` pointing at a fresh Postgres.
    """
    from sqlalchemy import func, select

    from core.db import init_db, session_scope
    from core.models import Filing

    init_db()
    with session_scope() as session:
        return bool(session.scalar(select(func.count()).select_from(Filing)) or 0)


def main() -> None:
    if os.environ.get("PHISHERMANAI_SKIP_LOAD") != "1":
        try:
            if corpus_is_loaded():
                log.info("corpus present, skipping load")
            else:
                log.warning("corpus empty -- loading reference data (offline)")
                from data.load_all import main as load_all

                sys.argv = ["load_all"]  # load_all parses argv; give it no flags
                load_all()
        except Exception:
            # A corpus problem must not cost us the health endpoint. Serving
            # degraded is more debuggable than a container that crash-loops.
            log.exception("corpus check/load failed; starting anyway (expect /health degraded)")

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    # One worker by default. The warning-card cache in api/main.py is a
    # per-process dict, so with N workers a card rendered by one worker 404s on
    # the other N-1. Scale out only after that cache moves somewhere shared.
    workers = int(os.environ.get("WEB_CONCURRENCY", "1"))

    log.info("serving api.main:app on %s:%s (workers=%s)", host, port, workers)
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        workers=workers,
        proxy_headers=True,          # behind a PaaS load balancer
        forwarded_allow_ips="*",
        access_log=True,
    )


if __name__ == "__main__":
    main()
