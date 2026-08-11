"""
Phisherman AI Scam Detector - Pattern-based scam detection engine.
Ported from Kavach risk_engine.py. Deterministic, no LLM needed.

23 signal categories with weighted scoring, URL/phone/UPI extraction,
typosquat detection, India-specific patterns (UPI, Aadhaar, digital arrest).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("phisherman.scam_detector")

from . import context_gate  # noqa: E402  (shared with scamgate's L0 detector)
from . import entities  # noqa: E402  (shared extractors - see entities.py)

DATA_DIR = Path(__file__).parent.parent / "data"

_cache: dict[str, dict] = {}


def _load(name: str) -> dict:
    if name not in _cache:
        p = DATA_DIR / name
        _cache[name] = json.loads(p.read_text()) if p.exists() else {}
    return _cache[name]


def scam_signals() -> dict:
    return _load("scam_signals.json")


def risk_weights() -> dict:
    return _load("risk_weights.json")


def domain_whitelist() -> dict:
    return _load("domain_whitelist.json")


def reload_data():
    """Clear data cache to reload from disk."""
    _cache.clear()


# --- Extractors ---
#
# Defined once in engines/entities.py and imported by both this engine and
# scamgate. They previously held separate copies of UPI_RE; scamgate learned that
# it matches the front of every email address, this engine did not, and
# "Contains UPI handle(s): 1" fired on every mail page. See entities.py.

URL_RE = entities.URL_RE
PHONE_RE = entities.PHONE_RE
UPI_RE = entities.UPI_CANDIDATE_RE  # candidate shape only; not a UPI decision

extract_urls = entities.extract_urls
extract_phones = entities.extract_phones
extract_upi = entities.extract_upi


# --- Domain verification ---

def domain_of(url: str) -> Optional[str]:
    """Extract registered domain from URL."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        parts = host.lower().split(".")
        if len(parts) >= 3 and parts[-2] in ("co", "gov", "org", "ac", "net"):
            return ".".join(parts[-3:])
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return host
    except Exception:
        return None


def verify_domain(domain: str) -> dict:
    """Check domain against whitelist and typosquat patterns."""
    wl = domain_whitelist()
    all_allowed = set()
    for domains in wl.values():
        all_allowed.update(d.lower() for d in domains)

    d = domain.lower().strip()
    is_ok = any(d == a or d.endswith("." + a) for a in all_allowed)
    typosquat = (not is_ok) and any(
        d.endswith(suf) and d != suf
        for suf in ["gov.in", "nic.in", "sbi.co.in"]
    )
    return {"domain": domain, "is_whitelisted": is_ok, "suspicious_typosquat": typosquat}


# --- Scam Result ---

@dataclass
class ScamResult:
    risk_level: str          # SAFE, CAUTION, HIGH_RISK, CRITICAL
    risk_score: int          # 0-100 (higher = more dangerous)
    signals: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)
    categories_hit: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "signals": self.signals,
            "advice": self.advice,
            "extracted": self.extracted,
            "categories_hit": self.categories_hit,
        }


# --- Signal categories ---

SIGNAL_CATEGORIES = [
    ("financial_triggers", "Financial trigger (OTP/KYC/account threat)"),
    ("urgency_triggers", "Urgency manipulation"),
    ("authority_impersonation", "Authority impersonation cues"),
    ("money_ask", "Money / payment request"),
    ("deepfake_phrases", "Media manipulation / deepfake cues"),
    ("upi_scam_cues", "UPI collect/request cues"),
    ("phone_scam_cues", "Call/WhatsApp pressure cues"),
    ("investment_scam", "Investment/returns scam"),
    ("lottery_scam", "Lottery/prize scam"),
    ("loan_scam", "Loan scam / PII harvest"),
    ("pii_request", "Personal information request (Aadhaar/PAN/OTP)"),
    ("marketplace_scam", "Marketplace / classified ad scam"),
    ("utility_threat", "Utility disconnection threat"),
    ("whatsapp_malware", "WhatsApp malware / APK scam"),
    ("digital_arrest", "Digital arrest / fake law enforcement"),
    ("sim_swap_fraud", "SIM swap / porting fraud"),
    ("government_portal_fraud", "Fake government portal"),
    ("charity_ngo_fraud", "Charity / NGO donation fraud"),
    ("crypto_ponzi", "Crypto Ponzi / MLM scheme"),
    ("task_scam", "Task-based earning scam"),
    ("romance_sextortion", "Romance / sextortion scam"),
    ("job_scam", "Fake job / recruitment scam"),
    ("courier_parcel_scam", "Courier / parcel delivery scam"),
    ("remote_access_app", "Remote access app / screen-share install request"),
]


