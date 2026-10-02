"""CHOKEPOINT 4 -- DELIVERY. Is the link, app or domain authentic?

Detects the vehicle rather than the message: lookalike domains, freshly
registered domains, APK sideloads, shorteners and punycode.

The lookalike test is the important one. A fraudster who registers
canarabank-dividends.co.in can configure SPF, DKIM and DMARC perfectly and pass
every authentication check in existence, because those protocols verify that
mail genuinely came from the domain it claims -- not that the domain has any
right to the name it is using. Comparing against the domain map is what closes
that gap.

OFFLINE GUARANTEE
-----------------
Nothing here touches the network at request time. WHOIS ages and shortener
expansions are read from tables populated during development; a cache miss
yields "unknown", never a blocking lookup and never a guess.
"""

from __future__ import annotations

import functools
import logging
import re
from datetime import datetime, timezone

import tldextract
from rapidfuzz.distance import Levenshtein
from sqlalchemy import select

from core.chokepoints.base import DELIVERY, CheckResult, Reason
from core.db import session_scope
from core.models import DomainMap, ShortenerCache, WhoisCache
from core.textnorm import fold_homoglyphs, normalise_domain

log = logging.getLogger("phishermanai.delivery")

URL_RE = re.compile(
    r"""(?xi)
    \b(
        (?:https?://|www\.)                  # scheme or www
        [^\s<>"'\)\]]+
      | (?<![@\w.])                          # bare domain, not part of an e-mail
        [a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?
        (?:\.[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)+
        \.(?:com|in|co\.in|net|org|xyz|top|online|club|site|info|biz|app|io|me|
             live|shop|store|link|click|vip|fun|icu|cc|ru|tk|ml|ga|cf|gq|pro|
             work|website|space|host|press|pw|su|cn|ph|monster)
        (?:/[^\s<>"'\)\]]*)?
    )""",
)

# Registered less than this many days ago is a strong fraud signal: legitimate
# corporate infrastructure is years old, phishing domains are days old.
NEW_DOMAIN_DAYS = 90

# TLDs disproportionately used for abuse, largely because they are free or
# near-free to register in bulk.
ELEVATED_RISK_TLDS = {
    "xyz", "top", "online", "club", "site", "click", "link", "vip", "fun",
    "icu", "tk", "ml", "ga", "cf", "gq", "pw", "su", "monster", "work",
    "website", "space", "host", "press", "cc", "shop", "store", "live",
}

URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "cutt.ly", "rb.gy", "shorturl.at", "rebrand.ly", "bl.ink", "short.io",
    "tiny.cc", "t.ly", "s.id", "u.to", "clck.ru", "surl.li", "shrtco.de",
    "wa.me", "t.me", "linktr.ee",
}

# Affixes bolted onto a real brand to manufacture a plausible-looking domain.
SUSPICIOUS_AFFIXES = (
    "secure", "verify", "verification", "login", "signin", "account", "update",
    "india", "official", "support", "help", "helpdesk", "service", "services",
    "dividend", "dividends", "refund", "claim", "claims", "kyc", "alert",
    "care", "portal", "online", "web", "app", "pay", "payment", "wallet",
    "invest", "investor", "trading", "trade", "demat", "bonus", "reward",
)

APK_RE = re.compile(r"https?://[^\s<>\"']+\.apk\b|\b[\w\-]+\.apk\b", re.I)

# A URL carrying the victim's own e-mail address as a plaintext parameter.
#
# Legitimate services identify a recipient with an opaque token precisely so the
# address is not exposed in a link. Phishing kits pass the address in the clear
# because the fake login page uses it to pre-fill the username field, which makes
# the page look personalised and convincing.
#
# This single rule would have caught the LinkedIn-impersonation miss on its own:
#   https://manoranjannurseryschoolnoida.in/fram/flames.php?email=jose@monkey.org
#
# False-positive risk is close to zero: a real unsubscribe or preferences link
# uses a hash or an account id, not a bare address.
CREDENTIAL_IN_URL_RE = re.compile(
    r"[?&](email|e|mail|user|usr|username|login|id|account|acc)="
    r"[^&\s]*(?:@|%40)",
    re.I,
)


