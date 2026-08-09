"""Field-by-field tamper detection against the matched filing.

This is the second half of the novel contribution: a document that is genuine
in every other respect -- real company, real letterhead, real language, sent
from a domain that passes DMARC -- but with one field edited.

TWO RULES GOVERN THIS ENTIRE MODULE
-----------------------------------

1. PYTHON COMPARES, MODELS DO NOT. A vision model may read "Rs 40" off an
   image. Whether 40 equals the 4 that Canara Bank filed is decided by an
   integer comparison, never by asking a model. Models extract; Python decides.

2. A FIELD WE COULD NOT READ CLEARLY CAN NEVER PRODUCE "TAMPERED". If the
   amount was blurry, the honest answer is "we could not read this; the filed
   value is X; check the original", and the verdict is UNVERIFIED. A false
   accusation of tampering against a real document destroys credibility far
   faster than a miss does, because the user can verify we were wrong.

The decision table below is implemented exactly as specified:

    match=True,  conf=HIGH        -> contributes to GENUINE
    match=False, conf=HIGH        -> TAMPERED  (severity 5)
    match=False, conf=MEDIUM      -> TAMPERED  (severity 3) + "please verify"
    match=False, conf=UNREADABLE  -> UNVERIFIED, never tampered
    field absent in document      -> ignored, never penalised
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date
from typing import Any

from sqlalchemy import select

from core.db import session_scope
from core.fields import ExtractedFields
from core.models import Filing
from core.textnorm import normalise_for_matching

HIGH = "HIGH"
MEDIUM = "MEDIUM"
UNREADABLE = "UNREADABLE"

# Money is compared to the paisa. Anything looser would let a Rs 4.00 vs Rs 4.05
# edit through; anything tighter trips on float representation.
AMOUNT_TOLERANCE = 0.005


@dataclass
class FieldComparison:
    field: str
    extracted_value: Any
    filed_value: Any
    match: bool | None                    # None = not comparable
    read_confidence: str = HIGH
    severity: int = 0
    bbox: list[int] | None = None         # for the red box in the UI
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        def enc(v):
            return v.isoformat() if isinstance(v, date) else v
        return {
            "field": self.field,
            "extracted_value": enc(self.extracted_value),
            "filed_value": enc(self.filed_value),
            "match": self.match,
            "read_confidence": self.read_confidence,
            "severity": self.severity,
            "bbox": self.bbox,
            "message": self.message,
        }


@dataclass
class TamperResult:
    tampered: bool = False
    confidence: str = HIGH
    comparisons: list[FieldComparison] = dc_field(default_factory=list)
    extra_signals: list[dict[str, Any]] = dc_field(default_factory=list)
    filing_id: int | None = None
    downgraded_to_unverified: bool = False

    @property
    def altered_fields(self) -> list[FieldComparison]:
        return [c for c in self.comparisons if c.match is False and c.read_confidence != UNREADABLE]

    @property
    def unreadable_fields(self) -> list[FieldComparison]:
        return [c for c in self.comparisons if c.read_confidence == UNREADABLE]

    @property
    def max_severity(self) -> int:
        severities = [c.severity for c in self.comparisons]
        severities += [s.get("severity", 0) for s in self.extra_signals]
        return max(severities, default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tampered": self.tampered,
            "confidence": self.confidence,
            "filing_id": self.filing_id,
            "comparisons": [c.to_dict() for c in self.comparisons],
            "extra_signals": self.extra_signals,
            "altered_fields": [c.field for c in self.altered_fields],
            "unreadable_fields": [c.field for c in self.unreadable_fields],
            "downgraded_to_unverified": self.downgraded_to_unverified,
        }


# --------------------------------------------------------------------------
# Field comparators
# --------------------------------------------------------------------------

def _compare_amount(extracted: float | None, filed: float | None) -> bool | None:
    if extracted is None or filed is None:
        return None
    return abs(extracted - filed) <= AMOUNT_TOLERANCE


def _compare_date(extracted: date | None, filed: date | None) -> bool | None:
    if extracted is None or filed is None:
        return None
    return extracted == filed


def _compare_string(extracted: str | None, filed: str | None) -> bool | None:
    if not extracted or not filed:
        return None
    return normalise_for_matching(extracted) == normalise_for_matching(filed)


# Payment-instruction language. Its presence in a document whose filing has
# none is the strongest single tamper signal we have, because a real dividend
# circular never asks an investor to pay anything.
PAYMENT_INSTRUCTION_RE = re.compile(
    r"(?:pay|transfer|remit|deposit|send)\s[^.!?\n]{0,60}"
    r"(?:rs\.?|inr|₹|fee|charge|amount|upi|account)"
    r"|(?:upi|a/c|account\s*(?:no|number))\s*[:\-]?\s*\S+"
    r"|processing\s*fee|verification\s*(?:charge|fee)|convenience\s*fee",
    re.I,
)

FIELD_SEVERITY = {
    "dividend_per_share": 5,
    "record_date": 5,
    "meeting_date": 4,
    "evoting_start": 4,
    "evoting_end": 4,
    "evoting_url": 5,
    "isin": 5,
    "cin": 4,
}


def _confidence_for(field_name: str, fields: ExtractedFields) -> tuple[str, list[int] | None]:
    """Read confidence and bounding box for a field, if the extractor recorded them.

    Text input (email, pasted message) is read exactly, so confidence is HIGH.
    Image input carries per-field confidence from the dual-path extractor, and
    that is what can downgrade a comparison to UNREADABLE.
    """
    confidence = fields.field_confidence.get(field_name) if fields.field_confidence else None
    if confidence is None:
        return HIGH, None
    if confidence >= 0.85:
        level = HIGH
    elif confidence >= 0.5:
        level = MEDIUM
    else:
        level = UNREADABLE
    bbox = None
    if isinstance(fields.field_confidence.get(f"{field_name}__bbox"), list):
        bbox = fields.field_confidence[f"{field_name}__bbox"]
    return level, bbox


def compare_to_filing(
    fields: ExtractedFields,
    filing_id: int,
    *,
    document_text: str = "",
    bboxes: dict[str, list[int]] | None = None,
) -> TamperResult:
    """Compare extracted fields against the filed record, field by field."""
    result = TamperResult(filing_id=filing_id)
    bboxes = bboxes or {}

    with session_scope() as session:
        filing = session.execute(
            select(Filing).where(Filing.id == filing_id)
        ).scalar_one_or_none()
        if filing is None:
            return result

        checks: list[tuple[str, Any, Any, Any]] = [
            ("dividend_per_share", fields.dividend_per_share, filing.dividend_per_share, _compare_amount),
            ("record_date", fields.record_date, filing.record_date, _compare_date),
            ("meeting_date", fields.meeting_date, filing.meeting_date, _compare_date),
            ("evoting_start", fields.evoting_start, filing.evoting_start, _compare_date),
            ("evoting_end", fields.evoting_end, filing.evoting_end, _compare_date),
            ("isin", fields.isin, filing.isin, _compare_string),
        ]

        filed_date_str = (
            filing.filing_date.strftime("%d %B %Y") if filing.filing_date else "the filing date"
        )

        for name, extracted, filed, comparator in checks:
            # Field absent on either side: nothing to compare, no penalty.
            if extracted is None or filed is None:
                continue

            matched = comparator(extracted, filed)
            if matched is None:
                continue

            confidence, conf_bbox = _confidence_for(name, fields)
            bbox = bboxes.get(name) or conf_bbox

            if matched:
                comparison = FieldComparison(
                    field=name, extracted_value=extracted, filed_value=filed,
                    match=True, read_confidence=confidence, severity=0, bbox=bbox,
                    message=f"The {name.replace('_', ' ')} matches what "
                            f"{filing.company_name} filed with {filing.exchange}.",
                )
            elif confidence == UNREADABLE:
                # THE RULE: never accuse on an unreadable field.
                comparison = FieldComparison(
                    field=name, extracted_value=None, filed_value=filed,
                    match=None, read_confidence=UNREADABLE, severity=0, bbox=bbox,
                    message=(
                        f"Could not read the {name.replace('_', ' ')} clearly. "
                        f"The filed value is {filed}. Please check the original document."
                    ),
                )
                result.downgraded_to_unverified = True
            elif confidence == MEDIUM:
                comparison = FieldComparison(
                    field=name, extracted_value=extracted, filed_value=filed,
                    match=False, read_confidence=MEDIUM,
                    severity=3, bbox=bbox,
                    message=(
                        f"This document appears to say {extracted} for the "
                        f"{name.replace('_', ' ')}, but {filing.company_name} filed "
                        f"{filed} with {filing.exchange} on {filed_date_str}. "
                        "The document was not fully legible -- please verify against the original."
                    ),
                )
            else:
                comparison = FieldComparison(
                    field=name, extracted_value=extracted, filed_value=filed,
                    match=False, read_confidence=HIGH,
                    severity=FIELD_SEVERITY.get(name, 4), bbox=bbox,
                    message=(
                        f"This document says {extracted} for the "
                        f"{name.replace('_', ' ')}. {filing.company_name} filed "
                        f"{filed} with {filing.exchange} on {filed_date_str}."
                    ),
                )
            result.comparisons.append(comparison)

        # ------------------------------------------------ inserted payment demand
        filing_text = f"{filing.headline or ''} {filing.body_text or ''}"
        doc_has_payment = bool(PAYMENT_INSTRUCTION_RE.search(document_text or ""))
        filing_has_payment = bool(PAYMENT_INSTRUCTION_RE.search(filing_text))

        if doc_has_payment and not filing_has_payment:
            match = PAYMENT_INSTRUCTION_RE.search(document_text or "")
            result.extra_signals.append({
                "code": "PAYMENT_INSTRUCTION_NOT_IN_FILING",
                "severity": 5,
                "message": (
                    f"This document asks you to make a payment, but the announcement "
                    f"{filing.company_name} actually filed with {filing.exchange} contains "
                    "no payment instruction. Genuine dividend and meeting notices never "
                    "ask investors to pay anything."
                ),
                "evidence": {
                    "matched_text": match.group(0)[:160] if match else None,
                    "filing_id": filing.id,
                    "filing_headline": filing.headline,
                },
            })

        # ------------------------------------------------ payment details present
        if fields.upi_ids or fields.account_numbers:
            result.extra_signals.append({
                "code": "PAYMENT_DETAILS_IN_CORPORATE_NOTICE",
                "severity": 5 if not filing_has_payment else 3,
                "message": (
                    "This corporate communication contains payment details. Companies and "
                    "registrars pay dividends into your registered bank account "
                    "automatically; they never collect money from investors."
                ),
                "evidence": {
                    "upi_ids": fields.upi_ids,
                    "account_numbers": fields.account_numbers,
                },
            })

    # ------------------------------------------------------------- verdict
    altered = result.altered_fields
    if altered:
        high_confidence = [c for c in altered if c.read_confidence == HIGH]
        result.tampered = True
        result.confidence = HIGH if high_confidence else MEDIUM
    elif result.unreadable_fields:
        result.tampered = False
        result.confidence = UNREADABLE
    else:
        result.tampered = False
        result.confidence = HIGH

    return result
