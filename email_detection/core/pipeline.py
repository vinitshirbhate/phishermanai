"""End-to-end verification pipeline.

One entry point -- `verify()` -- takes whatever the user submitted and returns a
Verdict. Everything before this file is a component; this is the orchestration:

    route input -> extract fields -> run 4 chokepoints -> match filing
                -> compare fields -> score -> recommend actions

The chokepoints are independent by design, so they run without ordering
constraints. The filings cross-check runs afterwards because it needs the
resolved entity, and tamper comparison runs last because it needs the match.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from core.actions import build_reports, recommended_actions
from core.chokepoints import claim, delivery, entity, money
from core.chokepoints.base import CheckResult
from core.fields import extract_all
from core.freshness import data_horizon, document_postdates_corpus
from core.freshness import filing_is_amended, has_later_amendment
from core.freshness import summary as freshness_summary
from core.ingest.email_parser import (
    AuthVerdict,
    header_anomalies,
    parse_email,
    reconcile_auth_with_domain,
)
from core.ingest.forward import analysis_text as forward_analysis_text
from core.ingest.forward import detect_raw as forward_detect_raw
from core.ingest.router import ParsedInput, route
from core.filings.matcher import FilingMatch, match_filing
from core.filings.tamper import compare_to_filing
from core.scoring import Verdict, score, try_short_circuit

log = logging.getLogger(__name__)


def _claimed_entity(parsed: ParsedInput) -> str | None:
    """Who does this message present itself as?

    Order matters: the e-mail display name is the most explicit claim, then any
    company we can resolve from the body, then the sending domain's mapped
    owner.
    """
    if parsed.email and parsed.email.from_display_name:
        name = parsed.email.from_display_name
        for suffix in (" Investor Relations", " Investor Services", " Support",
                       " Secretarial", " Enforcement Department", " Team"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        if name.strip():
            return name.strip()

    from core.filings.matcher import find_company_in_text
    company = find_company_in_text(parsed.raw_text)
    if company:
        return company["name"]

    if parsed.email and parsed.email.from_domain:
        from core.ingest.email_parser import lookup_domain
        mappings = lookup_domain(parsed.email.from_domain)
        if mappings:
            return mappings[0]["entity_name"]
    return None


def _mentions_multiple_companies(text: str, threshold: int = 2) -> bool:
    """Does this document name two or more distinct listed companies?

    Used to tell a single-company circular (comparable against one filing) from
    a holdings statement or portfolio summary (comparable against none).
    """
    from core.chokepoints.entity import _entity_index
    from core.textnorm import normalise_company_name

    # Distinct ISINs are the most direct evidence of a holdings list, and they
    # do not depend on matching company names at all. Name matching alone missed
    # these documents: the entity index is keyed on full names ("reliance
    # industries"), so a statement line reading "RELIANCE -EQ RS 10" never
    # matched, and only one company was counted.
    from core.lexicon.identifiers import mask_identifiers
    masked = mask_identifiers(text)
    distinct_isins = {i.value.upper() for i in masked.by_kind("ISIN")}
    if len(distinct_isins) >= threshold:
        return True
    if len(masked.by_kind("SCRIP_DESCRIPTOR")) >= threshold:
        return True

    index = _entity_index()
    if not index:
        return False

    words = normalise_company_name(text).split()
    found: list[str] = []
    # Size 1 is included: many listed companies are a single word ("Reliance",
    # "Infosys", "Titan"), and stopping at 2 meant a holdings statement listing
    # them was not recognised as multi-company.
    for size in range(5, 0, -1):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i + size])
            if len(phrase) < 4:
                continue
            record = index.get(phrase)
            if not record or record[0].get("entity_type") != "LISTED_COMPANY":
                continue
            # OVERLAPPING NAMES ARE ONE COMPANY, NOT TWO. The index holds both
            # "tata motors" and "tata motors passenger vehicles" as separate
            # listed entities, so a circular naming the longer one matched both
            # and looked like a two-company portfolio -- which nulled its filing
            # match and silently disabled tamper detection on it.
            #
            # Scanning longest-first means any later phrase contained in one
            # already found is a fragment of the same name.
            if any(phrase in seen or seen in phrase for seen in found):
                continue
            found.append(phrase)
            if len(found) >= threshold:
                return True
    return False


def _claimed_entity_from_forward(forward_info, text: str) -> str | None:
    """Who did the ORIGINAL message claim to be from?

    Only the original matters. The forwarder is the person asking us for help.
    """
    from email.utils import parseaddr

    raw_from = forward_info.original_from or ""
    display, _address = parseaddr(raw_from)
    if display and display.strip():
        return display.strip()

    # PRECEDENCE MATTERS. The sending domain outranks any company named in the
    # body, because a document routinely mentions companies it is not from -- a
    # CDSL holdings statement lists every scrip you own. When the attached
    # original had no display name, falling through to body extraction picked
    # "Anant Raj Ltd" out of the holdings table and then reported CDSL's own
    # domain as the wrong sender.
    if forward_info.original_from_domain:
        from core.ingest.email_parser import lookup_domain
        mappings = lookup_domain(forward_info.original_from_domain)
        if mappings:
            return mappings[0]["entity_name"]

    from core.filings.matcher import find_company_in_text
    company = find_company_in_text(text)
    if company:
        return company["name"]
    return None


def _matched_filing_amended(filing_id: int | None) -> bool:
    """Was the matched filing itself a correction, or later corrected?"""
    if filing_id is None:
        return False
    try:
        from sqlalchemy import select

        from core.db import session_scope
        from core.models import Filing

        with session_scope() as session:
            filing = session.execute(
                select(Filing).where(Filing.id == filing_id)
            ).scalar_one_or_none()
        return filing_is_amended(filing) or has_later_amendment(filing)
    except Exception:  # noqa: BLE001 - never block a verdict on a lookup
        return False


def verify(
    data: bytes | str,
    filename: str | None = None,
    *,
    source_type: str | None = None,
    live_verify: bool = False,
    money_sent: bool = False,
) -> tuple[Verdict, ParsedInput, dict[str, Any]]:
    """Verify a submission. Returns the verdict, the parsed input, and timings."""
    started = time.perf_counter()
    timings: dict[str, Any] = {}

    # ---- 1. Parse
    t0 = time.perf_counter()
    parsed = route(data, filename, source_type=source_type)
    timings["parse_ms"] = int((time.perf_counter() - t0) * 1000)

    text = parsed.raw_text
    fields = parsed.structured
    claimed = _claimed_entity(parsed)

    # ---- 1b. Forwarding
    #
    # Forwarding is the primary way people submit suspicious mail. The message
    # we were handed is the FORWARDER'S; the message to judge is the one inside
    # it. Analysing the wrapper meant flagging the user's own Gmail address as
    # an institution impersonator.
    forward_info = None
    if parsed.email is not None:
        forward_info = forward_detect_raw(data)
        if forward_info.is_forward:
            text = forward_analysis_text(forward_info, text)
            # Re-extract against the ORIGINAL body, not the wrapper.
            fields = extract_all(text, urls=parsed.urls)
            parsed.structured = fields

            # The claimed entity must come from the ORIGINAL sender, never from
            # the forwarder. `_claimed_entity` reads the outer From display
            # name, which on a forward is the user -- so a broker's own SEBI
            # registration number was compared against "Investor" and reported
            # as REG_NO_NAME_MISMATCH on genuine mail.
            claimed = _claimed_entity_from_forward(forward_info, text)

    # ---- 1c. Authorised-sender short-circuit
    #
    # Runs BEFORE any chokepoint. A direct email carrying a valid, aligned DKIM
    # signature from an authorised domain has already proved both its integrity
    # and its sender; running content rules over it can only produce false
    # positives. Excluded for screenshots, forwards and pasted text -- see
    # try_short_circuit for why each exclusion matters.
    short_circuit = try_short_circuit(parsed, forward_info)
    if short_circuit is not None:
        timings["total_ms"] = int((time.perf_counter() - started) * 1000)
        timings["short_circuit"] = True
        short_circuit.recommended_actions = recommended_actions(
            short_circuit, claimed_entity=claimed, money_sent=money_sent,
        )
        log.info("short-circuit: %s (%s)", short_circuit.verdict, short_circuit.short_circuit)
        return short_circuit, parsed, timings

    # ---- 2. Email authentication (email input only)
    auth_verdict = None
    auth_anomalies: list[Any] = []
    if parsed.email is not None:
        t0 = time.perf_counter()
        if forward_info is not None and forward_info.is_forward:
            if forward_info.forward_type == "ATTACHED" and forward_info.original_message is not None:
                # The original headers survived, so authenticate the ORIGINAL.
                inner = parse_email(forward_info.original_message.as_bytes())
                auth_verdict = reconcile_auth_with_domain(inner, claimed_entity=claimed)
                auth_anomalies = header_anomalies(inner)
            else:
                # Inline forward: the original's DKIM/SPF/DMARC are GONE, not
                # failed. Saying "authentication failed" would misrepresent
                # evidence we never received.
                auth_verdict = AuthVerdict(
                    status="UNKNOWN",
                    code="AUTH_UNAVAILABLE_INLINE_FORWARD",
                    message=(
                        "This message was forwarded inline, which strips the original "
                        "security headers. We could not check DKIM, SPF or DMARC for "
                        f"{forward_info.original_from_domain or 'the original sender'}. "
                        "Forward as an attachment for a stronger verdict."
                    ),
                    severity=1,
                    evidence={
                        "forward_type": forward_info.forward_type,
                        "original_sender": forward_info.original_from_domain,
                        "auth_available": False,
                    },
                )
                # No header anomalies: they would all describe the forwarder.
                auth_anomalies = []
        else:
            auth_verdict = reconcile_auth_with_domain(parsed.email, claimed_entity=claimed)
            auth_anomalies = header_anomalies(parsed.email)
        timings["auth_ms"] = int((time.perf_counter() - t0) * 1000)

    # ---- 3. The four chokepoints
    t0 = time.perf_counter()
    checks: list[CheckResult] = []

    has_payment = bool(fields and (fields.upi_ids or fields.account_numbers))
    checks.append(money.check(
        text, fields, claimed_entity=claimed, qr_payloads=parsed.qr_payloads,
    ))
    checks.append(claim.check(text, has_payment_request=has_payment, fields=fields))
    # The sending domain is a delivery surface, not just metadata.
    sender_domains: dict[str, str] = {}
    if parsed.email is not None:
        for role, value in (("from", parsed.email.from_domain),
                            ("return_path", parsed.email.return_path_domain),
                            ("reply_to", parsed.email.reply_to_domain)):
            if value:
                sender_domains[role] = value
        message_id = (parsed.email.headers or {}).get("Message-ID", "")
        if "@" in message_id:
            sender_domains.setdefault("message_id", message_id.split("@")[-1].strip("<> 	"))
    checks.append(delivery.check(
        text, urls=parsed.urls, claimed_entity=claimed, sender_domains=sender_domains,
        html=parsed.email.body_html if parsed.email else None,
    ))
    checks.append(entity.check(
        text,
        claimed_entity=claimed,
        sender_domain=parsed.email.from_domain if parsed.email else None,
        live_verify=live_verify,
    ))
    timings["chokepoints_ms"] = int((time.perf_counter() - t0) * 1000)

    # ---- 4. Filings cross-check
    t0 = time.perf_counter()
    filing_match: FilingMatch | None = None
    tamper_result = None
    try:
        filing_match = match_filing(
            text, fields, phash=parsed.phash, company_hint=claimed,
        )
        # A document that merely LISTS securities is not a communication ABOUT
        # any one of them. A CDSL holdings statement naming Reliance and Anant
        # Raj was matched to a Reliance filing, its dates compared, and the
        # mismatch reported as TAMPERED on genuine mail.
        #
        # Tamper comparison therefore only runs when the document is about a
        # single company. Two or more distinct listed companies means a
        # portfolio, statement or watchlist, and there is no single filing it
        # could be a copy of.
        if filing_match.found and _mentions_multiple_companies(text):
            filing_match.notes.append(
                "Document lists several companies, so it is a statement rather than a "
                "single-company circular. Field comparison skipped."
            )
            filing_match.filing_id = None
        if filing_match.found:
            bboxes = {}
            if parsed.ocr_boxes:
                # Map a field to the box whose text contains its value, so the
                # UI can draw the red rectangle in the right place.
                for box in parsed.ocr_boxes:
                    for name in ("dividend_per_share", "record_date", "meeting_date"):
                        value = getattr(fields, name, None)
                        if value is not None and str(value) in box.text:
                            bboxes.setdefault(name, box.bbox)
            tamper_result = compare_to_filing(
                fields, filing_match.filing_id, document_text=text, bboxes=bboxes,
            )

            # ---- Data-horizon guards -------------------------------------
            #
            # Stale data normally fails safe: no matching filing means
            # UNVERIFIED, and missing data cannot manufacture a false GENUINE.
            # The exception is an AMENDED filing. If a company revised a
            # dividend from Rs 4 to Rs 5 and we still hold the Rs 4 record, a
            # genuine new circular quoting Rs 5 would be reported TAMPERED --
            # a confident false accusation against a real document, which is
            # the worst outcome this system can produce.
            #
            # Both guards only ever downgrade. Neither can turn anything into
            # GENUINE.
            if tamper_result is not None and tamper_result.tampered:
                document_date = None
                if parsed.email is not None and parsed.email.date:
                    try:
                        document_date = datetime.fromisoformat(parsed.email.date).date()
                    except (ValueError, TypeError):
                        document_date = None

                if document_postdates_corpus(document_date):
                    horizon = data_horizon()
                    tamper_result.tampered = False
                    tamper_result.downgraded_to_unverified = True
                    tamper_result.extra_signals.append({
                        "code": "DOCUMENT_POSTDATES_OUR_DATA",
                        "severity": 0,
                        "message": (
                            f"Our exchange filing data ends {horizon}. This document is "
                            "dated later, so a newer filing may exist that we have not "
                            "seen. We cannot compare it, and we will not call it altered."
                        ),
                        "evidence": {"document_date": str(document_date),
                                     "corpus_as_of": str(horizon)},
                    })
                elif _matched_filing_amended(filing_match.filing_id):
                    tamper_result.tampered = False
                    tamper_result.downgraded_to_unverified = True
                    tamper_result.extra_signals.append({
                        "code": "MATCHED_FILING_WAS_AMENDED",
                        "severity": 0,
                        "message": (
                            "The filing this document matches was later corrected by the "
                            "company. The difference may be with the correction rather "
                            "than with this document, so we will not call it altered."
                        ),
                        "evidence": {"filing_id": filing_match.filing_id},
                    })
    except Exception as exc:  # noqa: BLE001 - filings are an enhancement, not a gate
        log.warning("filings cross-check failed: %s", exc)
    timings["filings_ms"] = int((time.perf_counter() - t0) * 1000)

    # ---- 5. Score
    verdict = score(
        checks,
        tamper_result=tamper_result,
        filing_match=filing_match,
        auth_verdict=auth_verdict,
        parsed_input=parsed,
        auth_anomalies=auth_anomalies,
    )

    # ---- 6. Actions
    verdict.recommended_actions = recommended_actions(
        verdict, claimed_entity=claimed, money_sent=money_sent,
    )
    verdict.evidence_summary["claimed_entity"] = claimed
    verdict.evidence_summary["source_type"] = parsed.source_type
    verdict.evidence_summary["reports"] = build_reports(
        verdict,
        content_hash=parsed.content_hash,
        claimed_entity=claimed,
        sender=parsed.email.from_address if parsed.email else None,
        domains=[d for d in {
            __import__("core.chokepoints.delivery", fromlist=["registrable_domain"])
            .registrable_domain(u) for u in parsed.urls
        } if d],
        upi_ids=fields.upi_ids if fields else [],
    )

    # Every verdict states the date of the data it was checked against. A
    # verification with no horizon is not auditable.
    verdict.evidence_summary["freshness"] = freshness_summary()

    timings["total_ms"] = int((time.perf_counter() - started) * 1000)
    return verdict, parsed, timings
