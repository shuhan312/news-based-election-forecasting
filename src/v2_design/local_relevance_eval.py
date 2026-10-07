"""Score a local relevance classifier against V1's human reference.

Metrics follow v2_design/local_relevance_v1/criteria.md: binary include vs
not-include (any non-include output, including blanks, schema errors and
needs_second_review, counts as exclude), Cohen's kappa and include recall,
each with a 2,000-resample article bootstrap. The gate is read on the point
estimates.

Running this module scores B0, the archived output of V1's frozen v2
classifier. It needs no API call.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

SPLIT = Path("v2_design/local_relevance_v1/split.csv")
HUMAN = {
    "corpus_manual": Path("news_collection/full_corpus_review.csv"),
    "v1_validation_seen": Path("news_collection/llm_validation_sample.csv"),
}
B0_OUTPUT = {
    "corpus_manual": Path("news_collection/manual_review_llm_v2_corpus.csv"),
    "v1_validation_seen":
        Path("news_collection/manual_review_llm_v2_validation.csv"),
}
OUT = Path("v2_design/local_relevance_v1/baseline_b0.json")
KAPPA_BAR, RECALL_BAR = 0.60, 0.75
RESAMPLES, SEED = 2000, 20261007


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_split() -> list[dict]:
    return _read(SPLIT)


def human_labels() -> dict[str, int]:
    labels = {}
    for path in HUMAN.values():
        for r in _read(path):
            if r["arm"] == "local" and r["e5_decision"] in ("include", "exclude"):
                labels[r["article_id"]] = int(r["e5_decision"] == "include")
    return labels


def kappa(y: np.ndarray, p: np.ndarray) -> float:
    po = float((y == p).mean())
    pe = float(y.mean() * p.mean() + (1 - y.mean()) * (1 - p.mean()))
    return (po - pe) / (1 - pe) if pe < 1 else 0.0


def recall(y: np.ndarray, p: np.ndarray) -> float:
    return float(p[y == 1].mean()) if (y == 1).any() else float("nan")


def score(y: np.ndarray, p: np.ndarray) -> dict:
    rng = np.random.default_rng(SEED)
    ks, rs = [], []
    for _ in range(RESAMPLES):
        i = rng.integers(0, len(y), len(y))
        ks.append(kappa(y[i], p[i]))
        rs.append(recall(y[i], p[i]))
    k, r = kappa(y, p), recall(y, p)
    return {
        "n": int(len(y)), "human_include": int(y.sum()),
        "predicted_include": int(p.sum()),
        "agreement": round(float((y == p).mean()), 4),
        "kappa": round(k, 4),
        "kappa_ci95": [round(float(np.percentile(ks, q)), 4) for q in (2.5, 97.5)],
        "include_recall": round(r, 4),
        "include_recall_ci95": [round(float(np.nanpercentile(rs, q)), 4)
                                for q in (2.5, 97.5)],
        "include_precision": round(float(y[p == 1].mean()), 4) if p.any() else None,
        "passes_gate": bool(k >= KAPPA_BAR and r >= RECALL_BAR),
    }


def evaluate(predictions: dict[str, int], split_name: str) -> dict:
    """Score {article_id: 1 include / 0 otherwise} on one split."""
    labels = human_labels()
    ids = [r["article_id"] for r in load_split() if r["split"] == split_name]
    missing = [i for i in ids if i not in predictions]
    y = np.array([labels[i] for i in ids])
    p = np.array([predictions.get(i, 0) for i in ids])
    return {**score(y, p), "missing_predictions_counted_exclude": len(missing)}


def b0_predictions() -> dict[str, int]:
    preds = {}
    for path in B0_OUTPUT.values():
        for r in _read(path):
            preds[r["article_id"]] = int(r["e5_decision"] == "include")
    return preds


def main() -> None:
    preds = b0_predictions()
    payload = {
        "arm": "B0 - V1 frozen v2 classifier (claude-sonnet-5), archived output",
        "criteria": "v2_design/local_relevance_v1/criteria.md",
        "dev": evaluate(preds, "dev"),
        "test": evaluate(preds, "test"),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
