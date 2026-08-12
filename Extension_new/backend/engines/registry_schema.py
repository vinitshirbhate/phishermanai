"""
registry_schema.py - one record shape for regulator registries, anywhere,
plus the tiering rule that decides which fields may leave this machine.

TWO PROBLEMS, ONE MODULE
--------------------------
1. Every regulator publishes a different shape. SEBI gives you
   "Registration No. / Name / E-mail / Telephone / Validity"; the SEC gives
   you a CRD number and a Form ADV; the FCA gives you an FRN. If each
   scraper invents its own dict, the matcher has to know about all of them
   and the eighteenth one breaks it. `RegistryRecord` is the single shape
   every jurisdiction adapter normalises INTO, so the verification logic is
   written once.

2. Verification needs contact data. Impersonation is detected by MATCHING:
   an email claiming to be 1 Finance is checkable only against 1 Finance's
   registered email. So the naive read is "ship the whole directory".

   That read is wrong, and the reason is worth stating precisely rather
   than as a compliance shrug.

WHY THE FULL DIRECTORY MUST NOT SHIP IN THE EXTENSION
-------------------------------------------------------
SEBI's register lists ~3,000 Investment Advisers and Research Analysts,
a large share of whom are individual proprietors. For those registrants the
"Address" field is a home address and the "Telephone" field is a personal
mobile. Bundling all 18 categories with contact fields intact produces, in
every user's browser profile, a plain-JSON file containing tens of
thousands of named individuals' home addresses and mobile numbers.

That file is not merely a DPDPA problem. It is a *target list*. The exact
adversary this product exists to stop - someone running vishing and
spear-phishing against Indian securities-market participants - would find a
pre-cleaned, deduplicated, regulator-sourced directory of advisers'
personal mobiles considerably more useful than anything they currently buy.
Shipping it inside an anti-phishing tool would mean the tool's own data
file is the best phishing asset in the ecosystem. "Investors must be safe"
has to include the ~3,000 individual advisers who are also people.

THE DESIGN THAT KEEPS BOTH
----------------------------
Verification is a MATCH operation, not a LOOKUP operation. The extension
never needs to *read* the registered phone number; it needs to answer
"does the number in front of me equal the registered one?" That is
satisfiable with a one-way hash.

    TIER_FULL     - every field SEBI publishes, verbatim.
                    Lives in backend/data/, on the user's own machine,
                    fetched by them directly from the regulator. Never
                    bundled, never transmitted. This is the tier that
                    answers "show me the record" for a human operator.

    TIER_ANCHOR   - what ships in the extension. Registration number, name,
                    category, status, validity, CIN, and SALTED HASHES of
                    the contact identifiers, plus the email DOMAIN in clear
                    (a domain is corporate identity, not personal data, and
                    it is what actually catches lookalike senders).
                    Full-power matching, zero readable PII, and it cannot
                    be reversed into a call list.

    TIER_PUBLIC   - registration number, name, category, status only. For
                    anything shared, exported, or logged.

The salt is per-install and generated locally (see `install_salt()`), so
two users' anchor files are not comparable and a stolen bundle cannot be
rainbow-tabled against a national phone-number space. This costs nothing:
the extension hashes what it observes with its own salt and compares
locally.

CIN
---
Corporate Identification Number is company-registry data from MCA, not
personal data, and it is the join key between "who SEBI registered" and
"what company actually exists". It is carried in TIER_ANCHOR in clear
precisely because it is the non-personal identifier that lets a user check
a corporate claim without needing anybody's mobile number.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"

TIER_FULL = "full"
TIER_ANCHOR = "anchor"
TIER_PUBLIC = "public"

# Free/consumer mail providers. A registrant's gmail.com address is NOT a
# corporate identity anchor - treating it as one would let any gmail sender
# match any gmail-registered adviser. Recorded, never used for domain match.
FREE_MAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.in",
    "hotmail.com", "outlook.com", "live.com", "rediffmail.com", "rediff.com",
    "ymail.com", "icloud.com", "protonmail.com", "aol.com", "msn.com",
    "yandex.com", "zoho.com", "zohomail.com", "mail.com", "gmx.com",
}

_CIN_RE = re.compile(r"\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b", re.I)


# --------------------------------------------------------------------------- #
# Jurisdictions
# --------------------------------------------------------------------------- #
# `id_label` is what that regulator calls its registration number, so UI copy
# is correct per jurisdiction instead of saying "SEBI number" to a UK user.
JURISDICTIONS = {
    "IN-SEBI": {
        "regulator": "Securities and Exchange Board of India",
        "country": "IN", "id_label": "SEBI Registration No.",
        "register_url": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes",
        "implemented": True,
    },
    "IN-MCA": {
        "regulator": "Ministry of Corporate Affairs",
        "country": "IN", "id_label": "CIN",
        "register_url": "https://www.mca.gov.in/mcafoportal/companyLLPMasterData.do",
        "implemented": False,
    },
    "IN-RBI": {
        "regulator": "Reserve Bank of India", "country": "IN",
        "id_label": "RBI Registration No.",
        "register_url": "https://www.rbi.org.in/scripts/bs_viewcontent.aspx?Id=2",
        "implemented": False,
    },
    "US-SEC": {
        "regulator": "U.S. Securities and Exchange Commission",
        "country": "US", "id_label": "CRD / SEC No.",
        "register_url": "https://adviserinfo.sec.gov/", "implemented": False,
    },
    "UK-FCA": {
        "regulator": "Financial Conduct Authority", "country": "GB",
        "id_label": "FRN",
        "register_url": "https://register.fca.org.uk/", "implemented": False,
    },
    "SG-MAS": {
        "regulator": "Monetary Authority of Singapore", "country": "SG",
        "id_label": "MAS Licence No.",
        "register_url": "https://eservices.mas.gov.sg/fid", "implemented": False,
    },
    "AU-ASIC": {
        "regulator": "Australian Securities and Investments Commission",
        "country": "AU", "id_label": "AFS Licence No.",
        "register_url": "https://asic.gov.au/online-services/search-asics-registers/",
        "implemented": False,
    },
}


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #
@dataclass
class RegistryRecord:
    """One registered entity, in one regulator's register, anywhere."""

    # --- identity: non-personal, present in every tier -------------------- #
    jurisdiction: str                     # key into JURISDICTIONS
    reg_number: str
    reg_prefix: str
    registered_name: str
    name_normalised: str
    category: str                         # our normalised code, e.g. "IA"
    category_label: str = ""              # regulator's own label
    status: str = "active"
    validity_start: Optional[str] = None
    validity_end: Optional[str] = None    # "perpetual" is a legal value here
    as_on_date: Optional[str] = None

    # --- corporate identity: non-personal, ships in clear ----------------- #
    # CIN identifies a COMPANY, not a person. It is the join key to MCA and
    # the thing that lets a user check "is this actually a real company"
    # without anybody's mobile number entering the picture.
    cin: Optional[str] = None
    entity_kind: Optional[str] = None     # "company" | "llp" | "individual"
    email_domain: Optional[str] = None    # corporate identity, not personal
    domain_anchor: Optional[str] = None   # email_domain minus free-mail hosts
    website: Optional[str] = None

    # --- contact: PERSONAL DATA. TIER_FULL ONLY. -------------------------- #
    # Populated by the scraper, used to compute the anchors below, then
    # dropped by `to_tier(TIER_ANCHOR)`. If you find yourself wanting these
    # in the extension, re-read this module's docstring - the operation you
    # want is almost certainly a match, and matching is already available.
    email: Optional[str] = None
    telephone: Optional[str] = None
    fax: Optional[str] = None
    address: Optional[str] = None
    correspondence_address: Optional[str] = None
    contact_person: Optional[str] = None

    # --- match anchors: one-way, salted. Ship freely. --------------------- #
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None
    contact_person_hash: Optional[str] = None

    source_url: Optional[str] = None
    raw: dict = field(default_factory=dict)

    # Field groups, so the tiering is declared once and cannot drift.
    PERSONAL_FIELDS = ("email", "telephone", "fax", "address",
                       "correspondence_address", "contact_person")
    ANCHOR_FIELDS = ("email_hash", "phone_hash", "contact_person_hash")
    PUBLIC_FIELDS = ("jurisdiction", "reg_number", "reg_prefix",
                     "registered_name", "name_normalised", "category",
                     "category_label", "status", "validity_start",
                     "validity_end", "as_on_date")

    def to_tier(self, tier: str) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        if tier == TIER_FULL:
            return d
        # Anything below FULL loses readable personal data, permanently.
        for f in self.PERSONAL_FIELDS:
            d.pop(f, None)
        if tier == TIER_ANCHOR:
            return d
        if tier == TIER_PUBLIC:
            return {k: d.get(k) for k in self.PUBLIC_FIELDS}
        raise ValueError(f"unknown tier: {tier!r}")


