"""CHOKEPOINT 1 -- ENTITY. Is the claimed sender real and SEBI-registered?

Resolves the organisation a message claims to be against real registers: the
BSE scrip master for listed companies and SEBI's own intermediary registers for
brokers, advisers, research analysts, RTAs and depository participants.

THE CHECK THAT MATTERS
----------------------
Validating that a SEBI registration number is well-formed is nearly worthless
on its own -- the format is public and trivial to imitate. The check with teeth
is confirming that the number belongs to the entity claiming it. Fraudsters
routinely paste a genuine registration number lifted from a real broker's
website into their own material, because almost nobody looks it up.

Because we loaded SEBI's registers with names attached, we can. A message
signed "Alpha Wealth Advisory, SEBI Reg INA000017523" is caught immediately:
that number is registered to 1 Finance Private Limited. That is
REG_NO_NAME_MISMATCH, and it is severity 5.

Identifier formats are validated arithmetically where possible -- the ISIN
check digit is computed, not pattern-matched.
"""

from __future__ import annotations

import functools
import re
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import select

from core.chokepoints.base import ENTITY, CheckResult, Reason
from core.db import session_scope
from core.fields import CIN_RE, ISIN_RE, SEBI_REG_RE
from core.models import Entity
from core.textnorm import normalise_company_name, normalise_for_matching

FUZZY_THRESHOLD = 85

# Bodies that never contact an individual investor to demand money. Naming them
# is itself the impersonation.
AUTHORITY_NAMES = {
    "sebi": "Securities and Exchange Board of India",
    "securities and exchange board": "Securities and Exchange Board of India",
    "nse": "National Stock Exchange of India",
    "national stock exchange": "National Stock Exchange of India",
    "bse": "BSE Limited",
    "bombay stock exchange": "BSE Limited",
    "nsdl": "National Securities Depository Limited",
    "cdsl": "Central Depository Services India Limited",
    "rbi": "Reserve Bank of India",
    "reserve bank": "Reserve Bank of India",
    "amfi": "Association of Mutual Funds in India",
}

# Word-boundary matched, NOT substring. A substring test for "pay" matches
# "Payment Of Dividend" in the subject line of every genuine dividend
# intimation, which made this rule fire on legitimate corporate mail.
PAYMENT_DEMAND_RE = re.compile(
    r"\b(?:pay|pays|paying|transfer|remit|deposit|send\s+money|fee|fees|fine|"
    r"penalty|charges?|settle|dues|outstanding\s+amount)\b",
    re.I,
)

# Negations that invert a payment cue. Genuine notices very often say exactly
# "no payment is required from you" -- the opposite of a demand.
PAYMENT_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|neither|nor)\b[^.!?\n]{0,40}?\b(?:action|payment|fee|"
    r"charge|amount|money)\b"
    r"|\b(?:payment|fee|charge|money)\b[^.!?\n]{0,30}?\b(?:is\s+not|are\s+not|never)\b",
    re.I,
)

# An authority is only being IMPERSONATED when the message presents itself AS
# that body. Genuine corporate filings cite SEBI and the exchanges constantly
# ("intimated to BSE Limited under Regulation 30 of the SEBI (LODR)
# Regulations"), and treating a citation as impersonation flagged every
# legitimate corporate communication we tested.
AUTHORITY_AS_SENDER_RE = re.compile(
    r"\b(?:notice|message|communication|order|intimation|letter|email)\s+from\s+"
    r"(?:the\s+)?(?:sebi|nse|bse|nsdl|cdsl|rbi)\b"
    r"|\bthis\s+is\s+(?:a\s+)?(?:an\s+)?(?:official\s+)?(?:notice\s+)?from\s+"
    r"(?:the\s+)?(?:sebi|nse|bse|nsdl|cdsl|rbi)\b"
    r"|\b(?:sebi|nse|bse|nsdl|cdsl|rbi)\s+"
    r"(?:notice|enforcement|department|order|team|helpdesk|support|official)\b"
    r"|\bofficial\s+notice\s+from\s+(?:sebi|nse|bse|rbi)\b"
    r"|\bon\s+behalf\s+of\s+(?:the\s+)?(?:sebi|nse|bse|nsdl|cdsl|rbi)\b",
    re.I,
)

