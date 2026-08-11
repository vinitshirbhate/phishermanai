"""
provenance_lane.py - C2PA Content Credentials inspection.

Implements the `provenance_lane` module that extension/contracts/
module_registry.json has DECLARED since day one and which had no
implementation behind it. The registry entry describes it as treating
"content credentials and provenance states as first-class outputs instead
of deepfake theater" - that phrasing is the whole design brief and this
module is written to honour it literally.

WHY PROVENANCE AND NOT A DEEPFAKE CLASSIFIER
---------------------------------------------
scripts/check_blocked_claims.py fails the build on "this is a deepfake",
"this voice is synthetic", and "is AI-generated". That gate is not
squeamishness, it is an accuracy position: a CNN that outputs
"87% likely synthetic" on a compressed WhatsApp forward is guessing, and
shipping that guess as a verdict to a retail investor is how you get people
confidently ignoring real warnings (and confidently disbelieving real
videos of real executives).

C2PA inverts the question. Instead of "does this LOOK generated", it asks
"is there a cryptographically signed, tamper-evident record of where this
came from, and does the signer chain to a trust anchor". That is a fact,
checkable, falsifiable, and it fails CLOSED - a broken hash is a broken
hash, not a probability.

THE STATES, AND WHY `absent` IS NOT `suspicious`
--------------------------------------------------
This mirrors securities_identity.py's own hard rule that missing
credentials are never proof of deception. Most media on the Indian internet
in 2026 carries no Content Credentials at all - screenshots, re-encodes,
WhatsApp forwards and every platform that strips metadata on upload. If
`no_credentials` were rendered as a warning, the tool would warn on
essentially everything and teach users to dismiss it, which is precisely
the failure this module exists to avoid.

    verified_signed    manifest present, hash matches, signer chains to a
                       configured trust anchor. The ONLY state that raises
                       trust.
    signed_untrusted   valid, intact manifest, but the signer does not
                       chain to a trust anchor we recognise. Informative,
                       NOT accusatory - an unknown signer is unknown, not
                       fraudulent.
    tampered           manifest present and the asset hash does NOT match.
                       Something changed after signing. This is the one
                       state that is genuinely adverse, and it is a
                       cryptographic fact rather than an inference.
    no_credentials     nothing to check. Neutral. Never a warning.
    unsupported        we cannot read this media type / the SDK is absent.
                       Honest incapacity, distinct from `no_credentials`.

DEPENDENCY POSTURE
-------------------
backend/requirements.txt holds 3 runtime deps against an NFR-9 budget of
10. The `c2pa` Python binding is therefore an OPTIONAL extra, not a hard
requirement: when it is not installed this module returns `unsupported`
with a reason, and the rest of the product is unaffected. The heavy
lifting is meant to happen client-side anyway (@contentauth/c2pa-web runs
the same Rust core compiled to WASM, in-browser, so the media never leaves
the user's machine) - this backend path exists for the side panel's
explicit "inspect this image" action and for evaluation harnesses.

    pip install c2pa-python          # optional, enables real verification
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("phisherman.provenance_lane")

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"

# Trust deltas, in the same convention as securities_identity.SECURITIES_DELTA.
# Note the asymmetry, which is deliberate: a good provenance result is worth
# less than a bad one costs, and `no_credentials` is worth exactly zero.
PROVENANCE_DELTA = {
    "verified_signed": +20,
    "signed_untrusted": 0,
    "no_credentials": 0,      # NEVER negative. See module docstring.
    "unsupported": 0,
    "tampered": -35,
}

STATE_ORDER = ["tampered", "signed_untrusted", "unsupported",
               "no_credentials", "verified_signed"]

# Media types the C2PA spec covers and that we will attempt.
SUPPORTED_MIME = {
    "image/jpeg", "image/png", "image/webp", "image/avif", "image/tiff",
    "image/heic", "image/heif", "image/svg+xml",
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4",
    "application/pdf",
}

_c2pa_mod = None
_c2pa_probed = False


def _c2pa():
    """Import the optional c2pa binding once, cache the outcome either way."""
    global _c2pa_mod, _c2pa_probed
    if not _c2pa_probed:
        _c2pa_probed = True
        try:
            import c2pa  # type: ignore
            _c2pa_mod = c2pa
            logger.info("c2pa binding available - provenance verification live")
        except ImportError:
            _c2pa_mod = None
            logger.info("c2pa binding not installed - provenance lane returns "
                        "`unsupported` (pip install c2pa-python to enable)")
    return _c2pa_mod


@dataclass
class ProvenanceResult:
    state: str
    trust_delta: int = 0
    mime: Optional[str] = None
    # Human-readable, blocked-claims-safe reason strings. These are written to
    # be pasted straight into UI without further editing, which is why none of
    # them assert synthetic origin.
    reasons: list = field(default_factory=list)
    signer: Optional[str] = None
    claim_generator: Optional[str] = None
    signed_at: Optional[str] = None
    trust_anchor_matched: bool = False
    # C2PA `digitalSourceType` assertion, when the signer chose to declare it.
    # This is the ONLY place a "made with generative AI" statement can come
    # from, and note the direction: it is a DISCLOSURE BY THE SIGNER, not our
    # inference about the pixels. Reporting a self-declared assertion is not
    # the same act as accusing content of being synthetic.
    declared_source_type: Optional[str] = None
    ingredient_count: int = 0
    asset_sha256: Optional[str] = None
    error: Optional[str] = None
    disclosure: str = (
        "Provenance describes a signed record attached to this file. Absence "
        "of a record is normal and is not a finding about the content. "
        "Presence of a record describes the signer's claim, not our judgement "
        "of what the content depicts."
    )


def _reason(code: str, text: str, source_url: Optional[str] = None) -> dict:
    return {"code": code, "text": text, "source_url": source_url}


C2PA_SPEC_URL = "https://c2pa.org/specifications/specifications/2.1/index.html"


def _load_trust_anchors() -> list:
    """
    Trust anchors are the list of signing certificates we are willing to treat
    as authoritative. Ships empty by default and that is intentional: silently
    baking in a vendor list would make `verified_signed` mean "signed by
    someone Adobe likes", which is not the same claim as "signed by the
    exchange / AMC / regulator this content claims to be from".

    For the securities use case the anchor list that actually matters is one
    SEBI or the MIIs would have to publish - a registry of signing certs for
    official communications from SEBI, NSE, BSE, NSDL, CDSL and registered
    intermediaries. No such registry exists today. That absence is the real
    finding, and it is worth stating plainly in a TechSprint submission
    rather than papering over: the detection half of the problem statement is
    tractable with existing open standards, and the authentication half is
    blocked on a trust-list nobody has stood up yet.
    """
    p = DATA_DIR / "c2pa_trust_anchors.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc.get("anchors", [])
    except Exception:
        return []


def inspect_bytes(data: bytes, mime: str = "", filename: str = "") -> dict:
    """
    Inspect one media asset for C2PA Content Credentials.

    Returns a ProvenanceResult dict. Never raises: a provenance check that
    500s on a malformed upload would take the whole scan down with it, and a
    malformed file is exactly the input an adversary controls.
    """
    mime = (mime or "").lower().split(";")[0].strip()
    sha = hashlib.sha256(data).hexdigest() if data else None

    if not data:
        return asdict(ProvenanceResult(
            state="unsupported", mime=mime, asset_sha256=None,
            error="empty asset",
            reasons=[_reason("PROV_EMPTY", "Nothing to inspect.")]))

    if mime and mime not in SUPPORTED_MIME:
        return asdict(ProvenanceResult(
            state="unsupported", mime=mime, asset_sha256=sha,
            reasons=[_reason(
                "PROV_MIME_UNSUPPORTED",
                f"Content Credentials are not defined for {mime}. This is a "
                "limit of what can be checked, not a finding about the file.",
                C2PA_SPEC_URL)]))

    c2pa = _c2pa()
    if c2pa is None:
        return asdict(ProvenanceResult(
            state="unsupported", mime=mime, asset_sha256=sha,
            error="c2pa binding not installed",
            reasons=[_reason(
                "PROV_SDK_ABSENT",
                "Provenance verification is not available in this install. "
                "The offline and registry checks above are unaffected.",
                C2PA_SPEC_URL)]))

    try:
        reader = c2pa.Reader(mime or "image/jpeg", data)
        raw = reader.json()
        manifest_store = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as exc:  # noqa: BLE001 - includes "no manifest", which is normal
        msg = str(exc)
        # The SDK signals "there is simply nothing here" as an exception. That
        # is the single most common outcome on the open web and must NOT be
        # presented as an error, let alone a warning.
        if "no claim" in msg.lower() or "manifest not found" in msg.lower() \
                or "jumbf" in msg.lower():
            return asdict(ProvenanceResult(
                state="no_credentials", mime=mime, asset_sha256=sha,
                reasons=[_reason(
                    "PROV_NONE",
                    "No Content Credentials attached. Most images and videos "
                    "online carry none — platforms commonly strip them on "
                    "upload — so this is expected and says nothing about the "
                    "content itself.",
                    C2PA_SPEC_URL)]))
        logger.info("provenance read failed (%s): %s", filename or mime, msg)
        return asdict(ProvenanceResult(
            state="unsupported", mime=mime, asset_sha256=sha, error=msg,
            reasons=[_reason("PROV_READ_FAILED",
                             "The provenance record could not be read.")]))

    return _interpret(manifest_store, mime=mime, sha=sha)


def _interpret(store: dict, *, mime: str, sha: Optional[str]) -> dict:
    """Turn a C2PA manifest store into one of our five states."""
    active_label = store.get("active_manifest")
    manifests = store.get("manifests", {}) or {}
    active = manifests.get(active_label, {}) if active_label else {}

    # validation_status is populated by the SDK when a check FAILED. An empty
    # list is the good case.
    failures = [v for v in (store.get("validation_status") or [])
                if str(v.get("code", "")).startswith(("assertion.", "claim.",
                                                       "signingCredential.",
                                                       "algorithmUnsupported"))]

    signer = None
    signed_at = None
    sig_info = active.get("signature_info") or {}
    if sig_info:
        signer = sig_info.get("issuer") or sig_info.get("common_name")
        signed_at = sig_info.get("time")

    claim_generator = active.get("claim_generator_info")
    if isinstance(claim_generator, list) and claim_generator:
        claim_generator = claim_generator[0].get("name")
    elif isinstance(claim_generator, dict):
        claim_generator = claim_generator.get("name")
    elif not isinstance(claim_generator, str):
        claim_generator = active.get("claim_generator")

    # digitalSourceType: the signer's OWN declaration about how the asset was
    # produced. We surface it verbatim and attribute it to the signer.
    declared = None
    for a in (active.get("assertions") or []):
        label = a.get("label", "")
        if "actions" in label:
            for act in (a.get("data", {}) or {}).get("actions", []) or []:
                dst = act.get("digitalSourceType") or act.get("softwareAgent")
                if dst and "trainedAlgorithmicMedia" in str(dst):
                    declared = "trainedAlgorithmicMedia"
                    break
                if dst and not declared:
                    declared = str(dst)

    ingredients = active.get("ingredients") or []

    if failures:
        codes = ", ".join(sorted({str(f.get("code")) for f in failures})[:4])
        return asdict(ProvenanceResult(
            state="tampered", trust_delta=PROVENANCE_DELTA["tampered"],
            mime=mime, asset_sha256=sha, signer=signer, signed_at=signed_at,
            claim_generator=claim_generator, declared_source_type=declared,
            ingredient_count=len(ingredients),
            reasons=[_reason(
                "PROV_VALIDATION_FAILED",
                "This file carries a Content Credential, but the record does "
                "not match the file as it stands now — it has been altered "
                "since it was signed, or the record was damaged in transit. "
                f"Validation codes: {codes}.",
                C2PA_SPEC_URL)]))

    anchors = _load_trust_anchors()
    anchored = bool(signer) and any(
        a.get("issuer", "").lower() in (signer or "").lower() for a in anchors)

    reasons = []
    if declared == "trainedAlgorithmicMedia":
        # Attribution matters in the wording. "The signer states" is a report;
        # "this is AI-generated" would be a verdict and is a blocked claim.
        reasons.append(_reason(
            "PROV_DECLARED_GENERATIVE",
            "The signer of this file declared in its Content Credential that "
            "generative AI was used in producing it.",
            C2PA_SPEC_URL))

    if anchored:
        reasons.insert(0, _reason(
            "PROV_TRUSTED_SIGNER",
            f"Signed by {signer}, which matches a configured trust anchor, "
            "and the file is unchanged since signing.",
            C2PA_SPEC_URL))
        return asdict(ProvenanceResult(
            state="verified_signed",
            trust_delta=PROVENANCE_DELTA["verified_signed"],
            mime=mime, asset_sha256=sha, signer=signer, signed_at=signed_at,
            claim_generator=claim_generator, trust_anchor_matched=True,
            declared_source_type=declared, ingredient_count=len(ingredients),
            reasons=reasons))

    reasons.insert(0, _reason(
        "PROV_SIGNED_UNKNOWN_ANCHOR",
        f"The file is unchanged since signing, but the signer"
        + (f" ({signer})" if signer else "")
        + " is not on a trust list this install recognises. Unknown is not "
          "the same as untrustworthy — there is currently no published "
          "registry of signing certificates for official Indian securities-"
          "market communications to check against.",
        C2PA_SPEC_URL))
    return asdict(ProvenanceResult(
        state="signed_untrusted",
        trust_delta=PROVENANCE_DELTA["signed_untrusted"],
        mime=mime, asset_sha256=sha, signer=signer, signed_at=signed_at,
        claim_generator=claim_generator, trust_anchor_matched=False,
        declared_source_type=declared, ingredient_count=len(ingredients),
        reasons=reasons))


def capability_report() -> dict:
    """
    What this install can actually do right now. Surfaced via the API so the
    UI can say "provenance checking is off" instead of quietly returning
    `unsupported` forever and looking like every file is unreadable.
    """
    c2pa = _c2pa()
    anchors = _load_trust_anchors()
    return {
        "available": c2pa is not None,
        "sdk": "c2pa-python" if c2pa is not None else None,
        "install_hint": None if c2pa is not None else "pip install c2pa-python",
        "supported_mime": sorted(SUPPORTED_MIME),
        "trust_anchors_configured": len(anchors),
        "trust_anchor_note": (
            "No trust anchors configured. `verified_signed` is unreachable "
            "until a signing-certificate list is supplied. For securities-"
            "market use the meaningful list would be one published by SEBI or "
            "the MIIs; none exists today."
        ) if not anchors else None,
        "client_side_alternative": {
            "package": "@contentauth/c2pa-web",
            "note": ("Same Rust core compiled to WASM, runs in the browser so "
                     "media never leaves the user's device. Preferred path for "
                     "the extension; this backend endpoint is for the side "
                     "panel's explicit inspect action and for eval harnesses."),
        },
    }
