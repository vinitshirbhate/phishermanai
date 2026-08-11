"""
ml/features.py - THE single definition of the ML feature set (F-A2, §4.4, NFR-10).

This module is the ONLY place the 24 features are defined. The extension's
`content_script.js` must emit exactly these names, in exactly this order, by
importing the generated `feature_manifest.json`. `eval/parity_test.py` enforces
JS/Python agreement. Two feature definitions must never exist in this codebase.

If you add, rename, or reorder a feature, bump FEATURE_SET_VERSION and
regenerate the manifest:  python -m ml.features --emit
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "ml" / "feature_manifest.json"

FEATURE_SET_VERSION = "fs_v2"

# Ordered feature list. ORDER IS PART OF THE CONTRACT - do not reorder.
FEATURE_NAMES: list[str] = [
    # Lexical (7)
    "url_length",
    "url_entropy",
    "subdomain_count",
    "param_count",
    "has_ip_host",
    "has_punycode",
    "sensitive_keyword_count",
    # DOM structural (10)
    "external_link_ratio",
    "empty_links_ratio",
    "suspicious_form_action",
    "hidden_iframe_count",
    "script_to_content_ratio",
    "password_field_count",
    "input_field_count",
    "meta_refresh_present",
    "external_resource_ratio",
    "dom_nesting_depth",
    # Securities / India (7)
    "upi_id_present",
    "upi_outside_valid_namespace",
    "registration_claim_present",
    "registration_resolves",
    "securities_keyword_density",
    "typosquat_distance_to_intermediary",
    "guaranteed_return_claim_present",
    # Artefact-free domain-string group (18) - see DOMAIN_FEATURE_NAMES below.
    # Computed from the registrable domain ONLY, after stripping "www.", and
    # ignoring scheme, path and query entirely. This is the ONLY group the
    # shipped URL model trains on; see eval/corpus_audit.py for why.
    "host_len",
    "host_entropy",
    "label_count",
    "hyphens",
    "digits",
    "digit_ratio",
    "vowel_ratio",
    "longest_label",
    "tld_len",
    "suspicious_tld",
    "has_ip",
    "brand_token_count",
    "domain_entropy",
    "domain_len",
    "repeated_char_runs",
    "consonant_run_max",
    "has_digit_letter_mix",
]

# The artefact-free set the shipped model uses. 18 features.
#
# `has_punycode` is DELIBERATELY SHARED with the lexical group rather than
# duplicated: it is already computed from the hostname alone, so it carries no
# scheme, path or query information and is artefact-free as it stands. Adding a
# second identically-defined column under a new name would only introduce
# collinearity. That is why FEATURE_NAMES grows by 17 while this group has 18.
DOMAIN_FEATURE_NAMES: list[str] = [
    "host_len", "host_entropy", "label_count", "hyphens", "digits", "digit_ratio",
    "vowel_ratio", "longest_label", "tld_len", "suspicious_tld", "has_ip",
    "has_punycode", "brand_token_count", "domain_entropy", "domain_len",
    "repeated_char_runs", "consonant_run_max", "has_digit_letter_mix",
]

FEATURE_GROUPS = {
    "lexical": FEATURE_NAMES[0:7],
    "dom": FEATURE_NAMES[7:17],
    "securities": FEATURE_NAMES[17:24],
    "domain": DOMAIN_FEATURE_NAMES,
}

# Registrable-domain suffixes needing three labels (public-suffix approximation).
# A full PSL would be a new dependency for marginal gain; this covers the ccTLD
# shapes that actually appear in an India-facing corpus. Documented as an
# approximation rather than presented as exact.
MULTI_LABEL_SUFFIXES = frozenset("""
co.in net.in org.in gen.in firm.in ind.in ac.in edu.in res.in gov.in nic.in mil.in
co.uk org.uk me.uk ac.uk gov.uk net.uk sch.uk ltd.uk plc.uk
com.au net.au org.au edu.au gov.au id.au
co.jp or.jp ne.jp ac.jp go.jp
com.br net.br org.br gov.br
com.cn net.cn org.cn gov.cn edu.cn
com.sg net.sg org.sg edu.sg gov.sg
com.my net.my org.my edu.my gov.my
com.hk com.tw com.mx com.tr com.ar com.pk com.bd com.np com.lk
co.za org.za co.nz org.nz co.kr co.id co.th or.th
com.ph com.vn com.sa com.eg com.ng com.gh com.kw com.qa
co.il org.il com.ua com.pl com.ru
""".split())

# TLDs with a persistently poor abuse reputation (free or near-free registration).
SUSPICIOUS_TLDS = frozenset({
    "tk", "ml", "ga", "cf", "gq", "top", "xyz", "buzz", "click", "link", "work",
    "loan", "download", "review", "country", "stream", "gdn", "racing", "win",
    "bid", "party", "trade", "date", "faith", "science", "cricket", "accountant",
    "men", "rest", "fit", "surf", "monster", "quest", "cyou", "icu", "sbs",
})

# Brand tokens that impersonation URLs graft onto an unrelated registrable
# domain. Their presence in the domain string is signal precisely because the
# genuine brand does not need to put its own name in someone else's domain.
BRAND_TOKENS = frozenset({
    "paytm", "phonepe", "gpay", "googlepay", "bhim", "upi", "npci",
    "sbi", "hdfc", "icici", "axis", "kotak", "yesbank", "pnb", "bob", "canara",
    "zerodha", "groww", "upstox", "angelone", "angelbroking", "sharekhan",
    "motilal", "iifl", "5paisa", "dhan", "kite", "smallcase",
    "nse", "bse", "sebi", "nsdl", "cdsl", "cams", "kfintech", "amfi",
    "aadhaar", "uidai", "incometax", "gst", "epfo", "irctc",
    "amazon", "flipkart", "netflix", "whatsapp", "instagram", "facebook",
    "google", "microsoft", "apple", "paypal",
})

VOWELS = frozenset("aeiou")

SENSITIVE_KEYWORDS = [
    "login", "verify", "otp", "password", "kyc", "aadhaar", "pan", "cvv",
    "upi", "bank", "account", "wallet", "secure", "update", "confirm",
]

SECURITIES_LEXICON = [
    "sebi", "nse", "bse", "demat", "ipo", "trading", "portfolio", "mutual fund",
    "stock", "shares", "broker", "investment", "returns", "profit", "advisory",
    "research analyst", "fpi", "block trade", "allotment", "securities",
]

GUARANTEED_RETURN_RE = re.compile(
    r"\b(assured|guaranteed|risk[\s-]?free|100%\s*safe)\b.{0,30}"
    r"\b(return|returns|profit|gain|income)\b|"
    r"\b(return|returns|profit)\b.{0,20}\b(guaranteed|assured|risk[\s-]?free)\b",
    re.IGNORECASE,
)

# UPI id: something@handle. Reused by securities_identity too, but defined here
# for the standalone feature path.
UPI_RE = re.compile(r"\b[a-z0-9.\-_]{2,}@[a-z][a-z0-9.]{1,}\b", re.IGNORECASE)
IP_HOST_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def registrable_domain(host: str) -> str:
    """
    The registrable domain, with "www." stripped and everything else discarded.

    Deliberately NOT the full host and NOT the URL: scheme, path and query are
    the three collection artefacts in PhiUSIIL (eval/corpus_audit.py), and any
    feature touching them learns URL canonicalisation rather than fraud.
    """
    h = (host or "").lower().strip().strip(".")
    if h.startswith("www."):
        h = h[4:]
    if not h or IP_HOST_RE.match(h):
        return h
    parts = h.split(".")
    if len(parts) <= 2:
        return h
    if ".".join(parts[-2:]) in MULTI_LABEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def domain_string(host: str) -> str:
    """
    The feature input: the hostname with "www." stripped, and NOTHING else.

    Scheme, path and query are discarded because eval/corpus_audit.py shows all
    three are collection artefacts. Subdomains are RETAINED - `label_count` and
    `longest_label` are meaningless on a bare two-label registrable domain, and
    brand-in-subdomain ("paytm.evil.com") is a real impersonation pattern.

    Read §B.0 of eval/REPORT.md before trusting features built on this: subdomain
    depth is itself substantially artefactual in PhiUSIIL, because the legitimate
    class was harvested as canonicalised `www.<domain>` homepages. The audit
    quantifies exactly how much.
    """
    h = (host or "").lower().strip().strip(".")
    return h[4:] if h.startswith("www.") else h


def _is_ascii_letter(c: str) -> bool:
    """ASCII-only on purpose: str.isalpha() is Unicode-aware but the JS mirror in
    background.js is not, and tests/test_feature_parity.py compares at 1e-6."""
    return "a" <= c <= "z" or "A" <= c <= "Z"


def _is_ascii_digit(c: str) -> bool:
    return "0" <= c <= "9"


def _longest_run(s: str, predicate) -> int:
    best = run = 0
    for ch in s:
        run = run + 1 if predicate(ch) else 0
        best = max(best, run)
    return best


def _repeated_char_runs(s: str) -> int:
    """Number of runs of the SAME character of length >= 3 ('gooogle' -> 1)."""
    runs = i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        if j - i >= 3:
            runs += 1
        i = j
    return runs


def domain_features(host: str) -> dict[str, float]:
    """
    The 18 artefact-free features, computed from the registrable domain string.

    Mirrored byte-for-byte by `domainFeatures()` in extension/background.js;
    tests/test_feature_parity.py fails the build on any divergence.
    """
    # `host_*` features span the whole www-stripped host (subdomains included);
    # `domain_*` features describe only the registrable label the owner chose.
    reg = domain_string(host)
    labels = [p for p in reg.split(".") if p] if reg else []
    is_ip = bool(reg and IP_HOST_RE.match(reg))
    registrable = registrable_domain(host)
    reg_labels = [p for p in registrable.split(".") if p] if registrable else []
    sld = "" if is_ip or not reg_labels else reg_labels[0]
    tld = "" if is_ip or not labels else labels[-1]

    letters = [c for c in reg if _is_ascii_letter(c)]
    digit_count = sum(1 for c in reg if _is_ascii_digit(c))
    vowel_count = sum(1 for c in letters if c in VOWELS)

    # NOTE - no round() anywhere in this group, deliberately. Python's round() is
    # banker's rounding and JS toFixed() rounds half away from zero, so a ratio
    # landing exactly on a 5 in the 5th decimal (digit_ratio = 1/32 = 0.03125,
    # entirely reachable) would differ by 1e-4 between the two implementations
    # and break tests/test_feature_parity.py's 1e-6 gate. Unrounded, both sides
    # perform identical IEEE-754 arithmetic and agree to ~1e-16.
    return {
        "host_len": float(len(reg)),
        "host_entropy": _shannon_entropy(reg),
        "label_count": float(len(labels)),
        "hyphens": float(reg.count("-")),
        "digits": float(digit_count),
        "digit_ratio": (digit_count / len(reg)) if reg else 0.0,
        "vowel_ratio": (vowel_count / len(letters)) if letters else 0.0,
        "longest_label": float(max((len(p) for p in labels), default=0)),
        "tld_len": float(len(tld)),
        "suspicious_tld": 1.0 if tld in SUSPICIOUS_TLDS else 0.0,
        "has_ip": 1.0 if is_ip else 0.0,
        # Over the whole host: "paytm.evil.com" grafts the brand onto a subdomain,
        # which is exactly the pattern worth catching.
        "brand_token_count": float(sum(1 for b in BRAND_TOKENS if b in reg)),
        "domain_entropy": _shannon_entropy(sld),
        "domain_len": float(len(sld)),
        "repeated_char_runs": float(_repeated_char_runs(reg)),
        "consonant_run_max": float(_longest_run(
            sld, lambda c: _is_ascii_letter(c) and c not in VOWELS)),
        "has_digit_letter_mix": 1.0 if (any(_is_ascii_digit(c) for c in sld)
                                        and any(_is_ascii_letter(c) for c in sld)) else 0.0,
    }


class _DomStats(HTMLParser):
    """Single-pass DOM statistics from an HTML string (stdlib only)."""

    def __init__(self, page_host: str):
        super().__init__(convert_charrefs=True)
        self.page_host = page_host
        self.link_total = 0
        self.link_external = 0
        self.link_empty = 0
        self.suspicious_form_action = 0
        self.hidden_iframe = 0
        self.script_count = 0
        self.password_fields = 0
        self.input_fields = 0
        self.meta_refresh = 0
        self.resource_total = 0
        self.resource_external = 0
        self.text_len = 0
        self._depth = 0
        self.max_depth = 0
        self._void = {"br", "img", "input", "meta", "link", "hr", "area", "base"}

    def _is_external(self, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        return bool(host) and self.page_host not in host and host not in self.page_host

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in self._void:
            self._depth += 1
            self.max_depth = max(self.max_depth, self._depth)
        if tag == "a":
            self.link_total += 1
            href = (a.get("href") or "").strip()
            if not href or href in ("#", "javascript:void(0)"):
                self.link_empty += 1
            elif self._is_external(href):
                self.link_external += 1
        elif tag == "form":
            action = (a.get("action") or "").strip()
            if action and self._is_external(action):
                self.suspicious_form_action = 1
        elif tag == "iframe":
            style = (a.get("style") or "").lower()
            if a.get("hidden") is not None or "display:none" in style or a.get("width") in ("0", "1"):
                self.hidden_iframe += 1
        elif tag == "script":
            self.script_count += 1
        elif tag == "input":
            self.input_fields += 1
            if (a.get("type") or "").lower() == "password":
                self.password_fields += 1
        elif tag == "meta":
            if (a.get("http-equiv") or "").lower() == "refresh":
                self.meta_refresh = 1
        elif tag in ("img", "link", "source"):
            src = (a.get("src") or a.get("href") or "").strip()
            if src:
                self.resource_total += 1
                if self._is_external(src):
                    self.resource_external += 1

    def handle_endtag(self, tag):
        if tag not in self._void and self._depth > 0:
            self._depth -= 1

    def handle_data(self, data):
        self.text_len += len(data.strip())


def extract(page: dict) -> dict[str, float]:
    """
    Extract the 24 features from a normalised page dict:
        { url, html, text, securities? }
    `securities` (optional) is the resolved securities_identity result; when
    absent, the two register-dependent features fall back to text heuristics so
    this extractor still runs standalone (training/eval).

    Returns a name->float dict covering exactly FEATURE_NAMES.
    """
    url = page.get("url") or ""
    html = page.get("html") or ""
    text = (page.get("text") or "").strip()
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.hostname or ""

    # --- Lexical ---
    subdomain_count = max(0, host.count(".") - 1) if host else 0
    f = {
        "url_length": float(len(url)),
        "url_entropy": round(_shannon_entropy(url), 4),
        "subdomain_count": float(subdomain_count),
        "param_count": float(parsed.query.count("=") if parsed.query else 0),
        "has_ip_host": 1.0 if IP_HOST_RE.match(host) else 0.0,
        "has_punycode": 1.0 if "xn--" in host else 0.0,
        "sensitive_keyword_count": float(
            sum(1 for k in SENSITIVE_KEYWORDS if k in url.lower() or k in text.lower())
        ),
    }

    # --- DOM structural ---
    dom = _DomStats(host)
    if html:
        try:
            dom.feed(html)
        except Exception:  # malformed HTML must never crash extraction
            pass
    lt = dom.link_total or 1
    content_units = max(1, dom.text_len // 40)  # coarse "content node" proxy
    res_total = dom.resource_total or 1
    f.update({
        "external_link_ratio": round(dom.link_external / lt, 4),
        "empty_links_ratio": round(dom.link_empty / lt, 4),
        "suspicious_form_action": float(dom.suspicious_form_action),
        "hidden_iframe_count": float(dom.hidden_iframe),
        "script_to_content_ratio": round(dom.script_count / content_units, 4),
        "password_field_count": float(dom.password_fields),
        "input_field_count": float(dom.input_fields),
        "meta_refresh_present": float(dom.meta_refresh),
        "external_resource_ratio": round(dom.resource_external / res_total, 4),
        "dom_nesting_depth": float(dom.max_depth),
    })

    # --- Securities / India ---
    low = f"{url}\n{text}".lower()
    tokens = re.findall(r"[a-z0-9]+", low)
    total_tokens = len(tokens) or 1
    sec_hits = sum(low.count(term) for term in SECURITIES_LEXICON)
    upi_ids = UPI_RE.findall(text) + UPI_RE.findall(url)

    sec = page.get("securities") or {}
    reg_present = bool(sec.get("claims")) if sec else bool(re.search(r"\bIN[AHZPM]\d{6,}\b|\bARN-\d{4,}\b", text, re.IGNORECASE))
    reg_resolves = 1.0 if (sec and sec.get("state") == "valid") else 0.0
    upi_outside = 0.0
    if sec and sec.get("upi"):
        upi_outside = 1.0 if any(not u.get("in_valid_namespace") for u in sec["upi"]) else 0.0
    elif upi_ids:
        upi_outside = 0.0 if any("@valid" in u.lower() for u in upi_ids) else 1.0

    f.update({
        "upi_id_present": 1.0 if upi_ids else 0.0,
        "upi_outside_valid_namespace": upi_outside,
        "registration_claim_present": 1.0 if reg_present else 0.0,
        "registration_resolves": reg_resolves,
        "securities_keyword_density": round(sec_hits / total_tokens, 4),
        "typosquat_distance_to_intermediary": float(page.get("typosquat_distance", 99)),
        "guaranteed_return_claim_present": 1.0 if GUARANTEED_RETURN_RE.search(low) else 0.0,
    })

    # --- Artefact-free domain-string group (the shipped URL model's inputs) ---
    f.update(domain_features(host))

    # Guarantee: exactly the contracted keys, in order.
    return {name: float(f[name]) for name in FEATURE_NAMES}


def to_vector(page: dict) -> list[float]:
    feats = extract(page)
    return [feats[name] for name in FEATURE_NAMES]


def build_manifest() -> dict:
    return {
        "feature_set_version": FEATURE_SET_VERSION,
        "count": len(FEATURE_NAMES),
        "feature_names": FEATURE_NAMES,
        "groups": FEATURE_GROUPS,
        "domain_feature_names": DOMAIN_FEATURE_NAMES,
        "note": "Single source of truth is ml/features.py. content_script.js must emit these names in this order.",
        "shipped_url_model_group": (
            "domain — 18 artefact-free features from the registrable domain string only. "
            "Scheme, www-prefix, path and query are excluded by design: in PhiUSIIL all "
            "three are collection artefacts (see eval/corpus_audit.py), and a model using "
            "them learns URL canonicalisation rather than fraud."
        ),
    }


def emit_manifest(path: Path = MANIFEST_PATH) -> Path:
    path.write_text(json.dumps(build_manifest(), indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feature definition / manifest tool")
    parser.add_argument("--emit", action="store_true", help="Write feature_manifest.json")
    args = parser.parse_args()
    if args.emit:
        p = emit_manifest()
        print(f"Wrote {p.relative_to(ROOT)} ({len(FEATURE_NAMES)} features, {FEATURE_SET_VERSION})")
    else:
        print(f"{len(FEATURE_NAMES)} features @ {FEATURE_SET_VERSION}")
        for i, n in enumerate(FEATURE_NAMES):
            print(f"  {i:2d}  {n}")
