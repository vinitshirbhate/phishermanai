#!/usr/bin/env python3
"""
scripts/check_blocked_claims.py - F-D3 blocked-claims CI gate.

Fails the build if a blocked claim appears in USER-FACING COPY.

Scope matters here. We scan the strings the product shows a user (extension UI,
i18n, docs) - NOT detection patterns or fixtures. `backend/data/*` deliberately
contains phrases like "100% safe" and "guaranteed profit": those are scam text we
DETECT, not claims we MAKE. Scanning them would produce nonsense failures and the
gate would be switched off, which is worse than not having it.

Usage:
    python scripts/check_blocked_claims.py          # exit 1 on violation
    python scripts/check_blocked_claims.py --list   # show the rule set
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files whose strings reach the user.
SCAN_GLOBS = [
    "extension/**/*.js",
    "extension/**/*.html",
    "extension/i18n/*.json",
    "README.md",
]
# Never scan: detection corpora, fixtures, evaluation inputs, this checker.
EXCLUDE_PARTS = ("backend/data/", "eval/fixtures/", "node_modules/", ".venv/",
                 "scripts/check_blocked_claims.py", "extension/data/")

# (regex, human explanation). Deliberately phrase-level, not word-level.
BLOCKED = [
    (r"(?i)\bthis\s+is\s+a\s+deepfake\b", "synthetic-origin verdict (F-D3)"),
    (r"(?i)\bthis\s+(voice|audio)\s+is\s+synthetic\b", "synthetic-voice verdict (F-D3)"),
    (r"(?i)\b(is|are)\s+ai[-\s]generated\b", "synthetic-origin verdict without provenance (F-D3)"),
    (r"(?i)\bverified\s+safe\b", "'verified safe' is a blocked claim (F-D3)"),
    (r"(?i)\b(100%|completely|totally)\s+safe\b", "absolute safety claim (extension_policy blocked_claims)"),
    (r"(?i)\bguaranteed\s+protection\b", "guaranteed protection (extension_policy)"),
    (r"(?i)\bzero\s+data\s+collection\b", "zero data collection (extension_policy)"),
    (r"(?i)\bgovernment[-\s]affiliated\b", "government affiliation (extension_policy)"),
    (r"(?i)\bsebi[-\s](approved|registered|certified)\b",
     "'SEBI-approved/registered' as a claim about this tool (F-D3)"),
    (r"(?i)\bwe\s+(guarantee|ensure)\s+(your\s+)?(safety|security)\b", "guarantee of safety"),
    (r"(?i)\bcannot\s+be\s+(scammed|phished)\b", "absolute protection claim"),
]


# A blocked phrase is only a violation when the product asserts it OF ITSELF.
# Two contexts are legitimate and must not fail the build:
#   1. Negation/disclaimer - "makes no claim to be SEBI-approved"
#   2. Third-party description - "every SEBI-registered broker must display..."
# Without these, honest copy that explicitly disclaims a banned claim would fail,
# authors would switch the gate off, and it would protect nothing.
NEGATION = re.compile(
    r"(?i)\b(no|not|never|without|non|cannot|can't|don'?t|denies|disclaim\w*|"
    r"avoid\w*|forbidden|blocked|prohibit\w*|refus\w*|makes no)\b")
THIRD_PARTY = re.compile(
    r"(?i)\b(broker\w*|advis[eo]r\w*|analyst\w*|intermediar\w*|entity|entities|firm\w*|"
    r"distributor\w*|registrant\w*|licenc\w*|licens\w*|their|its holder)\b")


def _is_exempt(line: str, match_start: int) -> tuple[bool, str]:
    """Return (exempt, why). Looks at the clause around the match, not the whole file.

    Known limitation: THIRD_PARTY is line-scoped, so a line that both claims a
    credential for this tool AND mentions a broker would be exempted
    ("Our tool is SEBI-registered, unlike any broker"). Every exemption is
    PRINTED on each run so a reviewer can see what was waived rather than having
    it silently disappear. Tighten by splitting on clause boundaries if this
    ever waives something real.
    """
    before = line[:match_start]
    # Negation anywhere earlier in the same sentence/clause.
    if NEGATION.search(before[-120:]):
        return True, "negated/disclaimed"
    # Describing who must hold a registration, rather than claiming one.
    if THIRD_PARTY.search(line):
        return True, "describes a third party, not this tool"
    return False, ""


def iter_files():
    seen = set()
    for pattern in SCAN_GLOBS:
        for p in ROOT.glob(pattern):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if any(x in rel for x in EXCLUDE_PARTS) or rel in seen:
                continue
            seen.add(rel)
            yield p, rel


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print the rule set and exit")
    args = ap.parse_args()

    if args.list:
        print(f"{len(BLOCKED)} blocked-claim rules:")
        for rx, why in BLOCKED:
            print(f"  {why}\n    {rx}")
        return 0

    violations = []
    exempted = []
    scanned = 0
    for path, rel in iter_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("//", "#", "*")):
                continue  # comments are not user-facing copy
            for rx, why in BLOCKED:
                m = re.search(rx, line)
                if not m:
                    continue
                exempt, reason = _is_exempt(line, m.start())
                if exempt:
                    exempted.append((rel, i, m.group(0).strip(), reason))
                    continue
                violations.append((rel, i, m.group(0).strip(), why))

    print(f"Scanned {scanned} user-facing files against {len(BLOCKED)} rules.")
    if exempted:
        print(f"  {len(exempted)} contextual exemption(s) (disclaimers / third-party descriptions):")
        for rel, ln, hit, reason in exempted:
            print(f"    {rel}:{ln}  {hit!r} — {reason}")
    if violations:
        print(f"\nBLOCKED_CLAIMS_FAIL — {len(violations)} violation(s):\n")
        for rel, ln, hit, why in violations:
            print(f"  {rel}:{ln}")
            print(f"    matched : {hit!r}")
            print(f"    reason  : {why}\n")
        return 1
    print("BLOCKED_CLAIMS_PASS — no blocked claim in user-facing copy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
