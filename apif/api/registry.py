"""Source-trust registry endpoints: the investor's "is this really from SEBI?" check."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile

from .. import pipeline
from ..engines import trust_registry
from ..schemas import RegistryLookupResult, Signal

router = APIRouter(prefix="/api/v1/registry", tags=["trust registry"])


@router.get("/lookup", response_model=RegistryLookupResult)
async def lookup(
    q: str = Query(..., description="Domain, URL, email address, or @handle"),
) -> RegistryLookupResult:
    """Check an origin against the registry of official market sources.

    A negative result distinguishes "unknown" from "impersonates a known source" -- the
    latter sets `lookalike_of` and is far stronger evidence of phishing.
    """
    return trust_registry.lookup(q)


@router.get("/organisations")
async def organisations() -> dict:
    """The full trusted-source list backing the lookup."""
    from ..engines.trust_registry import _registry  # noqa: PLC2701 - internal by design

    orgs = _registry()
    return {"count": len(orgs), "organisations": orgs}


@router.post("/check-source", response_model=Signal)
async def check_source(
    source: str | None = Form(None, description="URL, sender address, or @handle"),
    claimed_issuer: str | None = Form(None, description="Who the content claims to be"),
    document: UploadFile | None = File(
        None, description="Optional PDF circular, checked for a digital signature"
    ),
) -> Signal:
    """Full source-authentication check, returned as a scored Signal.

    Supplying both `source` and `claimed_issuer` is what detects the classic fake: a
    message claiming to be SEBI that arrives from a domain SEBI does not own.
    """
    pdf_path = None
    if document is not None:
        pdf_path = await pipeline.save_upload(
            document.filename or "document.pdf", await document.read()
        )
    return trust_registry.analyze(
        source=source, claimed_issuer=claimed_issuer, pdf_path=pdf_path
    )


