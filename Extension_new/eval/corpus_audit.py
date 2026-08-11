#!/usr/bin/env python3
"""
eval/corpus_audit.py - audit PhiUSIIL BEFORE trusting any number derived from it.

This script exists because the URL model missed its MCC target, and the first
thing we did was open the corpus rather than tune the model. What it found is
that the target was unreachable honestly, and that a model which *does* reach it
on this corpus has learned URL formatting rather than fraud.

What it measures, on datasets/raw/phiusiil.parquet (UCI id 967, label 1 = legit):

  1. Three collection artefacts in the legitimate class - scheme, "www."
     prefix, and the total absence of paths and query strings.
  2. Single-feature MCC for two of those artefacts on their own.
  3. Experiment A - the shipped lexical features, LR, random split.
  4. Experiment B - 34 artefact-bearing lexical features, SAME LR, same split.
     This is the demonstration that the corpus is unusable as-is. IT IS NOT A
     MODEL WE SHIP, and its score is quoted nowhere outside section B.0.
  5. What Experiment B's model does to real, legitimate deep links - including
     sebi.gov.in's own intermediary register URL, which carries a path AND a
     query string and is therefore shaped exactly like PhiUSIIL's phishing class.

The 34 features in Experiment B are defined INLINE here, deliberately. They must
never enter ml/features.py: that module is the single definition of the SHIPPED
feature set (NFR-10 / C5), and these columns exist only to prove a negative.

Output: prints a report, and writes eval/corpus_audit.json containing both the
raw figures and a pre-rendered markdown block that eval/run_eval.py embeds
verbatim into REPORT.md §B.0. No figure in the report is hand-entered.

Usage:
    python eval/corpus_audit.py
    python eval/corpus_audit.py --limit 60000     # faster, for iteration
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features import FEATURE_GROUPS, extract  # noqa: E402

CORPUS = ROOT / "datasets" / "raw" / "phiusiil.parquet"
OUT_JSON = ROOT / "eval" / "corpus_audit.json"

# Legitimate deep links used to show what an artefact-driven model does in
# production. Every one of these is a real, legitimate URL with a path and/or a
# query string - the exact shape PhiUSIIL's legitimate class never contains.
LEGITIMATE_DEEP_LINKS = [
    "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=14",
    "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes",
    "https://zerodha.com/products/kite",
    "https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY%2050",
    "https://www.bseindia.com/corporates/List_Scrips.html?expandable=1",
    "https://investor.sebi.gov.in/sebicheck",
    "https://www.rbi.org.in/Scripts/BS_ViewMasCirculardetails.aspx?id=12345",
    "https://en.wikipedia.org/wiki/Securities_and_Exchange_Board_of_India",
]


def shannon(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


# --------------------------------------------------------------------------- #
# Experiment B's feature set - ARTEFACT-BEARING BY DESIGN. Never shipped.
# --------------------------------------------------------------------------- #
ARTEFACT_FEATURE_NAMES = [
    "url_len", "host_len", "path_len", "query_len", "n_dots", "n_slashes",
    "n_hyphens", "n_digits", "digit_ratio", "n_params", "n_amp", "is_https",
    "has_www", "has_port", "n_subdomains", "tld_len", "url_entropy",
    "host_entropy", "path_depth", "has_query", "has_fragment", "n_upper",
    "n_special", "longest_token", "has_ip", "has_punycode", "n_at", "n_equals",
    "n_underscore", "n_percent", "path_has_ext", "n_letters", "vowel_ratio",
    "bare_homepage",
]


def artefact_features(url: str) -> list[float]:
    p = urlparse(url if "://" in url else "http://" + url)
    host = (p.hostname or "").lower()
    path = p.path or ""
    query = p.query or ""
    labels = [x for x in host.split(".") if x]
    digits = sum(c.isdigit() for c in url)
    letters = sum(c.isalpha() for c in url)
    vowels = sum(c in "aeiouAEIOU" for c in url)
    tokens = [t for t in __import__("re").split(r"[^A-Za-z0-9]+", url) if t]
    return [
        float(len(url)), float(len(host)), float(len(path)), float(len(query)),
        float(url.count(".")), float(url.count("/")), float(url.count("-")),
        float(digits), digits / len(url) if url else 0.0,
        float(query.count("=")), float(query.count("&")),
        1.0 if p.scheme == "https" else 0.0,
        1.0 if host.startswith("www.") else 0.0,
        1.0 if p.port else 0.0,
        float(max(0, len(labels) - 2)),
        float(len(labels[-1]) if labels else 0),
        shannon(url), shannon(host),
        float(len([x for x in path.split("/") if x])),
        1.0 if query else 0.0,
        1.0 if p.fragment else 0.0,
        float(sum(c.isupper() for c in url)),
        float(sum(not c.isalnum() for c in url)),
        float(max((len(t) for t in tokens), default=0)),
        1.0 if __import__("re").match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else 0.0,
        1.0 if "xn--" in host else 0.0,
        float(url.count("@")), float(url.count("=")), float(url.count("_")),
        float(url.count("%")),
        1.0 if __import__("re").search(r"\.(php|html?|aspx?|jsp)$", path, 2) else 0.0,
        float(letters), vowels / letters if letters else 0.0,
        1.0 if not path.strip("/") else 0.0,
    ]


# --------------------------------------------------------------------------- #
def load(limit: int):
    import pandas as pd
    if not CORPUS.exists():
        raise SystemExit(f"corpus not found: {CORPUS.relative_to(ROOT)} — run `python -m ml.train` once to fetch it")
    df = pd.read_parquet(CORPUS).dropna(subset=["URL"])
    df["y"] = 1 - df["label"].astype(int)          # y = 1 means PHISHING
    if limit and len(df) > limit:
        pos = df[df.y == 1].sample(n=limit // 2, random_state=42)
        neg = df[df.y == 0].sample(n=limit // 2, random_state=42)
        df = pd.concat([pos, neg]).sample(frac=1.0, random_state=42)
    return df["URL"].astype(str).to_numpy(), df["y"].to_numpy()


def artefact_table(urls, y) -> dict:
    scheme = np.array([urlparse(u).scheme for u in urls])
    host = np.array([(urlparse(u).hostname or "").lower() for u in urls])
    path = np.array([len((urlparse(u).path or "").strip("/")) for u in urls])
    query = np.array([len(urlparse(u).query or "") for u in urls])
    digits = np.array([sum(c.isdigit() for c in u) for u in urls], dtype=float)
    www_stripped = np.array([h[4:] if h.startswith("www.") else h for h in host])
    labels_www_stripped = np.array([len([p for p in h.split(".") if p]) for h in www_stripped])
    hostlen_www_stripped = np.array([len(h) for h in www_stripped], dtype=float)

    legit, phish = (y == 0), (y == 1)
    return {
        "n_total": int(len(urls)),
        "n_legit": int(legit.sum()),
        "n_phish": int(phish.sum()),
        "https_legit": float((scheme[legit] == "https").mean()),
        "https_phish": float((scheme[phish] == "https").mean()),
        "www_legit": float(np.mean([h.startswith("www.") for h in host[legit]])),
        "www_phish": float(np.mean([h.startswith("www.") for h in host[phish]])),
        "barepath_legit": float((path[legit] == 0).mean()),
        "barepath_phish": float((path[phish] == 0).mean()),
        "query_legit": float((query[legit] > 0).mean()),
        "query_phish": float((query[phish] > 0).mean()),
        "digits_legit": float(digits[legit].mean()),
        "digits_phish": float(digits[phish].mean()),
        # A FOURTH artefact, found while building the artefact-free model.
        # Stripping "www." is not enough: the legitimate class was harvested as
        # canonicalised homepages, so it barely has subdomains at all, while the
        # phishing class does. Subdomain DEPTH therefore leaks the same
        # collection artefact through any host-level feature.
        "subdomains_legit_2label": float(np.mean(labels_www_stripped[legit] == 2)),
        "subdomains_phish_2label": float(np.mean(labels_www_stripped[phish] == 2)),
        "subdomains_legit_deep": float(np.mean(labels_www_stripped[legit] >= 4)),
        "subdomains_phish_deep": float(np.mean(labels_www_stripped[phish] >= 4)),
        "hostlen_legit": float(hostlen_www_stripped[legit].mean()),
        "hostlen_phish": float(hostlen_www_stripped[phish].mean()),
        # Single-feature MCC: each artefact used alone as the whole classifier.
        "mcc_is_http": _single_feature_mcc(scheme != "https", y),
        "mcc_no_www": _single_feature_mcc(
            np.array([not h.startswith("www.") for h in host]), y),
        "mcc_has_subdomain": _single_feature_mcc(labels_www_stripped > 2, y),
    }


def _single_feature_mcc(pred_bool, y) -> float:
    from sklearn.metrics import matthews_corrcoef
    return float(matthews_corrcoef(y, pred_bool.astype(int)))


def run_lr(X, y, label: str, group_key=None) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split, GroupShuffleSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import (matthews_corrcoef, average_precision_score, roc_curve)

    if group_key is None:
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
    else:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
        tr, te = next(gss.split(X, y, groups=group_key))
        Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]

    sc = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
    clf.fit(sc.transform(Xtr), ytr)
    proba = clf.predict_proba(sc.transform(Xte))[:, 1]
    pred = (proba >= 0.5).astype(int)
    fpr, tpr, _ = roc_curve(yte, proba)
    ok = np.flatnonzero(fpr <= 0.01)
    return {
        "label": label,
        "mcc": float(matthews_corrcoef(yte, pred)),
        "pr_auc": float(average_precision_score(yte, proba)),
        "recall_at_fpr1": float(tpr[ok[-1]]) if len(ok) else 0.0,
        "n_test": int(len(yte)),
        "n_features": int(X.shape[1]),
        "_model": (clf, sc),
    }


def render_markdown(a: dict, expA: dict, expB: dict, deep: list) -> str:
    """The block embedded verbatim into REPORT.md §B.0."""
    L = []
    W = L.append
    W("```text")
    W(f"PhiUSIIL (UCI id 967) — {a['n_total']:,} rows, URL column only.")
    W(f"  legitimate class : {a['n_legit']:,}")
    W(f"  phishing class   : {a['n_phish']:,}")
    W("")
    W("COLLECTION ARTEFACTS IN THE LEGITIMATE CLASS")
    W("                                    legitimate      phishing")
    W(f"  scheme is https              {a['https_legit']:11.1%}   {a['https_phish']:11.1%}")
    W(f"  host starts 'www.'           {a['www_legit']:11.1%}   {a['www_phish']:11.1%}")
    W(f"  bare homepage, no path       {a['barepath_legit']:11.1%}   {a['barepath_phish']:11.1%}")
    W(f"  has a query string           {a['query_legit']:11.1%}   {a['query_phish']:11.1%}")
    W(f"  mean digits in URL           {a['digits_legit']:11.2f}   {a['digits_phish']:11.2f}")
    W("")
    W("A FOURTH ARTEFACT — SUBDOMAIN DEPTH (stripping 'www.' does not remove it)")
    W("The legitimate class was harvested as canonicalised homepages, so it has")
    W("almost no subdomains; the phishing class does. Any host-level feature")
    W("therefore still carries the collection artefact.")
    W("                                    legitimate      phishing")
    W(f"  exactly 2 labels             {a['subdomains_legit_2label']:11.1%}   "
      f"{a['subdomains_phish_2label']:11.1%}")
    W(f"  4 or more labels             {a['subdomains_legit_deep']:11.1%}   "
      f"{a['subdomains_phish_deep']:11.1%}")
    W(f"  mean host length             {a['hostlen_legit']:11.2f}   {a['hostlen_phish']:11.2f}")
    W("")
    W("SINGLE-FEATURE MCC (one artefact used alone as the entire classifier)")
    W(f"  is_http        {a['mcc_is_http']:.4f}")
    W(f"  no_www         {a['mcc_no_www']:.4f}")
    W(f"  has_subdomain  {a['mcc_has_subdomain']:.4f}   <- as strong as Experiment A's")
    W("                           whole 7-feature model")
    W("")
    W("WHAT THAT DOES TO A MODEL   (same LogisticRegression, same random split)")
    W(f"  A  {expA['n_features']:2d} shipped lexical features   "
      f"MCC {expA['mcc']:.4f}  PR-AUC {expA['pr_auc']:.4f}  R@FPR1% {expA['recall_at_fpr1']:.4f}")
    W(f"  B  {expB['n_features']:2d} artefact-bearing features  "
      f"MCC {expB['mcc']:.4f}  PR-AUC {expB['pr_auc']:.4f}  R@FPR1% {expB['recall_at_fpr1']:.4f}")
    W("")
    W("EXPERIMENT B SCORED ON REAL LEGITIMATE DEEP LINKS")
    W("  (every URL below is genuine; p is Experiment B's P(phishing))")
    for d in deep:
        flag = "FLAGGED" if d["p_phishing"] >= 0.5 else "  ok   "
        W(f"  {flag}  p={d['p_phishing']:.3f}  {d['url'][:66]}")
    n_flagged = sum(1 for d in deep if d["p_phishing"] >= 0.5)
    W("")
    W(f"  {n_flagged}/{len(deep)} legitimate deep links flagged as phishing by the "
      f"MCC {expB['mcc']:.2f} model.")
    W("```")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="0 = full corpus")
    args = ap.parse_args()

    t0 = time.time()
    print("Loading corpus ...")
    urls, y = load(args.limit)
    print(f"  {len(urls):,} rows\n")

    print("Measuring collection artefacts ...")
    a = artefact_table(urls, y)
    print(f"  legit https={a['https_legit']:.1%}  www={a['www_legit']:.1%}  "
          f"bare-path={a['barepath_legit']:.1%}  query={a['query_legit']:.1%}")
    print(f"  single-feature MCC: is_http={a['mcc_is_http']:.4f}  no_www={a['mcc_no_www']:.4f}\n")

    print("Experiment A — shipped lexical features, LR, random split ...")
    lex = FEATURE_GROUPS["lexical"]
    XA = np.array([[extract({"url": u, "html": "", "text": ""})[n] for n in lex] for u in urls])
    expA = run_lr(XA, y, "A: shipped lexical, random split")
    print(f"  MCC {expA['mcc']:.4f}  PR-AUC {expA['pr_auc']:.4f}  "
          f"R@FPR1% {expA['recall_at_fpr1']:.4f}\n")

    print("Experiment B — 34 artefact-bearing features, SAME LR, same split ...")
    XB = np.array([artefact_features(u) for u in urls])
    expB = run_lr(XB, y, "B: artefact-bearing, random split")
    print(f"  MCC {expB['mcc']:.4f}  PR-AUC {expB['pr_auc']:.4f}  "
          f"R@FPR1% {expB['recall_at_fpr1']:.4f}")
    print("  ^ DO NOT SHIP. This is the artefact, not detection skill.\n")

    print("Scoring real legitimate deep links with Experiment B's model ...")
    clf, sc = expB["_model"]
    XD = np.array([artefact_features(u) for u in LEGITIMATE_DEEP_LINKS])
    pD = clf.predict_proba(sc.transform(XD))[:, 1]
    deep = [{"url": u, "p_phishing": float(p)} for u, p in zip(LEGITIMATE_DEEP_LINKS, pD)]
    for d in deep:
        print(f"  {'FLAGGED' if d['p_phishing'] >= 0.5 else '  ok   '} "
              f"p={d['p_phishing']:.3f}  {d['url'][:70]}")
    n_flagged = sum(1 for d in deep if d["p_phishing"] >= 0.5)
    print(f"\n  {n_flagged}/{len(deep)} genuine deep links flagged as phishing.\n")

    for e in (expA, expB):
        e.pop("_model", None)
    block = render_markdown(a, expA, expB, deep)
    OUT_JSON.write_text(json.dumps({
        "generated_by": "eval/corpus_audit.py",
        "corpus": "PhiUSIIL (UCI id 967), URL column only",
        "n_rows_audited": int(len(urls)),
        "artefacts": a,
        "experiment_a": expA,
        "experiment_b": expB,
        "legitimate_deep_links": deep,
        "n_deep_links_flagged": n_flagged,
        "markdown_block": block,
    }, indent=2) + "\n", encoding="utf-8")

    print("=" * 74)
    print(block)
    print("=" * 74)
    print(f"\nWrote {OUT_JSON.relative_to(ROOT)}  ({time.time() - t0:.1f}s)")
    print("eval/run_eval.py embeds `markdown_block` verbatim into REPORT.md §B.0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
