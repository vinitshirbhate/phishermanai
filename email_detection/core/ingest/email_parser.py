"""Email parsing and source authentication (Layer 1).

THE CORE INSIGHT OF THIS PROJECT LIVES IN THIS FILE
---------------------------------------------------
Every deployed anti-phishing system verifies WHERE a message came from. SPF,
DKIM and DMARC do that job well. But consider what a DMARC pass actually
asserts:

    "This mail genuinely originated from the domain it claims to be from,
     and that domain's owner authorised it."

That is all. It says nothing about whether the domain has any right to the
NAME it is trading under. A fraudster who registers canarabank-dividends.co.in,
publishes correct SPF and DKIM records, and sets a DMARC policy will PASS every
authentication check that exists -- while impersonating Canara Bank.

So authentication alone is not enough, and treating a DMARC pass as a verdict
is the mistake this project exists to correct. The logic below is therefore:

    dmarc_pass  AND domain maps to the claimed entity  -> STRONG PASS
    dmarc_pass  AND domain does NOT map to that entity -> SUSPICIOUS
                     (reason code AUTHENTICATED_BUT_UNRECOGNISED_DOMAIN)
    dmarc_fail                                          -> FAIL

The middle case is the interesting one, and it is the case every other system
reports as "safe, DMARC passed".

We read the Authentication-Results header rather than re-verifying signatures.
The receiving provider already performed the cryptography and recorded the
outcome; re-implementing DKIM validation would add failure modes without adding
information.
"""

from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from sqlalchemy import select

from core.chokepoints.delivery import extract_urls, registrable_domain
from core.db import session_scope
from core.models import DomainMap
from core.textnorm import normalise_company_name, normalise_domain

try:
    import authres
except ImportError:  # pragma: no cover
    authres = None


# Free mail providers. A message from one of these is not "the company" no
# matter what the display name says.
FREEMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.in",
    "hotmail.com", "outlook.com", "live.com", "rediffmail.com", "aol.com",
    "protonmail.com", "proton.me", "zoho.com", "mail.com", "gmx.com",
    "icloud.com", "yandex.com", "tutanota.com",
}


@dataclass
class EmailAuth:
    """What the receiving provider recorded about this message's authenticity."""

    spf: str | None = None            # pass | fail | softfail | neutral | none | permerror
    dkim: str | None = None
    dmarc: str | None = None
    auth_serv_id: str | None = None
    raw_header: str | None = None
    source: str = "authentication_results_header"
    # The domain that actually signed the message (the DKIM d= tag). Alignment
    # is what makes a DKIM pass meaningful: anyone can sign their own mail, so
    # "dkim=pass" alone says nothing about the sender's identity. Only a pass
    # SIGNED BY the domain in the From header proves the claimed sender signed it.
    dkim_domain: str | None = None

    @property
    def dmarc_passed(self) -> bool:
        return (self.dmarc or "").lower() == "pass"

    @property
    def dmarc_failed(self) -> bool:
        return (self.dmarc or "").lower() in ("fail", "permerror", "temperror")

    @property
    def any_result_present(self) -> bool:
        return any([self.spf, self.dkim, self.dmarc])

    def dkim_aligned_with(self, from_domain: str) -> bool:
        """Did the domain in the From header itself sign this message?

        Compared on the registrable domain, so mail signed by `sbi.co.in` and
        sent from `alerts.sbi.co.in` counts as aligned -- that is the same
        organisation -- while `evil.com` signing mail claiming to be from
        `sbi.co.in` does not.
        """
        if not self.dkim_domain or not from_domain:
            return False
        from core.chokepoints.delivery import registrable_domain

        signer = registrable_domain(self.dkim_domain) or self.dkim_domain.lower()
        claimed = registrable_domain(from_domain) or from_domain.lower()
        return bool(signer) and signer == claimed

    def to_dict(self) -> dict[str, Any]:
        return {
            "spf": self.spf, "dkim": self.dkim, "dmarc": self.dmarc,
            "auth_serv_id": self.auth_serv_id, "source": self.source,
        }


