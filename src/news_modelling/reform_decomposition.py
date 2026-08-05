"""Decompose arm deltas into Reform vs non-Reform components.

    PYTHONPATH=src .venv/bin/python -m news_modelling.reform_decomposition

Supervisor directive (2026-08-05): "Your -13.0 is really -10.3 for Reform
and +2.7 for everyone else. Worth plotting those two components separately."

Also verifies the claim that the party-indicator benchmark is harmful for
Reform itself (user's WhatsApp reply cited -0.29). The score_specification
function already computes a Reform-only scope; this module extracts it and
derives the non-Reform residual from the weighted difference.

EXPLORATORY. Post-unblinding.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from news_modelling.blinded_2026_predictions import (
    predict_specification,
    sanitise_holdout_rows,
    _assign_ranks,
)
from news_modelling.blinded_2026_predictions_v2 import (
    _fit_specification,
    aggregate_v2_residuals,
)
from news_modelling.production_news_experiment import _feature_index, _read_csv
from news_modelling.stage1_bundle import load_stage1_bundle
from news_modelling.unblind_2026 import load_observed, score_specification

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUT_DIR = Path("news_features/reform_decomposition_v1")

WINDOWS = (
    "180_to_91_days", "90_to_31_days", "30_to_15_days",
    "14_to_8_days", "7_to_4_days", "final_72_hours",
)

PARTIES = ("conservative", "green", "labour", "liberal_democrat",
           "reform_uk", "ukip")

ARMS = {
    "frozen": ["party_article_share", "net_portrayal_share"],
    "placebo_party_dummies": [
        "party_is_conservative", "party_is_green", "party_is_labour",
        "party_is_liberal_democrat", "party_is_reform_uk", "party_is_ukip",
    ],
    "placebo_reform_dummy": ["party_is_reform_uk"],
}

STATUS = (
    "EXPLORATORY per-party delta decomposition, post-unblinding. "
    "Decomposes each arm's MAE delta into Reform and non-Reform components."
)


def _run_decomposed(columns, cells, feature_index, blinded, observed, window):
    """Run one arm and return delta for all, Reform-only, and non-Reform."""
    model, record = _fit_specification(
        cells, feature_index, period=window, feature_columns=columns)
    predictions, clipped = predict_specification(
        blinded, feature_index, model, period=window, feature_columns=columns)
    for row in predictions:
        row["included_in_reported_metrics"] = (
            "True" if row["party_key"] is not None else "False")
    _assign_ranks(
        predictions, "news_enhanced_prediction", "analysis_number_of_seats")

    # score_specification already splits all-supported vs reform
    metrics = score_specification(predictions, observed, with_bootstrap=False)
    overall = metrics["all_supported_parties"]
    reform = metrics["reform_uk"]

    n_all = overall["recalibrated_without_news"]["rows"]
    n_reform = reform["recalibrated_without_news"]["rows"]
    n_non = n_all - n_reform
    delta_all = overall["news_vs_recalibrated_mae"]
    delta_reform = reform["news_vs_recalibrated_mae"]

    # MAE is a mean, so the weighted decomposition is exact
    delta_non = ((n_all * delta_all - n_reform * delta_reform) / n_non
                 if n_non > 0 else None)

    return {
        "window": window,
        "all": {
            "n": n_all, "delta": round(delta_all, 4),
            "recal_mae": round(overall["recalibrated_without_news"]["mae"], 4),
            "news_mae": round(overall["news_enhanced"]["mae"], 4),
        },
        "reform": {
            "n": n_reform, "delta": round(delta_reform, 4),
            "recal_mae": round(reform["recalibrated_without_news"]["mae"], 4),
            "news_mae": round(reform["news_enhanced"]["mae"], 4),
        },
        "non_reform": {
            "n": n_non,
            "delta": round(delta_non, 4) if delta_non is not None else None,
        },
    }


def main() -> None:
    bundle = load_stage1_bundle(BUNDLE)
    oof = [dict(r) for r in bundle.out_of_fold]
    cells = aggregate_v2_residuals(oof)
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    observed = load_observed()
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)

    # Inject synthetic party indicator columns (same as identity_placebos.py
    # line 250-252); without this, party_is_* features are all zero.
    for (election, party, window), row in feature_index.items():
        for name in PARTIES:
            row[f"party_is_{name}"] = "1" if party == name else "0"

    results = {}
    for arm_name, columns in ARMS.items():
        results[arm_name] = [
            _run_decomposed(
                columns, cells, feature_index, blinded, observed, w)
            for w in WINDOWS
        ]

    payload = {"status": STATUS, "arms": results}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "reform_decomposition.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    arms = payload["arms"]

    def fmt(v):
        return f"{v:+.4f}" if v is not None else "-"

    lines = [
        "# Reform vs non-Reform delta decomposition",
        "",
        f"**{payload['status']}**",
        "",
        "Delta is the change in MAE against the recalibrated control; "
        "positive means news improved prediction. The non-Reform delta "
        "is derived from the weighted difference: "
        "(N_all * delta_all - N_reform * delta_reform) / N_non_reform.",
        "",
    ]

    for arm_name, windows in arms.items():
        lines += [
            f"## {arm_name}",
            "",
            "| window | all delta (n) | Reform delta (n) | non-Reform delta (n) |",
            "| --- | ---: | ---: | ---: |",
        ]
        for w in windows:
            lines.append(
                f"| {w['window']} "
                f"| {fmt(w['all']['delta'])} ({w['all']['n']}) "
                f"| {fmt(w['reform']['delta'])} ({w['reform']['n']}) "
                f"| {fmt(w['non_reform']['delta'])} ({w['non_reform']['n']}) |"
            )
        lines.append("")

    # Highlight the headline for party_dummies
    headline = next(
        (w for w in arms.get("placebo_party_dummies", [])
         if w["window"] == "90_to_31_days"), None)
    if headline:
        lines += [
            "## Key finding: party dummies at 90-31 days",
            "",
            f"- Overall delta: **{fmt(headline['all']['delta'])}** "
            f"({headline['all']['n']} rows)",
            f"- Reform delta: **{fmt(headline['reform']['delta'])}** "
            f"({headline['reform']['n']} rows)",
            f"- Non-Reform delta: **{fmt(headline['non_reform']['delta'])}** "
            f"({headline['non_reform']['n']} rows)",
            "",
        ]

    (OUT_DIR / "reform_decomposition_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
