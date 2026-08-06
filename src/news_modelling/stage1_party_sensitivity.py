"""What does the Stage 1 re-run do to the headline?

    PYTHONPATH=src .venv/bin/python -m news_modelling.stage1_party_sensitivity

Supervisor directive (2026-08-05): "What does the Stage 1 re-run do to the
headline?" — asked in the context of the observation that the production
Stage 1 model pools Conservative, Labour, Liberal Democrat and Green into
``party_category = established``, leaving their per-party systematic offsets
in the residual. A news layer fitted on those residuals can absorb the
offsets, making news features look useful when they are actually cleaning
up after a coarse baseline.

## The analytical approach (no model re-training)

Re-training the gradient-boosted-tree model is a separate project. This
module instead performs the minimal analytical test: remove the per-party
mean residual from the fitting cells and adjust the holdout baselines by
the same amount, then re-run the frozen news specification. The result
tells us: if Stage 1 already knew each party's systematic offset (i.e. had
per-party intercepts), how much of the certified +0.2404 would survive?

## Which parties are adjusted

Only the four pooled into ``party_category = established``:
Conservative, Labour, Liberal Democrat, Green. Reform UK and UKIP already
have their own boolean indicators (``is_reform_uk``, ``is_ukip``) in the
production model, so a re-run would not change their treatment. The
``all_six`` variant removes all parties' offsets as a sensitivity check.

Mathematically this is exact for any model that is linear in its party
intercepts. For the GBT model in Stage 1 it is a first-order approximation:
the GBT could in principle learn non-linear party interactions that change
when intercepts are added, but the SHAP values show that `party_category`
and `standard_party_name` together account for a modest share of the
model's variance, so the residual adjustment is a reasonable proxy.

## What the numbers mean

- ``original_delta``: the certified headline, unchanged.
- ``demeaned_delta``: the headline after removing per-party offsets.
- ``absorbed_by_identity``: the difference — the part of the original
  delta that was cleaning up after Stage 1's party pooling.
- ``survival_fraction``: demeaned / original — the share that is genuinely
  election-specific news.

A survival fraction near 1.0 means the news layer was not exploiting party
identity through the residual. A survival fraction near 0.0 means the whole
result was a party-intercept correction.

EXPLORATORY. Post-unblinding.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.blinded_2026_predictions import (
    _assign_ranks,
    _normalise_contests,
    predict_specification,
    sanitise_holdout_rows,
)
from news_modelling.blinded_2026_predictions_v2 import (
    _fit_specification,
    aggregate_v2_residuals,
)
from news_modelling.placebo_specifications import FROZEN, committed_deltas
from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
    party_key,
)
from news_modelling.stage1_bundle import load_stage1_bundle
from news_modelling.unblind_2026 import load_observed, score_specification

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUT_DIR = Path("news_features/stage1_party_sensitivity_v1")

WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

ESTABLISHED = {"conservative", "green", "labour", "liberal_democrat"}

STATUS = (
    "EXPLORATORY Stage 1 party-intercept sensitivity, post-unblinding. "
    "Simulates what happens to the news layer's headline when Stage 1 "
    "absorbs per-party mean residuals."
)


def compute_party_means(cells: list[dict]) -> dict[str, float]:
    """Mean residual per party across all fitting elections.

    Weighted by the number of candidate rows backing each cell, because
    cells with more rows have more precise residual estimates.
    """
    by_party: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for cell in cells:
        by_party[cell["party_key"]].append(
            (cell["mean_residual"], cell["candidate_rows"]))
    means = {}
    for party, pairs in by_party.items():
        total_weight = sum(w for _, w in pairs)
        means[party] = sum(r * w for r, w in pairs) / total_weight
    return means


def demean_cells(cells: list[dict], party_means: dict[str, float]) -> list[dict]:
    """Subtract the per-party mean residual from each fitting cell."""
    return [
        {**cell, "mean_residual": cell["mean_residual"]
                                  - party_means.get(cell["party_key"], 0.0)}
        for cell in cells
    ]


def run_demeaned_arm(
    columns: list[str],
    demeaned_cells: list[dict],
    feature_index: dict,
    blinded: list[dict],
    observed: dict,
    window: str,
    party_means: dict[str, float],
) -> dict:
    """Run one specification with demeaned fitting cells and adjusted baselines.

    The holdout baseline predictions are adjusted upward by the per-party
    mean residual. This simulates what Stage 1 would have predicted if it
    had per-party intercepts: it would have corrected its own systematic
    under/over-prediction for each party.
    """
    model, record = _fit_specification(
        demeaned_cells, feature_index, period=window, feature_columns=columns)

    adjusted_blinded = []
    for row in blinded:
        row = dict(row)
        key = party_key(row.get("standard_party_name"))
        if key is not None and key in party_means:
            row["predicted_vote_share"] = (
                float(row["predicted_vote_share"]) + party_means[key])
        adjusted_blinded.append(row)

    predictions, clipped = predict_specification(
        adjusted_blinded, feature_index, model,
        period=window, feature_columns=columns)
    for row in predictions:
        row["included_in_reported_metrics"] = (
            "True" if row["party_key"] is not None else "False")
    _assign_ranks(predictions, "news_enhanced_prediction",
                  "analysis_number_of_seats")
    metrics = score_specification(predictions, observed, with_bootstrap=True)
    overall = metrics["all_supported_parties"]
    ci = metrics.get("bootstrap_news_vs_recalibrated", {})
    return {
        "window": window,
        "feature_columns": list(columns),
        "training_rows": record["training_rows"],
        "coefficients": record["standardised_coefficients"],
        "clipped_rows": clipped,
        "delta_vs_recalibrated": overall["news_vs_recalibrated_mae"],
        "ci_lower": ci.get("improvement_ci_lower"),
        "ci_upper": ci.get("improvement_ci_upper"),
        "seat_accuracy": metrics["seat_accuracy_news"]["accuracy"],
    }


def _run_variant(label, cells, party_means, feature_index, blinded, observed,
                 original):
    """One demeaning variant: demean cells, adjust baselines, compare."""
    demeaned = demean_cells(cells, party_means)
    results = [
        run_demeaned_arm(FROZEN, demeaned, feature_index, blinded, observed,
                         w, party_means)
        for w in WINDOWS
    ]
    comparisons = []
    for orig, dem in zip(original, results):
        window = orig["window"]
        od = orig["delta_vs_recalibrated"]
        dd = dem["delta_vs_recalibrated"]
        comparisons.append({
            "window": window,
            "original_delta": od,
            "original_ci": [orig.get("ci_lower"), orig.get("ci_upper")],
            "demeaned_delta": dd,
            "demeaned_ci": [dem.get("ci_lower"), dem.get("ci_upper")],
            "absorbed_by_identity": od - dd,
            "survival_fraction": dd / od if od != 0 else None,
            "original_coefficients": orig.get("coefficients"),
            "demeaned_coefficients": dem.get("coefficients"),
        })
    return comparisons


def main() -> None:
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    cells = aggregate_v2_residuals([dict(r) for r in bundle.out_of_fold])
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    observed = load_observed()

    # --- reproduction gate ------------------------------------------------
    from news_modelling.placebo_specifications import run_arm
    original = [run_arm(FROZEN, cells, feature_index, blinded, observed, w)
                for w in WINDOWS]
    reference = committed_deltas()
    mismatches = [
        (r["window"], round(r["delta_vs_recalibrated"], 3), reference[r["window"]])
        for r in original
        if abs(round(r["delta_vs_recalibrated"], 3)
               - reference[r["window"]]) > 1e-9
    ]
    if mismatches:
        raise RuntimeError(
            "the frozen specification did not reproduce its committed "
            f"deltas: {mismatches}")

    # --- per-party mean residuals -----------------------------------------
    all_means = compute_party_means(cells)
    established_means = {k: v for k, v in all_means.items()
                         if k in ESTABLISHED}

    # --- primary variant: only the four established parties ----------------
    established_comparisons = _run_variant(
        "established_only", cells, established_means,
        feature_index, blinded, observed, original)

    # --- sensitivity: all six parties -------------------------------------
    all_six_comparisons = _run_variant(
        "all_six", cells, all_means,
        feature_index, blinded, observed, original)

    payload = {
        "status": STATUS,
        "feature_table": str(FEATURES),
        "fitting_cells": len(cells),
        "party_mean_residuals_all": {k: round(v, 6) for k, v in
                                      sorted(all_means.items())},
        "party_mean_residuals_established": {k: round(v, 6) for k, v in
                                              sorted(established_means.items())},
        "reproduction_check_passed": len(mismatches) == 0,
        "established_only": established_comparisons,
        "all_six": all_six_comparisons,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "stage1_party_sensitivity.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    all_means = payload["party_mean_residuals_all"]
    est_means = payload["party_mean_residuals_established"]

    def fmt(v):
        return f"{v:+.4f}" if v is not None else "-"

    def pct(v):
        return f"{v * 100:.1f}%" if v is not None else "-"

    lines = [
        "# What does the Stage 1 re-run do to the headline?",
        "",
        f"**{payload['status']}**",
        "",
        "## Per-party mean residual from the 45 fitting cells",
        "",
        "| party | mean residual (pp) | adjusted in primary variant? |",
        "| --- | ---: | --- |",
    ]
    for party, mean in sorted(all_means.items()):
        adjusted = "yes" if party in ESTABLISHED else "no (already has own indicator)"
        lines.append(f"| {party} | {mean:+.4f} | {adjusted} |")

    def _comparison_table(comparisons, label):
        out = [
            "",
            f"## {label}",
            "",
            "| window | original | 95% CI | demeaned | 95% CI | survival |",
            "| --- | ---: | --- | ---: | --- | ---: |",
        ]
        for c in comparisons:
            out.append(
                f"| {c['window']} | {fmt(c['original_delta'])} | "
                f"[{fmt(c['original_ci'][0])}, {fmt(c['original_ci'][1])}] | "
                f"{fmt(c['demeaned_delta'])} | "
                f"[{fmt(c['demeaned_ci'][0])}, {fmt(c['demeaned_ci'][1])}] | "
                f"{pct(c['survival_fraction'])} |")
        headline = next(c for c in comparisons
                        if c["window"] == "90_to_31_days")
        out += [
            "",
            f"Headline (90-31 days): **{fmt(headline['original_delta'])}** "
            f"-> **{fmt(headline['demeaned_delta'])}**, survival "
            f"**{pct(headline['survival_fraction'])}**.",
        ]
        return out, headline

    # --- primary: established only ----------------------------------------
    est_lines, est_headline = _comparison_table(
        payload["established_only"],
        "Primary: Con/Lab/LibDem/Green offsets removed "
        "(Reform and UKIP unchanged)")

    # --- sensitivity: all six ---------------------------------------------
    all_lines, all_headline = _comparison_table(
        payload["all_six"],
        "Sensitivity: all six parties' offsets removed")

    lines += est_lines + all_lines

    lines += [
        "",
        "## Coefficient comparison at 90-31 days",
        "",
        "| variant | party_article_share | net_portrayal_share |",
        "| --- | ---: | ---: |",
    ]
    if est_headline.get("original_coefficients"):
        oc = est_headline["original_coefficients"]
        lines.append(
            f"| original | {oc.get('party_article_share', 0):+.4f} | "
            f"{oc.get('net_portrayal_share', 0):+.4f} |")
    if est_headline.get("demeaned_coefficients"):
        dc = est_headline["demeaned_coefficients"]
        lines.append(
            f"| established demeaned | {dc.get('party_article_share', 0):+.4f} | "
            f"{dc.get('net_portrayal_share', 0):+.4f} |")
    if all_headline.get("demeaned_coefficients"):
        dc = all_headline["demeaned_coefficients"]
        lines.append(
            f"| all six demeaned | {dc.get('party_article_share', 0):+.4f} | "
            f"{dc.get('net_portrayal_share', 0):+.4f} |")

    lines.append("")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "stage1_party_sensitivity_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
