"""Generate test fixtures from REAL filings in the database.

    python -m eval.make_fixtures

Fixtures are grounded in actual BSE announcements rather than invented text.
That matters: a tampered fixture is only a meaningful test if the untampered
original genuinely exists in the filings table, so the matcher has something
real to find and the tamper detector has a real value to disagree with.

Produces, in eval/fixtures/:
  genuine_*.eml     a real corporate communication, DMARC pass, mapped domain
  tampered_*.eml    the same message with ONE field altered
  fraud_*.eml       fabricated fraud (lookalike domain, personal UPI, promises)
  edge_*.eml        legitimate but unregistered -- the false-positive test

Every fixture is written alongside a manifest recording what was changed, so
the evaluation harness has ground truth without hand-labelling.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from core.db import session_scope
from core.models import DomainMap, Filing

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
MANIFEST = FIXTURE_DIR / "manifest.json"

RNG = random.Random(20260807)   # deterministic: fixtures must be reproducible


def _auth_header(domain: str, *, dmarc: str = "pass", spf: str = "pass", dkim: str = "pass") -> str:
    return (
        f"mx.google.com; dkim={dkim} header.i=@{domain} header.s=selector1; "
        f"spf={spf} (google.com: domain of noreply@{domain} designates 203.0.113.10 "
        f"as permitted sender) smtp.mailfrom=noreply@{domain}; "
        f"dmarc={dmarc} (p=REJECT sp=REJECT dis=NONE) header.from={domain}"
    )


def _build_eml(
    *,
    subject: str,
    from_name: str,
    from_addr: str,
    body: str,
    auth: str,
    reply_to: str | None = None,
    date: datetime | None = None,
    html_body: str | None = None,
) -> bytes:
    msg = EmailMessage()
    domain = from_addr.split("@")[-1]
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Date"] = format_datetime(date or datetime.now())
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = "investor@example.com"
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Return-Path"] = f"<bounce@{domain}>"
    msg["Authentication-Results"] = auth
    msg["Received"] = (
        f"from mail.{domain} (mail.{domain} [203.0.113.10]) by mx.google.com "
        f"with ESMTPS id abc123; {format_datetime(date or datetime.now())}"
    )
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg.as_bytes()


def _domain_for(company_name: str, mappings: dict[str, str]) -> tuple[str, str] | None:
    """Find an official domain for a company from the domain map."""
    from core.textnorm import normalise_company_name
    target = normalise_company_name(company_name)
    if not target:
        return None
    for entity_norm, domain in mappings.items():
        if entity_norm and (entity_norm == target or entity_norm in target or target in entity_norm):
            return domain, entity_norm
    return None


def _pick_source_filings(session, limit: int = 6) -> list[Filing]:
    """Real dividend filings that carry a value we can later tamper with."""
    rows = session.execute(
        select(Filing)
        .where(Filing.filing_type == "DIVIDEND")
        .where(Filing.dividend_per_share.is_not(None))
        .order_by(Filing.filing_date.desc())
    ).scalars().all()
    if len(rows) < limit:
        rows += session.execute(
            select(Filing)
            .where(Filing.record_date.is_not(None))
            .order_by(Filing.filing_date.desc())
            .limit(limit * 3)
        ).scalars().all()
    return rows


def _genuine_body(filing: Filing, domain: str) -> str:
    parts = [
        f"Dear Shareholder,",
        "",
        f"{filing.company_name} wishes to inform its members of the following "
        "corporate action, intimated to BSE Limited under Regulation 30 of the "
        "SEBI (Listing Obligations and Disclosure Requirements) Regulations, 2015.",
        "",
    ]
    if filing.headline:
        parts += [f"Subject: {filing.headline}", ""]
    if filing.dividend_per_share is not None:
        parts.append(
            f"The Board of Directors has recommended a dividend of "
            f"Rs {filing.dividend_per_share:g} per equity share for the financial year 2025-26."
        )
    if filing.record_date:
        parts.append(
            f"The Record Date for determining the members eligible to receive the "
            f"dividend has been fixed as {filing.record_date.strftime('%A, %B %d, %Y')}."
        )
    if filing.evoting_start and filing.evoting_end:
        parts.append(
            f"The remote e-voting period commences on "
            f"{filing.evoting_start.strftime('%d %B %Y')} at 9:00 A.M. and ends on "
            f"{filing.evoting_end.strftime('%d %B %Y')} at 5:00 P.M."
        )
    parts += [
        "",
        "Members holding shares in electronic form are requested to notify any "
        "change in their bank mandate to their Depository Participant. Members "
        "holding shares in physical form may write to the Registrar and Transfer Agent.",
        "",
        f"This communication is for information only. No action or payment is required from you.",
        "",
        f"For {filing.company_name}",
        "Company Secretary and Compliance Officer",
        f"https://www.{domain}",
    ]
    return "\n".join(parts)


def build_fixtures() -> dict[str, Any]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []

    with session_scope() as session:
        from core.textnorm import normalise_company_name
        mappings = {
            normalise_company_name(name): domain
            for domain, name in session.execute(
                select(DomainMap.domain, DomainMap.entity_name)
                .where(DomainMap.relationship_type == "OFFICIAL")
            )
        }

        filings = _pick_source_filings(session)
        usable: list[tuple[Filing, str]] = []
        for filing in filings:
            hit = _domain_for(filing.company_name, mappings)
            if hit:
                usable.append((filing, hit[0]))
            if len(usable) >= 5:
                break

        # Fall back to RTA-sent notices, which is how most investors actually
        # receive these, if no company domain matched.
        if len(usable) < 5:
            for filing in filings:
                if len(usable) >= 5:
                    break
                if all(filing.id != f.id for f, _ in usable):
                    usable.append((filing, "kfintech.com"))

        # ---------------------------------------------------------- GENUINE
        for idx, (filing, domain) in enumerate(usable, 1):
            body = _genuine_body(filing, domain)
            when = filing.filing_date or datetime.now()
            eml = _build_eml(
                subject=f"{filing.company_name} - {filing.headline or 'Corporate Action Intimation'}"[:160],
                from_name=f"{filing.company_name} Investor Relations",
                from_addr=f"investor.relations@{domain}",
                body=body,
                auth=_auth_header(domain),
                date=when,
            )
            path = FIXTURE_DIR / f"genuine_{idx:02d}.eml"
            path.write_bytes(eml)
            manifest.append({
                "file": path.name, "label": "GENUINE", "filing_id": filing.id,
                "company": filing.company_name, "from_domain": domain,
                "dividend_per_share": filing.dividend_per_share,
                "record_date": filing.record_date.isoformat() if filing.record_date else None,
                "tampered_field": None,
            })

            # --------------------------------------------------- TAMPERED
            # Exactly one field altered, so the detector must name that field.
            tamper_body = body
            tampered_field = None
            original_value = None
            new_value = None

            if filing.dividend_per_share is not None:
                original_value = f"{filing.dividend_per_share:g}"
                # A 10x inflation is the classic edit: plausible at a glance.
                new_value = f"{filing.dividend_per_share * 10:g}"
                tamper_body = tamper_body.replace(
                    f"Rs {original_value} per equity share",
                    f"Rs {new_value} per equity share",
                )
                tampered_field = "dividend_per_share"
            elif filing.record_date:
                original_value = filing.record_date.strftime("%A, %B %d, %Y")
                shifted = filing.record_date + timedelta(days=14)
                new_value = shifted.strftime("%A, %B %d, %Y")
                tamper_body = tamper_body.replace(original_value, new_value)
                tampered_field = "record_date"

            if tampered_field:
                # A real tampered circular also adds the payment instruction the
                # genuine filing never contains -- that is the point of the edit.
                tamper_body = tamper_body.replace(
                    "This communication is for information only. No action or payment is required from you.",
                    "To receive this dividend directly to your account, confirm your bank "
                    "details and pay the Rs 250 processing fee to 9876543210@ybl within 24 hours.",
                )
                eml = _build_eml(
                    subject=f"{filing.company_name} - Dividend Credit Confirmation Required",
                    from_name=f"{filing.company_name} Investor Relations",
                    from_addr=f"investor.relations@{domain}",
                    body=tamper_body,
                    auth=_auth_header(domain),
                    date=when,
                )
                path = FIXTURE_DIR / f"tampered_{idx:02d}.eml"
                path.write_bytes(eml)
                manifest.append({
                    "file": path.name, "label": "TAMPERED", "filing_id": filing.id,
                    "company": filing.company_name, "from_domain": domain,
                    "tampered_field": tampered_field,
                    "original_value": original_value, "altered_value": new_value,
                })

        # -------------------------------------------------------- FRAUDULENT
        frauds = [
            {
                "name": "fraud_01_lookalike_dividend.eml",
                "subject": "Canara Bank: Your unclaimed dividend of Rs 18,450 is pending",
                "from_name": "Canara Bank Investor Services",
                "from_addr": "dividends@canarabank-dividends.co.in",
                "domain": "canarabank-dividends.co.in",
                "body": (
                    "Dear Investor,\n\n"
                    "Our records show an unclaimed dividend of Rs 18,450 in your name.\n"
                    "This amount will be transferred to the IEPF if not claimed within 48 hours.\n\n"
                    "Click here to claim: https://canarabank-dividends.co.in/claim\n\n"
                    "A refundable verification charge of Rs 500 is payable to 9876543210@ybl "
                    "to release the amount to your account.\n\n"
                    "Canara Bank Investor Services\n"
                ),
                "note": "lookalike domain + personal UPI + urgency",
            },
            {
                "name": "fraud_02_guaranteed_returns.eml",
                "subject": "Guaranteed 30% monthly returns - limited seats",
                "from_name": "Wealth Multiplier Advisory",
                "from_addr": "advisor@wealthmultiplier.xyz",
                "domain": "wealthmultiplier.xyz",
                "body": (
                    "Namaste Investor,\n\n"
                    "Join our VIP trading group and earn GUARANTEED 30% monthly returns "
                    "with zero risk. Our SEBI registered experts (SEBI Reg INA000017523) "
                    "have delivered consistent profits for 5 years.\n\n"
                    "Only 3 seats left! Pay Rs 25,000 now to 9876543210@paytm to reserve "
                    "your seat. Download our trading app: https://wealthmultiplier.xyz/app.apk\n\n"
                    "Hurry, offer expires today!\n"
                ),
                "note": "guaranteed returns + stolen reg no + personal UPI + APK + urgency",
            },
            {
                "name": "fraud_03_sebi_impersonation.eml",
                "subject": "URGENT: SEBI notice - your demat account is frozen",
                "from_name": "SEBI Enforcement Department",
                "from_addr": "enforcement@sebi-verification.online",
                "domain": "sebi-verification.online",
                "body": (
                    "OFFICIAL NOTICE FROM SEBI\n\n"
                    "Your demat account has been frozen due to suspicious transactions "
                    "flagged under money laundering investigation.\n\n"
                    "To avoid a non-bailable arrest warrant, pay the penalty of Rs 45,000 "
                    "immediately to account 123456789012, IFSC HDFC0001234.\n\n"
                    "Failure to comply within 24 hours will result in legal action.\n\n"
                    "SEBI Enforcement Department\n"
                ),
                "note": "regulator impersonation + digital arrest + payment demand",
            },
        ]
        for item in frauds:
            eml = _build_eml(
                subject=item["subject"], from_name=item["from_name"],
                from_addr=item["from_addr"], body=item["body"],
                # These PASS DMARC: the fraudster owns the domain. That is the
                # whole point -- authentication cannot catch them.
                auth=_auth_header(item["domain"]),
            )
            path = FIXTURE_DIR / item["name"]
            path.write_bytes(eml)
            manifest.append({
                "file": path.name, "label": "FRAUDULENT",
                "from_domain": item["domain"], "note": item["note"],
                "dmarc": "pass",
            })

        # A spoofed sender that actually fails DMARC.
        eml = _build_eml(
            subject="Zerodha: verify your account to avoid suspension",
            from_name="Zerodha Support",
            from_addr="support@zerodha.com",
            body=(
                "Your Zerodha account will be suspended.\n"
                "Verify now: http://zerodha-verify.top/login\n"
                "Share the OTP sent to your mobile with our executive to complete verification.\n"
            ),
            auth=_auth_header("zerodha.com", dmarc="fail", spf="fail", dkim="fail"),
            reply_to="recovery.desk@gmail.com",
        )
        path = FIXTURE_DIR / "fraud_04_spoofed_dmarc_fail.eml"
        path.write_bytes(eml)
        manifest.append({
            "file": path.name, "label": "FRAUDULENT",
            "from_domain": "zerodha.com", "dmarc": "fail",
            "note": "forged sender, DMARC fail, reply-to mismatch, OTP request",
        })

        # ------------------------------------------------- EDGE: legit but unknown
        # The false-positive test. Real, harmless, but not in our registry --
        # this MUST come back UNVERIFIED, never FRAUDULENT.
        edges = [
            {
                "name": "edge_01_unregistered_but_real.eml",
                "subject": "Sundaram Textiles Ltd - Notice of 42nd Annual General Meeting",
                "from_name": "Sundaram Textiles Secretarial",
                "from_addr": "secretarial@sundaramtextiles-ltd.co.in",
                "domain": "sundaramtextiles-ltd.co.in",
                "body": (
                    "Dear Member,\n\n"
                    "Notice is hereby given that the 42nd Annual General Meeting of "
                    "Sundaram Textiles Limited will be held on Tuesday, 25 August 2026 "
                    "at 11:00 A.M. through video conferencing.\n\n"
                    "The Notice and Annual Report have been sent to members whose email "
                    "addresses are registered with the Company.\n\n"
                    "No payment of any kind is required to attend the meeting.\n\n"
                    "For Sundaram Textiles Limited\n"
                    "Company Secretary\n"
                ),
                "note": "genuine-looking AGM notice from a company not in our registry",
            },
            {
                "name": "edge_02_small_ria_newsletter.eml",
                "subject": "Monthly market commentary - July 2026",
                "from_name": "Meridian Investment Advisors",
                "from_addr": "research@meridianadvisors.co.in",
                "domain": "meridianadvisors.co.in",
                "body": (
                    "Dear Client,\n\n"
                    "Our July commentary is attached. Equity markets remained range-bound "
                    "through the month.\n\n"
                    "Please note that investments in securities are subject to market risks. "
                    "We do not guarantee any returns. Past performance is not indicative of "
                    "future results.\n\n"
                    "Meridian Investment Advisors\n"
                ),
                "note": "harmless newsletter with compliance disclaimer; must not trip claim rules",
            },
        ]
        for item in edges:
            eml = _build_eml(
                subject=item["subject"], from_name=item["from_name"],
                from_addr=item["from_addr"], body=item["body"],
                auth=_auth_header(item["domain"]),
            )
            path = FIXTURE_DIR / item["name"]
            path.write_bytes(eml)
            manifest.append({
                "file": path.name, "label": "EDGE_UNREGISTERED_BUT_REAL",
                "from_domain": item["domain"], "note": item["note"],
            })

    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for item in manifest:
        counts[item["label"]] = counts.get(item["label"], 0) + 1
    return {"written": len(manifest), "by_label": counts, "dir": str(FIXTURE_DIR)}


if __name__ == "__main__":  # pragma: no cover
    result = build_fixtures()
    print(json.dumps(result, indent=2))
    for item in json.loads(MANIFEST.read_text(encoding="utf-8")):
        extra = item.get("tampered_field") or item.get("note") or ""
        print(f"  {item['label']:<28} {item['file']:<34} {extra}")