@dataclass
class ParsedEmail:
    subject: str = ""
    from_display_name: str = ""
    from_address: str = ""
    from_domain: str = ""
    reply_to_address: str = ""
    reply_to_domain: str = ""
    return_path: str = ""
    return_path_domain: str = ""
    to_addresses: list[str] = field(default_factory=list)
    date: str | None = None
    body_text: str = ""
    body_html: str = ""
    urls: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    received_chain: list[str] = field(default_factory=list)
    auth: EmailAuth = field(default_factory=EmailAuth)
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return f"{self.subject}\n\n{self.body_text}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "from_display_name": self.from_display_name,
            "from_address": self.from_address,
            "from_domain": self.from_domain,
            "reply_to_address": self.reply_to_address,
            "return_path": self.return_path,
            "to_addresses": self.to_addresses,
            "date": self.date,
            "urls": self.urls,
            "attachments": self.attachments,
            "received_hops": len(self.received_chain),
            "auth": self.auth.to_dict(),
        }


# --------------------------------------------------------------------------
# Header parsing
# --------------------------------------------------------------------------

_AUTH_FALLBACK_RE = re.compile(
    r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.I
)


def parse_authentication_results(header_value: str) -> EmailAuth:
    """Read spf/dkim/dmarc outcomes from an Authentication-Results header.

    `authres` is used when available because it implements RFC 8601 properly.
    Providers do emit headers that authres rejects, so a permissive regex is
    kept as a fallback -- losing the result entirely would be worse than
    reading it loosely.
    """
    result = EmailAuth(raw_header=header_value)
    if not header_value:
        return result

    if authres is not None:
        try:
            parsed = authres.AuthenticationResultsHeader.parse(
                f"Authentication-Results: {header_value}"
                if not header_value.lower().startswith("authentication-results:")
                else header_value
            )
            result.auth_serv_id = getattr(parsed, "authserv_id", None)
            for item in getattr(parsed, "results", []):
                method = (getattr(item, "method", "") or "").lower()
                value = (getattr(item, "result", "") or "").lower()
                if method == "spf" and not result.spf:
                    result.spf = value
                elif method == "dkim" and not result.dkim:
                    result.dkim = value
                    # The d= / header.i= tag names the signing domain.
                    props = getattr(item, "header_d", None) or getattr(item, "header_i", None)
                    if props:
                        result.dkim_domain = str(props).lstrip("@").strip().lower()
                elif method == "dmarc" and not result.dmarc:
                    result.dmarc = value
            if result.any_result_present:
                return result
        except Exception:  # noqa: BLE001 - fall through to the regex
            pass

    signer = _DKIM_DOMAIN_RE.search(header_value)
    if signer and not result.dkim_domain:
        result.dkim_domain = signer.group(1).lstrip("@").strip().lower()

    for method, value in _AUTH_FALLBACK_RE.findall(header_value):
        method, value = method.lower(), value.lower()
        if method == "spf" and not result.spf:
            result.spf = value
        elif method == "dkim" and not result.dkim:
            result.dkim = value
        elif method == "dmarc" and not result.dmarc:
            result.dmarc = value
    result.source = "authentication_results_header_regex_fallback"
    return result


def _decode_body(message: EmailMessage) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []

    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        disposition = (part.get_content_disposition() or "").lower()
        if disposition == "attachment":
            continue
        try:
            payload = part.get_content()
        except Exception:  # noqa: BLE001 - undecodable part
            raw = part.get_payload(decode=True)
            payload = raw.decode("utf-8", "replace") if raw else ""
        if content_type == "text/plain":
            text_parts.append(payload)
        elif content_type == "text/html":
            html_parts.append(payload)

    html = "\n".join(html_parts)
    text = "\n".join(text_parts)
    if not text and html:
        # Strip tags so downstream checks see readable prose. Script and style
        # bodies are removed first so their contents are not read as text.
        stripped = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        stripped = re.sub(r"(?s)<br\s*/?>|</p>|</div>|</tr>", "\n", stripped)
        stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
        text = re.sub(r"[ \t]+", " ", stripped)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, html


def _extract_html_links(html: str) -> list[str]:
    return re.findall(r"""(?i)href\s*=\s*["']([^"']+)["']""", html or "")


