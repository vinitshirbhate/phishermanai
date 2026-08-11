"""
ScamGate - The Ultimate Scam & Threat Detection Orchestrator.

Three-tier architecture:
  L0: Pattern match (instant, deterministic, zero-cost)
  L1: Local LLM (phi4 via Ollama, fast, private, free)
  L2: Cloud API (Groq/DeepSeek, deep analysis, paid)

Flow: Every input hits L0. If L0 confidence < threshold or score is
ambiguous (30-70 range), escalate to L1. If L1 flags critical or
requests deeper analysis, escalate to L2. Results merge into a
unified ScamGateVerdict.

Designed for: browser extension, CLI, API, bot integration.
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import sys
import time
import urllib.request
import ssl
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("scamgate")

from . import context_gate  # noqa: E402  (shared with the legacy scam_detector)
from . import entities  # noqa: E402  (shared extractors - see entities.py)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_cache: dict[str, object] = {}


def _load_json(name: str) -> dict:
    if name not in _cache:
        p = DATA_DIR / name
        _cache[name] = json.loads(p.read_text()) if p.exists() else {}
    return _cache[name]


def _load_lines(name: str) -> set[str]:
    key = f"lines:{name}"
    if key not in _cache:
        p = DATA_DIR / "feeds" / name
        if p.exists():
            _cache[key] = {
                line.strip().lower()
                for line in p.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            }
        else:
            _cache[key] = set()
    return _cache[key]


# Blocklist feeds arrive in THREE different formats and the raw lines are not
# comparable to a hostname:
#
#   blocklistproject_phishing.txt   "0.0.0.0 www.sapl.com.hk"   (hosts file)
#   phishing_domains_active.txt     "915856.buffalosouljah.com" (bare domain)
#   scam_blocklist_domains.txt      "||falkewear.shop^"         (AdBlock rule)
#
# `dom in self.phish_domains` therefore matched NOTHING on two of the three
# lists. The two highest-weight signals in this engine - "Known scam domain"
# (+40) and "Known phishing domain" (+50), the only hard evidence it has - could
# never fire against 659,000 of the 819,000 entries. Every other check was
# tuned around blocklist hits that were not arriving.
#
# Normalised once here so both this engine and link_reputation compare like
# with like.
_HOSTS_PREFIX = ("0.0.0.0", "127.0.0.1", "::1", "::")


def _normalise_blocklist_entry(line: str) -> str:
    s = line.strip().lower()
    if not s or s.startswith(("#", "!", "@@")):
        return ""
    # AdBlock: ||domain.com^  /  ||domain.com^$third-party
    if s.startswith("||"):
        s = s[2:]
        for cut in ("^", "$", "/"):
            i = s.find(cut)
            if i != -1:
                s = s[:i]
    else:
        # Hosts file: "0.0.0.0 domain.com" (also handles tabs / extra columns)
        parts = s.split()
        if len(parts) >= 2 and parts[0] in _HOSTS_PREFIX:
            s = parts[1]
        elif len(parts) > 1:
            return ""                       # unrecognised multi-column line
    s = s.strip().strip(".")
    if not s or " " in s or "." not in s:
        return ""
    if s in ("localhost", "local", "broadcasthost"):
        return ""
    return s


def load_domain_set(name: str) -> set[str]:
    """A feed file as comparable hostnames, whatever format it ships in."""
    key = f"domains:{name}"
    if key not in _cache:
        p = DATA_DIR / "feeds" / name
        out: set[str] = set()
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                d = _normalise_blocklist_entry(line)
                if d:
                    out.add(d)
        _cache[key] = out
    return _cache[key]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class L0Result:
    """Pattern-based detection result."""
    score: int  # 0-100
    signals: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)
    processing_ms: float = 0.0
    behavior: Optional[dict] = None  # behavior_lane.BehaviorResult.to_dict()


@dataclass
class L1Result:
    """Local LLM analysis result."""
    verdict: str  # safe, suspicious, scam, phishing, manipulation
    confidence: float  # 0.0-1.0
    reasoning: str = ""
    recommendations: list[str] = field(default_factory=list)
    processing_ms: float = 0.0


@dataclass
class L2Result:
    """Cloud API deep analysis result."""
    verdict: str
    confidence: float
    analysis: str = ""
    threat_type: str = ""
    recommendations: list[str] = field(default_factory=list)
    provider: str = ""
    processing_ms: float = 0.0


@dataclass
class ScamGateVerdict:
    """Unified verdict combining all tiers."""
    trust_score: int  # 0-100 (100 = fully trusted)
    risk_level: str  # SAFE, CAUTION, WARNING, DANGER
    verdict: str  # clean, suspicious, scam, phishing, malware, manipulation
    confidence: float  # 0.0-1.0
    signals: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)
    tiers_used: list[str] = field(default_factory=list)
    behavior: Optional[dict] = None  # how the text works on the reader, not what it is about
    l0: Optional[dict] = None
    l1: Optional[dict] = None
    l2: Optional[dict] = None
    processing_ms: float = 0.0
    timestamp: str = ""
    input_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------
# Shared with scam_detector via engines/entities.py - these were duplicated
# literals and drifted apart once already. See entities.py for the full account.
URL_RE = entities.URL_RE
PHONE_RE = entities.PHONE_RE
UPI_RE = entities.UPI_CANDIDATE_RE
EMAIL_RE = entities.EMAIL_RE
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

HIGH_RISK_TLDS = {
    ".top", ".xyz", ".click", ".loan", ".buzz", ".gq", ".tk", ".ml",
    ".ga", ".cf", ".work", ".date", ".bid", ".stream", ".racing",
    ".download", ".win", ".review", ".party", ".science", ".trade",
}


def extract_all(text: str) -> dict:
    src = text or ""
    emails = entities.extract_emails(src)

    # UPI_RE ("name@handle") also matches the leading portion of every email
    # address. The filter that used to live here only dropped candidates found
    # inside an email present in the SAME text, so a bare "user@gmail" with no
    # full address alongside it still registered as a payment handle. The rule
    # now also requires the suffix to be PSP-shaped rather than mail-shaped.
    upi = entities.extract_upi(src)

    return {
        "urls": URL_RE.findall(src)[:20],
        "phones": [m.group(1) for m in PHONE_RE.finditer(src)][:10],
        "upi": upi[:10],
        "emails": emails[:10],
        "aadhaar": AADHAAR_RE.findall(src)[:5],
        "pan": PAN_RE.findall(src)[:5],
    }


def domain_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        parts = host.lower().split(".")
        if len(parts) >= 3 and parts[-2] in ("co", "gov", "org", "ac", "net"):
            return ".".join(parts[-3:])
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return host
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# L0: Pattern-based detection (instant, deterministic)
# ---------------------------------------------------------------------------
class L0PatternDetector:
    """Zero-cost pattern matching against signal database + threat feeds."""

    def __init__(self):
        self.signals = _load_json("scam_signals.json")
        self.weights = _load_json("risk_weights.json")
        self.whitelist = _load_json("domain_whitelist.json")
        self.govt_domains = _load_json("govt_domains_india.json")
        self._scam_domains: set[str] | None = None
        self._phish_domains: set[str] | None = None


    @property
    def scam_domains(self) -> set[str]:
        if self._scam_domains is None:
            self._scam_domains = load_domain_set("scam_blocklist_domains.txt")
        return self._scam_domains

    @property
    def phish_domains(self) -> set[str]:
        if self._phish_domains is None:
            self._phish_domains = load_domain_set("blocklistproject_phishing.txt")
        return self._phish_domains

    def detect(self, text: str, url: str = "") -> L0Result:
        start = time.perf_counter()
        t = (text or "").lower().strip()
        signals: list[str] = []
        categories: list[str] = []
        score = 0

        # Signal keyword matching (23 categories).
        #
        # Bare entity and topic tokens ("sebi", "rbi", "kyc", "pay", "upi") are
        # GATED: they score only when the text also shows an act being performed
        # on the reader. Mentioning a regulator is not impersonating one, and a
        # checkout page saying "pay" is not a payment scam. Multi-word phrases
        # that carry the act inside them ("share your otp", "digital arrest")
        # are ungated and score as before.
        #
        # Without this, a Google results page for "sebi" scored 21/100 DANGER
        # off two words, and every bank site tripped the same wires.
        # An RBI-namespace host is a licence-gated identity, not an ordinary
        # domain: only a bank the RBI licensed can hold a .bank.in address.
        # On such a host the financial vocabulary this lexicon hunts for
        # ('otp', 'kyc', 'account', 'offer', 'win') is the site's own subject
        # matter, not evidence against it. Without this, hdfc.bank.in scored
        # 14/100 DANGER on its own homepage while a hdfc-bank-secure.com
        # lookalike would have scored better -- the signal was inverted.
        #
        # This suppresses VOCABULARY heuristics only. Blocklist hits, TLS
        # failures and credential-form checks below are untouched and still
        # win: a compromised bank page must still be catchable.
        from . import rbi_domains
        _rbi = rbi_domains.classify(domain_of(url)) if url else None

        def hit(key: str, label: str):
            nonlocal score
            if _rbi and _rbi.get('suppress_lexicon'):
                return
            keywords = [k.lower() for k in self.signals.get(key, [])]
            matched = [k for k in keywords if k in t]
            if not matched:
                return
            if not context_gate.should_score(key, matched, text or ""):
                return

            signals.append(label)
            categories.append(key)
            score += int(self.weights.get(key, 10))

        hit("financial_triggers", "Financial trigger (OTP/KYC/account threat)")
        hit("urgency_triggers", "Urgency manipulation")
        hit("authority_impersonation", "Authority impersonation")
        hit("money_ask", "Money/payment request")
        hit("deepfake_phrases", "Deepfake/media manipulation cues")
        hit("upi_scam_cues", "UPI scam cues")
        hit("phone_scam_cues", "Phone/WhatsApp pressure")
        hit("investment_scam", "Investment/returns scam")
        hit("lottery_scam", "Lottery/prize scam")
        hit("loan_scam", "Loan scam / PII harvest")
        hit("pii_request", "Personal info request (Aadhaar/PAN/OTP)")
        hit("marketplace_scam", "Marketplace scam")
        hit("utility_threat", "Utility disconnection threat")
        hit("whatsapp_malware", "WhatsApp malware/APK")
        hit("digital_arrest", "Digital arrest / fake law enforcement")
        hit("sim_swap_fraud", "SIM swap fraud")
        hit("government_portal_fraud", "Fake government portal")
        hit("charity_ngo_fraud", "Charity/NGO fraud")
        hit("crypto_ponzi", "Crypto Ponzi/MLM")
        hit("task_scam", "Task-based earning scam")
        hit("romance_sextortion", "Romance/sextortion")
        hit("job_scam", "Fake job/recruitment")
        hit("courier_parcel_scam", "Courier/parcel scam")
        hit("remote_access_app", "Remote access app request")

        # Link shortener / redirect red flags
        link_kws = [k.lower() for k in self.signals.get("link_red_flags", [])]
        if any(k in t for k in link_kws):
            signals.append("Shortened/redirect link detected")
            score += int(self.weights.get("link_shortener", 15))
            categories.append("link_red_flags")

        # Legitimate pattern discount
        legit_kw = [k.lower() for k in self.signals.get("legitimate_patterns", [])]
        if sum(1 for k in legit_kw if k in t) >= 2:
            signals.append("Legitimate notification pattern detected")
            score = max(score - abs(int(self.weights.get("legitimate_discount", -25))), 0)

        # Extract entities
        extracted = extract_all(text)
        if url:
            extracted["scan_url"] = url

        # URL analysis.
        #
        # The page's OWN domain and the domains it merely LINKS TO are different
        # kinds of evidence and are no longer treated alike. A search results
        # page, a news article or a Wikipedia entry links out constantly; scoring
        # each outbound host as a risk made link-rich legitimate pages look worse
        # the more useful they were. Links are still checked against the
        # blocklists - a link to a known phishing host is real evidence - but a
        # link to an unremarkable domain is not.
        page_dom = domain_of(url) if url else ""
        if _rbi:
            # Stated as a protective fact, and bounded. signal_polarity.js
            # renders protective signals distinctly, so this will not read
            # as a threat in the UI.
            signals.append(_rbi["signal"])
            score = max(0, score - 20)
        link_urls = [u for u in extracted["urls"] if domain_of(u) != page_dom][:10]

        wl_domains = set()
        for key, domains in self.whitelist.items():
            if key.startswith("_") or not isinstance(domains, list):
                continue  # skip the _meta block
            wl_domains.update(d.lower() for d in domains)

        def _whitelisted(d: str) -> bool:
            return any(d == a or d.endswith("." + a) for a in wl_domains)

        def _blocklist_check(u: str, dom: str, where: str):
            """Hard evidence only: named on a threat blocklist."""
            nonlocal score
            if dom in self.scam_domains:
                signals.append(f"Known scam domain{where}: {dom}")
                score += 40
                if "scam_domain" not in categories:
                    categories.append("scam_domain")
            if dom in self.phish_domains:
                signals.append(f"Known phishing domain{where}: {dom}")
                score += 50
                if "phishing_domain" not in categories:
                    categories.append("phishing_domain")

        # --- The page's own domain ---
        if page_dom:
            _blocklist_check(url, page_dom, "")

            for tld in HIGH_RISK_TLDS:
                if page_dom.endswith(tld):
                    signals.append(f"High-risk TLD: {tld}")
                    score += 15
                    break

            if not _whitelisted(page_dom):
                # Impersonating a government host is evidence. Simply not being
                # on our 26-entry whitelist is not - that describes almost every
                # domain on the internet, so it can corroborate suspicion but
                # must never create it.
                if any(page_dom.endswith(s) and page_dom != s
                       for s in ["gov.in", "nic.in", "sbi.co.in"]):
                    signals.append(f"Possible government typosquat: {page_dom}")
                    score += 30
                elif "." in page_dom and score > 0:
                    signals.append(f"Domain not in the verified list: {page_dom}")
                    score += 5

            if url.startswith("http://") and not url.startswith("http://localhost"):
                signals.append("Insecure HTTP connection")
                score += 5

        # --- Domains this page links to ---
        for u in link_urls:
            dom = domain_of(u)
            if not dom:
                continue
            _blocklist_check(u, dom, " linked")
            for tld in HIGH_RISK_TLDS:
                if dom.endswith(tld):
                    signals.append(f"Link to high-risk TLD: {tld}")
                    score += 10
                    break

        # Phone/UPI/PII presence.
        #
        # These are CORROBORATORS, not accusations. Every company contact page
        # lists a phone number and most list an email; a merchant page shows a
        # UPI handle legitimately. They only add weight once the content has
        # already raised something, which is the `score > 0` guard.
        if score > 0:
            if extracted["phones"]:
                signals.append(f"Contains {len(extracted['phones'])} phone number(s)")
                score += 8
            if extracted["upi"]:
                signals.append(f"Contains {len(extracted['upi'])} UPI ID(s)")
                score += 10
        if extracted["aadhaar"]:
            signals.append(f"Contains Aadhaar-like number(s)")
            score += 12
        if extracted["pan"]:
            signals.append(f"Contains PAN number(s)")
            score += 10

        # Live threat feed lookup (URLs only - non-blocking best-effort)
        feed_urls = ([url] if url else []) + link_urls
        if feed_urls and not any(u.startswith("http://localhost") for u in feed_urls[:3]):
            try:
                from . import threat_feeds
                for u in feed_urls[:3]:
                    feed = threat_feeds.check_url(u)
                    if feed and feed.is_threat:
                        signals.append(f"Threat feed hit: {', '.join(feed.threat_types)} ({', '.join(feed.feeds_checked)})")
                        score += 40
                        for tt in feed.threat_types:
                            if tt not in categories:
                                categories.append(f"feed:{tt}")
                        break  # one hit is enough
            except Exception:
                pass  # fail-open: feeds unavailable = continue without

        # Behavioural lane - the structure of the message, not its vocabulary.
        #
        # The keyword categories above are substring-matched, so they miss ordinary
        # grammatical variation ("working from home" != "work from home"). A real
        # task-scam message hit none of the 24 categories and scored 8/100 risk.
        # This lane scores what the text DOES: what it promises, what it asks for
        # first, and how it escalates. Fail-open - never blocks a verdict.
        behavior_dict = None
        try:
            from . import behavior_lane
            beh = behavior_lane.analyze(text)
            behavior_dict = beh.to_dict()
            if beh.trust_penalty > 0:
                score += beh.trust_penalty
                signals.extend(behavior_lane.top_signals(beh))
                if beh.band in ("moderate", "strong", "severe") and "behavioral_manipulation" not in categories:
                    categories.append("behavioral_manipulation")
        except Exception as e:
            logger.debug("behaviour lane unavailable (fail-open): %s", e)

        score, note = context_gate.apply_corroboration_cap(score, categories)
        if note:
            signals.append(note)

        score = min(score, 100)
        ms = round((time.perf_counter() - start) * 1000, 2)

        return L0Result(
            score=score,
            signals=signals,
            categories=categories,
            extracted=extracted,
            processing_ms=ms,
            behavior=behavior_dict,
        )


# ---------------------------------------------------------------------------
# L1: Local LLM analysis (private, free, fast on M4)
# ---------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("SCAMGATE_MODEL", "phisherman-guard")

L1_SYSTEM = """You are ScamGate, a security analyst AI. Analyze the input for:
1. Scam indicators (financial fraud, phishing, social engineering)
2. Manipulation tactics (urgency, authority spoofing, fear)
3. Misinformation signals (fake news, misleading claims)
4. Malware indicators (suspicious links, APK downloads, remote access)

