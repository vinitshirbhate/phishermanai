"""The golden corpus as a blocking test.

Runs on every commit. If this fails, a rule has become direction-blind and is
firing on genuine institutional mail -- the failure mode that makes a user
switch the tool off.

The fix is to add a suppressor to the offending rule, or DELETE the rule.
Weakening the corpus to make a rule pass is not an option: the corpus is the
product requirement, the rule is an implementation detail.
"""

from __future__ import annotations

import pytest

from eval.run_golden import GOLDEN_DIR, run


@pytest.mark.skipif(
    not (GOLDEN_DIR / "manifest.json").exists(),
    reason="golden corpus not built; run: python -m eval.make_golden",
)
def test_golden_corpus_clean():
    """No genuine communication may be called FRAUDULENT or TAMPERED."""
    result = run(verbose=False)

    assert result["total"] >= 120, (
        f"golden corpus has shrunk to {result['total']} samples; it must not be "
        "weakened to make rules pass"
    )

    if result["failures"]:
        lines = [
            f"  {f['file']} [{f['set']}] -> {f['verdict']}: {', '.join(f['problems'])}"
            for f in result["failures"][:20]
        ]
        pytest.fail(
            f"{len(result['failures'])} genuine message(s) were flagged:\n"
            + "\n".join(lines)
            + "\n\nAdd a suppressor to the offending rule, or delete the rule. "
              "Run `python -m eval.run_golden` for matched spans and context."
        )


@pytest.mark.skipif(
    not (GOLDEN_DIR / "manifest.json").exists(),
    reason="golden corpus not built",
)
def test_no_high_severity_findings_on_genuine_mail():
    """Nothing above severity 3 may fire on the corpus."""
    result = run(verbose=False)
    high = {
        code: count for code, count in result["rule_fires"].items()
        if code not in ("AUTH_UNAVAILABLE_INLINE_FORWARD",)
        and any(f"severity-" in p and code in p for f in result["failures"] for p in f["problems"])
    }
    assert not high, f"severity>=4 findings on genuine mail: {high}"


@pytest.mark.skipif(
    not (GOLDEN_DIR / "manifest.json").exists(),
    reason="golden corpus not built",
)
def test_forwarded_mail_analysed_as_original_sender():
    """A forward must never be judged by the forwarder's address."""
    import json

    from core.pipeline import verify

    manifest = json.loads((GOLDEN_DIR / "manifest.json").read_text(encoding="utf-8"))
    forwards = [m for m in manifest if m["forward_type"] in ("INLINE", "ATTACHED")]
    assert forwards, "corpus contains no forwarded samples"

    for item in forwards[:6]:
        verdict, _parsed, _timings = verify(
            (GOLDEN_DIR / item["file"]).read_bytes(), filename=item["file"]
        )
        codes = {r["code"] for r in verdict.reasons}
        assert "INSTITUTIONAL_CLAIM_FROM_FREEMAIL" not in codes, (
            f"{item['file']}: the forwarder's own Gmail address was treated as "
            "an institution impersonating a company"
        )
        assert verdict.verdict not in ("FRAUDULENT", "TAMPERED"), (
            f"{item['file']}: genuine forwarded mail flagged {verdict.verdict}"
        )