@functools.lru_cache(maxsize=1)
def _known_domains() -> list[tuple[str, str, str]]:
    """(domain, entity_name, relationship) for every mapped domain."""
    try:
        with session_scope() as session:
            return [
                (d, n, r) for d, n, r in session.execute(
                    select(DomainMap.domain, DomainMap.entity_name, DomainMap.relationship_type)
                )
            ]
    except Exception:  # noqa: BLE001
        return []


def reset_domain_cache() -> None:
    _known_domains.cache_clear()


@functools.lru_cache(maxsize=1)
def _extractor() -> tldextract.TLDExtract:
    """The process-wide suffix-list extractor, with a no-filesystem fallback.

    tldextract's module-level `extract()` takes a filelock inside its cache
    directory before it will even READ that cache. In a container running as a
    non-root user against a root-owned cache, that raises PermissionError on
    every single domain parse, which propagates all the way up and 500s the
    whole /verify path -- a deployment detail taking out the engine.

    So probe the cache once, and on any failure fall back to the suffix list
    bundled inside the package, which needs no cache directory and no network.
    Slightly staler, but this is exactly the list the docstring on safe_domain
    already assumes, and a missing new gTLD makes us say nothing rather than
    say something wrong.
    """
    cached = tldextract.TLDExtract()
    try:
        cached("example.co.uk")
        return cached
    except Exception as exc:  # noqa: BLE001 - any cache failure, not just perms
        log.warning("tldextract cache unusable (%s); using the bundled suffix list", exc)
        return tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def registrable_domain(url_or_domain: str) -> str:
    """eTLD+1, e.g. 'canarabank-dividends.co.in' from a full URL."""
    ext = _extractor()(url_or_domain)
    if not ext.domain:
        return ""
    return ".".join(p for p in (ext.domain, ext.suffix) if p)


def safe_domain(url_or_domain: str) -> str | None:
    """Registrable domain, or None when the input does not parse to a real one.

    A PARSE FAILURE IS NOT A FINDING. "www.cdslindia.com-" (a trailing hyphen
    from wrapped text) parsed to a "domain" called `com-`, and the engine then
    emitted two substantive findings about it -- DOMAIN_AGE_UNKNOWN and
    DOMAIN_NOT_IN_REGISTRY -- on a genuine CDSL statement.

    The suffix is validated against the Public Suffix List that tldextract
    bundles. Anything whose suffix is absent from the PSL is not a domain we
    can reason about, so we return None and the caller emits nothing at all.
    """
    if not url_or_domain:
        return None
    ext = _extractor()(url_or_domain.strip())
    # An empty suffix means the PSL did not recognise the TLD.
    if not ext.domain or not ext.suffix:
        return None
    domain = f"{ext.domain}.{ext.suffix}".lower()
    # Belt and braces: reject anything still structurally impossible.
    if not re.fullmatch(r"[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z0-9\-]{2,63})+", domain):
        return None
    return domain


# Trailing characters that are punctuation in prose but legal in a URL, so they
# must be trimmed before parsing: "visit example.com." and "example.com-" are
# sentence artefacts, not domains.
_URL_TRAILING = ".,;:!?)]}>'\"-_~"


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    seen: list[str] = []
    for m in URL_RE.finditer(text):
        url = m.group(1).rstrip(_URL_TRAILING)
        if url and url not in seen:
            seen.append(url)
    return seen


def _homoglyph_skeleton(domain: str) -> str:
    """Collapse visually confusable sequences so 'rn' and 'm' compare equal."""
    skeleton = fold_homoglyphs(domain.lower())
    skeleton = skeleton.replace("rn", "m").replace("vv", "w")
    skeleton = skeleton.replace("0", "o").replace("1", "l").replace("5", "s")
    return re.sub(r"[^a-z]", "", skeleton)


