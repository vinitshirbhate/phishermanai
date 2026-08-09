"""
NFR-10 enforcement: `ml/features.py` is the SINGLE definition of the feature set.

The service worker necessarily re-implements extraction in JS (it cannot import
Python), so a second implementation exists in `background.js::mlFeaturesFromUrl`.
That is the exact condition NFR-10 warns about. This test pins the two together:
any divergence on a feature the shipped model actually uses fails the build.

This caught a real defect on first run (`upi_outside_valid_namespace` hardcoded
to 0 in JS while Python returned 1), which would have fed the model a wrong
input on every scored URL without any other test noticing.

Standalone:  python tests/test_feature_parity.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features import extract  # noqa: E402

MODEL = ROOT / "extension" / "models" / "lr_v1.json"
BACKGROUND = ROOT / "extension" / "background.js"

URLS = [
    "https://www.example.com/",
    "http://192.168.1.1/login.php?otp=1",
    "https://xn--80ak6aa92e.com/verify",
    "https://a.b.c.d.example.co.in/kyc?upi=1&otp=2&x=3",
    "https://secure-login-update.paytm-verify.top/otp",
    "http://bank-account-confirm.xyz/wallet?cvv=9",
    "https://pay.to/someone@okhdfcbank",
    "https://pay.to/broker.brk@validhdfc",
    "https://aadhaar-pan-update.in/secure/confirm",
    "https://plain.example.org",
]


def _js_features(urls: list[str]) -> list[dict]:
    src = BACKGROUND.read_text(encoding="utf-8")
    m = re.search(r"function mlFeaturesFromUrl\(rawUrl\) \{.*?\n\}", src, re.S)
    assert m, "mlFeaturesFromUrl not found in background.js"
    script = m.group(0) + "\nconsole.log(JSON.stringify(" + json.dumps(urls) + \
        ".map(u => mlFeaturesFromUrl(u))));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, f"node failed: {out.stderr[:300]}"
    return json.loads(out.stdout)


def test_js_and_python_features_agree_on_model_inputs():
    if not MODEL.exists():
        print("SKIP — no model yet")
        return
    used = json.loads(MODEL.read_text(encoding="utf-8"))["feature_names"]
    js_rows = _js_features(URLS)
    drift = []
    for url, jf in zip(URLS, js_rows):
        pf = extract({"url": url, "html": "", "text": ""})
        for name in used:
            a, b = float(pf[name]), float(jf.get(name, 0.0))
            if abs(a - b) > 1e-6:
                drift.append(f"{name}: py={a} js={b} on {url}")
    assert not drift, "feature drift between ml/features.py and background.js:\n  " + \
        "\n  ".join(drift)


def test_js_emits_every_feature_the_model_consumes():
    if not MODEL.exists():
        return
    used = json.loads(MODEL.read_text(encoding="utf-8"))["feature_names"]
    js = _js_features(["https://example.com/x"])[0]
    missing = [n for n in used if n not in js]
    assert not missing, f"background.js does not emit model features: {missing}"


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}"); passed += 1
        except Exception as exc:
            print(f"FAIL  {name}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
