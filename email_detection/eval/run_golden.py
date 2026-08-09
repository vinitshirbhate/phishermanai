"""Golden-corpus regression harness.

    python -m eval.run_golden

Asserts that genuine Indian financial communications are NEVER flagged:

    * ZERO messages come back FRAUDULENT or TAMPERED
    * ZERO findings of severity >= 4 fire

Prints every rule that fired with its matched span and surrounding context, so
a misfire is diagnosable at a glance rather than requiring a bisect.

EXITS NON-ZERO ON ANY FAILURE. Wired into pytest as
tests/test_golden.py::test_golden_corpus_clean, so it runs on every commit.

A rule that fails here and cannot be fixed by adding a suppressor must be
DELETED. Do not weaken the corpus to save a rule -- the corpus is the product
requirement, the rule is an implementation detail.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

FORBIDDEN_VERDICTS = {"FRAUDULENT", "TAMPERED"}
MAX_ALLOWED_SEVERITY = 3       # anything >= 4 is a failure on genuine mail

CONTEXT_CHARS = 80


def _context(text: str, span: list[int] | None) -> str:
    if not span or len(span) != 2:
        return ""
    lo = max(0, span[0] - CONTEXT_CHARS)
    hi = min(len(text), span[1] + CONTEXT_CHARS)
    snippet = text[lo:hi].replace("\n", " ").replace("\r", " ")
    return " ".join(snippet.split())


def run(verbose: bool = True) -> dict[str, Any]:
    from core.pipeline import verify

    manifest_path = GOLDEN_DIR / "manifest.json"
    if not manifest_path.exists():
        print("No golden corpus. Run: python -m eval.make_golden", file=sys.stderr)
        return {"ok": False, "error": "no_corpus", "total": 0}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # The adversarial sets: genuine mail whose subject matter IS fraud. Held in
    # a separate manifest so they can be reported on their own -- they are the
    # inputs most likely to break a rule engine, so their FP rate is the number
    # that matters most.
    adversarial_path = GOLDEN_DIR / "adversarial" / "manifest.json"
    if adversarial_path.exists():
        manifest += json.loads(adversarial_path.read_text(encoding="utf-8"))

    failures: list[dict[str, Any]] = []
    rule_fires: Counter[str] = Counter()
    fire_examples: dict[str, dict[str, Any]] = {}
    by_set: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()

    for item in manifest:
        path = GOLDEN_DIR / item["file"]
        if not path.exists():
            continue
        by_set[item["set"]] += 1

        verdict, parsed, _timings = verify(path.read_bytes(), filename=item["file"])
        verdicts[verdict.verdict] += 1

        problems = []
        if verdict.verdict in FORBIDDEN_VERDICTS:
            problems.append(f"verdict={verdict.verdict}")

        for reason in verdict.reasons:
            severity = reason.get("severity", 0)
            if severity >= 1:
                rule_fires[reason["code"]] += 1
                fire_examples.setdefault(reason["code"], {
                    "file": item["file"],
                    "severity": severity,
                    "matched": (reason.get("evidence") or {}).get("matched_text", ""),
                    "context": _context(parsed.raw_text, (reason.get("evidence") or {}).get("span")),
                    "message": reason.get("message", "")[:110],
                })
            if severity > MAX_ALLOWED_SEVERITY:
                problems.append(f"severity-{severity} {reason['code']}")

        if problems:
            failures.append({
                "file": item["file"], "set": item["set"],
                "verdict": verdict.verdict, "problems": problems,
            })

    ok = not failures

    if verbose:
        print()
        print("=" * 78)
        print("  GOLDEN CORPUS -- genuine mail that must never be flagged")
        print("=" * 78)
        print(f"\n  samples: {sum(by_set.values())}")
        for name, count in sorted(by_set.items()):
            print(f"    {name:<22}{count:>4}")

        print("\n  verdicts:")
        for name, count in verdicts.most_common():
            marker = "  <-- FAILURE" if name in FORBIDDEN_VERDICTS else ""
            print(f"    {name:<22}{count:>4}{marker}")

        if rule_fires:
            print("\n  rules that fired (every one is a candidate for suppression):")
            for code, count in rule_fires.most_common():
                example = fire_examples[code]
                flag = " !! FAILURE" if example["severity"] > MAX_ALLOWED_SEVERITY else ""
                print(f"    [{example['severity']}] {code:<44}{count:>4}x{flag}")
                if example["matched"]:
                    print(f"          matched: {example['matched'][:70]!r}")
                if example["context"]:
                    print(f"          context: ...{example['context'][:150]}...")
        else:
            print("\n  no rules fired at all -- corpus is completely clean")

        if failures:
            print(f"\n  FAILURES: {len(failures)}")
            for failure in failures[:25]:
                print(f"    {failure['file']:<34}{failure['verdict']:<12}{failure['problems']}")
        print()
        print("=" * 78)
        print(f"  RESULT: {'PASS' if ok else 'FAIL'} "
              f"({len(failures)} failure(s) across {sum(by_set.values())} samples)")
        print("=" * 78)
        print()

    return {
        "ok": ok,
        "total": sum(by_set.values()),
        "failures": failures,
        "rule_fires": dict(rule_fires),
        "verdicts": dict(verdicts),
        "by_set": dict(by_set),
    }


if __name__ == "__main__":  # pragma: no cover
    result = run()
    sys.exit(0 if result["ok"] else 1)
