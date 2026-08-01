"""Exploratory comparison: residual (A) versus joint stacked (B) news models.

    PYTHONPATH=src .venv/bin/python -m news_modelling.compare_news_approaches

The design brief asks for at least two news-model approaches to be
implemented and compared. Both have existed in ``news_estimator`` since
the estimator was written; only the residual approach was ever carried
into production. This module runs the missing comparison — after the
unblinding, so it is **exploratory by construction**: nothing here can
join the confirmatory verdict, and the output says so.

The two approaches, at the production fitting grain
---------------------------------------------------
Both are fitted on the same 45 election x party cells the v2 freeze used
(2017, 2021 and the eight pre-holdout by-elections), with the same
frozen two-feature specifications and the same fixed ridge penalty:

- **A (residual)**: target = mean Stage 1 residual per cell; final
  prediction = mean baseline + predicted residual. This is what v1/v2
  froze.
- **B (joint)**: target = mean observed share per cell; the mean
  baseline prediction enters as an extra feature the model may
  re-weight, alongside the news features. B can rescale a biased
  baseline where A cannot; A cannot disguise baseline recalibration as
  news signal where B can.

Evaluation is leave-one-election-out over the ten fitting elections:
fit on nine elections' cells, predict the held-out election's cells,
pool the held-out errors. Group-aware and chronology-agnostic - with
ten elections spanning 2015-2025 a strict rolling origin would leave
early folds with almost nothing to fit on, and LOEO is the established
robustness pattern in this repository (the LOPO audit). A
baseline-only reference (predict the cell's mean baseline unchanged)
is reported beside both approaches so neither can look good merely by
tracking the baseline.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.blinded_2026_predictions_v2 import FIT_ELECTION_MAP
from news_modelling.news_estimator import RidgeModel
from news_modelling.production_news_experiment import (
    FIXED_RIDGE_PENALTY,
    _feature_index,
    _float_or_structural_zero,
    _read_csv,
    party_key,
)
from news_modelling.stage1_bundle import load_stage1_bundle

FEATURES = Path("news_features/news_feature_table_v2.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUTPUT_DIR = Path("news_features/approach_comparison_v1")

STATUS = (
    "EXPLORATORY, post-unblinding. This comparison cannot join the "
    "confirmatory verdict and no approach may be promoted from it."
)


def fitting_cells(oof_rows: list[dict]) -> list[dict]:
    """One cell per (fitting election, party): baseline, observed, residual.

    Same grain and anti-pseudo-replication rule as every production fit;
    the joint approach needs the observed and baseline means separately,
    which the frozen residual aggregator does not carry.
    """

    sums: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"observed": [], "baseline": []})
    for row in oof_rows:
        election = row.get("election_id")
        if election not in FIT_ELECTION_MAP:
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        cell = sums[(election, key)]
        cell["observed"].append(float(row["observed_vote_share"]))
        cell["baseline"].append(float(row["predicted_vote_share"]))
    return [
        {
            "election_id": election,
            "news_election_id": FIT_ELECTION_MAP[election],
            "party_key": key,
            "mean_observed": float(np.mean(values["observed"])),
            "mean_baseline": float(np.mean(values["baseline"])),
        }
        for (election, key), values in sorted(sums.items())
    ]


def _design(cells: list[dict], feature_index: dict, columns: list[str],
            period: str, *, with_baseline: bool) -> np.ndarray:
    rows = []
    for cell in cells:
        feature = feature_index[(cell["news_election_id"],
                                 cell["party_key"], period)]
        values = [_float_or_structural_zero(feature, column)
                  for column in columns]
        if with_baseline:
            # Approach B admits the baseline as a feature the ridge may
            # re-weight; approach A never sees it inside the model.
            values.append(cell["mean_baseline"])
        rows.append(values)
    return np.array(rows, dtype=float)


def leave_one_election_out(cells: list[dict], feature_index: dict,
                           columns: list[str], period: str) -> dict:
    """Pooled held-out cell errors for A, B and the baseline reference."""

    errors = {"residual_A": [], "joint_B": [], "baseline_only": []}
    for held in sorted({cell["election_id"] for cell in cells}):
        train = [cell for cell in cells if cell["election_id"] != held]
        test = [cell for cell in cells if cell["election_id"] == held]

        design_a = _design(train, feature_index, columns, period,
                           with_baseline=False)
        target_a = np.array([cell["mean_observed"] - cell["mean_baseline"]
                             for cell in train])
        model_a = RidgeModel(FIXED_RIDGE_PENALTY).fit(design_a, target_a)
        pred_a = model_a.predict(
            _design(test, feature_index, columns, period,
                    with_baseline=False))

        design_b = _design(train, feature_index, columns, period,
                           with_baseline=True)
        target_b = np.array([cell["mean_observed"] for cell in train])
        model_b = RidgeModel(FIXED_RIDGE_PENALTY).fit(design_b, target_b)
        pred_b = model_b.predict(
            _design(test, feature_index, columns, period,
                    with_baseline=True))

        for cell, adj, joint in zip(test, pred_a, pred_b):
            observed = cell["mean_observed"]
            errors["residual_A"].append(
                abs(cell["mean_baseline"] + adj - observed))
            errors["joint_B"].append(abs(joint - observed))
            errors["baseline_only"].append(
                abs(cell["mean_baseline"] - observed))
    return {name: round(float(np.mean(values)), 4)
            for name, values in errors.items()}


def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    cells = fitting_cells([dict(row) for row in bundle.out_of_fold])

    results = {"status": STATUS, "cells": len(cells),
               "elections": len({c["election_id"] for c in cells}),
               "specifications": []}
    a_wins = b_wins = 0
    for analysis, spec in audit["frozen_feature_sets"].items():
        for period in audit["feature_table"]["windows"]:
            scores = leave_one_election_out(
                cells, feature_index, list(spec["columns"]), period)
            better = ("A" if scores["residual_A"] < scores["joint_B"]
                      else "B")
            a_wins += better == "A"
            b_wins += better == "B"
            results["specifications"].append({
                "analysis": analysis, "period": period,
                "loeo_cell_mae": scores, "lower_mae": better,
            })

    results["summary"] = {
        "A_better": a_wins, "B_better": b_wins,
        "note": (
            "Counts of which approach had the lower leave-one-election-out "
            "cell MAE per frozen specification. The baseline_only column is "
            "the no-news reference both approaches must beat before either "
            "matters."
        ),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "approach_comparison.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Residual (A) versus joint stacked (B): the design's comparison",
        "", f"**{STATUS}**", "",
        f"Fitted on the {results['cells']} v2 election x party cells across "
        f"{results['elections']} pre-2026 elections; leave-one-election-out; "
        "frozen features and penalty throughout.", "",
        "| analysis | window | A residual | B joint | baseline only | lower |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for entry in results["specifications"]:
        scores = entry["loeo_cell_mae"]
        lines.append(
            f"| {entry['analysis']} | {entry['period']} | "
            f"{scores['residual_A']:.3f} | {scores['joint_B']:.3f} | "
            f"{scores['baseline_only']:.3f} | {entry['lower_mae']} |")
    lines += [
        "",
        f"**A lower in {a_wins} of {a_wins + b_wins} specifications; "
        f"B lower in {b_wins}.**", "",
    ]
    (OUTPUT_DIR / "approach_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