Respond in EXACT JSON format:
{"verdict":"safe|suspicious|scam|phishing|malware|manipulation","confidence":0.0-1.0,"reasoning":"one line","recommendations":["action1","action2"]}

Be decisive. If it looks like a scam, say so. If it's clean, say safe."""


class L1LocalLLM:
    """Local Ollama-based analysis."""

    def __init__(self, model: str = OLLAMA_MODEL, url: str = OLLAMA_URL):
        self.model = model
        self.url = url

    def available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.url}/api/tags")
            req.add_header("User-Agent", "ScamGate/1.0")
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read())
                models = [m["name"].split(":")[0] for m in data.get("models", [])]
                return self.model.split(":")[0] in models
        except Exception:
            return False

    def analyze(self, text: str, l0: L0Result) -> L1Result:
        start = time.perf_counter()
        context = f"L0 signals: {', '.join(l0.signals[:5])}\nL0 score: {l0.score}/100\n\nContent to analyze:\n{text[:3000]}"

        try:
            payload = json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": L1_SYSTEM},
                    {"role": "user", "content": context},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 200},
            }).encode()

            req = urllib.request.Request(
                f"{self.url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "ScamGate/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())

            content = resp.get("message", {}).get("content", "")
            # Parse JSON from response
            try:
                # Find JSON in response
                start_idx = content.find("{")
                end_idx = content.rfind("}") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    parsed = json.loads(content[start_idx:end_idx])
                else:
                    parsed = {"verdict": "suspicious", "confidence": 0.5, "reasoning": content[:200]}
            except json.JSONDecodeError:
                parsed = {"verdict": "suspicious", "confidence": 0.5, "reasoning": content[:200]}

            ms = round((time.perf_counter() - start) * 1000, 2)
            return L1Result(
                verdict=parsed.get("verdict", "suspicious"),
                confidence=float(parsed.get("confidence", 0.5)),
                reasoning=parsed.get("reasoning", ""),
                recommendations=parsed.get("recommendations", []),
                processing_ms=ms,
            )
        except Exception as e:
            ms = round((time.perf_counter() - start) * 1000, 2)
            logger.warning("L1 analysis failed: %s", e)
            return L1Result(
                verdict="error",
                confidence=0.0,
                reasoning=f"L1 unavailable: {str(e)[:80]}",
                processing_ms=ms,
            )