# Registration-number prefix -> what that register covers. Used to explain a
# mismatch in plain language.
REG_PREFIX_MEANING = {
    "INZ": "stock broker", "INB": "stock broker", "INF": "stock broker",
    "INA": "investment adviser", "INH": "research analyst",
    "INM": "merchant banker", "INR": "registrar / share transfer agent",
    "INP": "portfolio manager", "INBI": "banker to an issue",
    "IND": "debenture trustee", "IN-DP": "depository participant",
    "MF/": "mutual fund",
}


# --------------------------------------------------------------------------
# Identifier validation
# --------------------------------------------------------------------------

def is_valid_cin(cin: str) -> bool:
    """CIN = L/U + 5-digit industry + 2-letter state + 4-digit year
    + 3-letter ownership + 6-digit registration number. 21 characters.
    """
    cin = (cin or "").strip().upper()
    if len(cin) != 21:
        return False
    return bool(re.match(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$", cin))


def isin_check_digit(isin: str) -> int | None:
    """Compute the ISIN check digit (ISO 6166).

    Letters expand to two digits (A=10 ... Z=35), the resulting digit string is
    processed with the Luhn algorithm, and the check digit is whatever makes the
    total a multiple of ten. Computing this catches a fabricated ISIN that has
    the right shape, which a regex cannot.
    """
    isin = (isin or "").strip().upper()
    if len(isin) != 12:
        return None
    body = isin[:11]
    if not re.match(r"^[A-Z]{2}[A-Z0-9]{9}$", body):
        return None

    digits = ""
    for ch in body:
        if ch.isdigit():
            digits += ch
        elif ch.isalpha():
            digits += str(ord(ch) - 55)   # A -> 10
        else:
            return None

    total = 0
    # Luhn: double every second digit counting from the right of the full
    # (body + check) number, i.e. from the right of `digits` starting at index 0.
    for i, ch in enumerate(reversed(digits)):
        value = int(ch)
        if i % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - (total % 10)) % 10


def is_valid_isin(isin: str) -> bool:
    isin = (isin or "").strip().upper()
    if not re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", isin):
        return False
    expected = isin_check_digit(isin)
    return expected is not None and expected == int(isin[-1])


def registration_kind(reg_no: str) -> str | None:
    reg = (reg_no or "").strip().upper()
    for prefix, meaning in sorted(REG_PREFIX_MEANING.items(), key=lambda kv: -len(kv[0])):
        if reg.startswith(prefix):
            return meaning
    return None


# --------------------------------------------------------------------------
# Entity resolution
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def entity_aliases() -> dict[str, str]:
    """Acronyms and trading names -> the registered entity name.

    Indian institutions are universally referred to by acronym (CDSL, NSDL,
    KFin, RIL), and those acronyms do not fuzzy-match their full legal names.
    Resolving them explicitly is what stops "CDSL e-Voting" from being scored
    against a coincidental match.
    """
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "reference" / "entity_aliases.csv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            alias = normalise_company_name(row.get("alias", ""))
            target = (row.get("entity_name") or "").strip()
            if alias and target:
                out[alias] = target
    return out


@functools.lru_cache(maxsize=1)
def _entity_index() -> dict[str, list[dict[str, Any]]]:
    """normalised_name -> entity records. Built once per process."""
    index: dict[str, list[dict[str, Any]]] = {}
    try:
        with session_scope() as session:
            rows = session.execute(
                select(Entity.name, Entity.normalised_name, Entity.entity_type,
                       Entity.sebi_reg_no, Entity.isin, Entity.official_domains,
                       Entity.official_contact, Entity.status)
            ).all()
    except Exception:  # noqa: BLE001
        return {}

    for name, norm, etype, reg, isin, domains, contact, status in rows:
        if not norm:
            continue
        index.setdefault(norm, []).append({
            "name": name, "normalised_name": norm, "entity_type": etype,
            "sebi_reg_no": reg, "isin": isin, "official_domains": domains or [],
            "official_contact": contact or {}, "status": status,
        })
    return index


@functools.lru_cache(maxsize=1)
def _reg_no_index() -> dict[str, list[dict[str, Any]]]:
    """SEBI registration number -> the entities holding it."""
    index: dict[str, list[dict[str, Any]]] = {}
    for records in _entity_index().values():
        for rec in records:
            if rec.get("sebi_reg_no"):
                index.setdefault(rec["sebi_reg_no"].strip().upper(), []).append(rec)
    return index


@functools.lru_cache(maxsize=1)
def _isin_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for records in _entity_index().values():
        for rec in records:
            if rec.get("isin"):
                index.setdefault(rec["isin"].strip().upper(), rec)
    return index


def reset_entity_cache() -> None:
    _entity_index.cache_clear()
    _reg_no_index.cache_clear()
    _isin_index.cache_clear()


# Words that carry no organisational identity on their own. A display name made
# only of these is a role or a department, not a company.
#
# Without this guard, rapidfuzz's WRatio does partial matching and resolves
# "Company Secretary" to "Bombay Dyeing & Manufacturing COMPANY Ltd" at over 85,
# and "CDSL e-Voting" to "T T Ltd". Every genuine corporate email signed by the
# Company Secretary then appeared to claim to be a different listed company.
GENERIC_ENTITY_TOKENS = {
    "company", "secretary", "compliance", "officer", "investor", "investors",
    "relations", "relation", "services", "service", "support", "helpdesk",
    "help", "desk", "care", "customer", "team", "department", "dept", "office",
    "voting", "evoting", "e", "notice", "notices", "alert", "alerts", "info",
    "information", "admin", "administrator", "noreply", "no", "reply", "mail",
    "mailer", "statements", "statement", "grievance", "grievances", "redressal",
    "registrar", "transfer", "agent", "share", "shares", "securities", "limited",
    "ltd", "india", "indian", "the", "of", "and", "for", "corporate", "group",
    "contact", "enquiry", "enquiries", "queries", "query", "operations", "ops",
}

# Minimum length for a fuzzy entity match. Short strings score misleadingly high.
MIN_FUZZY_LENGTH = 6


def is_generic_name(name: str) -> bool:
    """True when a name carries no organisational identity of its own."""
    norm = normalise_company_name(name)
    if not norm:
        return True
    tokens = [t for t in norm.split() if t]
    if not tokens:
        return True
    return all(t in GENERIC_ENTITY_TOKENS for t in tokens)


def resolve_entity(name: str, *, threshold: int = FUZZY_THRESHOLD) -> dict[str, Any] | None:
    """Resolve a name to a known entity: exact on the normalised form, else fuzzy.

    Returns None for role names and department names -- see GENERIC_ENTITY_TOKENS.
    A confident wrong answer here is worse than no answer, because it invents a
    conflict between the sender and the domain they legitimately sent from.
    """
    norm = normalise_company_name(name)
    if not norm:
        return None

    index = _entity_index()
    if norm in index:
        record = dict(index[norm][0])
        record["match_score"] = 100
        record["match_type"] = "EXACT"
        return record

    # Known acronyms and trading names resolve before fuzzy matching, so "CDSL"
    # reaches Central Depository Services rather than a coincidental match.
    alias_target = entity_aliases().get(norm)
    if alias_target:
        alias_norm = normalise_company_name(alias_target)
        if alias_norm in index:
            record = dict(index[alias_norm][0])
            record["match_score"] = 100
            record["match_type"] = "ALIAS"
            return record
        return {
            "name": alias_target, "normalised_name": alias_norm,
            "entity_type": "OTHER_INTERMEDIARY", "sebi_reg_no": None, "isin": None,
            "official_domains": [], "official_contact": {}, "status": "ACTIVE",
            "match_score": 100, "match_type": "ALIAS",
        }

    if is_generic_name(norm) or len(norm) < MIN_FUZZY_LENGTH:
        return None

    match = process.extractOne(norm, index.keys(), scorer=fuzz.WRatio, score_cutoff=threshold)
    if not match:
        return None

    # Guard against partial-ratio inflation: the match must share a token that
    # is not merely generic corporate vocabulary.
    query_tokens = {t for t in norm.split() if t not in GENERIC_ENTITY_TOKENS}
    match_tokens = {t for t in match[0].split() if t not in GENERIC_ENTITY_TOKENS}
    if query_tokens and match_tokens and not (query_tokens & match_tokens):
        if fuzz.token_set_ratio(norm, match[0]) < 92:
            return None

    record = dict(index[match[0]][0])
    record["match_score"] = int(match[1])
    record["match_type"] = "FUZZY"
    return record


def find_claimed_entities(text: str) -> list[dict[str, Any]]:
    """Names of organisations this message claims to be from or about.

    Word n-grams are looked up against the normalised-name index rather than
    fuzzy-matching every one of ~10,000 entities against every phrase, which
    would be far too slow per request.
    """
    if not text:
        return []
    index = _entity_index()
    if not index:
        return []

    norm_text = normalise_company_name(text)
    words = norm_text.split()
    found: dict[str, dict[str, Any]] = {}

    # Longest n-grams first so "canara bank" wins over "canara".
    for size in range(6, 0, -1):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i + size])
            if len(phrase) < 4:
                continue
            if phrase in index:
                record = index[phrase][0]
                if record["normalised_name"] not in found:
                    found[record["normalised_name"]] = {
                        **record, "matched_phrase": phrase,
                        "match_score": 100, "match_type": "EXACT",
                    }

    low = normalise_for_matching(text)
    for token, official in AUTHORITY_NAMES.items():
        if re.search(rf"\b{re.escape(token)}\b", low):
            found.setdefault(f"__authority__{token}", {
                "name": official, "entity_type": "REGULATOR" if token in
                ("sebi", "rbi", "securities and exchange board", "reserve bank") else "EXCHANGE",
                "matched_phrase": token, "match_score": 100, "match_type": "AUTHORITY",
                "official_domains": [], "official_contact": {}, "status": "ACTIVE",
                "sebi_reg_no": None, "isin": None,
            })
    return list(found.values())


