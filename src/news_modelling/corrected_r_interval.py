"""Bootstrap interval for the attenuation-corrected correlation.

    PYTHONPATH=src .venv/bin/python -m news_modelling.corrected_r_interval

Supervisor directive (2026-08-05): "Careful with the 0.66 though. Dividing
by sqrt(0.594) inflates the uncertainty as much as the point estimate, and
0.594 has its own error. I'd lead with the observed 0.509 and put the
corrected figure in a footnote with an interval."

The observed r is the Pearson correlation between a news feature and the
party-demeaned fitting-cell residual, computed over cells that carry news
coverage at the headline window. The corrected r divides by sqrt(reliability)
to undo the attenuation caused by noisy cell-mean estimates.

Both the correlation and the reliability depend on which cells are sampled,
so dividing a point estimate by a point estimate understates the uncertainty.
This module bootstraps both simultaneously: resample cells with replacement,
recompute r and reliability from the resample, compute corrected r, and
report the percentile interval.

EXPLORATORY. Post-unblinding.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.blinded_2026_predictions_v2 import (
    FIT_ELECTION_MAP,
    aggregate_v2_residuals,
)
from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
    party_key,
)
from news_modelling.stage1_bundle import load_stage1_bundle

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUT_DIR = Path("news_features/corrected_r_interval_v1")

WINDOW = "90_to_31_days"
FEATURE = "party_frame_incumbent_judgement_share"
N_BOOT = 10_000
SEED = 20260805

STATUS = (
    "EXPLORATORY attenuation-corrected r with bootstrap interval, "
    "post-unblinding."
)


def _pooled_sigma2(oof_rows: list[dict]) -> float:
    """Weighted pooled within-cell variance of residuals.

    Standard pooled-variance formula: sum each cell's SS, divide by
    total df. Only cells with n > 1 contribute (single-candidate cells
    have no within-cell variance to estimate).
    """
    by_cell: dict[tuple, list[float]] = defaultdict(list)
    for row in oof_rows:
        election = row.get("election_id")
        if election not in FIT_ELECTION_MAP:
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        by_cell[(election, key)].append(
            float(row["observed_vote_share"])
            - float(row["predicted_vote_share"])
        )

    total_ss = 0.0
    total_df = 0
    for resids in by_cell.values():
        n = len(resids)
        if n < 2:
            continue
        total_ss += float(np.var(resids, ddof=1)) * (n - 1)
        total_df += n - 1
    return total_ss / total_df


def _collect_covered_cells(
    cells: list[dict],
    feature_index: dict,
    sigma2: float,
) -> list[dict]:
    """Covered fitting cells with feature value and per-cell metadata."""
    # Party means across covered cells only (for demeaning)
    covered_raw = []
    for cell in cells:
        row = feature_index.get(
            (cell["news_election_id"], cell["party_key"], WINDOW))
        if row is None:
            continue
        count = str(row.get("party_article_count", "")).strip()
        if count in ("", "0") or float(count) == 0:
            continue
        feat = str(row.get(FEATURE, "")).strip()
        if feat == "":
            continue
        covered_raw.append({
            "party": cell["party_key"],
            "n": cell["candidate_rows"],
            "mean_residual": cell["mean_residual"],
            "feature_val": float(feat),
            "sampling_var": sigma2 / cell["candidate_rows"],
        })

    # Demean residuals by party mean (computed over covered cells only)
    party_sums: dict[str, list[float]] = defaultdict(list)
    for c in covered_raw:
        party_sums[c["party"]].append(c["mean_residual"])
    party_means = {p: float(np.mean(v)) for p, v in party_sums.items()}
    for c in covered_raw:
        c["demeaned_residual"] = c["mean_residual"] - party_means[c["party"]]

    return covered_raw


def _pearson(xs, ys):
    if len(xs) < 3:
        return None
    return float(np.corrcoef(xs, ys)[0, 1])


def _reliability(cell_means, sampling_vars):
    """reliability = 1 - mean(sampling_var) / var(cell_means)."""
    var_means = float(np.var(cell_means, ddof=1))
    if var_means == 0:
        return None
    return 1.0 - float(np.mean(sampling_vars)) / var_means


def bootstrap_corrected_r(covered: list[dict], n_boot: int, seed: int):
    """Resample cells, recompute r, reliability, and corrected r."""
    rng = np.random.default_rng(seed)
    n = len(covered)

    feats = np.array([c["feature_val"] for c in covered])
    resids = np.array([c["demeaned_residual"] for c in covered])
    means = np.array([c["mean_residual"] for c in covered])
    svars = np.array([c["sampling_var"] for c in covered])

    boot_r = []
    boot_rel = []
    boot_corrected = []

    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        r = _pearson(feats[idx], resids[idx])
        rel = _reliability(means[idx], svars[idx])
        if r is None or rel is None or rel <= 0:
            continue
        boot_r.append(r)
        boot_rel.append(rel)
        boot_corrected.append(r / np.sqrt(rel))

    return boot_r, boot_rel, boot_corrected


def main() -> None:
    bundle = load_stage1_bundle(BUNDLE)
    oof = [dict(r) for r in bundle.out_of_fold]
    cells = aggregate_v2_residuals(oof)
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)

    sigma2 = _pooled_sigma2(oof)
    covered = _collect_covered_cells(cells, feature_index, sigma2)

    # Point estimates
    feats = [c["feature_val"] for c in covered]
    resids = [c["demeaned_residual"] for c in covered]
    means = [c["mean_residual"] for c in covered]
    svars = [c["sampling_var"] for c in covered]

    observed_r = _pearson(feats, resids)
    reliability = _reliability(means, svars)
    corrected_r = observed_r / np.sqrt(reliability) if reliability and reliability > 0 else None

    # Bootstrap
    boot_r, boot_rel, boot_corrected = bootstrap_corrected_r(
        covered, N_BOOT, SEED)

    payload = {
        "status": STATUS,
        "feature": FEATURE,
        "window": WINDOW,
        "covered_cells": len(covered),
        "pooled_sigma2": round(sigma2, 3),
        "observed_r": round(observed_r, 4),
        "reliability": round(reliability, 4),
        "corrected_r": round(corrected_r, 4) if corrected_r else None,
        "n_bootstrap": N_BOOT,
        "bootstrap_observed_r": {
            "ci_lower": round(float(np.percentile(boot_r, 2.5)), 4),
            "ci_upper": round(float(np.percentile(boot_r, 97.5)), 4),
            "median": round(float(np.median(boot_r)), 4),
        },
        "bootstrap_reliability": {
            "ci_lower": round(float(np.percentile(boot_rel, 2.5)), 4),
            "ci_upper": round(float(np.percentile(boot_rel, 97.5)), 4),
            "median": round(float(np.median(boot_rel)), 4),
        },
        "bootstrap_corrected_r": {
            "ci_lower": round(float(np.percentile(boot_corrected, 2.5)), 4),
            "ci_upper": round(float(np.percentile(boot_corrected, 97.5)), 4),
            "median": round(float(np.median(boot_corrected)), 4),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "corrected_r_interval.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    def fmt(v):
        return f"{v:+.4f}" if v is not None else "-"

    obs = payload["bootstrap_observed_r"]
    rel = payload["bootstrap_reliability"]
    cor = payload["bootstrap_corrected_r"]

    lines = [
        "# Attenuation-corrected correlation with bootstrap interval",
        "",
        f"**{payload['status']}**",
        "",
        f"Feature: `{payload['feature']}`",
        f"Window: {payload['window']}",
        f"Covered cells: {payload['covered_cells']}",
        f"Pooled within-cell variance (sigma-squared): {payload['pooled_sigma2']}",
        "",
        "## Point estimates",
        "",
        f"- Observed r: **{fmt(payload['observed_r'])}**",
        f"- Reliability: **{payload['reliability']}**",
        f"- Corrected r = observed / sqrt(reliability): "
        f"**{fmt(payload['corrected_r'])}**",
        "",
        "## Bootstrap intervals (10,000 resamples of cells)",
        "",
        "| quantity | point estimate | 95% CI |",
        "| --- | ---: | --- |",
        f"| observed r | {fmt(payload['observed_r'])} | "
        f"[{fmt(obs['ci_lower'])}, {fmt(obs['ci_upper'])}] |",
        f"| reliability | {payload['reliability']} | "
        f"[{rel['ci_lower']}, {rel['ci_upper']}] |",
        f"| corrected r | {fmt(payload['corrected_r'])} | "
        f"[{fmt(cor['ci_lower'])}, {fmt(cor['ci_upper'])}] |",
        "",
        "The corrected r interval is wider than the observed r interval "
        "because dividing by sqrt(reliability) amplifies the uncertainty "
        "in both the numerator and the denominator.",
        "",
    ]
    (OUT_DIR / "corrected_r_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