def find_lookalike(domain: str) -> dict | None:
    """Compare a domain against the known-good map.

    Three independent tests, because fraudsters use all three:
      * edit distance <= 2   (canarabankk.com)
      * homoglyph skeleton   (canarabar1k.com, Cyrillic 'а')
      * brand + affix        (canarabank-dividends.co.in)
    """
    domain = normalise_domain(domain)
    if not domain:
        return None

    known = _known_domains()
    if not known:
        return None
    known_domains = {d for d, _, _ in known}
    if domain in known_domains:
        return None

    base = domain.split(".")[0]
    base_skeleton = _homoglyph_skeleton(base)

    best: dict | None = None
    for known_domain, entity_name, _rel in known:
        known_base = known_domain.split(".")[0]

        distance = Levenshtein.distance(base, known_base)
        if 0 < distance <= 2 and len(known_base) >= 5:
            candidate = {
                "matched": known_domain, "entity": entity_name,
                "technique": "EDIT_DISTANCE", "distance": distance,
            }
            if best is None or distance < best.get("distance", 99):
                best = candidate

        if base_skeleton and base_skeleton == _homoglyph_skeleton(known_base) and base != known_base:
            return {"matched": known_domain, "entity": entity_name,
                    "technique": "HOMOGLYPH", "distance": 0}

        # Brand plus an affix: the brand must appear as a delimited token so
        # 'canarabank-dividends' matches but 'bankofindia' does not match 'bank'.
        if len(known_base) >= 5 and known_base in base and base != known_base:
            remainder = base.replace(known_base, "", 1).strip("-._")
            if any(affix in remainder for affix in SUSPICIOUS_AFFIXES) or remainder in ("", "-"):
                return {"matched": known_domain, "entity": entity_name,
                        "technique": "BRAND_PLUS_AFFIX", "distance": len(remainder),
                        "affix": remainder}
    return best


def _whois_age_days(domain: str) -> tuple[int | None, dict]:
    """Age in days from the WHOIS cache. Never resolves live."""
    try:
        with session_scope() as session:
            row = session.execute(
                select(WhoisCache).where(WhoisCache.domain == domain)
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return None, {"cache": "unavailable"}

    if row is None:
        return None, {"cache": "miss", "domain": domain}
    if not row.creation_date:
        return None, {"cache": "hit_no_creation_date", "domain": domain}

    created = row.creation_date
    if created.tzinfo:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)
    age = (datetime.utcnow() - created).days
    return age, {
        "cache": "hit", "created": created.date().isoformat(),
        "registrar": row.registrar, "age_days": age,
    }


def _expand_shortener(url: str) -> str | None:
    try:
        with session_scope() as session:
            row = session.execute(
                select(ShortenerCache).where(ShortenerCache.short_url == url)
            ).scalar_one_or_none()
            return row.expanded_url if row else None
    except Exception:  # noqa: BLE001
        return None