def detect(text: str) -> ScamResult:
    """
    Fast deterministic scam detection. No LLM needed.
    Returns ScamResult with risk_score 0-100 and matched signals.
    """
    try:
        return _detect_inner(text)
    except Exception as e:
        logger.error("Scam detection error (fail-open): %s", e)
        return ScamResult(
            risk_level="SAFE",
            risk_score=0,
            signals=["Engine error — fail-open"],
            advice=["If unsure, verify links and avoid sharing personal info."],
        )


def _detect_inner(text: str) -> ScamResult:
    sig = scam_signals()
    w = risk_weights()
    signals: list[str] = []
    categories_hit: list[str] = []
    score = 0
    t = (text or "").lower().strip()

    if not t:
        return ScamResult(risk_level="SAFE", risk_score=0)

    # Match all 24 signal categories.
    #
    # Bare entity/topic tokens ("sebi", "rbi", "kyc", "pay", "upi") are gated by
    # engines/context_gate.py - they score only when the text also shows an act
    # being performed on the reader. Mentioning a regulator is not impersonating
    # one. Same gate as scamgate's L0, deliberately shared rather than copied:
    # this engine and that one previously diverged, and fixing only one left
    # /api/analyze/page (the path ordinary web pages take) still wrong.
    for key, label in SIGNAL_CATEGORIES:
        keywords = [k.lower() for k in sig.get(key, [])]
        matched = [k for k in keywords if k in t]
        if not matched:
            continue
        if not context_gate.should_score(key, matched, text or ""):
            continue
        signals.append(label)
        categories_hit.append(key)
        score += int(w.get(key, 0))

    # Legitimate pattern discount
    legit_kw = [k.lower() for k in sig.get("legitimate_patterns", [])]
    legit_count = sum(1 for k in legit_kw if k in t)
    if legit_count >= 2:
        discount = abs(int(w.get("legitimate_discount", -25)))
        signals.append("Legitimate notification pattern detected")
        score = max(score - discount, 0)

    # URL analysis
    urls = extract_urls(text)
    phones = extract_phones(text)
    upis = extract_upi(text)
    extracted = {"urls": urls[:10], "phones": phones[:10], "upi": upis[:10]}

    # Links.
    #
    # "Contains link(s): N" used to add risk for the mere presence of a hyperlink,
    # and every domain absent from the whitelist added more. That made ordinary,
    # link-rich pages - search results, news, encyclopaedia articles - score worse
    # the more useful they were. A link is not evidence; a link to a KNOWN BAD
    # host is. Only the latter scores now.
    if urls:
        red_flags = sig.get("link_red_flags", [])
        if any(any(red.lower() in u.lower() for red in red_flags) for u in urls):
            signals.append("Link shortener detected")
            score += int(w.get("link_shortener", 15))

        for u in urls[:5]:
            dom = domain_of(u)
            if not dom:
                continue
            v = verify_domain(dom)
            if v["suspicious_typosquat"]:
                signals.append(f"Possible typosquat: {dom}")
                score += int(w.get("typosquat", 20))

    # Contact details corroborate an existing suspicion; they do not create one.
    # Every company contact page lists a phone number, and merchants show UPI
    # handles legitimately.
    if score > 0:
        if phones:
            signals.append(f"Contains phone number(s): {len(phones)}")
            score += int(w.get("has_phones", 8))
            if len(phones) >= 2:
                signals.append("Multiple numbers (common in support scams)")
                score += int(w.get("multi_phone", 8))

        if upis:
            signals.append(f"Contains UPI handle(s): {len(upis)}")
            score += int(w.get("has_upi", 12))

    score, note = context_gate.apply_corroboration_cap(score, categories_hit)
    if note:
        signals.append(note)

    score = min(score, 100)

    # Classify
    if score >= 70:
        level = "CRITICAL"
    elif score >= 45:
        level = "HIGH_RISK"
    elif score >= 20:
        level = "CAUTION"
    else:
        level = "SAFE"

    # Advice
    if level in ("CRITICAL", "HIGH_RISK"):
        advice = [
            "Do NOT share OTP, PIN, or banking credentials.",
            "Do NOT approve UPI collect requests unless you initiated them.",
            "Verify links using official domains only.",
            "If money is requested, pause and verify via official channels.",
            "Report scams at cybercrime.gov.in or call 1930.",
        ]
    elif level == "CAUTION":
        advice = [
            "Exercise caution before clicking links or sharing information.",
            "Verify the sender through official channels.",
            "If unsure, contact the organisation directly using their official website.",
        ]
    else:
        advice = []

    return ScamResult(
        risk_level=level,
        risk_score=score,
        signals=signals,
        advice=advice,
        extracted=extracted,
        categories_hit=categories_hit,
    )
