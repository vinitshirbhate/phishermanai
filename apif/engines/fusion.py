"""Risk fusion — combines detector signals into a single threat score.

Two design choices worth stating explicitly:

1. Only *available* signals are scored, and the weights are renormalized over them.
   A detector that failed (HF Space down, no audio track, market data missing) must not
   look like evidence of innocence, which is what averaging zeros over the full weight
   set would do.

2. One override rule runs after the weighted sum, because it encodes a fact the linear
   model structurally cannot represent: a registry-verified official source caps the
   score at Low. A digitally signed SEBI circular is not "somewhat suspicious" because
   its language scored high.

   A second override previously forced Critical when a voice both matched a known
   official *and* carried synthetic artefacts -- a targeted clone. It was removed with
   the SpeechBrain speaker-verification model: without a voiceprint comparison there is
   no `speaker_match` to test, so the rule could never fire. Restoring speaker
   verification is what would bring it back.
"""

from __future__ import annotations

from ..config import get_settings
from ..schemas import (
    SIGNAL_COORDINATION,
    SIGNAL_MARKET_ANOMALY,
    SIGNAL_SOURCE_UNTRUSTED,
    SIGNAL_TEXT_PHISHING,
    SIGNAL_VIDEO_DEEPFAKE,
    SIGNAL_VOICE_SPOOF,
    Band,
    Signal,
    Verdict,
)

__all__ = ["OVERRIDE_VERIFIED_OFFICIAL", "fuse", "score_to_band"]

OVERRIDE_VERIFIED_OFFICIAL = "verified_official_source"


def _weights() -> dict[str, float]:
    s = get_settings()
    return {
        SIGNAL_TEXT_PHISHING: s.weight_text_phishing,
        SIGNAL_VOICE_SPOOF: s.weight_voice_spoof,
        SIGNAL_VIDEO_DEEPFAKE: s.weight_video_deepfake,
        SIGNAL_SOURCE_UNTRUSTED: s.weight_source_untrusted,
        SIGNAL_COORDINATION: s.weight_coordination,
        SIGNAL_MARKET_ANOMALY: s.weight_market_anomaly,
    }


def score_to_band(score: float) -> Band:
    s = get_settings()
    if score < s.band_medium:
        return "Low"
    if score < s.band_high:
        return "Medium"
    if score < s.band_critical:
        return "High"
    return "Critical"


def _weighted_score(signals: list[Signal]) -> float:
    weights = _weights()
    usable = [s for s in signals if s.available and s.name in weights]
    total_weight = sum(weights[s.name] for s in usable)
    if total_weight <= 0:
        # Every detector failed or none were applicable. Returning 0.0 here would read
        # as "safe"; the caller distinguishes this via the empty-signals headline.
        return 0.0
    return sum(s.score * weights[s.name] for s in usable) / total_weight


def _headline(band: Band, signals: list[Signal], override: str | None) -> str:
    if override == OVERRIDE_VERIFIED_OFFICIAL:
        return "Verified official communication"
    if not any(s.available for s in signals):
        return "Inconclusive - no detector could evaluate this content"

    # Name the strongest contributing signal so the headline says *why*.
    weights = _weights()
    ranked = sorted(
        (s for s in signals if s.available and s.name in weights),
        key=lambda s: s.score * weights[s.name],
        reverse=True,
    )
    driver = ranked[0] if ranked else None
    labels = {
        SIGNAL_TEXT_PHISHING: "phishing/scam language",
        SIGNAL_VOICE_SPOOF: "synthetic audio",
        SIGNAL_VIDEO_DEEPFAKE: "manipulated video",
        SIGNAL_SOURCE_UNTRUSTED: "unverified source",
        SIGNAL_COORDINATION: "coordinated amplification",
        SIGNAL_MARKET_ANOMALY: "abnormal price/volume activity",
    }
    if band == "Low":
        return "No significant propaganda indicators detected"
    reason = labels.get(driver.name, "multiple indicators") if driver else "multiple indicators"
    prefix = {"Medium": "Possible", "High": "Likely", "Critical": "High-confidence"}[band]
    return f"{prefix} market propaganda - driven by {reason}"


def fuse(signals: list[Signal]) -> Verdict:
    """Combine signals into a Verdict. Pure function - safe to unit-test directly."""
    score = _weighted_score(signals)
    override: str | None = None

    source = next(
        (s for s in signals if s.name == SIGNAL_SOURCE_UNTRUSTED and s.available), None
    )

    # Override: a registry-verified, digitally signed official source caps at Low.
    if source is not None:
        ev = source.evidence
        if ev.get("registry_matched") and ev.get("signature_valid"):
            score = min(score, get_settings().band_medium - 0.01)
            override = OVERRIDE_VERIFIED_OFFICIAL

    score = max(0.0, min(1.0, score))
    band = score_to_band(score)
    return Verdict(
        risk_score=round(score, 4),
        band=band,
        headline=_headline(band, signals, override),
        signals=signals,
        override_applied=override,
    )
