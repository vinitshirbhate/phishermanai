"""Benchmark: how far does a perceptual hash drift across WhatsApp re-forwards?

    python -m eval.phash_drift

WHY THIS EXPERIMENT EXISTS
--------------------------
Content-provenance schemes such as C2PA attach a signed manifest to a file. That
manifest does not survive WhatsApp: the platform re-encodes every image and
strips its metadata, so the signature is gone after a single forward. Any
verification approach for this channel has to work on the pixels that arrive,
not on metadata that does not.

That argues for a perceptual hash -- but only if we know how much it drifts.
This measures exactly that: take genuine documents, push each through
WhatsApp-style compression 1, 3 and 5 times, and record the Hamming distance
from the original hash at each generation.

The result is what justifies the tier thresholds in core/filings/matcher.py
(< 10 same document, 10-20 likely altered, > 20 different) rather than leaving
them as round numbers someone picked.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from PIL import Image

from core.ingest.image_pipeline import compute_phash, phash_distance, preprocess
from eval.make_screenshots import whatsapp_degrade

RESULTS_DIR = Path(__file__).resolve().parent / "results"
SHOT_DIR = Path(__file__).resolve().parent / "fixtures" / "screenshots"
GENERATIONS = (1, 3, 5)


def _hash_of(img: Image.Image) -> str | None:
    processed, _ = preprocess(img)
    return compute_phash(processed)


def run() -> dict:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(SHOT_DIR.glob("*.png"))
    if not sources:
        return {"error": "No screenshots found. Run: python -m eval.make_screenshots"}

    rows: list[dict] = []
    per_generation: dict[int, list[int]] = {g: [] for g in GENERATIONS}
    # A different document, to show the distance between unrelated images and
    # confirm the thresholds actually separate the two populations.
    cross_distances: list[int] = []

    baselines: dict[str, str] = {}
    for path in sources:
        original = Image.open(path)
        original.load()
        base_hash = _hash_of(original)
        if not base_hash:
            continue
        baselines[path.name] = base_hash

        row = {"file": path.name}
        for generations in GENERATIONS:
            degraded = whatsapp_degrade(original, generations=generations)
            degraded_hash = _hash_of(degraded)
            distance = phash_distance(base_hash, degraded_hash) if degraded_hash else None
            row[f"gen_{generations}"] = distance
            if distance is not None:
                per_generation[generations].append(distance)
        rows.append(row)

    names = list(baselines)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            distance = phash_distance(baselines[a], baselines[b])
            if distance is not None:
                cross_distances.append(distance)

    summary = {
        "documents": len(rows),
        "hash_bits": 256,
        "per_generation": {
            f"gen_{g}": {
                "n": len(v),
                "mean": round(statistics.mean(v), 2) if v else None,
                "median": statistics.median(v) if v else None,
                "max": max(v) if v else None,
                "min": min(v) if v else None,
            }
            for g, v in per_generation.items()
        },
        "different_documents": {
            "n": len(cross_distances),
            "mean": round(statistics.mean(cross_distances), 2) if cross_distances else None,
            "min": min(cross_distances) if cross_distances else None,
        },
        "rows": rows,
    }

    (RESULTS_DIR / "phash_drift.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Chart, if matplotlib is available. The numbers are the deliverable; the
    # chart is a convenience.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        data = [per_generation[g] for g in GENERATIONS]
        ax.boxplot(data, tick_labels=[f"{g}x" for g in GENERATIONS])
        same_max = max((max(v) for v in data if v), default=0)
        ax.axhline(10, color="#d97706", ls="--", lw=1.2, label="tier threshold: same document (<10)")
        ax.axhline(20, color="#dc2626", ls="--", lw=1.2, label="tier threshold: altered (10-20)")
        if cross_distances:
            ax.axhline(
                statistics.mean(cross_distances), color="#334155", ls=":", lw=1.2,
                label=f"mean distance between different documents ({statistics.mean(cross_distances):.0f})",
            )
        ax.set_xlabel("WhatsApp recompression generations")
        ax.set_ylabel("pHash Hamming distance from original (256-bit)")
        ax.set_title("Perceptual hash drift across WhatsApp re-forwarding")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(RESULTS_DIR / "phash_drift.png", dpi=140)
        summary["chart"] = str(RESULTS_DIR / "phash_drift.png")
    except Exception as exc:  # noqa: BLE001
        summary["chart_error"] = str(exc)

    return summary


if __name__ == "__main__":  # pragma: no cover
    result = run()
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    print("\nper-document distances:")
    for row in result.get("rows", []):
        print(f"  {row['file']:<36} " + "  ".join(
            f"{g}x={row.get(f'gen_{g}')}" for g in GENERATIONS
        ))
