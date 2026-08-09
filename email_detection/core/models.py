"""SQLAlchemy 2.0 declarative models for PhishermanAI.

PORTABILITY NOTE (SQLite -> Postgres)
------------------------------------
This schema runs on SQLite for the hackathon (zero server setup) but is written
to be Postgres-portable. Specifically:

  * No SQLite-only types. Everything is String/Text/Integer/Float/Date/DateTime/JSON.
  * `JSON` maps to TEXT-backed JSON on SQLite and to `json` on Postgres. For a
    Postgres deployment, switch these to `JSONB` and add GIN indexes on
    `filings.raw_json` -- one-line change, marked with `# PG: JSONB` below.
  * Enum-like columns are plain String + a CheckConstraint rather than native
    ENUM types, because SQLite has no ENUM and Postgres ENUMs need migrations
    to extend. The allowed values live in the Python enums in this module.
  * Autoincrement integer PKs work identically on both.
  * `official_domains` / `official_upi_handles` are JSON arrays rather than a
    child table, to keep the seed CSVs human-editable. In Postgres these would
    become `text[]` or a proper join table.

Migration path: `alembic init`, autogenerate against these models, then apply
the three swaps above. No data reshaping required.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Controlled vocabularies
# --------------------------------------------------------------------------

class FilingType(str, enum.Enum):
    DIVIDEND = "DIVIDEND"
    EGM_NOTICE = "EGM_NOTICE"
    AGM_NOTICE = "AGM_NOTICE"
    EVOTING = "EVOTING"
    BOARD_MEETING = "BOARD_MEETING"
    RESULTS = "RESULTS"
    OTHER = "OTHER"


class EntityType(str, enum.Enum):
    LISTED_COMPANY = "LISTED_COMPANY"
    BROKER = "BROKER"
    RTA = "RTA"
    EXCHANGE = "EXCHANGE"
    REGULATOR = "REGULATOR"
    MUTUAL_FUND = "MUTUAL_FUND"
    RIA = "RIA"
    RESEARCH_ANALYST = "RESEARCH_ANALYST"
    DEPOSITORY = "DEPOSITORY"
    # Remaining SEBI intermediary categories, present because we load the real
    # registers rather than a hand-picked subset.
    DEPOSITORY_PARTICIPANT = "DEPOSITORY_PARTICIPANT"
    MERCHANT_BANKER = "MERCHANT_BANKER"
    BANKER_TO_ISSUE = "BANKER_TO_ISSUE"
    DEBENTURE_TRUSTEE = "DEBENTURE_TRUSTEE"
    CREDIT_RATING_AGENCY = "CREDIT_RATING_AGENCY"
    KRA = "KRA"
    PORTFOLIO_MANAGER = "PORTFOLIO_MANAGER"
    OTHER_INTERMEDIARY = "OTHER_INTERMEDIARY"


FILING_TYPES = tuple(t.value for t in FilingType)
ENTITY_TYPES = tuple(t.value for t in EntityType)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    """Render a portable CheckConstraint expression."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

