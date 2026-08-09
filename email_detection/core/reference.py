"""Reference-data loaders for the chokepoints.

These CSVs are small, static and read on every verification, so they are parsed
once at first use and held in module-level caches. Everything here is local
disk -- no network, by design.
"""

from __future__ import annotations

import csv
import functools
import re
from pathlib import Path
from typing import NamedTuple

REF_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"


class UpiRule(NamedTuple):
    pattern: str
    match_type: str          # REGEX | SUFFIX
    category: str            # VALID_INTERMEDIARY | VALID_NO_CATEGORY | PERSONAL_PSP
    psp_or_entity: str
    severity: int
    explanation: str
    source: str


class BankCode(NamedTuple):
    prefix: str
    name: str
    bank_type: str


@functools.lru_cache(maxsize=1)
def upi_rules() -> list[UpiRule]:
    path = REF_DIR / "upi_handles.csv"
    if not path.exists():
        return []
    out: list[UpiRule] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                severity = int(row.get("severity_if_investment_payment") or 0)
            except ValueError:
                severity = 0
            out.append(UpiRule(
                pattern=(row.get("pattern") or "").strip(),
                match_type=(row.get("match_type") or "SUFFIX").strip().upper(),
                category=(row.get("category") or "").strip().upper(),
                psp_or_entity=(row.get("psp_or_entity") or "").strip(),
                severity=severity,
                explanation=(row.get("explanation") or "").strip(),
                source=(row.get("source") or "").strip(),
            ))
    return out


@functools.lru_cache(maxsize=1)
def _compiled_upi_regexes() -> list[tuple[re.Pattern[str], UpiRule]]:
    return [
        (re.compile(rule.pattern, re.I), rule)
        for rule in upi_rules()
        if rule.match_type == "REGEX" and rule.pattern
    ]


@functools.lru_cache(maxsize=1)
def _upi_suffix_index() -> dict[str, UpiRule]:
    return {
        rule.pattern.lower().lstrip("@"): rule
        for rule in upi_rules()
        if rule.match_type == "SUFFIX"
    }


def classify_upi_handle(upi_id: str) -> UpiRule | None:
    """Classify a UPI address against the reference rules.

    Regex rules (the SEBI @valid formats) are checked first because they are
    exact structural statements; the personal-PSP suffix index is the fallback.
    Returns None when the handle matches nothing we know, which the caller must
    treat as unknown rather than safe.
    """
    if not upi_id or "@" not in upi_id:
        return None
    normalised = upi_id.strip().lower()

    for regex, rule in _compiled_upi_regexes():
        if regex.match(normalised):
            return rule

    suffix = normalised.rsplit("@", 1)[-1]
    return _upi_suffix_index().get(suffix)


@functools.lru_cache(maxsize=1)
def bank_codes() -> dict[str, BankCode]:
    path = REF_DIR / "ifsc_banks.csv"
    if not path.exists():
        return {}
    out: dict[str, BankCode] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            prefix = (row.get("ifsc_prefix") or "").strip().upper()
            if not prefix:
                continue
            out[prefix] = BankCode(
                prefix=prefix,
                name=(row.get("bank_name") or "").strip(),
                bank_type=(row.get("bank_type") or "").strip(),
            )
    return out


def resolve_ifsc(ifsc: str) -> BankCode | None:
    """Map an IFSC code to its bank via the first four characters."""
    if not ifsc or len(ifsc) < 4:
        return None
    return bank_codes().get(ifsc[:4].upper())


IFSC_FORMAT_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def is_valid_ifsc_format(ifsc: str) -> bool:
    """IFSC = 4-letter bank code, then a reserved '0', then a 6-char branch code."""
    return bool(IFSC_FORMAT_RE.match((ifsc or "").strip().upper()))