# --------------------------------------------------------------------------
# Main check
# --------------------------------------------------------------------------

def check(
    text: str,
    *,
    claimed_entity: str | None = None,
    sender_domain: str | None = None,
    live_verify: bool = False,
) -> CheckResult:
    """Run the ENTITY chokepoint.

    `live_verify` optionally confirms a registration number against SEBI's live
    register. Off by default: the demo path is offline, and a failed lookup must
    never change a verdict.
    """
    result = CheckResult(chokepoint=ENTITY, passed=None, confidence=0.0)
    text = text or ""
    norm_low = normalise_for_matching(text)

    entities = find_claimed_entities(text)
    if claimed_entity:
        resolved = resolve_entity(claimed_entity)
        if resolved:
            entities.append({**resolved, "matched_phrase": claimed_entity})

    checks_run = 0

    # ------------------------------------------------------------------- CIN
    cin_match = CIN_RE.search(text)
    if cin_match:
        checks_run += 1
        cin = cin_match.group(1).upper()
        if not is_valid_cin(cin):
            result.add(Reason(
                code="CIN_MALFORMED",
                message=(
                    f"The company identification number {cin} is not a valid CIN. "
                    "A real CIN is 21 characters in a fixed pattern."
                ),
                evidence={"cin": cin},
                severity=4,
            ))
        else:
            result.add(Reason(
                code="CIN_FORMAT_VALID",
                message=f"The CIN {cin} is correctly formed.",
                evidence={"cin": cin},
                severity=0,
            ))

    # ------------------------------------------------------------------ ISIN
    isin_match = ISIN_RE.search(text)
    if isin_match:
        checks_run += 1
        isin = isin_match.group(1).upper()
        if not is_valid_isin(isin):
            result.add(Reason(
                code="ISIN_CHECK_DIGIT_FAILED",
                message=(
                    f"The ISIN {isin} fails its check-digit test, which means it is not a "
                    "real security identifier. Genuine ISINs are self-verifying."
                ),
                evidence={"isin": isin, "expected_check_digit": isin_check_digit(isin)},
                severity=5,
            ))
        else:
            known = _isin_index().get(isin)
            if known:
                result.add(Reason(
                    code="ISIN_RESOLVED",
                    message=f"The ISIN {isin} is valid and belongs to {known['name']}.",
                    evidence={"isin": isin, "entity": known["name"]},
                    severity=0,
                ))
            else:
                result.add(Reason(
                    code="ISIN_VALID_BUT_UNKNOWN",
                    message=(
                        f"The ISIN {isin} is correctly formed but is not in our registry "
                        "of listed securities."
                    ),
                    evidence={"isin": isin},
                    severity=2,
                ))

    # -------------------------------------------------- SEBI registration no.
    reg_match = SEBI_REG_RE.search(text)
    if reg_match:
        checks_run += 1
        reg_no = reg_match.group(1).upper()
        kind = registration_kind(reg_no)
        holders = _reg_no_index().get(reg_no, [])

        if not holders:
            result.add(Reason(
                code="REG_NO_NOT_FOUND",
                message=(
                    f"The SEBI registration number {reg_no} does not appear in SEBI's "
                    "register of registered intermediaries."
                ),
                evidence={"registration_no": reg_no, "kind": kind},
                severity=4,
            ))
        else:
            registered_names = [h["name"] for h in holders]
            claimed_names = [
                e.get("matched_phrase") or e.get("name")
                for e in entities
                if e.get("match_type") != "AUTHORITY"
            ]
            if claimed_entity:
                claimed_names.append(claimed_entity)

            # THE CHECK THAT MATTERS: does this number belong to whoever is
            # using it?
            matched = False
            best_score = 0
            for claimed in filter(None, claimed_names):
                claimed_norm = normalise_company_name(claimed)
                for registered in registered_names:
                    score = fuzz.WRatio(claimed_norm, normalise_company_name(registered))
                    best_score = max(best_score, int(score))
                    if score >= FUZZY_THRESHOLD:
                        matched = True
                        break
                if matched:
                    break

            if matched:
                result.add(Reason(
                    code="REG_NO_VERIFIED",
                    message=(
                        f"SEBI registration {reg_no} is genuine and is registered to "
                        f"{registered_names[0]}, matching the sender."
                    ),
                    evidence={"registration_no": reg_no, "registered_to": registered_names,
                              "kind": kind, "match_score": best_score},
                    severity=0,
                ))
            elif claimed_names:
                result.add(Reason(
                    code="REG_NO_NAME_MISMATCH",
                    message=(
                        f"This message quotes SEBI registration {reg_no}, but that number "
                        f"belongs to {registered_names[0]} -- not to "
                        f"{claimed_names[0]}. Quoting somebody else's registration number "
                        "is a common way to appear regulated."
                    ),
                    evidence={
                        "registration_no": reg_no,
                        "registered_to": registered_names,
                        "claimed_by": claimed_names[:3],
                        "kind": kind,
                        "best_match_score": best_score,
                    },
                    severity=5,
                ))
            else:
                result.add(Reason(
                    code="REG_NO_VALID_NO_CLAIMANT",
                    message=(
                        f"SEBI registration {reg_no} is genuine and belongs to "
                        f"{registered_names[0]}, but this message does not clearly say "
                        "which firm is sending it."
                    ),
                    evidence={"registration_no": reg_no, "registered_to": registered_names},
                    severity=2,
                ))

            if live_verify:
                try:
                    from data.scrapers.sebi import lookup_registration_live
                    live = lookup_registration_live(reg_no)
                    if live.get("ok"):
                        result.add(Reason(
                            code="REG_NO_LIVE_CONFIRMED" if live.get("found") else "REG_NO_LIVE_ABSENT",
                            message=(
                                f"Confirmed against SEBI's live register: {reg_no} is "
                                f"registered to {', '.join(live['registered_names'])}."
                                if live.get("found") else
                                f"SEBI's live register returned no entry for {reg_no}."
                            ),
                            evidence=live,
                            severity=0 if live.get("found") else 4,
                        ))
                except Exception:  # noqa: BLE001 - live check is best-effort only
                    pass

    # ------------------------------------------------ impersonated authority
    #
    # Two conditions must BOTH hold, and each was a separate false-positive
    # source when it stood alone:
    #   (a) the message presents itself AS the authority, rather than citing it
    #   (b) it makes a real, non-negated demand for money
    demands_payment = bool(PAYMENT_DEMAND_RE.search(norm_low)) and not PAYMENT_NEGATION_RE.search(norm_low)

    claimed_is_authority = bool(AUTHORITY_AS_SENDER_RE.search(norm_low))
    if claimed_entity:
        claimed_norm = normalise_company_name(claimed_entity)
        claimed_is_authority = claimed_is_authority or any(
            normalise_company_name(official) == claimed_norm or token == claimed_norm
            for token, official in AUTHORITY_NAMES.items()
        )

    for entity in entities:
        if entity.get("match_type") != "AUTHORITY":
            continue
        checks_run += 1
        if demands_payment and claimed_is_authority:
            result.add(Reason(
                code="AUTHORITY_DEMANDS_PAYMENT",
                message=(
                    f"This message presents itself as {entity['name']} and asks for money. "
                    f"{entity['name']} does not contact individual investors to demand "
                    "payment, under any circumstances. Treat this as an impersonation."
                ),
                evidence={"authority": entity["name"], "matched_phrase": entity["matched_phrase"]},
                severity=5,
            ))
        else:
            result.add(Reason(
                code="AUTHORITY_REFERENCED",
                message=f"This message refers to {entity['name']}.",
                evidence={"authority": entity["name"]},
                severity=0,
            ))

    # ------------------------------------------------------- resolved sender
    real_entities = [e for e in entities if e.get("match_type") != "AUTHORITY"]
    for entity in real_entities[:3]:
        checks_run += 1
        if entity.get("status") and entity["status"] != "ACTIVE":
            result.add(Reason(
                code="ENTITY_NOT_ACTIVE",
                message=f"{entity['name']} is recorded in our registry with status {entity['status']}.",
                evidence={"entity": entity["name"], "status": entity["status"]},
                severity=3,
            ))
        else:
            result.add(Reason(
                code="ENTITY_RESOLVED",
                message=(
                    f"{entity['name']} is a real {entity['entity_type'].replace('_', ' ').lower()}"
                    + (f" registered with SEBI as {entity['sebi_reg_no']}." if entity.get("sebi_reg_no") else ".")
                ),
                evidence={
                    "entity": entity["name"],
                    "entity_type": entity["entity_type"],
                    "sebi_reg_no": entity.get("sebi_reg_no"),
                    "match_type": entity.get("match_type"),
                    "match_score": entity.get("match_score"),
                    "official_contact": entity.get("official_contact"),
                },
                severity=0,
            ))

    # ---------------------------------------------------------------- verdict
    if checks_run == 0:
        return CheckResult.undetermined(
            ENTITY, "This message does not name a company, regulator or registration number we can check."
        )

    failures = [r for r in result.reasons if r.severity >= 4]
    if failures:
        result.passed = False
        result.confidence = min(1.0, 0.7 + 0.1 * len(failures))
    elif any(r.severity == 3 for r in result.reasons):
        result.passed = False
        result.confidence = 0.5
    elif any(r.code in ("REG_NO_VERIFIED", "ISIN_RESOLVED", "ENTITY_RESOLVED") for r in result.reasons):
        result.passed = True
        result.confidence = 0.8
    else:
        result.passed = None
        result.confidence = 0.4

    return result
