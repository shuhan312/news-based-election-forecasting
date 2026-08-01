"""The two decompositions section 16 declared: attribution and mechanism.

    PYTHONPATH=src .venv/bin/python -m news_modelling.exploratory_decompositions

Both were pre-declared in the evidence register at the moment the
unblinding was recorded, precisely so that running them later would not
be an invented afterthought. Both are exploratory: they reuse the
already-unblinded outcomes and can promote nothing.

Decomposition 1 - who carried the v2 improvement?
-------------------------------------------------
The v1-to-v2 contrast changed two things at once: fitting cells grew
from 11 to 45, and Reform-era cells entered for the first time. This
decomposition refits the v2 variant WITHOUT its seven Reform cells (38
cells remain), regenerates the 2026 predictions for the twelve
confirmatory specifications, scores them against the observed results,
and lays the deltas beside the full-fit deltas recorded at unblinding.
If the improvements survive without the Reform cells, the enlarged and
diversified election set carried them; if they collapse, the Reform-era
cells did.

Decomposition 2 - is news a tide gauge?
---------------------------------------
The mechanism reading says party-level news features can only correct a
party's election-wide level, never its ward-to-ward variation, because
every candidate of a party receives the same broadcast adjustment. That
is testable arithmetic: split each party's 2026 error into an
election-wide mean shift (the bias a level correction can fix) and the
within-election dispersion around that mean (which a broadcast cannot
touch). If the news models' gains sit almost entirely in the bias term
while dispersion stays put, the tide-gauge reading is confirmed as a
description of what happened.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.blinded_2026_predictions import (
    predict_specification,
    sanitise_holdout_rows,
)
from news_modelling.blinded_2026_predictions_v2 import (
    V2_VARIANT,
    _fit_specification,
    aggregate_v2_residuals,
)
from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
)
from news_modelling.stage1_bundle import load_stage1_bundle
from news_modelling.unblind_2026 import CONFIRMATORY, load_observed

FEATURES = Path("news_features/news_feature_table_v2.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")
V2_PREDICTIONS = Path(
    "news_features/blinded_2026_predictions_v2/blinded_predictions.csv")
OUTPUT_DIR = Path("news_features/exploratory_decompositions_v1")

STATUS = ("EXPLORATORY, post-unblinding, pre-declared in register section "
          "16. Nothing here joins the confirmatory verdict.")


def confirmatory_windows(audit: dict) -> list[tuple[str, str, list[str]]]:
    """(analysis, window, columns) for the twelve confirmatory cells."""

    out = []
    for analysis, spec in audit["frozen_feature_sets"].items():
        if analysis not in CONFIRMATORY["v2"]["analyses"]:
            continue
        for window in audit["feature_table"]["windows"]:
            out.append((analysis, window, list(spec["columns"])))
    return out


def _score(rows: list[dict], observed: dict) -> dict:
    """Supported-row MAE for the news and recalibrated predictions."""

    news, recal = [], []
    for row in rows:
        if row["party_key"] is None:
            continue
        actual = observed[row["candidate_contest_id"]]["observed_vote_share"]
        news.append(abs(row["news_enhanced_prediction"] - actual))
        recal.append(abs(row["recalibrated_prediction"] - actual))
    return {
        "news_mae": float(np.mean(news)),
        "recalibrated_mae": float(np.mean(recal)),
        "news_vs_recalibrated": float(np.mean(recal) - np.mean(news)),
    }


def decomposition_one() -> dict:
    """Refit without Reform cells; compare 2026 deltas to the full fit."""

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    observed = load_observed()
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])

    full_cells = aggregate_v2_residuals(
        [dict(row) for row in bundle.out_of_fold])
    no_reform = [c for c in full_cells if c["party_key"] != "reform_uk"]

    # The full-fit reference deltas come from the unblinding record, not a
    # recomputation, so this table can never drift from section 16.
    unblinding = json.loads(UNBLINDING.read_text(encoding="utf-8"))
    full_delta = {
        (e["analysis"], e["period"]):
            e["metrics"]["all_supported_parties"]["news_vs_recalibrated_mae"]
        for e in unblinding["files"]["v2"] if e["family"] == "confirmatory"
    }

    rows = []
    survived = collapsed = 0
    for analysis, window, columns in confirmatory_windows(audit):
        model, _record = _fit_specification(
            no_reform, feature_index, period=window, feature_columns=columns)
        predictions, _clipped = predict_specification(
            blinded, feature_index, model,
            period=window, feature_columns=columns)
        scores = _score(predictions, observed)
        reference = full_delta[(analysis, window)]
        entry = {
            "analysis": analysis, "window": window,
            "full_fit_delta": round(reference, 4),
            "no_reform_delta": round(scores["news_vs_recalibrated"], 4),
        }
        if reference > 0:
            if scores["news_vs_recalibrated"] > 0:
                survived += 1
                entry["verdict"] = "improvement survives without Reform cells"
            else:
                collapsed += 1
                entry["verdict"] = "improvement collapses without Reform cells"
        else:
            entry["verdict"] = "no full-fit improvement to attribute"
        rows.append(entry)

    return {
        "fitting_cells": {"full": len(full_cells),
                          "without_reform": len(no_reform)},
        "specifications": rows,
        "improvements_survived": survived,
        "improvements_collapsed": collapsed,
    }


def _split_errors(pairs: list[tuple[float, float]]) -> dict:
    """Bias (mean signed error) and dispersion (MAE after removing it)."""

    errors = np.array([pred - obs for pred, obs in pairs])
    bias = float(np.mean(errors))
    return {
        "rows": len(pairs),
        "abs_bias": round(abs(bias), 4),
        "signed_bias": round(bias, 4),
        "dispersion_mae": round(float(np.mean(np.abs(errors - bias))), 4),
        "total_mae": round(float(np.mean(np.abs(errors))), 4),
    }


def _confirmatory_blocks(observed: dict) -> dict:
    """(analysis, window) -> party -> [(prediction, observed)] pairs.

    One reading of the frozen v2 prediction file serves both mechanism
    decompositions: per-party lists for the news predictions and, under
    a ``baseline|`` prefix, the same lists for the baseline predictions.
    """

    blocks: dict[tuple, dict[str, list]] = defaultdict(
        lambda: defaultdict(list))
    with V2_PREDICTIONS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["fit_variant"] != V2_VARIANT:
                continue
            if row["period_role"] != "confirmed_window":
                continue
            if row["analysis"] not in CONFIRMATORY["v2"]["analyses"]:
                continue
            if row["included_in_reported_metrics"] != "True":
                continue
            actual = observed[row["candidate_contest_id"]]
            key = (row["analysis"], row["period"])
            blocks[key][row["party_key"]].append(
                (float(row["news_enhanced_prediction"]),
                 actual["observed_vote_share"]))
            blocks[key]["all"].append(
                (float(row["news_enhanced_prediction"]),
                 actual["observed_vote_share"]))
            blocks[key]["baseline|" + row["party_key"]].append(
                (float(row["baseline_prediction"]),
                 actual["observed_vote_share"]))
            blocks[key]["baseline|all"].append(
                (float(row["baseline_prediction"]),
                 actual["observed_vote_share"]))
    return blocks


def decomposition_two() -> dict:
    """Split each party's 2026 error into mean shift and dispersion.

    For a set of predictions and a party: bias is the election-wide mean
    signed error; dispersion is the MAE that remains after subtracting
    that bias from every error. A broadcast party-level adjustment can
    only move the bias term.
    """

    observed = load_observed()
    split = _split_errors
    blocks = _confirmatory_blocks(observed)

    per_spec = []
    for (analysis, window), parties in sorted(blocks.items()):
        news_all = split(parties["all"])
        base_all = split(parties["baseline|all"])
        per_spec.append({
            "analysis": analysis, "window": window,
            "baseline": base_all, "news": news_all,
            "bias_change": round(news_all["abs_bias"] - base_all["abs_bias"], 4),
            "dispersion_change": round(
                news_all["dispersion_mae"] - base_all["dispersion_mae"], 4),
        })

    return {"per_specification": per_spec}


def decomposition_two_per_party() -> dict:
    """The sharper test the pooled decomposition declared: per-party bias.

    Pooled over all parties, contest normalisation pins the bias term
    near zero, so a party-level tide-gauge correction is invisible in
    the pooled bias column. Split BY party the pinning disappears: each
    party's bias is its election-wide mean signed error, exactly the
    quantity a broadcast party-level adjustment can move, and its
    dispersion is the ward-to-ward variation such an adjustment cannot
    touch. The tide-gauge reading therefore predicts: news moves the
    per-party bias terms and leaves per-party dispersion nearly alone.
    For the central party the baseline's Reform bias is the -1.4-point
    under-prediction the annex recorded (9.3 predicted against 10.7
    observed); this table shows what each frozen specification did to
    it.
    """

    observed = load_observed()
    blocks = _confirmatory_blocks(observed)

    per_spec = []
    for (analysis, window), parties in sorted(blocks.items()):
        party_rows = {}
        for party in sorted(p for p in parties
                            if p != "all" and not p.startswith("baseline|")):
            news = _split_errors(parties[party])
            base = _split_errors(parties["baseline|" + party])
            party_rows[party] = {
                "baseline": base, "news": news,
                "abs_bias_change": round(
                    news["abs_bias"] - base["abs_bias"], 4),
                "dispersion_change": round(
                    news["dispersion_mae"] - base["dispersion_mae"], 4),
            }
        per_spec.append({"analysis": analysis, "window": window,
                         "parties": party_rows})
    return {"per_specification": per_spec}


def main() -> None:
    results = {
        "status": STATUS,
        "attribution": decomposition_one(),
        "mechanism": decomposition_two(),
        "mechanism_per_party": decomposition_two_per_party(),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "decomposition_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")

    attribution = results["attribution"]
    lines = [
        "# The two pre-declared decompositions", "", f"**{STATUS}**", "",
        "## 1. Attribution: refit without the seven Reform cells", "",
        f"Fitting cells {attribution['fitting_cells']['full']} -> "
        f"{attribution['fitting_cells']['without_reform']}.", "",
        "| analysis | window | full-fit delta | no-Reform delta | verdict |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in attribution["specifications"]:
        lines.append(
            f"| {row['analysis']} | {row['window']} | "
            f"{row['full_fit_delta']:+.4f} | {row['no_reform_delta']:+.4f} | "
            f"{row['verdict']} |")
    lines += [
        "",
        f"Of the full fit's positive deltas: "
        f"**{attribution['improvements_survived']} survive** without Reform "
        f"cells, **{attribution['improvements_collapsed']} collapse**.", "",
        "## 2. Mechanism: bias against dispersion", "",
        "| analysis | window | baseline bias / dispersion | "
        "news bias / dispersion | bias change | dispersion change |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for row in results["mechanism"]["per_specification"]:
        lines.append(
            f"| {row['analysis']} | {row['window']} | "
            f"{row['baseline']['abs_bias']:.3f} / "
            f"{row['baseline']['dispersion_mae']:.3f} | "
            f"{row['news']['abs_bias']:.3f} / "
            f"{row['news']['dispersion_mae']:.3f} | "
            f"{row['bias_change']:+.4f} | {row['dispersion_change']:+.4f} |")
    lines += [
        "",
        "Reading this table honestly requires one arithmetic fact: the "
        "pooled bias is pinned near zero by contest normalisation (every "
        "contest's shares sum to 100, so pooled over-predictions and "
        "under-predictions largely cancel). A party-level tide-gauge "
        "correction therefore does NOT appear in the pooled bias column - "
        "it appears as pooled dispersion, because shifting parties' "
        "relative levels re-arranges errors across candidates. The "
        "observed pattern - dispersion falls in exactly the mid-range "
        "windows where MAE improved (90-31 and 30-15 days) and rises where "
        "MAE worsened (180-91 days) - is consistent with the tide-gauge "
        "reading in that pooled form. The sharper per-party test follows.",
        "",
        "## 2b. Per-party bias against dispersion (the declared refinement)",
        "",
        "Split by party the normalisation pinning disappears: each party's",
        "bias is the election-wide level error a broadcast adjustment CAN",
        "move, and its dispersion is the ward geography it cannot. Reform,",
        "the central party, across all twelve specifications (signed bias:",
        "positive = over-predicted):",
        "",
        "| analysis | window | bias base -> news | dispersion base -> news |",
        "| --- | --- | --- | --- |",
    ]
    per_party = results["mechanism_per_party"]["per_specification"]
    for spec in per_party:
        reform = spec["parties"]["reform_uk"]
        lines.append(
            f"| {spec['analysis']} | {spec['window']} | "
            f"{reform['baseline']['signed_bias']:+.3f} -> "
            f"{reform['news']['signed_bias']:+.3f} | "
            f"{reform['baseline']['dispersion_mae']:.3f} -> "
            f"{reform['news']['dispersion_mae']:.3f} |")
    lines += [
        "",
        "All parties in the headline 90-31-day window (change from the "
        "baseline; negative = the news model reduced that error "
        "component):",
        "",
        "| party | combined d-abs-bias | combined d-dispersion | "
        "national d-abs-bias | national d-dispersion |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    headline = {
        spec["analysis"]: spec["parties"] for spec in per_party
        if spec["window"] == "90_to_31_days"
    }
    for party in sorted(headline["combined_exploratory"]):
        combined = headline["combined_exploratory"][party]
        national = headline["national_exploratory"][party]
        lines.append(
            f"| {party} | {combined['abs_bias_change']:+.3f} | "
            f"{combined['dispersion_change']:+.3f} | "
            f"{national['abs_bias_change']:+.3f} | "
            f"{national['dispersion_change']:+.3f} |")
    # The summary sentence is computed from the numbers above rather
    # than written by hand, so the file cannot assert a pattern its own
    # tables contradict.
    combined_specs = headline["combined_exploratory"]
    bias_moved = sum(1 for p in combined_specs.values()
                     if abs(p["abs_bias_change"]) > 0.05)
    disp_moved = sum(1 for p in combined_specs.values()
                     if abs(p["dispersion_change"]) > 0.05)
    lines += [
        "",
        f"In the combined 90-31-day specification, {bias_moved} of "
        f"{len(combined_specs)} parties saw their level error move by "
        f"more than 0.05 points while {disp_moved} saw their ward-level "
        "dispersion move by that much - the tide-gauge reading predicts "
        "the first number to be the larger one.",
        "",
    ]
    (OUTPUT_DIR / "decomposition_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
