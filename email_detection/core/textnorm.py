"""Text normalisation shared by entity resolution, claim scanning and lookalike
domain detection.

Two separate normalisations live here and they are deliberately different:

  normalise_for_matching()  -- aggressive. Folds homoglyphs, strips zero-width
                               characters, collapses whitespace. Used before
                               regex claim rules so that "guаranteed" (with a
                               Cyrillic a) still matches /guaranteed/.

  normalise_company_name()  -- strips corporate suffixes and punctuation so
                               "Canara Bank Ltd.", "CANARA BANK LIMITED" and
                               "Canara Bank" all collapse to "canara bank".

Fraudsters use Cyrillic/Greek lookalikes precisely because they defeat naive
string matching, so folding them is not a nicety -- it is a detection control.
"""

from __future__ import annotations

import re
import unicodedata

# Characters that render (near-)identically to ASCII but carry different code
# points. Sources: Unicode confusables (TR39) restricted to the sets we
# actually see in Indian financial phishing -- Cyrillic and Greek.
HOMOGLYPHS: dict[str, str] = {
    # Cyrillic -> Latin
    "а": "a", "А": "A",
    "е": "e", "Е": "E",
    "о": "o", "О": "O",
    "р": "p", "Р": "P",
    "с": "c", "С": "C",
    "у": "y", "У": "Y",
    "х": "x", "Х": "X",
    "і": "i", "І": "I",
    "ј": "j", "Ј": "J",
    "һ": "h", "Н": "H",
    "В": "B", "М": "M", "К": "K", "Т": "T",
    "Ѕ": "S", "ѕ": "s",
    # Greek -> Latin
    "ο": "o", "Ο": "O",
    "α": "a", "Α": "A",
    "ε": "e", "Ε": "E",
    "ρ": "p", "Ρ": "P",
    "υ": "u", "Υ": "Y",
    "κ": "k", "Κ": "K",
    "ν": "v", "Ν": "N",
    "τ": "t", "Τ": "T",
    "Β": "B", "Η": "H", "Ι": "I", "Μ": "M", "Χ": "X",
    # Fullwidth / mathematical variants seen in copy-pasted scam text
    "ａ": "a", "ｅ": "e", "ｏ": "o",
}

_HOMOGLYPH_TABLE = str.maketrans(HOMOGLYPHS)

# Zero-width and other invisible characters used to break keyword filters:
# ZWSP, ZWNJ, ZWJ, word joiner, soft hyphen, BOM, LTR/RTL marks.
INVISIBLE_CHARS = "​‌‍⁠­﻿‎‏‪‫‬‭‮"
_INVISIBLE_RE = re.compile(f"[{re.escape(INVISIBLE_CHARS)}]")

# Legal-form suffixes stripped before fuzzy entity matching. Order matters:
# longer forms first so "private limited" is removed before "limited".
#
# "corporation", "corp" and "company" are deliberately NOT in this list, even
# though they look like suffixes. In Indian corporate names they are part of the
# name itself -- Birla Corporation, Titan Company, Power Grid Corporation of
# India, Oil and Natural Gas Corporation. Stripping them collapsed "Birla
# Corporation Ltd" to "birla", which then failed to match its own filings and
# collided with unrelated Birla-group entities.
COMPANY_SUFFIXES = [
    "private limited", "public limited", "pvt ltd", "pvt. ltd.", "pvt limited",
    "limited", "ltd", "ltd.", "llp", "inc", "incorporated", "plc",
]

# Trailing geographic qualifiers that vary between filings and letterheads.
COMPANY_QUALIFIERS = ["india", "of india", "(india)"]

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s@.\-/%:+]", re.UNICODE)


def strip_invisible(text: str) -> str:
    """Remove zero-width and bidi control characters."""
    return _INVISIBLE_RE.sub("", text)


def fold_homoglyphs(text: str) -> str:
    """Map Cyrillic/Greek lookalikes onto their Latin equivalents."""
    return text.translate(_HOMOGLYPH_TABLE)


def normalise_for_matching(text: str, *, lower: bool = True) -> str:
    """Aggressive normalisation used before running claim regexes.

    NFKC first (folds fullwidth forms and ligatures), then invisible-character
    removal, then homoglyph folding, then whitespace collapse.

    Note: this preserves Devanagari and other Indic scripts untouched -- claim
    rules match Hindi phrases directly, so we must not transliterate here.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = strip_invisible(out)
    out = fold_homoglyphs(out)
    out = _WS_RE.sub(" ", out)
    out = out.strip()
    return out.lower() if lower else out


def normalise_company_name(name: str) -> str:
    """Collapse a company name to a comparable form.

    "Sambhav Steel Tubes Limited" and "Sambhav Steel Tubes Ltd" must produce the
    same string, otherwise the filings matcher misses genuine documents.
    """
    if not name:
        return ""
    out = normalise_for_matching(name)
    out = out.replace("&", " and ")
    out = _PUNCT_RE.sub(" ", out)
    out = _WS_RE.sub(" ", out).strip()

    # Strip suffixes repeatedly: "Foo Industries Ltd Co" -> "foo industries".
    changed = True
    while changed:
        changed = False
        for suffix in COMPANY_SUFFIXES:
            if out.endswith(" " + suffix):
                out = out[: -len(suffix) - 1].strip()
                changed = True
        for qual in COMPANY_QUALIFIERS:
            if out.endswith(" " + qual):
                out = out[: -len(qual) - 1].strip()
                changed = True
    return _WS_RE.sub(" ", out).strip()


def normalise_domain(domain: str) -> str:
    """Lowercase, strip scheme/port/trailing dot and a leading 'www.'."""
    if not domain:
        return ""
    d = domain.strip().lower()
    d = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0]
    d = d.split("@")[-1]        # strip userinfo
    d = d.split(":")[0]         # strip port
    d = d.rstrip(".")
    if d.startswith("www."):
        d = d[4:]
    return d


def canonical_hash_text(text: str) -> str:
    """Normalisation used for the exact-match (TIER 1) content hash.

    Must be stable across re-encodings: strip all whitespace differences,
    punctuation spacing and case, so a PDF-to-text and an email body of the same
    circular hash identically.
    """
    out = normalise_for_matching(text)
    out = re.sub(r"[^\w]", "", out)
    return out


def collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()