class Filing(Base):
    """A corporate announcement as filed with an exchange. This is ground truth.

    Everything the tamper detector compares against lives here. `raw_json` keeps
    the untouched API response so we can re-derive fields later without
    re-scraping (the demo path must never hit the network).
    """

    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12))
    scrip_code: Mapped[str | None] = mapped_column(String(16))
    exchange: Mapped[str] = mapped_column(String(8), nullable=False, default="BSE")
    filing_type: Mapped[str] = mapped_column(String(24), nullable=False, default=FilingType.OTHER.value)
    filing_date: Mapped[datetime | None] = mapped_column(DateTime)
    headline: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JSON)  # PG: JSONB

    # Structured fields the tamper detector compares field-by-field.
    dividend_per_share: Mapped[float | None] = mapped_column(Float)
    record_date: Mapped[date | None] = mapped_column(Date)
    meeting_date: Mapped[date | None] = mapped_column(Date)
    evoting_start: Mapped[date | None] = mapped_column(Date)
    evoting_end: Mapped[date | None] = mapped_column(Date)

    # Stable identity of the source record, used for idempotent re-loads.
    source_id: Mapped[str | None] = mapped_column(String(64))
    # Cached sentence-transformer embedding (JSON float array) so semantic
    # ranking never recomputes per request.
    embedding: Mapped[list | None] = mapped_column(JSON)  # PG: JSONB / pgvector
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("exchange", "source_id", name="uq_filing_source"),
        CheckConstraint(_in_list("filing_type", FILING_TYPES), name="ck_filing_type"),
        Index("ix_filings_company_name", "company_name"),
        Index("ix_filings_isin", "isin"),
        Index("ix_filings_filing_date", "filing_date"),
        Index("ix_filings_scrip_code", "scrip_code"),
        Index("ix_filings_type_date", "filing_type", "filing_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Filing {self.company_name!r} {self.filing_type} {self.filing_date}>"


class Entity(Base):
    """A real-world organisation a message might claim to be from.

    Covers listed companies (from the BSE scrip master), plus hand-curated
    brokers, RTAs, depositories, exchanges and the regulator.
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Suffix-stripped, lowercased form used for fuzzy matching. Denormalised on
    # purpose: rapidfuzz over a precomputed column is much faster than
    # normalising 5,000 names per request.
    normalised_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    cin: Mapped[str | None] = mapped_column(String(21))
    sebi_reg_no: Mapped[str | None] = mapped_column(String(32))
    isin: Mapped[str | None] = mapped_column(String(12))
    scrip_code: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")

    official_domains: Mapped[list | None] = mapped_column(JSON)       # PG: JSONB
    official_upi_handles: Mapped[list | None] = mapped_column(JSON)   # PG: JSONB
    official_contact: Mapped[dict | None] = mapped_column(JSON)       # phone/email/url
    rta_name: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)

    domains: Mapped[list["DomainMap"]] = relationship(back_populates="entity")

    __table_args__ = (
        CheckConstraint(_in_list("entity_type", ENTITY_TYPES), name="ck_entity_type"),
        Index("ix_entities_name", "name"),
        Index("ix_entities_normalised_name", "normalised_name"),
        Index("ix_entities_isin", "isin"),
        Index("ix_entities_sebi_reg_no", "sebi_reg_no"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Entity {self.name!r} {self.entity_type}>"


class DomainMap(Base):
    """Which domains legitimately belong to which entity.

    This is the table that turns a passing DMARC check into a meaningful one:
    DMARC proves a mail came from the domain it claims, this table answers
    whether that domain has any business claiming to be the entity.
    """

    __tablename__ = "domain_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"))
    entity_name: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    # OFFICIAL | EVOTING | INVESTOR_SERVICES | RTA_PORTAL | TRADING_PLATFORM | EMAIL_SENDER
    relationship_type: Mapped[str] = mapped_column(String(32), default="OFFICIAL")
    verified_source: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    entity: Mapped["Entity | None"] = relationship(back_populates="domains")

    __table_args__ = (
        UniqueConstraint("domain", "entity_name", name="uq_domain_entity"),
        Index("ix_domain_map_domain", "domain"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DomainMap {self.domain} -> {self.entity_name}>"


class ClaimRule(Base):
    """A regex-backed rule about what a financial message may legally promise."""

    __tablename__ = "claim_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    # A regex that SUPPRESSES this rule when found near a match.
    #
    # Most credential and urgency vocabulary is direction-blind: "sending OTP
    # on registered Mobile" (an institution authenticating you) and "share the
    # OTP with me" (a fraudster stealing from you) contain the same tokens. The
    # pattern matches the noun; this column encodes the direction that makes it
    # harmless. Genuine e-voting, KYC and AGM mail is dense with such language,
    # so without this every real CDSL/NSDL notice reads as an attack.
    safe_context: Mapped[str | None] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("code", name="uq_claim_rule_code"),
        CheckConstraint("severity BETWEEN 1 AND 5", name="ck_claim_severity"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClaimRule {self.code} sev={self.severity}>"


class KnownFraud(Base):
    """Fingerprints of content already reported as fraudulent.

    `report_count` is what turns N identical reports into one campaign rather
    than N tickets -- see /stats clustering.
    """

    __tablename__ = "known_frauds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    phash: Mapped[str | None] = mapped_column(String(64))
    domain: Mapped[str | None] = mapped_column(String(253))
    label: Mapped[str | None] = mapped_column(String(64))
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    report_count: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        Index("ix_known_frauds_content_hash", "content_hash"),
        Index("ix_known_frauds_phash", "phash"),
        Index("ix_known_frauds_domain", "domain"),
    )


class Verification(Base):
    """Every verdict we issue, for /stats and fraud-campaign clustering.

    PRIVACY: we deliberately store only a hash of the submitted content plus the
    derived verdict -- never the raw message body. See docs/PRIVACY.md.
    """

    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    phash: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default="WEB")  # WEB | EXTENSION | API
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    claimed_entity: Mapped[str | None] = mapped_column(String(256))
    top_domain: Mapped[str | None] = mapped_column(String(253))
    reason_codes: Mapped[list | None] = mapped_column(JSON)  # PG: JSONB
    matched_filing_id: Mapped[int | None] = mapped_column(ForeignKey("filings.id"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # --- SMTP gateway fields (Phase 7) -------------------------------------
    # Populated only when a message arrives through the mail gateway. The
    # Message-ID is the dedup key: the same message re-delivered (a retry, or a
    # copy to a second recipient) reuses the stored verdict instead of being
    # re-verified.
    #
    # PRIVACY: envelope metadata only. The body is still never stored -- the
    # subject is kept because the gateway rewrites it and an operator needs to
    # see the original to explain what happened.
    message_id: Mapped[str | None] = mapped_column(String(998))
    from_addr: Mapped[str | None] = mapped_column(String(320))
    to_addr: Mapped[str | None] = mapped_column(String(998))
    subject_original: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_verifications_content_hash", "content_hash"),
        Index("ix_verifications_verdict", "verdict"),
        Index("ix_verifications_created_at", "created_at"),
    )


class WhoisCache(Base):
    """Disk-backed WHOIS results.

    HARD CONSTRAINT: the demo path never resolves WHOIS live. Lookups during
    development populate this table; at request time we read from it and return
    `passed=None` (unknown) on a miss rather than blocking on the network.
    """

    __tablename__ = "whois_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(253), nullable=False, unique=True)
    creation_date: Mapped[datetime | None] = mapped_column(DateTime)
    expiration_date: Mapped[datetime | None] = mapped_column(DateTime)
    registrar: Mapped[str | None] = mapped_column(String(256))
    country: Mapped[str | None] = mapped_column(String(64))
    lookup_ok: Mapped[int] = mapped_column(Integer, default=1)
    raw: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ShortenerCache(Base):
    """Cached URL-shortener expansions, for the same offline reason as WHOIS."""

    __tablename__ = "shortener_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    short_url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    expanded_url: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
