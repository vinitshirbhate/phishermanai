"""FastAPI application entry point.

    uvicorn apif.main:app --reload --port 8000

Startup is deliberately cheap: no ML model is loaded here. Every model is a lazy
singleton behind its detector, so the service is ready in under a second and the first
request that needs a given model pays for it once.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import analyze, feed, registry
from .config import get_settings
from .detectors import llm_analyst, text_phishing, voice
from .ingest import firecrawl, store
from .pipeline import MediaTooLongError
from .schemas import HealthStatus

DESCRIPTION = """
Detects AI-generated market propaganda and verifies genuine market communications.

**Detection** - text phishing/scam classification, video deepfake detection,
synthetic-speech detection, coordinated-campaign analysis, and market-correlation checks,
fused into a single threat score.

**Verification** - a registry of official SEBI / exchange / listed-company channels with
lookalike-domain detection and digital-signature checks, so a genuine circular can be
confirmed rather than merely "not flagged".

Start with `POST /api/v1/verify` - it accepts text, audio, video, or an image and routes
automatically.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store.init_db()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="APIF - AI Propaganda Intelligence Framework",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
)

# Open CORS: this is a backend-only build, and the dashboards that will consume it are
# not yet written. Restrict to known origins before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router)
app.include_router(registry.router)
app.include_router(feed.router)


@app.exception_handler(MediaTooLongError)
async def media_too_long_handler(request: Request, exc: MediaTooLongError) -> JSONResponse:
    """413 rather than a 200 verdict.

    An unanalysed clip must never come back as band 'Low' -- a caller rendering the band
    would show green for content nothing actually examined.
    """
    return JSONResponse(status_code=413, content={"detail": str(exc)})


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {
        "name": "APIF - AI Propaganda Intelligence Framework",
        "version": __version__,
        "docs": "/docs",
        "primary_endpoint": "POST /api/v1/verify",
    }


@app.get("/health", response_model=HealthStatus, tags=["meta"])
async def health() -> HealthStatus:
    """Reports this service plus each downstream it depends on.

    Downstreams are checked concurrently and are all optional: the phishing classifier
    being down degrades one signal, it does not take the service offline. Hence
    'degraded' rather than a non-200.
    """
    phishing, llm, spoof, (firecrawl_ok, firecrawl_err) = await asyncio.gather(
        text_phishing.health(), llm_analyst.health(), voice.health(), firecrawl.check_key()
    )
    dependencies = {
        "phishing_classifier": phishing,
        "openrouter": llm,
        "voice_spoof": spoof,
        "firecrawl": "ok" if firecrawl_ok else (firecrawl_err or "unavailable"),
        "database": "ok",
    }
    healthy = phishing == "ok"
    return HealthStatus(
        status="ok" if healthy else "degraded",
        version=__version__,
        dependencies=dependencies,
    )
