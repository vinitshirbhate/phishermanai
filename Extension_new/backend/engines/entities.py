"""
Shared entity extractors: URLs, phones, emails, UPI handles.

UPI_RE was duplicated in scam_detector.py and scamgate.py. Only scamgate learned
that the pattern also matches the front of every email address, so
scam_detector reported "support@sebi.gov.in" as a payment handle and added risk
to every mail page. Defined once here; both engines import it.

A UPI VPA is identifier@psp, where psp is a bank/app suffix, never a TLD or mail
host. is_upi_handle() applies three rules, cheapest first:

  1. Drop candidates that are the prefix of a real email address in the text.
  2. Accept a known PSP suffix.
  3. Otherwise reject TLD-shaped and free-mail suffixes.

Rule 3 keeps unknown-but-real PSPs while refusing user@gmail and support@sebi.
A missed handle costs a corroborating signal; a false one accuses an email
address of being a payment request, which is a G-2 false accusation.
"""
from __future__ import annotations

import re

__all__ = [
    "URL_RE", "PHONE_RE", "EMAIL_RE", "UPI_CANDIDATE_RE",
    "PSP_HANDLES", "FREE_MAIL_HOSTS",
    "extract_urls", "extract_phones", "extract_emails", "extract_upi",
    "is_upi_handle",
]

URL_RE = re.compile(r"(https?://[^\s\)\]\}<>\"']+)")
PHONE_RE = re.compile(r"(?:\+91[-\s]?)?(?:0)?([6-9]\d{9})\b")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
UPI_CANDIDATE_RE = re.compile(r"\b([a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,})\b")

# NPCI PSP handles. Not exhaustive and not required to be - rule 3 below is what
# handles the ones missing here. Sourced from the handles appearing in
# backend/data/reported_upi.json plus the major live PSPs.
PSP_HANDLES = frozenset({
    "upi", "ybl", "ibl", "axl", "apl", "abfspay", "airtel", "airtelpaymentsbank",
    "aubank", "axisb", "axisbank", "axisgo", "bandhan", "barodampay", "boi",
    "cbin", "cnrb", "csbpay", "dbs", "dlb", "equitas", "ezeepay", "federal",
    "fbl", "finobank", "freecharge", "hdfcbank", "hsbc", "icici", "idbi",
    "idfcbank", "idfcfirst", "indianbank", "indus", "indianbk", "iob", "jio",
    "jkb", "jupiteraxis", "kaypay", "kbl", "kmb", "kmbl", "kotak", "lvb",
    "mahb", "myicici", "naviaxis", "obc", "okaxis", "okbizaxis", "okhdfcbank",
    "okicici", "oksbi", "paytm", "payzapp", "postbank", "pingpay", "pnb",
    "psb", "purz", "rajgovhdfcbank", "rbl", "sbi", "scb", "scbl", "sib",
    "slice", "sliceaxis", "sliceaxisbank", "srcb", "tapicici", "timecosmos",
    "ubi", "uboi", "uco", "unionbank", "unionbankofindia", "utbi", "vijb",
    "waaxis", "waicici", "wasbi", "yesbank", "yesbankltd", "yapl",
})

FREE_MAIL_HOSTS = frozenset({
    "gmail", "googlemail", "yahoo", "ymail", "rediffmail", "rediff", "hotmail",
    "outlook", "live", "msn", "protonmail", "proton", "icloud", "me", "aol",
    "zoho", "mail", "gmx", "yandex", "fastmail", "hey", "tutanota",
})

# Suffixes that are TLDs or second-level domain labels. A candidate ending in one
# of these is the head of a hostname, not a PSP handle.
_TLD_LIKE = frozenset({
    "com", "net", "org", "edu", "gov", "int", "mil", "info", "biz", "io", "ai",
    "co", "in", "uk", "us", "eu", "de", "fr", "jp", "cn", "au", "ca", "nz",
    "app", "dev", "xyz", "online", "site", "tech", "store", "cloud", "me",
})


def _suffix(candidate: str) -> str:
    return candidate.rsplit("@", 1)[-1].lower()


def is_upi_handle(candidate: str, emails: list[str] | None = None) -> bool:
    """True when `candidate` is plausibly a UPI VPA rather than an email prefix."""
    cand = (candidate or "").strip().lower()
    if "@" not in cand:
        return False

    # Rule 1 - it is the front of a real email address that appears in the text.
    for e in (emails or []):
        e = e.lower()
        if cand == e or e.startswith(cand + "."):
            return False

    suffix = _suffix(cand)
    if not suffix:
        return False

    # Rule 2 - a known PSP handle is accepted outright.
    if suffix in PSP_HANDLES:
        return True

    # Rule 3 - otherwise it must not look like part of a mail domain.
    if suffix in FREE_MAIL_HOSTS or suffix in _TLD_LIKE:
        return False

    return True


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def extract_phones(text: str) -> list[str]:
    return [m.group(1) for m in PHONE_RE.finditer(text or "")]


def extract_emails(text: str) -> list[str]:
    return EMAIL_RE.findall(text or "")


def extract_upi(text: str) -> list[str]:
    """Payment handles only. Email addresses are not payment handles."""
    src = text or ""
    emails = extract_emails(src)
    out: list[str] = []
    for m in UPI_CANDIDATE_RE.finditer(src):
        cand = m.group(1)
        if is_upi_handle(cand, emails):
            out.append(cand)
    return out