# --------------------------------------------------------------------------- #
# Salt + anchors
# --------------------------------------------------------------------------- #
def install_salt() -> bytes:
    """
    Per-install salt, generated locally on first use.

    Per-install rather than global on purpose: a single shipped salt would
    make every user's anchor file identical and therefore precomputable
    against the Indian mobile-number space (10 digits is ~10^10, trivially
    brute-forced offline). A local random salt makes the anchors useful only
    to the machine that built them.
    """
    p = DATA_DIR / ".registry_salt"
    if p.exists():
        return p.read_bytes()
    salt = secrets.token_bytes(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(salt)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return salt


def normalise_email(v: str) -> str:
    return (v or "").strip().lower()


def normalise_phone(v: str) -> str:
    """
    Digits only, last 10 kept.

    SEBI's own data is inconsistent here - the sample record for
    1 Finance carries "00007738942481", which is a 10-digit Mumbai mobile
    (7738942481) behind four padding zeros and a country prefix. Hashing the
    raw string would fail to match the same number written any other way, so
    every number is reduced to its national significant digits first.
    """
    digits = re.sub(r"\D", "", v or "")
    return digits[-10:] if len(digits) >= 10 else digits


def anchor(value: str, salt: bytes) -> Optional[str]:
    """Salted one-way anchor. Truncated to 128 bits - ample for equality."""
    if not value:
        return None
    return hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def compute_anchors(rec: RegistryRecord, salt: bytes) -> RegistryRecord:
    rec.email_hash = anchor(normalise_email(rec.email or ""), salt)
    rec.phone_hash = anchor(normalise_phone(rec.telephone or ""), salt)
    rec.contact_person_hash = anchor(
        (rec.contact_person or "").strip().lower(), salt)
    if rec.email and not rec.email_domain:
        rec.email_domain = normalise_email(rec.email).rpartition("@")[2] or None
    if rec.email_domain and rec.email_domain not in FREE_MAIL:
        rec.domain_anchor = rec.email_domain
    return rec


def match_contact(observed: str, rec: dict, salt: bytes, kind: str) -> dict:
    """
    Does an observed email/phone match this registrant's registered one?

    This is the whole point of the anchor tier: a caller gets a definitive
    yes/no without the record ever containing a readable address or number.
    `unknown` is returned when the register simply has no value to compare -
    which, per this project's standing rule, is never evidence against the
    entity.
    """
    if kind == "email":
        probe, stored = normalise_email(observed), rec.get("email_hash")
    elif kind == "phone":
        probe, stored = normalise_phone(observed), rec.get("phone_hash")
    else:
        raise ValueError(f"unknown kind: {kind!r}")

    if not stored:
        return {"match": "unknown", "kind": kind,
                "reason": "The register holds no value for this field, so "
                          "there is nothing to compare against. This is not "
                          "a finding about the entity."}
    if not probe:
        return {"match": "unknown", "kind": kind,
                "reason": "Nothing observed to check."}
    if hmac.compare_digest(anchor(probe, salt) or "", stored):
        return {"match": "yes", "kind": kind,
                "reason": f"This {kind} matches the one on the regulator's "
                          f"register for {rec.get('reg_number')}."}
    return {"match": "no", "kind": kind,
            "reason": f"This {kind} is not the one on the regulator's "
                      f"register for {rec.get('reg_number')}. Registrants do "
                      "use additional addresses and numbers, so treat this as "
                      "a prompt to verify through a channel you chose, not as "
                      "proof of impersonation."}


def extract_cin(text: str) -> Optional[str]:
    """CIN out of free text. L/U + 5 industry + 2 state + 4 year + 3 + 6."""
    m = _CIN_RE.search(text or "")
    return m.group(1).upper() if m else None


def normalise_name(name: str) -> str:
    n = re.sub(r"\b(private|pvt|limited|ltd|llp|and|&)\b", " ", name or "",
               flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9 ]", " ", n.lower()).strip()


def infer_entity_kind(name: str, cin: Optional[str]) -> str:
    if cin:
        return "llp" if cin.upper().startswith("U") and "LLP" in name.upper() else "company"
    if re.search(r"\b(limited|ltd|private|pvt|llp|inc|corp)\b", name or "",
                 re.IGNORECASE):
        return "company"
    return "individual"


def tier_report() -> dict:
    """Machine-readable statement of what leaves this machine, for the UI."""
    return {
        "tiers": {
            TIER_FULL: {
                "location": "backend/data/ on the user's own machine only",
                "contains": list(RegistryRecord.PERSONAL_FIELDS) + ["everything else"],
                "leaves_device": False,
            },
            TIER_ANCHOR: {
                "location": "extension bundle",
                "contains": ["identity fields", "cin", "email_domain"]
                            + list(RegistryRecord.ANCHOR_FIELDS),
                "leaves_device": True,
                "note": ("Contact identifiers are present only as salted "
                         "one-way anchors. Equality can be checked; the "
                         "values cannot be read or recovered."),
            },
            TIER_PUBLIC: {
                "location": "anything exported, shared, or logged",
                "contains": list(RegistryRecord.PUBLIC_FIELDS),
                "leaves_device": True,
            },
        },
        "salt": "per-install, generated locally, never transmitted",
    }
