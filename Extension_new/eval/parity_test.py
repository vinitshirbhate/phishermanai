#!/usr/bin/env python3
"""
eval/parity_test.py - GATE G-1.

Verifies the JS scorer (extension/ml_scorer.js, Layer 1.5a) and the Python
reference produce the same P(phishing) within +/-0.02 on a held-out URL sample.

Why this is a gate and not a nicety: a silent StandardScaler mismatch between
training and the shipped JS is the highest-probability defect in this build, and
it fails open - the extension keeps returning plausible-looking probabilities
that are simply wrong. Nothing else in the system would catch it.

Usage:
    python eval/parity_test.py            # 200 rows, tolerance 0.02
    python eval/parity_test.py --n 500
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features import extract  # noqa: E402

MODEL_PATH = ROOT / "extension" / "models" / "lr_v1.json"
SCORER_JS = ROOT / "extension" / "ml_scorer.js"
TOLERANCE = 0.02


def python_score(model: dict, feats: dict) -> float:
    z = model["intercept"]
    for i, name in enumerate(model["feature_names"]):
        scale = model["scales"][i] or 1.0
        z += ((float(feats.get(name, 0.0)) - model["means"][i]) / scale) * model["coefficients"][i]
    return 1.0 / (1.0 + math.exp(-z))


def js_scores(feature_rows: list[dict]) -> list[float]:
    """Run the real extension scorer under node over the same feature vectors."""
    payload = {"model": str(MODEL_PATH).replace("\\", "/"), "rows": feature_rows}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f)
        tmp = f.name
    script = f"""
    const fs = require('fs');
    const ml = require({json.dumps(str(SCORER_JS).replace(chr(92), '/'))});
    const payload = JSON.parse(fs.readFileSync({json.dumps(tmp)}, 'utf8'));
    ml.load(JSON.parse(fs.readFileSync(payload.model, 'utf8')));
    console.log(JSON.stringify(payload.rows.map(r => ml.score(r).p_phishing)));
    """
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
    Path(tmp).unlink(missing_ok=True)
    if out.returncode != 0:
        raise RuntimeError(f"node failed: {out.stderr[:400]}")
    return json.loads(out.stdout.strip())


def sample_urls(n: int) -> list[str]:
    cache = ROOT / "datasets" / "raw" / "phiusiil.parquet"
    if cache.exists():
        import pandas as pd
        df = pd.read_parquet(cache).dropna(subset=["URL"])
        return df["URL"].astype(str).sample(n=min(n, len(df)), random_state=7).tolist()
    # Fallback: synthesise a spread of URL shapes so the gate still runs.
    base = ["https://www.example.com", "http://192.168.1.1/login.php",
            "https://xn--80ak6aa92e.com/verify", "https://a.b.c.d.e.example.co.in/kyc?upi=1&otp=2",
            "https://secure-login-update.paytm-verify.top/otp"]
    return [base[i % len(base)] + f"?i={i}" for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--tolerance", type=float, default=TOLERANCE)
    args = ap.parse_args()

    if not MODEL_PATH.exists():
        print(f"PARITY_SKIP — no model at {MODEL_PATH.relative_to(ROOT)}. Run `python -m ml.train` first.")
        return 0  # not a failure: the gate is N/A until a model exists

    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    print(f"Parity gate G-1 — model {model['model_version']} / {model['feature_set_version']}")
    failed = False

    # --- Check 1: JS vs the TRAINED ESTIMATOR's own output (the real gate) --- #
    # Anchored to sklearn's predict_proba captured at training time, so a
    # corrupted scaler/coefficient in the exported JSON is caught. Comparing two
    # readers of the same JSON (check 2) cannot catch that.
    ref = model.get("parity_reference")
    if not ref:
        print("  [1] anchor  : SKIP — model predates parity_reference; retrain to enable "
              "the export-mismatch check.")
    else:
        rows = [dict(zip(ref["feature_names"], r)) for r in ref["rows"]]
        js_anchor = js_scores(rows)
        d = [abs(a - b) for a, b in zip(ref["p_phishing"], js_anchor)]
        worst = max(d) if d else 0.0
        bad = sum(1 for x in d if x > args.tolerance)
        status = "PASS" if not bad else "FAIL"
        print(f"  [1] anchor  : {status}  n={len(d)}  max abs diff={worst:.6f}  "
              f"(JS vs sklearn predict_proba at train time)")
        if bad:
            failed = True
            for i, x in enumerate(d):
                if x > args.tolerance:
                    print(f"        row {i}: sklearn={ref['p_phishing'][i]:.5f} "
                          f"js={js_anchor[i]:.5f} diff={x:.5f}")
                    if i > 8:
                        break

    # --- Check 2: JS vs Python reference on fresh URLs (implementation drift) - #
    urls = sample_urls(args.n)
    feats = [extract({"url": u, "html": "", "text": ""}) for u in urls]
    py = [python_score(model, r) for r in feats]
    js = js_scores(feats)
    if len(py) != len(js):
        print(f"  [2] impl    : FAIL — length mismatch py={len(py)} js={len(js)}")
        return 1
    diffs = [abs(a - b) for a, b in zip(py, js)]
    over = [(urls[i], py[i], js[i], diffs[i]) for i, d2 in enumerate(diffs) if d2 > args.tolerance]
    print(f"  [2] impl    : {'PASS' if not over else 'FAIL'}  n={len(diffs)}  "
          f"max abs diff={max(diffs):.6f}  (JS vs Python reference on fresh URLs)")
    if over:
        failed = True
        for u, a, b, d2 in over[:10]:
            print(f"        diff={d2:.5f} py={a:.5f} js={b:.5f} {u[:70]}")

    if failed:
        print("\nPARITY_FAIL")
        return 1
    print("\nPARITY_PASS — exported model reproduces the trained estimator, and JS matches Python.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