def check(
    text: str,
    *,
    urls: list[str] | None = None,
    claimed_entity: str | None = None,
    sender_domains: dict[str, str] | None = None,
    html: str | None = None,
) -> CheckResult:
    """Run the DELIVERY chokepoint.

    `sender_domains` maps a role to a domain: from, return_path, reply_to,
    message_id. THE SENDING DOMAIN IS A DELIVERY SURFACE and must be inspected
    exactly like a body link -- this module previously looked at body URLs
    alone, and the omission has now caused three separate misses. In the
    LinkedIn impersonation, `barberajmeagher.gq` was parsed correctly by the
    email layer and then never checked by anything: a free-TLD throwaway domain
    sat in the From header while DELIVERY reported it had nothing to look at.
    """
    result = CheckResult(chokepoint=DELIVERY, passed=None, confidence=0.0)

    # Credential-harvesting parameters are checked against the raw URLs before
    # any domain parsing, because the finding is about the query string.
    for candidate in list(urls or []) + extract_urls(text or ""):
        match = CREDENTIAL_IN_URL_RE.search(candidate)
        if match:
            result.add(Reason(
                code="CREDENTIAL_IN_URL",
                message=(
                    "This link carries your e-mail address in plain text. Legitimate "
                    "services use an anonymous code instead. Phishing pages pass the "
                    "address so the fake login screen can fill in your username and "
                    "look convincing."
                ),
                evidence={"url": candidate[:300], "matched_parameter": match.group(0)[:80]},
                severity=5,
            ))
            break

    # Does this message make a financial claim at all? Used to gate findings
    # that are only meaningful in a financial context (see DOMAIN_NOT_IN_REGISTRY).
    financial_context = bool(re.search(
        r"(?:invest|investment|dividend|shares?|equity|stock|demat|broker|"
        r"mutual\s*fund|sip|portfolio|trading|nse|bse|sebi|ipo|folio|payment|"
        r"account|bank|upi|refund|kyc)", (text or ""), re.I))

    # Hidden links pointing somewhere the visible links do not. There is no
    # legitimate reason to conceal a link to a different domain in an email;
    # the decoy exists to fool scanners that read hrefs without rendering.
    if html:
        from core.ingest.html_links import find_hidden_link_divergence, parse_html

        links, _visible_text = parse_html(html)
        divergence = find_hidden_link_divergence(links)
        if divergence:
            severity = divergence.pop("severity", 4)
            result.add(Reason(
                code="HIDDEN_LINK_DIVERGENCE",
                message=(
                    "This message hides a link to one website behind a visible link to "
                    "another. Concealing a destination this way has no legitimate use -- "
                    "it is done to make automated checks see a reputable site while you "
                    "are sent somewhere else."
                ),
                evidence=divergence,
                severity=severity,
            ))

    found = list(urls or []) + extract_urls(text or "")

    # Sender-side domains join the set of domains under inspection.
    sender_roles: dict[str, str] = {}
    for role, raw_domain in (sender_domains or {}).items():
        domain = safe_domain(raw_domain or "")
        if domain:
            sender_roles.setdefault(domain, role)
            found.append(domain)
    # Deduplicate by registrable domain but keep the first full URL for display.
    seen_domains: dict[str, str] = {}
    unparseable = 0
    for url in found:
        domain = safe_domain(url)
        if domain is None:
            # Dropped silently and counted, never reported. See safe_domain().
            unparseable += 1
            continue
        if domain not in seen_domains:
            seen_domains[domain] = url

    # APK distribution: severity 5 regardless of anything else.
    for m in APK_RE.finditer(text or ""):
        result.add(Reason(
            code="APK_DOWNLOAD_LINK",
            message=(
                f"This message distributes an Android app file directly ({m.group(0)}). "
                "Genuine broking and mutual fund apps are only on the Play Store or App "
                "Store. An APK sent to you is how fake trading apps get installed."
            ),
            evidence={"apk_link": m.group(0)},
            severity=5,
        ))

    if not seen_domains and not result.reasons:
        return CheckResult.undetermined(DELIVERY, "This message contains no links or domains.")

    clean_domains = 0
    for domain, original_url in seen_domains.items():
        ext = _extractor()(domain)
        tld = (ext.suffix or "").split(".")[-1]

        if domain in URL_SHORTENERS or normalise_domain(original_url) in URL_SHORTENERS:
            expanded = _expand_shortener(original_url)
            result.add(Reason(
                code="URL_SHORTENER_IN_FINANCIAL_MESSAGE",
                message=(
                    f"This link is shortened ({domain}), so you cannot see where it goes "
                    "before clicking. Legitimate financial communications link to their "
                    "own site directly."
                ),
                evidence={"url": original_url, "expanded": expanded or "not in cache"},
                severity=3,
            ))
            if expanded:
                domain = normalise_domain(registrable_domain(expanded))
                if not domain:
                    continue

        known = {d for d, _, _ in _known_domains()}
        if domain in known:
            entity = next((n for d, n, _ in _known_domains() if d == domain), domain)
            result.add(Reason(
                code="KNOWN_OFFICIAL_DOMAIN",
                message=f"{domain} is the official domain of {entity}.",
                evidence={"domain": domain, "entity": entity},
                severity=0,
            ))
            clean_domains += 1
            continue

        # Punycode / IDN
        if domain.startswith("xn--") or ".xn--" in domain:
            result.add(Reason(
                code="PUNYCODE_DOMAIN",
                message=(
                    f"The domain {domain} uses non-Latin characters disguised to look "
                    "like ordinary letters. This is done to imitate a real brand."
                ),
                evidence={"domain": domain},
                severity=4,
            ))

        lookalike = find_lookalike(domain)
        if lookalike:
            result.add(Reason(
                code="LOOKALIKE_DOMAIN",
                message=(
                    f"The domain {domain} is built to resemble "
                    f"{lookalike['matched']}, which belongs to {lookalike['entity']}. "
                    "It is not the same domain."
                ),
                evidence={"domain": domain, **lookalike},
                severity=5,
            ))

        age_days, whois_evidence = _whois_age_days(domain)
        if age_days is not None and age_days < NEW_DOMAIN_DAYS:
            result.add(Reason(
                code="DOMAIN_REGISTERED_RECENTLY",
                message=(
                    f"This link goes to {domain}, a domain registered "
                    f"{age_days} days ago. Established institutions do not use "
                    "brand-new domains for investor communications."
                ),
                evidence=whois_evidence,
                severity=4,
            ))
        elif age_days is None and whois_evidence.get("cache") == "miss":
            # NOT a finding. "We have no WHOIS record" is a statement about our
            # cache, not about the message, and showing it to a user tells them
            # nothing they can act on. It fired twice on the LinkedIn miss --
            # including against linkedin.com itself -- as pure noise.
            log.debug("no WHOIS record cached for %s", domain)

        if tld in ELEVATED_RISK_TLDS:
            result.add(Reason(
                code="ELEVATED_RISK_TLD",
                message=(
                    f"The domain ends in .{tld}, an extension used far more often for "
                    "fraud than for legitimate Indian financial services."
                ),
                evidence={"domain": domain, "tld": tld},
                severity=3,
            ))

        # Only worth saying when the message is actually making a financial
        # claim. It fired on linkedin.com in the phishing miss, where "we have
        # no record of linkedin.com in our registry of financial domains" is
        # true, useless, and crowds out the findings that matter.
        if (not lookalike and tld not in ELEVATED_RISK_TLDS and age_days is None
                and financial_context):
            result.add(Reason(
                code="DOMAIN_NOT_IN_REGISTRY",
                message=(
                    f"We do not have {domain} in our registry of official financial "
                    "domains. That does not make it fraudulent -- our registry is not "
                    "exhaustive -- but we cannot confirm it either."
                ),
                evidence={"domain": domain, "role": sender_roles.get(domain, "link")},
                severity=1,
            ))

    failures = [r for r in result.reasons if r.severity >= 4]
    warnings = [r for r in result.reasons if r.severity == 3]

    if failures:
        result.passed = False
        result.confidence = min(1.0, 0.7 + 0.1 * len(failures))
    elif warnings:
        result.passed = False
        result.confidence = 0.5
    elif clean_domains and clean_domains == len(seen_domains):
        result.passed = True
        result.confidence = 0.85
    elif result.reasons:
        # A2: a check that produced findings has, by definition, determined
        # something. Reporting passed=None alongside four findings is what let
        # the LinkedIn phishing email through -- the scorer saw "no evidence"
        # and ignored everything DELIVERY had actually said.
        result.passed = False if result.max_severity >= 2 else True
        result.confidence = 0.4
    else:
        result.passed = None
        result.confidence = 0.35

    return result
