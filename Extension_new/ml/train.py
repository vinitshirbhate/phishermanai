#!/usr/bin/env python3
"""
ml/train.py - trains LR-lex (Layer 1.5a, in-extension) on the PhiUSIIL corpus.

Design note (requirement.md F-A2 / remediation §1.2): the DOM features cannot be
recovered from a dead phishing URL. Rather than fabricate them, this trains a
URL-only model, deployed as the in-extension lane - a capability gain, not a
compromise: a model that needs no DOM can score a link on hover and a URL inside
a WhatsApp message, surfaces where no DOM exists at all.

TWO DECISIONS THAT DEFINE THIS MODEL, both forced by eval/corpus_audit.py:

  1. ARTEFACT-FREE FEATURES ONLY. It trains on FEATURE_GROUPS["domain"] - 18
     features computed from the registrable domain string after stripping
     "www.", ignoring scheme, path and query entirely. The audit shows all
     three are collection artefacts in PhiUSIIL: 100% of legitimate URLs are
     canonicalised `https://www.<domain>` homepages with no path and no query.
     A model given those columns reaches MCC 0.99 by learning URL formatting,
     and flags every legitimate deep link - including sebi.gov.in's own
     register URL. We do not ship that model.

  2. DOMAIN-GROUPED SPLIT. GroupShuffleSplit on the registrable domain, so no
     domain appears in both train and test. A random split lets many URLs from
     one campaign domain straddle the split and flatters the result.

The result is a lower number than a random split on artefact-bearing features
would give, and it is the number we stand behind.

CRITICAL RULE (NFR-10): features are re-derived here through ml/features.py, the
single source of truth. PhiUSIIL's 54 pre-extracted columns are deliberately NOT
consumed - importing them would create a second feature definition.

Usage:
    python -m ml.train                 # full corpus, domain-grouped split
    python -m ml.train --limit 60000   # faster stratified subsample
    python -m ml.train --refresh-cache # re-fetch PhiUSIIL instead of using cached parquet
    python -m ml.train --n-boot 2000 --test-size 0.25 --cv-folds 5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features import (DOMAIN_FEATURE_NAMES, FEATURE_NAMES,  # noqa: E402
                         FEATURE_SET_VERSION, extract, registrable_domain)

RAW_DIR = ROOT / "datasets" / "raw"
OUT_JSON = ROOT / "extension" / "models" / "lr_v1.json"
MODEL_CARD = ROOT / "ml" / "model_card.md"
MODEL_VERSION = "lr_v1"
CACHE_META = RAW_DIR / "phiusiil.meta.json"


def commit_hash() -> str:
    """Short commit hash, suffixed with '-dirty' if the working tree has
    uncommitted changes. A model trained against a dirty tree that gets
    tagged with the last clean commit hash has silently wrong provenance."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=10)
        h = r.stdout.strip() or "unknown"
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10)
        dirty = bool(status.stdout.strip())
        return f"{h}-dirty" if dirty else h
    except Exception:
        return "unknown"