def parse_email(raw: bytes | str) -> ParsedEmail:
    """Parse a .eml into a ParsedEmail."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    message: EmailMessage = email.message_from_bytes(raw, policy=email.policy.default)

    parsed = ParsedEmail()
    parsed.headers = {k: str(v) for k, v in message.items()}

    parsed.subject = str(message.get("Subject", "") or "")
    display, addr = parseaddr(str(message.get("From", "") or ""))
    parsed.from_display_name = display.strip()
    parsed.from_address = addr.strip().lower()
    parsed.from_domain = normalise_domain(addr.split("@")[-1]) if "@" in addr else ""

    _, reply_to = parseaddr(str(message.get("Reply-To", "") or ""))
    parsed.reply_to_address = reply_to.strip().lower()
    parsed.reply_to_domain = normalise_domain(reply_to.split("@")[-1]) if "@" in reply_to else ""

    _, return_path = parseaddr(str(message.get("Return-Path", "") or ""))
    parsed.return_path = return_path.strip().lower()
    parsed.return_path_domain = normalise_domain(return_path.split("@")[-1]) if "@" in return_path else ""

    parsed.to_addresses = [
        a.strip().lower() for _, a in
        [parseaddr(x) for x in str(message.get("To", "") or "").split(",")] if a
    ]

    raw_date = message.get("Date")
    if raw_date:
        try:
            parsed.date = parsedate_to_datetime(str(raw_date)).isoformat()
        except (TypeError, ValueError):
            parsed.date = str(raw_date)

    parsed.received_chain = [str(v) for v in message.get_all("Received", [])]

    # Authentication-Results: take the topmost, which the receiving provider
    # added. Lower ones may have been forged upstream.
    auth_headers = message.get_all("Authentication-Results", [])
    if auth_headers:
        parsed.auth = parse_authentication_results(str(auth_headers[0]))
    else:
        for name in ("ARC-Authentication-Results", "X-Authentication-Results"):
            values = message.get_all(name, [])
            if values:
                parsed.auth = parse_authentication_results(str(values[0]))
                parsed.auth.source = f"{name.lower()}_header"
                break

    parsed.body_text, parsed.body_html = _decode_body(message)

    urls = _extract_html_links(parsed.body_html) + extract_urls(parsed.body_text)
    seen: list[str] = []
    for url in urls:
        url = url.strip()
        if url and not url.lower().startswith(("mailto:", "tel:", "#")) and url not in seen:
            seen.append(url)
    parsed.urls = seen

    for part in message.walk():
        if (part.get_content_disposition() or "").lower() == "attachment":
            payload = part.get_payload(decode=True) or b""
            parsed.attachments.append({
                "filename": part.get_filename() or "unnamed",
                "content_type": part.get_content_type(),
                "size_bytes": len(payload),
            })

    return parsed


# --------------------------------------------------------------------------
# Domain / entity reconciliation -- the core distinction
# --------------------------------------------------------------------------

def lookup_domain(domain: str) -> list[dict[str, Any]]:
    """Every domain_map entry for a domain, matching parent domains too."""
    domain = normalise_domain(domain)
    if not domain:
        return []
    try:
        with session_scope() as session:
            rows = session.execute(
                select(DomainMap.domain, DomainMap.entity_name,
                       DomainMap.entity_type, DomainMap.relationship_type)
            ).all()
    except Exception:  # noqa: BLE001
        return []

    registrable = registrable_domain(domain) or domain
    out = []
    for known, entity_name, entity_type, relationship in rows:
        if domain == known or registrable == known or domain.endswith("." + known):
            out.append({
                "domain": known, "entity_name": entity_name,
                "entity_type": entity_type, "relationship": relationship,
            })
    return out


@dataclass
class AuthVerdict:
    """The outcome of reconciling authentication against the domain map."""

    status: str                      # STRONG_PASS | SUSPICIOUS | FAIL | UNKNOWN
    code: str
    message: str
    severity: int
    evidence: dict[str, Any] = field(default_factory=dict)


def reconcile_auth_with_domain(
    parsed: ParsedEmail,
    claimed_entity: str | None = None,
) -> AuthVerdict:
    """Combine the DMARC result with what the sending domain actually is.

    This implements the three-way logic described at the top of the module.
    """
    domain = parsed.from_domain
    mappings = lookup_domain(domain)
    evidence: dict[str, Any] = {
        "from_domain": domain,
        "from_display_name": parsed.from_display_name,
        "dmarc": parsed.auth.dmarc,
        "spf": parsed.auth.spf,
        "dkim": parsed.auth.dkim,
        "domain_mapped_to": [m["entity_name"] for m in mappings],
        "claimed_entity": claimed_entity,
    }

    # --- DMARC failed: the mail did not come from where it says it did.
    if parsed.auth.dmarc_failed:
        return AuthVerdict(
            status="FAIL",
            code="DMARC_FAIL",
            message=(
                f"This email failed DMARC authentication, which means it was not sent by "
                f"{domain or 'the domain it claims'}. The sender address has been forged."
            ),
            severity=5,
            evidence=evidence,
        )

    # --- No authentication data at all.
    if not parsed.auth.any_result_present:
        return AuthVerdict(
            status="UNKNOWN",
            code="NO_AUTHENTICATION_RESULTS",
            message=(
                "This email carries no authentication results, so we cannot confirm "
                "whether the sender address is genuine. That often means it was saved "
                "or forwarded rather than received directly."
            ),
            severity=1,
            evidence=evidence,
        )

    # --- Free mail provider claiming to be an institution.
    if domain in FREEMAIL_DOMAINS:
        return AuthVerdict(
            status="SUSPICIOUS",
            code="INSTITUTIONAL_CLAIM_FROM_FREEMAIL",
            message=(
                f"This email was sent from a {domain} address. It may have passed "
                "authentication, but that only proves somebody genuinely sent it from "
                f"a {domain} account. No bank, broker or registrar communicates with "
                "investors from a free email account."
            ),
            severity=4,
            evidence=evidence,
        )

    if parsed.auth.dmarc_passed:
        if mappings:
            # Does the domain belong to the entity the message claims to be?
            #
            # A mismatch is only evidence when the claim resolves to a DIFFERENT
            # KNOWN entity. If the display name is a role ("Company Secretary"),
            # a service ("CDSL e-Voting") or anything we cannot resolve, we have
            # no conflicting claim -- only an unrecognised string -- and
            # treating that as impersonation flagged genuine mail from CDSL,
            # NSDL, Reliance and Infosys alike.
            if claimed_entity:
                from core.chokepoints.entity import is_generic_name, resolve_entity

                claimed_norm = normalise_company_name(claimed_entity)
                matched = any(
                    claimed_norm and (
                        claimed_norm in normalise_company_name(m["entity_name"])
                        or normalise_company_name(m["entity_name"]) in claimed_norm
                    )
                    for m in mappings
                )

                if not matched:
                    # An alias ("CDSL") resolving to the domain's owner is a match.
                    resolved = resolve_entity(claimed_entity)
                    if resolved:
                        resolved_norm = normalise_company_name(resolved["name"])
                        matched = any(
                            resolved_norm == normalise_company_name(m["entity_name"])
                            or resolved_norm in normalise_company_name(m["entity_name"])
                            or normalise_company_name(m["entity_name"]) in resolved_norm
                            for m in mappings
                        )
                    # No resolvable, distinct entity behind the claim: no conflict.
                    if resolved is None or is_generic_name(claimed_entity):
                        matched = True
                        evidence["claim_unresolvable"] = True

                # Same corporate group. Indian financial groups share a domain
                # across subsidiaries: Kotak Securities mail leaves kotak.com,
                # which the map records against Kotak Mahindra Bank, and SBI
                # Mutual Fund mail leaves sbimf.com, recorded against SBI Funds
                # Management. Both pairs are real, related entities, and calling
                # that impersonation flagged genuine mail from two of India's
                # largest financial groups.
                if not matched:
                    from core.chokepoints.entity import (
                        GENERIC_ENTITY_TOKENS,
                        entity_aliases,
                    )

                    # An acronym paired with a product name -- "CDSL Easi",
                    # "NSDL IDeAS" -- shares no token with the expanded legal
                    # name ("Central Depository Services India Limited"), so the
                    # whole-string alias lookup misses and the group-token test
                    # finds nothing in common. Resolve each token through the
                    # alias table before giving up.
                    aliases = entity_aliases()
                    for token in claimed_norm.split():
                        target = aliases.get(token)
                        if not target:
                            continue
                        target_norm = normalise_company_name(target)
                        if any(target_norm == normalise_company_name(m["entity_name"])
                               for m in mappings):
                            matched = True
                            evidence["alias_token"] = token
                            break

                if not matched:
                    from core.chokepoints.entity import GENERIC_ENTITY_TOKENS

                    claim_tokens = {
                        t for t in claimed_norm.split()
                        if t not in GENERIC_ENTITY_TOKENS and len(t) > 2
                    }
                    for mapping in mappings:
                        owner_tokens = {
                            t for t in normalise_company_name(mapping["entity_name"]).split()
                            if t not in GENERIC_ENTITY_TOKENS and len(t) > 2
                        }
                        shared = claim_tokens & owner_tokens
                        if shared:
                            matched = True
                            evidence["same_group_token"] = sorted(shared)
                            break

                if not matched:
                    return AuthVerdict(
                        status="SUSPICIOUS",
                        code="AUTHENTICATED_DOMAIN_WRONG_ENTITY",
                        message=(
                            f"This email genuinely came from {domain}, which belongs to "
                            f"{mappings[0]['entity_name']} -- but the message presents "
                            f"itself as {claimed_entity}. Those are different organisations."
                        ),
                        severity=4,
                        evidence=evidence,
                    )
            return AuthVerdict(
                status="STRONG_PASS",
                code="AUTHENTICATED_AND_RECOGNISED_DOMAIN",
                message=(
                    f"This email genuinely came from {domain}, the official domain of "
                    f"{mappings[0]['entity_name']}. Both the sender and the organisation "
                    "check out."
                ),
                severity=0,
                evidence=evidence,
            )

        # THE CASE EVERY OTHER SYSTEM CALLS SAFE.
        return AuthVerdict(
            status="SUSPICIOUS",
            code="AUTHENTICATED_BUT_UNRECOGNISED_DOMAIN",
            message=(
                f"This email really was sent by {domain} -- it passes every "
                "authentication check. But that only proves the sender owns that domain, "
                "not that the domain belongs to the company named in the message. "
                f"{domain} is not a domain we recognise as belonging to any registered "
                "financial institution. Anyone can register a domain and configure it to "
                "pass these checks."
            ),
            severity=3,
            evidence=evidence,
        )

    return AuthVerdict(
        status="UNKNOWN",
        code="AUTHENTICATION_INCONCLUSIVE",
        message=(
            f"Authentication for this email was inconclusive (DMARC: "
            f"{parsed.auth.dmarc or 'not recorded'}). We cannot confirm the sender."
        ),
        severity=2,
        evidence=evidence,
    )


def header_anomalies(parsed: ParsedEmail) -> list[AuthVerdict]:
    """Header-level phishing signals independent of DMARC."""
    out: list[AuthVerdict] = []

    # Reply-To pointing somewhere else than From: replies go to the fraudster.
    if parsed.reply_to_domain and parsed.from_domain:
        if registrable_domain(parsed.reply_to_domain) != registrable_domain(parsed.from_domain):
            out.append(AuthVerdict(
                status="SUSPICIOUS",
                code="REPLY_TO_MISMATCH",
                message=(
                    f"This email appears to come from {parsed.from_domain}, but any reply "
                    f"you send goes to {parsed.reply_to_address} instead. Legitimate "
                    "senders do not redirect replies to an unrelated address."
                ),
                severity=4,
                evidence={
                    "from_domain": parsed.from_domain,
                    "reply_to": parsed.reply_to_address,
                    "reply_to_domain": parsed.reply_to_domain,
                },
            ))

    # Return-Path mismatch: weaker (mailing lists do this legitimately).
    if parsed.return_path_domain and parsed.from_domain:
        if registrable_domain(parsed.return_path_domain) != registrable_domain(parsed.from_domain):
            out.append(AuthVerdict(
                status="SUSPICIOUS",
                code="RETURN_PATH_MISMATCH",
                message=(
                    f"The bounce address for this email ({parsed.return_path_domain}) is a "
                    f"different domain from the sender ({parsed.from_domain}). This is "
                    "normal for newsletters but is also how bulk phishing is sent."
                ),
                severity=2,
                evidence={"return_path": parsed.return_path, "from_domain": parsed.from_domain},
            ))

    # A display name that names a domain different from the actual sender.
    display = parsed.from_display_name or ""
    display_domains = re.findall(r"\b([a-z0-9\-]+\.(?:com|in|co\.in|org|net))\b", display.lower())
    for candidate in display_domains:
        if registrable_domain(candidate) != registrable_domain(parsed.from_domain):
            out.append(AuthVerdict(
                status="SUSPICIOUS",
                code="DISPLAY_NAME_DOMAIN_MISMATCH",
                message=(
                    f"The sender's name shows \"{display}\" but the email was actually sent "
                    f"from {parsed.from_domain}. The visible name is not the real address."
                ),
                severity=4,
                evidence={"display_name": display, "actual_domain": parsed.from_domain},
            ))
            break

    return out