# ---------------------------------------------------------------------------
# L2: Cloud API deep analysis (Groq -> DeepSeek fallback)
# ---------------------------------------------------------------------------
L2_SYSTEM = """You are ScamGate Deep Analyzer. Perform thorough security analysis:

1. Identify the EXACT type of threat (KYC fraud, lottery scam, phishing, etc.)
2. Explain the attack vector and social engineering technique used
3. Assess the sophistication level (amateur/intermediate/advanced)
4. Provide specific, actionable safety recommendations
5. If this involves an Indian context (UPI, Aadhaar, etc.), apply India-specific knowledge

Respond in JSON:
{"verdict":"safe|suspicious|scam|phishing|malware|manipulation","confidence":0.0-1.0,"threat_type":"specific type","analysis":"detailed explanation","recommendations":["specific action 1","specific action 2","specific action 3"]}"""


class L2CloudAPI:
    """Cloud API for deep analysis — Groq primary, DeepSeek fallback."""

    def __init__(self):
        self.providers = []
        self._load_providers()

    def _load_providers(self):
        # Try secrets_loader first
        try:
            sys.path.insert(0, str(Path.home() / ".mirrordna" / "lib"))
            from secrets_loader import get_secret
            groq = get_secret("GROQ_API_KEY")
            deepseek = get_secret("DEEPSEEK_API_KEY")
            mistral = get_secret("MISTRAL_API_KEY")
            openrouter = get_secret("OPENROUTER_API_KEY")
        except Exception:
            groq = os.environ.get("GROQ_API_KEY", "")
            deepseek = os.environ.get("DEEPSEEK_API_KEY", "")
            mistral = os.environ.get("MISTRAL_API_KEY", "")
            openrouter = os.environ.get("OPENROUTER_API_KEY", "")

        if groq:
            self.providers.append({
                "name": "groq", "url": "https://api.groq.com/openai/v1/chat/completions",
                "key": groq, "model": "llama-3.3-70b-versatile",
            })
        if deepseek:
            self.providers.append({
                "name": "deepseek", "url": "https://api.deepseek.com/chat/completions",
                "key": deepseek, "model": "deepseek-chat",
            })
        if mistral:
            self.providers.append({
                "name": "mistral", "url": "https://api.mistral.ai/v1/chat/completions",
                "key": mistral, "model": "mistral-small-latest",
            })
        if openrouter:
            self.providers.append({
                "name": "openrouter", "url": "https://openrouter.ai/api/v1/chat/completions",
                "key": openrouter, "model": "google/gemini-2.5-flash-lite",
            })

    def available(self) -> bool:
        return len(self.providers) > 0

    def analyze(self, text: str, l0: L0Result, l1: L1Result | None = None) -> L2Result:
        start = time.perf_counter()
        context_parts = [f"L0 score: {l0.score}/100, signals: {', '.join(l0.signals[:5])}"]
        if l1 and l1.verdict != "error":
            context_parts.append(f"L1 verdict: {l1.verdict} ({l1.confidence:.0%})")
        context_parts.append(f"\nContent:\n{text[:4000]}")
        user_msg = "\n".join(context_parts)

        for provider in self.providers:
            try:
                payload = json.dumps({
                    "model": provider["model"],
                    "messages": [
                        {"role": "system", "content": L2_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 500,
                    "temperature": 0.1,
                }).encode()

                req = urllib.request.Request(
                    provider["url"], data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {provider['key']}",
                        "User-Agent": "ScamGate/1.0",
                    },
                )
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                    resp = json.loads(r.read())

                content = resp["choices"][0]["message"]["content"]
                try:
                    si = content.find("{")
                    ei = content.rfind("}") + 1
                    parsed = json.loads(content[si:ei]) if si >= 0 else {}
                except (json.JSONDecodeError, ValueError):
                    parsed = {"verdict": "suspicious", "analysis": content[:300]}

                ms = round((time.perf_counter() - start) * 1000, 2)
                return L2Result(
                    verdict=parsed.get("verdict", "suspicious"),
                    confidence=float(parsed.get("confidence", 0.7)),
                    analysis=parsed.get("analysis", ""),
                    threat_type=parsed.get("threat_type", ""),
                    recommendations=parsed.get("recommendations", []),
                    provider=provider["name"],
                    processing_ms=ms,
                )
            except Exception as e:
                logger.warning("L2 %s failed: %s", provider["name"], e)
                continue

        ms = round((time.perf_counter() - start) * 1000, 2)
        return L2Result(
            verdict="error", confidence=0.0,
            analysis="All cloud providers failed",
            processing_ms=ms,
        )


# ---------------------------------------------------------------------------
# ScamGate: The Orchestrator
# ---------------------------------------------------------------------------
# Escalation thresholds
L0_ESCALATE_MIN = 20   # Escalate to L1 if L0 score >= this
L0_ESCALATE_MAX = 70   # Always escalate to L1 if score in ambiguous range
L1_ESCALATE_THRESHOLD = 0.6  # Escalate to L2 if L1 confidence < this or verdict is scam/phishing


class ScamGate:
    """
    The ultimate scam detection orchestrator.

    Three tiers:
      L0: Pattern match (0ms, free, deterministic)
      L1: Local LLM phi4 (1-3s, free, private)
      L2: Cloud API Groq/DeepSeek (2-5s, paid, deep)

    Usage:
        gate = ScamGate()
        verdict = gate.scan("Your KYC is expiring! Click here to update: http://sbi-update.top/kyc")
        print(verdict.trust_score, verdict.verdict, verdict.signals)
    """

    def __init__(self, auto_escalate: bool = True, max_tier: int = 2, skip_l1: bool = True):
        self.l0 = L0PatternDetector()
        self.l1 = L1LocalLLM()
        self.l2 = L2CloudAPI()
        self.auto_escalate = auto_escalate
        self.max_tier = max_tier  # 0=pattern only, 1=+local LLM, 2=+cloud
        self.skip_l1 = skip_l1  # Skip L1 (local LLM too slow for real-time)
        self.history: deque[dict] = deque(maxlen=500)
        self._stats = {"l0_calls": 0, "l1_calls": 0, "l2_calls": 0, "scams_caught": 0}

    def scan(self, text: str, url: str = "", force_tier: int = -1) -> ScamGateVerdict:
        """
        Scan text/URL for threats.

        Args:
            text: Content to scan (message, page text, SMS, etc.)
            url: Optional URL to check against blocklists
            force_tier: Force analysis up to this tier (-1 = auto)

        Returns:
            ScamGateVerdict with trust score, signals, and recommendations
        """
        overall_start = time.perf_counter()
        tiers_used = []
        input_hash = hashlib.sha256((text + url).encode()).hexdigest()[:16]

        # === L0: Pattern detection (always runs) ===
        l0 = self.l0.detect(text, url)
        self._stats["l0_calls"] += 1
        tiers_used.append("L0:pattern")

        l1_result = None
        l2_result = None
        target_tier = force_tier if force_tier >= 0 else self.max_tier

        # === L1: Local LLM (if needed - skipped by default, too slow for real-time) ===
        should_l1 = (
            target_tier >= 1
            and not self.skip_l1
            and self.auto_escalate
            and (L0_ESCALATE_MIN <= l0.score <= L0_ESCALATE_MAX or force_tier >= 1)
            and self.l1.available()
        )

        if should_l1:
            l1_result = self.l1.analyze(text, l0)
            self._stats["l1_calls"] += 1
            tiers_used.append(f"L1:{self.l1.model}")

        # === L2: Cloud API (if needed) ===
        should_l2 = (
            target_tier >= 2
            and self.auto_escalate
            and self.l2.available()
            and (
                force_tier >= 2
                or l0.score >= 70
                or (L0_ESCALATE_MIN <= l0.score < 70 and self.skip_l1)  # L0 ambiguous + L1 skipped -> go to L2
                or (l1_result and l1_result.verdict in ("scam", "phishing", "malware") and l1_result.confidence < L1_ESCALATE_THRESHOLD)
                or (l1_result and l1_result.confidence < 0.4)
            )
        )

        if should_l2:
            l2_result = self.l2.analyze(text, l0, l1_result)
            self._stats["l2_calls"] += 1
            tiers_used.append(f"L2:{l2_result.provider}")

        # === Merge verdicts ===
        verdict = self._merge(l0, l1_result, l2_result)
        total_ms = round((time.perf_counter() - overall_start) * 1000, 2)

        # Build final result
        result = ScamGateVerdict(
            trust_score=max(0, 100 - verdict["score"]),
            risk_level=verdict["risk_level"],
            verdict=verdict["verdict"],
            confidence=verdict["confidence"],
            signals=l0.signals + (l1_result.recommendations if l1_result and l1_result.verdict != "error" else []),
            categories=l0.categories,
            recommendations=verdict["recommendations"],
            extracted=l0.extracted,
            tiers_used=tiers_used,
            behavior=l0.behavior,
            l0=asdict(l0),
            l1=asdict(l1_result) if l1_result else None,
            l2=asdict(l2_result) if l2_result else None,
            processing_ms=total_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_hash=input_hash,
        )

        if result.verdict in ("scam", "phishing", "malware"):
            self._stats["scams_caught"] += 1

        self.history.appendleft(result.to_dict())
        return result

    def _merge(self, l0: L0Result, l1: L1Result | None, l2: L2Result | None) -> dict:
        """Merge tier results into unified verdict."""
        score = l0.score
        verdict = "clean"
        confidence = 0.0
        recommendations = []

        # L0 verdict
        if score >= 75:
            verdict = "scam"
            confidence = min(0.5 + score / 200, 0.85)
        elif score >= 45:
            verdict = "suspicious"
            confidence = 0.4 + score / 300
        else:
            verdict = "clean"
            confidence = max(0.6, 1.0 - score / 100)

        # Behavioural promotion.
        #
        # A "severe" band is not a pile of coincidental phrases - it means several
        # tactics matched AND at least one documented combo fired (a specific payout
        # attached to trivial work, a bonus followed by a fee, a locked withdrawal).
        # That is a recognised fraud structure, so it should read as "scam" rather
        # than "suspicious" even when no keyword, domain or feed lit up. Requiring a
        # combo is what keeps this from firing on wordy marketing copy, which can
        # accumulate tactics but does not form these pairings.
        beh = l0.behavior or {}
        if beh.get("band") == "severe" and len(beh.get("combos", [])) >= 1 and verdict == "suspicious":
            verdict = "scam"
            confidence = max(confidence, 0.7)

        # L1 override (if available and not error)
        if l1 and l1.verdict != "error":
            if l1.verdict in ("scam", "phishing", "malware") and l1.confidence > 0.6:
                verdict = l1.verdict
                score = max(score, 70)
                confidence = max(confidence, l1.confidence)
            elif l1.verdict == "safe" and l1.confidence > 0.8 and score < 40:
                score = min(score, 20)
                confidence = max(confidence, l1.confidence)
                verdict = "clean"
            elif l1.verdict == "manipulation":
                verdict = "manipulation"
                score = max(score, 50)
            recommendations.extend(l1.recommendations)

        # L2 override (highest authority)
        if l2 and l2.verdict != "error":
            if l2.verdict in ("scam", "phishing", "malware"):
                verdict = l2.verdict
                score = max(score, 80)
                confidence = max(confidence, l2.confidence)
            elif l2.verdict == "safe" and l2.confidence > 0.85:
                score = min(score, 15)
                confidence = l2.confidence
                verdict = "clean"
            elif l2.verdict == "manipulation":
                verdict = "manipulation"
                score = max(score, 55)
            recommendations.extend(l2.recommendations)

        # Deduplicate recommendations
        seen = set()
        unique_recs = []
        for r in recommendations:
            if r.lower() not in seen:
                seen.add(r.lower())
                unique_recs.append(r)

        # Default recommendations
        if not unique_recs:
            if score >= 75:
                unique_recs = [
                    "Do not share personal information, OTPs, or payment details.",
                    "Do not click any links or download attachments.",
                    "Report this to cybercrime.gov.in if you're in India.",
                ]
            elif score >= 45:
                unique_recs = [
                    "Verify this through official channels before taking action.",
                    "Do not share sensitive information until verified.",
                ]
            else:
                unique_recs = ["No immediate threat detected. Stay vigilant."]

        # Risk level
        if score >= 75:
            risk_level = "DANGER"
        elif score >= 45:
            risk_level = "WARNING"
        elif score >= 25:
            risk_level = "CAUTION"
        else:
            risk_level = "SAFE"

        return {
            "score": min(score, 100),
            "verdict": verdict,
            "confidence": round(min(confidence, 1.0), 2),
            "risk_level": risk_level,
            "recommendations": unique_recs[:5],
        }

    def stats(self) -> dict:
        return {**self._stats, "history_size": len(self.history)}

    def quick_scan(self, text: str, url: str = "") -> ScamGateVerdict:
        """L0-only scan. Instant, deterministic."""
        return self.scan(text, url, force_tier=0)

    def deep_scan(self, text: str, url: str = "") -> ScamGateVerdict:
        """Force all tiers."""
        return self.scan(text, url, force_tier=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="ScamGate — Ultimate Scam Detection")
    parser.add_argument("text", nargs="?", help="Text to scan")
    parser.add_argument("--url", default="", help="URL to check")
    parser.add_argument("--deep", action="store_true", help="Force deep scan (all tiers)")
    parser.add_argument("--quick", action="store_true", help="Quick scan (L0 only)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    args = parser.parse_args()

    if args.test:
        _run_tests()
        return

    if not args.text and not args.url:
        print("Usage: python scamgate.py 'text to scan' [--url URL] [--deep] [--quick] [--json]")
        print("       python scamgate.py --test")
        sys.exit(1)

    gate = ScamGate()
    text = args.text or ""

    if args.deep:
        result = gate.deep_scan(text, args.url)
    elif args.quick:
        result = gate.quick_scan(text, args.url)
    else:
        result = gate.scan(text, args.url)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        color = {"SAFE": "\033[92m", "CAUTION": "\033[93m", "WARNING": "\033[33m", "DANGER": "\033[91m"}
        reset = "\033[0m"
        c = color.get(result.risk_level, "")
        print(f"\n{c}{'═' * 50}")
        print(f"  ScamGate — Trust Score: {result.trust_score}/100")
        print(f"  Risk: {result.risk_level} | Verdict: {result.verdict}")
        print(f"  Confidence: {result.confidence:.0%} | Tiers: {', '.join(result.tiers_used)}")
        print(f"{'═' * 50}{reset}\n")
        if result.signals:
            print("Signals:")
            for s in result.signals[:8]:
                print(f"  • {s}")
        if result.recommendations:
            print("\nRecommendations:")
            for r in result.recommendations:
                print(f"  → {r}")
        print(f"\n  [{result.processing_ms}ms]")


def _run_tests():
    gate = ScamGate(max_tier=0)  # L0 only for speed
    tests = [
        ("Your KYC is expiring! Update now at http://sbi-update.top/kyc or account will be blocked", "scam", 60),
        ("Congratulations! You won ₹50,00,000 in lucky draw! Claim now!", "scam", 50),
        ("Hi, your Amazon order #12345 has been shipped. Track at amazon.in/track", "clean", 0),
        ("URGENT: Your SIM will be deactivated in 2 hours. Share Aadhaar to verify.", "scam", 60),
        ("Meeting at 3pm tomorrow to discuss Q1 results. See you there.", "clean", 0),
        ("Earn ₹5000 daily from home! No experience needed! Registration fee only ₹500", "scam", 50),
        ("Download this APK to secure your WhatsApp: bit.ly/wa-secure", "scam", 40),
        ("RBI notice: Your account frozen. Call +91-9876543210 immediately.", "scam", 60),
    ]

    passed = 0
    for text, expected_type, min_score in tests:
        result = gate.quick_scan(text)
        is_threat = result.verdict in ("scam", "phishing", "malware", "manipulation", "suspicious")
        expected_threat = expected_type != "clean"

        ok = (is_threat == expected_threat) and result.l0["score"] >= min_score
        status = "PASS" if ok else "FAIL"
        passed += 1 if ok else 0
        print(f"  [{status}] score={result.l0['score']:3d} verdict={result.verdict:12s} | {text[:60]}...")

    print(f"\n  {passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