def load_corpus(limit: int, refresh_cache: bool = False) -> tuple[list[str], np.ndarray, str]:
    """Returns (urls, y_phishing, dataset_sha256). y=1 means PHISHING."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = RAW_DIR / "phiusiil.parquet"

    if refresh_cache and cache.exists():
        print(f"  --refresh-cache: deleting {cache.relative_to(ROOT)}")
        cache.unlink()
        if CACHE_META.exists():
            CACHE_META.unlink()

    if cache.exists():
        import pandas as pd
        df = pd.read_parquet(cache)
        age_str = ""
        if CACHE_META.exists():
            try:
                fetched_at = json.loads(CACHE_META.read_text())["fetched_at"]
                age_days = (datetime.now(timezone.utc)
                            - datetime.fromisoformat(fetched_at)).days
                age_str = f", cached {age_days}d ago (fetched {fetched_at})"
            except Exception:
                age_str = ", cache age unknown (no valid metadata)"
        else:
            age_str = ", cache age unknown (pre-dates metadata tracking)"
        print(f"  loaded cached corpus: {len(df)} rows{age_str}")
        print("  (use --refresh-cache to re-fetch from UCI if this is stale)")
    else:
        from ucimlrepo import fetch_ucirepo
        import pandas as pd
        print("  fetching PhiUSIIL (UCI id 967) ...")
        d = fetch_ucirepo(id=967)
        df = pd.concat([d.data.features[["URL"]], d.data.targets], axis=1)
        df.columns = ["URL", "label"]
        df.to_parquet(cache)
        CACHE_META.write_text(json.dumps(
            {"fetched_at": datetime.now(timezone.utc).isoformat()}))
        print(f"  cached {len(df)} rows -> {cache.relative_to(ROOT)}")

    df = df.dropna(subset=["URL"])
    # PhiUSIIL: label 1 = legitimate. We predict P(phishing), so invert.
    df["y"] = 1 - df["label"].astype(int)

    if limit and len(df) > limit:
        # Stratified subsample for tractable pure-Python feature extraction.
        pos = df[df.y == 1].sample(n=limit // 2, random_state=42)
        neg = df[df.y == 0].sample(n=limit // 2, random_state=42)
        df = pd.concat([pos, neg]).sample(frac=1.0, random_state=42)
        print(f"  stratified subsample: {len(df)} rows ({limit//2} phishing / {limit//2} legit)")

    sha = hashlib.sha256("".join(sorted(df["URL"].astype(str).tolist())).encode()).hexdigest()[:16]
    return df["URL"].astype(str).tolist(), df["y"].to_numpy(), sha


def _extract_row(u: str, names: list[str]) -> list[float]:
    """Top-level (picklable) worker for parallel feature derivation."""
    feats = extract({"url": u, "html": "", "text": ""})
    return [feats[n] for n in names]


def derive(urls: list[str], names: list[str]) -> np.ndarray:
    """Re-derive the requested features from raw URLs via ml/features.py.

    Parallelised across processes: extract() is a pure function of the URL
    string, so this is an embarrassingly parallel row loop and was the
    dominant wall-clock cost on the full corpus in pure-Python form.
    """
    import os
    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_extract_row, urls, [names] * len(urls), chunksize=500))
    print(f"  feature derivation: {time.time()-t0:.1f}s for {len(urls)} rows "
          f"(parallel, {os.cpu_count()} workers)")
    return np.asarray(rows, dtype=float)


def domain_groups(urls: list[str]) -> np.ndarray:
    """Grouping key for the split: the registrable domain of each URL."""
    from urllib.parse import urlparse
    return np.array([registrable_domain(
        urlparse(u if "://" in u else "http://" + u).hostname or "") for u in urls])


def bootstrap_mcc_ci(y_true, y_pred, n_boot=1000, seed=42):
    from sklearn.metrics import matthews_corrcoef
    rng = np.random.default_rng(seed)
    idx_pos = np.flatnonzero(y_true == 1)
    idx_neg = np.flatnonzero(y_true == 0)
    vals = []
    for _ in range(n_boot):
        s = np.concatenate([rng.choice(idx_pos, len(idx_pos), replace=True),
                            rng.choice(idx_neg, len(idx_neg), replace=True)])
        vals.append(matthews_corrcoef(y_true[s], y_pred[s]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def group_cv_mcc(X, y, groups, n_splits=5, seed=42):
    """5-fold (default) GroupKFold MCC, purely for reporting/trust.

    The single held-out split's bootstrap CI only captures sampling variance
    of the test rows GIVEN that split - it says nothing about how much the
    result would move if a different set of domains had landed in test.
    GroupShuffleSplit's domain assignment is itself a random draw, so this
    cross-validated summary is the more honest variance estimate to quote
    alongside (not instead of) the single number that gets shipped.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import matthews_corrcoef
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    scores = []
    for tr_i, te_i in GroupKFold(n_splits=n_splits).split(X, y, groups=groups):
        s = StandardScaler().fit(X[tr_i])
        m = LogisticRegression(max_iter=2000, class_weight="balanced",
                               random_state=42).fit(s.transform(X[tr_i]), y[tr_i])
        scores.append(matthews_corrcoef(y[te_i], m.predict(s.transform(X[te_i]))))
    return scores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0,
                    help="stratified sample size (0 = full corpus, the default)")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="delete and re-fetch the cached PhiUSIIL parquet before training")
    ap.add_argument("--n-boot", type=int, default=1000,
                    help="bootstrap resamples for the MCC confidence interval")
    ap.add_argument("--test-size", type=float, default=0.3,
                    help="fraction of domains held out for the test split")
    ap.add_argument("--cv-folds", type=int, default=5,
                    help="GroupKFold folds for the cross-validated MCC robustness check")
    args = ap.parse_args()

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import (matthews_corrcoef, average_precision_score,
                                 brier_score_loss, confusion_matrix, roc_curve)

    print("Loading corpus ...")
    urls, y, dataset_sha = load_corpus(args.limit, refresh_cache=args.refresh_cache)

    # --- Feature selection is a DECISION, not a variance filter -------------- #
    # We do not "keep whatever has variance". Scheme, www-prefix, path and query
    # all have plenty of variance in this corpus - they are exactly the columns
    # eval/corpus_audit.py identifies as collection artefacts. The shipped model
    # trains on the artefact-free domain-string group and nothing else.
    kept = list(DOMAIN_FEATURE_NAMES)
    excluded = [n for n in FEATURE_NAMES if n not in kept]
    print(f"Deriving {len(kept)} artefact-free domain features via ml/features.py ...")
    X = derive(urls, kept)
    print(f"  using   : {kept}")
    print(f"  excluded: {len(excluded)} features (DOM/page-text unavailable in a URL-only "
          f"corpus, plus every scheme/path/query column — see eval/corpus_audit.py)")

    # --- Non-finite guard --------------------------------------------------- #
    # A silent inf/nan from a degenerate URL (e.g. a zero-length-denominator
    # ratio feature) would otherwise flow straight into StandardScaler/
    # LogisticRegression and either corrupt the fit silently or blow up deep
    # inside sklearn with an unhelpful traceback. Fail loudly here instead,
    # naming exactly which features and how many rows are affected.
    bad = ~np.isfinite(X)
    if bad.any():
        bad_rows, bad_cols = np.where(bad)
        offenders = sorted(set(kept[c] for c in bad_cols))
        example_urls = sorted({urls[r] for r in bad_rows[:5]})
        raise ValueError(
            f"{bad.sum()} non-finite value(s) across {len(offenders)} feature(s) "
            f"{offenders} in {len(set(bad_rows))} row(s). Example URLs: {example_urls}. "
            f"Fix ml/features.py — do not silently scale/clip these away."
        )

    zero_var = [kept[i] for i, v in enumerate(X.var(axis=0)) if v <= 1e-9]
    if zero_var:
        print(f"  NOTE: {len(zero_var)} domain features are zero-variance here: {zero_var}")
        if len(zero_var) >= len(kept) // 2:
            print(f"  WARNING: over half the feature set is zero-variance — this usually "
                  f"means feature extraction is broken (e.g. corpus schema changed), not "
                  f"that the corpus genuinely lacks signal. Investigate before trusting "
                  f"the metrics below.")

    # --- Domain-grouped split ------------------------------------------------ #
    groups = domain_groups(urls)
    gss = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=42)
    tr_idx, te_idx = next(gss.split(X, y, groups=groups))
    Xtr, Xte, ytr, yte = X[tr_idx], X[te_idx], y[tr_idx], y[te_idx]
    n_domains = int(len(set(groups)))
    leaked = set(groups[tr_idx]) & set(groups[te_idx])
    print(f"  domain-grouped split: {n_domains:,} distinct registrable domains, "
          f"{len(set(groups[tr_idx])):,} train / {len(set(groups[te_idx])):,} test, "
          f"overlap {len(leaked)}")
    if leaked:
        print(f"  FATAL: {len(leaked)} domain(s) leaked across the grouped split: "
              f"{sorted(leaked)[:10]}{' ...' if len(leaked) > 10 else ''}")
        return 1

    # Class balance per side — a skewed grouped split (e.g. most phishing
    # domains landing in train) would explain a metric swing and would
    # otherwise be invisible in the output.
    print(f"  class balance: train {ytr.mean():.3f} phishing "
          f"({int(ytr.sum())}/{len(ytr)}), test {yte.mean():.3f} phishing "
          f"({int(yte.sum())}/{len(yte)})")

    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
    clf.fit(scaler.transform(Xtr), ytr)

    proba = clf.predict_proba(scaler.transform(Xte))[:, 1]
    pred = (proba >= 0.5).astype(int)

    mcc = matthews_corrcoef(yte, pred)
    lo, hi = bootstrap_mcc_ci(yte, pred, n_boot=args.n_boot)
    pr_auc = average_precision_score(yte, proba)
    brier = brier_score_loss(yte, proba)
    tn, fp, fn, tp = confusion_matrix(yte, pred).ravel()

    fpr, tpr, thr = roc_curve(yte, proba)
    ok = np.flatnonzero(fpr <= 0.01)
    recall_at_fpr1 = float(tpr[ok[-1]]) if len(ok) else 0.0
    thr_at_fpr1 = float(thr[ok[-1]]) if len(ok) else 0.5

    print(f"\n  MCC              : {mcc:.4f}  (95% CI {lo:.4f}–{hi:.4f})   "
          f"target >= 0.55 -> {'MET' if mcc >= 0.55 else 'NOT MET'}")
    print(f"  PR-AUC           : {pr_auc:.4f}")
    print(f"  Recall @ FPR<=1% : {recall_at_fpr1:.4f}  (threshold {thr_at_fpr1:.4f})")
    print(f"  Brier            : {brier:.4f}")
    print(f"  Confusion        : TN={tn} FP={fp} FN={fn} TP={tp}")
    print(f"  n_test           : {len(yte):,}")

    # --- Cross-validated robustness check (reporting only; does not affect
    # what gets shipped) ------------------------------------------------------ #
    print(f"\n  Running {args.cv_folds}-fold GroupKFold MCC for a split-to-split "
          f"variance estimate ...")
    cv_scores = group_cv_mcc(X, y, groups, n_splits=args.cv_folds)
    cv_mean, cv_std = float(np.mean(cv_scores)), float(np.std(cv_scores))
    print(f"  {args.cv_folds}-fold group-CV MCC: {cv_mean:.4f} ± {cv_std:.4f}  "
          f"folds={[round(s, 4) for s in cv_scores]}")

    # --- Parity anchor (gate G-1) ------------------------------------------ #
    # Pin sklearn's OWN predict_proba on a fixed sample INTO the exported model.
    # Without this the parity test compares two readers of the same JSON, so a
    # corrupted scaler corrupts both sides identically and the gate passes while
    # the shipped model is wrong. Anchoring to the trained estimator's output is
    # what actually catches an export/scaler mismatch.
    #
    # Sampled (not sliced) from Xte: rows in Xte keep their original corpus
    # order after a GroupShuffleSplit, and adjacent rows are frequently the
    # same domain's subpages/campaign variants. Xte[:200] risked anchoring
    # parity on a handful of repeated domains instead of covering the space.
    anchor_rng = np.random.default_rng(42)
    anchor_idx = anchor_rng.choice(len(Xte), size=min(200, len(Xte)), replace=False)
    anchor_X = Xte[anchor_idx]
    anchor_p = clf.predict_proba(scaler.transform(anchor_X))[:, 1]
    parity_reference = {
        "note": "sklearn predict_proba at training time. eval/parity_test.py asserts the "
                "JS scorer reproduces these. Regenerate only by retraining.",
        "feature_names": kept,
        "rows": [[float(v) for v in row] for row in anchor_X],
        "p_phishing": [float(p) for p in anchor_p],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "parity_reference": parity_reference,
        "model_version": MODEL_VERSION,
        "feature_set_version": FEATURE_SET_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit_hash(),
        "dataset": "PhiUSIIL (UCI id 967), URL column only, features re-derived by ml/features.py",
        "dataset_sha256_16": dataset_sha,
        "n_train": int(len(ytr)), "n_test": int(len(yte)),
        "n_domains": n_domains,
        "feature_names": kept,
        "feature_group": "domain (artefact-free, registrable-domain string only)",
        "means": scaler.mean_.tolist(),
        "scales": scaler.scale_.tolist(),
        "coefficients": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
        "threshold_fpr1": thr_at_fpr1,
        "target_mcc": 0.55,
        "metrics": {"mcc": float(mcc), "mcc_ci95": [lo, hi], "pr_auc": float(pr_auc),
                    "recall_at_fpr1": recall_at_fpr1, "brier": float(brier),
                    "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
                    "group_cv": {"n_splits": args.cv_folds, "mean": cv_mean, "std": cv_std,
                                 "folds": [float(s) for s in cv_scores]}},
        "split": f"GroupShuffleSplit {int((1-args.test_size)*100)}/{int(args.test_size*100)} "
                 f"grouped by REGISTRABLE DOMAIN — no domain appears "
                 f"in both train and test ({n_domains:,} distinct domains). PhiUSIIL carries "
                 f"no timestamps, so a temporal split remains impossible; the domain grouping "
                 f"removes the campaign-template leakage a random split allows.",
        "coefficients_by_feature": dict(sorted(
            ((n, float(c)) for n, c in zip(kept, clf.coef_[0])),
            key=lambda kv: -abs(kv[1]))),
        "known_limitations": [
            "Artefact-free by construction: scheme, www-prefix, path and query are EXCLUDED "
            "because eval/corpus_audit.py shows all four are collection artefacts in PhiUSIIL "
            "(100% of legitimate URLs are canonicalised https://www. homepages with no path). "
            "A model given those columns scores MCC 0.99 and flags every legitimate deep link, "
            "including sebi.gov.in's own register URL. This model is deliberately weaker and "
            "deliberately honest.",
            "URL-only: DOM and page-text features cannot be recovered from a dead phishing URL.",
            "No temporal split available (no timestamps in PhiUSIIL); the domain-grouped split "
            "controls campaign leakage but not concept drift over time.",
            "Not evaluated on Indian securities-scam URLs specifically — PhiUSIIL is general "
            "phishing. Treat the securities framing as untested for this lane.",
            "This is a PRE-FILTER, never the verdict. The authentication path (registration "
            "resolution against the SEBI register) is deterministic, offline and independent "
            "of this model.",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\n  wrote {OUT_JSON.relative_to(ROOT)}")

    MODEL_CARD.write_text(f"""# Model Card - {MODEL_VERSION} (LR-lex)

| Field | Value |
|---|---|
| model_version | `{MODEL_VERSION}` |
| feature_set_version | `{FEATURE_SET_VERSION}` |
| trained_at | {payload['trained_at']} |
| commit | `{payload['commit']}` |
| dataset | PhiUSIIL (UCI id 967), URL column only |
| dataset_sha256 (16) | `{dataset_sha}` |
| n_train / n_test | {len(ytr):,} / {len(yte):,} |
| distinct registrable domains | {n_domains:,} |
| features used | {len(kept)} (the artefact-free `domain` group) of {len(FEATURE_NAMES)} defined |
| split | domain-grouped (`GroupShuffleSplit`, test_size={args.test_size}), no domain in both sides |
| decision threshold (FPR<=1%) | {thr_at_fpr1:.4f} |

## Metrics (held-out {int(args.test_size*100)}%, domain-grouped)

| Metric | Value | Target (requirement.md §7.1) | Met? |
|---|---|---|---|
| MCC | {mcc:.4f} (95% CI {lo:.4f}-{hi:.4f}) | >= 0.55 | {'YES' if mcc >= 0.55 else 'NO'} |
| PR-AUC | {pr_auc:.4f} | - | - |
| Recall @ FPR<=1% | {recall_at_fpr1:.4f} | - | - |
| Brier | {brier:.4f} | <= 0.12 | {'YES' if brier <= 0.12 else 'NO'} |
| Confusion | TN={tn} FP={fp} FN={fn} TP={tp} | - | - |

## Split-to-split robustness ({args.cv_folds}-fold GroupKFold, reporting only)

The single held-out number above comes with a bootstrap CI that only reflects
sampling variance of the test *rows* given the domains that happened to land in
test. Since `GroupShuffleSplit`'s domain assignment is itself a random draw,
this {args.cv_folds}-fold group-CV summary gives a more honest picture of how much
MCC would move under a different domain split. It does not change what ships —
the model above is trained on the single split, per the split rationale below.

| Fold MCC | Mean | Std |
|---|---|---|
| {', '.join(f'{s:.4f}' for s in cv_scores)} | {cv_mean:.4f} | {cv_std:.4f} |

The MCC target was revised from 0.85 to 0.55 on the evidence of
`eval/corpus_audit.py`. The rationale is in `eval/REPORT.md` §B.2: 0.85 was set
before anyone audited the corpus, and it is not reachable honestly on PhiUSIIL's
URL column. It IS reachable dishonestly - 34 artefact-bearing features score MCC
0.99 - which is precisely why the target moved rather than the feature set.

## Features used (artefact-free `domain` group)
{chr(10).join('- `' + f + '`  (coef {:+.3f})'.format(payload['coefficients_by_feature'][f]) for f in kept)}

## Features deliberately EXCLUDED
Not a variance filter - a decision. Scheme, `www.` prefix, path length, query
length, slash count and path depth all carry ample variance in this corpus; they
are excluded because they encode the collection artefact rather than fraud.
DOM and page-text features are additionally unavailable from a bare URL.

{chr(10).join('- `' + f + '`' for f in excluded)}

## Known limitations
{chr(10).join('- ' + l for l in payload['known_limitations'])}

## Rollback
The deterministic path (registration check + 18-rule offline gate) is independent
of this model and is immune to model drift. Deleting
`extension/models/lr_v1.json` disables Layer 1.5a; the chain still returns a
verdict from the remaining layers (F-D2).
""", encoding="utf-8")
    print(f"  wrote {MODEL_CARD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())