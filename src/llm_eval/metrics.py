"""Agreement metrics with bootstrap confidence intervals.

All metrics treat 1 as the positive class. Every resample draws one set of
article indices and computes every metric on it, so the intervals are
mutually consistent. With the same seed, the kappa and recall intervals match
those of v2_design.local_relevance_eval exactly.
"""

from __future__ import annotations

import numpy as np

RESAMPLES, SEED = 2000, 20261007


def kappa(y: np.ndarray, p: np.ndarray) -> float:
    """Cohen's kappa: agreement beyond what the two base rates imply."""
    po = float((y == p).mean())
    pe = float(y.mean() * p.mean() + (1 - y.mean()) * (1 - p.mean()))
    return (po - pe) / (1 - pe) if pe < 1 else 0.0


def recall(y: np.ndarray, p: np.ndarray) -> float:
    """Share of reference positives the model also called positive."""
    return float(p[y == 1].mean()) if (y == 1).any() else float("nan")


def precision(y: np.ndarray, p: np.ndarray) -> float:
    """Share of model positives that the reference also calls positive."""
    return float(y[p == 1].mean()) if (p == 1).any() else float("nan")


def f1(y: np.ndarray, p: np.ndarray) -> float:
    r, pr = recall(y, p), precision(y, p)
    if np.isnan(r) or np.isnan(pr) or r + pr == 0:
        return float("nan")
    return 2 * r * pr / (r + pr)


def agreement(y: np.ndarray, p: np.ndarray) -> float:
    return float((y == p).mean())


METRICS = {"kappa": kappa, "recall": recall, "precision": precision,
           "f1": f1, "agreement": agreement}


def score(y, p, *, resamples: int = RESAMPLES, seed: int = SEED) -> dict:
    """Point estimates plus 95% percentile bootstrap intervals."""
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=int)
    if y.shape != p.shape or y.size == 0:
        raise ValueError("y and p must be non-empty and the same length")
    rng = np.random.default_rng(seed)
    draws = {name: [] for name in METRICS}
    for _ in range(resamples):
        i = rng.integers(0, len(y), len(y))
        for name, fn in METRICS.items():
            draws[name].append(fn(y[i], p[i]))
    out = {"n": int(len(y)), "positives": int(y.sum()),
           "predicted_positives": int(p.sum())}
    for name, fn in METRICS.items():
        point = fn(y, p)
        out[name] = None if np.isnan(point) else round(point, 4)
        values = np.asarray(draws[name], dtype=float)
        if np.isnan(values).all():
            # Undefined in every resample (e.g. no positives at all).
            out[f"{name}_ci95"] = None
            continue
        # nanpercentile: a resample with no positives has undefined recall.
        lo, hi = (np.nanpercentile(values, q) for q in (2.5, 97.5))
        out[f"{name}_ci95"] = [round(float(lo), 4), round(float(hi), 4)]
    return out


def score_by(examples, predictions: dict[str, int], field: str) -> dict:
    """Scores per subgroup, e.g. per source or per labelling batch.

    `field` is "origin" or a key of Example.group. Subgroups are where
    aggregate agreement hides its failures.
    """
    groups: dict[str, list] = {}
    for e in examples:
        key = e.origin if field == "origin" else e.group.get(field, "")
        groups.setdefault(key, []).append(e)
    out = {}
    for key, members in sorted(groups.items()):
        y = [e.label for e in members]
        p = [predictions.get(e.id, 0) for e in members]
        out[key] = score(y, p, resamples=500)
    return out
