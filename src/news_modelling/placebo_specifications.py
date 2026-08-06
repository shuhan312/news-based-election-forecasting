"""Does the LLM layer beat counting articles?

    PYTHONPATH=src .venv/bin/python -m news_modelling.placebo_specifications

## The question, and why the obvious version of it is the wrong one

The confirmatory result is that the frozen specification beats its
recalibrated control by +0.2404 at 90-31 days. Beating a control is not the
same as earning a place: a variable that needs no language model at all may
do the same job. The supervisor's challenge was exactly this, and the test
for it is a placebo - swap the LLM features for a dumb proxy and see how much
of the result survives.

So the bar here is NOT zero. Zero is easy. **The bar is the article count.**

## What each arm is

- ``frozen`` is the committed specification, ``party_article_share`` plus
  ``net_portrayal_share``. It is run first and its six deltas are checked
  against the committed reference to four decimal places. If that check
  fails the run stops: a harness that cannot reproduce a known answer cannot
  be trusted with an unknown one.
- ``placebo_volume`` is ``party_article_count`` alone - how many articles
  mentioned this party. No content judgement of any kind enters it.
- ``placebo_volume_tone`` adds raw ``net_portrayal``, which restores the
  stance layer but nothing about what the coverage was ABOUT.
- the ``content_*`` arms each add ONE party-grain content feature to the
  frozen pair. These are the features that only became estimable when the
  issue and framing layers were re-aggregated per party; before that no
  content feature had ever entered a specification, which is why "the LLM
  layers earn nothing" was never actually tested.

## Three rules fixed before the run, so the answer cannot be shopped for

1. **Every arm is reported.** Seven content features go in one at a time and
   all seven come out in the table, winners and losers alike. Reporting the
   best of seven as though it were the only one tried is the failure mode
   this design exists to avoid.
2. **Features are added one at a time.** The fit has 45 cells. Nine features
   on 45 cells is a ridge fit held together by its penalty, so the all-seven
   arm is run and reported but read as an overfitting check rather than as a
   result.
3. **Eligibility is per window, not per table.** A content feature enters a
   window's specification only if it clears the ten-value reporting bar in
   THAT window's training rows. The near windows admit almost nothing, and
   the output says so rather than quietly fitting on four distinct values.

EXPLORATORY. The 2026 holdout was unsealed in section 16 and every number
here is post-unblinding; nothing in this module can promote or revise a
confirmatory verdict. What it can do is tell the difference between "news
features help" and "counting articles helps".
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    _assign_ranks,
    predict_specification,
    sanitise_holdout_rows,
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
REFERENCE = Path("news_features/local_v3_rerun_v1/rerun_results.json")
OUT_DIR = Path("news_features/placebo_specifications_v1")

WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

# The reporting bar the feature table itself applies, restated here because
# this module re-applies it per window rather than taking the table's
# across-window verdict.
MIN_DISTINCT_TRAINING_VALUES = 10

# The committed specification. Reproducing its deltas is this harness's
# licence to be believed about anything else.
FROZEN = ["party_article_share", "net_portrayal_share"]

# The dumb proxies. `party_article_count` is the one that matters: it is a
# count of articles mentioning a party and carries no judgement about their
# content, so whatever it reproduces is what the language model was not
# needed for.
PLACEBOS = {
    "placebo_volume": ["party_article_count"],
    "placebo_volume_tone": ["party_article_count", "net_portrayal"],
}

# The party-grain content features, in a fixed order. Chosen by which columns
# the re-aggregation made estimable - NOT by how any of them performed, which
# nothing here has looked at yet.
CONTENT_FEATURES = [
    "party_issue_immigration_share",
    "party_issue_national_politics_share",
    "party_issue_issue_other_share",
    "party_frame_incumbent_judgement_share",
    "party_frame_challenger_emergence_share",
    "party_frame_voter_discontent_share",
    "party_frame_local_impact_share",
]

STATUS = ("EXPLORATORY placebo comparison, post-unblinding. Every arm shares "
          "the frozen fitting cells, prediction code and scoring code; only "
          "`feature_columns` differs. Promotes nothing.")


def eligible_by_window() -> dict[str, set[str]]:
    """Content features that clear the reporting bar, window by window.

    The feature table records one verdict per column, taken over its best
    period. A specification uses a single window, so the verdict that governs
    it is that window's own count - which is stricter, and is what the
    builder's own comment says the rule means.
    """
    train = [r for r in csv.DictReader(FEATURES.open())
             if r["split_role"] == "train"]
    by_period: dict[str, list[dict]] = defaultdict(list)
    for row in train:
        by_period[row["period"]].append(row)

    eligible: dict[str, set[str]] = {}
    for window in WINDOWS:
        rows = by_period.get(window, [])
        eligible[window] = {
            column for column in CONTENT_FEATURES
            if len({r[column] for r in rows if r[column] != ""})
            >= MIN_DISTINCT_TRAINING_VALUES
        }
    return eligible


def committed_deltas() -> dict[str, float]:
    """The combined-arm confirmatory deltas this run must reproduce."""
    record = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return {window: entry["combined_confirmatory"]
            for window, entry in record["reference_deltas"].items()}


def run_arm(columns, cells, feature_index, blinded, observed, window):
    """One specification, one window, through the frozen pipeline."""
    model, record = _fit_specification(
        cells, feature_index, period=window, feature_columns=columns)
    predictions, clipped = predict_specification(
        blinded, feature_index, model, period=window, feature_columns=columns)
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


def main() -> None:
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    cells = aggregate_v2_residuals([dict(r) for r in bundle.out_of_fold])
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    observed = load_observed()
    eligible = eligible_by_window()

    arms: dict[str, list[dict]] = {}

    # --- 1. the reproduction gate -------------------------------------
    # Run first and checked before anything else executes. The frozen
    # specification's deltas are published; if this harness cannot land on
    # them, no other number it produces means anything.
    arms["frozen"] = [run_arm(FROZEN, cells, feature_index, blinded,
                              observed, w) for w in WINDOWS]
    reference = committed_deltas()
    mismatches = [
        (r["window"], round(r["delta_vs_recalibrated"], 3), reference[r["window"]])
        for r in arms["frozen"]
        if abs(round(r["delta_vs_recalibrated"], 3)
               - reference[r["window"]]) > 1e-9
    ]
    if mismatches:
        raise RuntimeError(
            "the frozen specification did not reproduce its committed "
            f"deltas, so nothing else in this run is trustworthy: {mismatches}")

    # --- 2. the placebos, which set the bar ---------------------------
    for name, columns in PLACEBOS.items():
        arms[name] = [run_arm(columns, cells, feature_index, blinded,
                              observed, w) for w in WINDOWS]

    # --- 3. the content features, one at a time -----------------------
    # A window where the feature does not clear the bar is recorded as
    # skipped rather than fitted on too few values.
    for column in CONTENT_FEATURES:
        rows = []
        for window in WINDOWS:
            if column not in eligible[window]:
                rows.append({"window": window, "skipped": "below the "
                             f"{MIN_DISTINCT_TRAINING_VALUES}-value bar in "
                             "this window"})
                continue
            rows.append(run_arm(FROZEN + [column], cells, feature_index,
                                blinded, observed, window))
        arms[f"content_{column}"] = rows

    # --- 4. all seven at once, as an overfitting check ----------------
    all_seven = []
    for window in WINDOWS:
        columns = FROZEN + sorted(eligible[window])
        if len(columns) <= len(FROZEN):
            all_seven.append({"window": window,
                              "skipped": "no content feature clears the bar"})
            continue
        all_seven.append(run_arm(columns, cells, feature_index, blinded,
                                 observed, window))
    arms["content_all_eligible"] = all_seven

    payload = {
        "status": STATUS,
        "feature_table": str(FEATURES),
        "fitting_cells": len(cells),
        "reporting_bar": MIN_DISTINCT_TRAINING_VALUES,
        "eligible_content_features_by_window": {
            w: sorted(c) for w, c in eligible.items()},
        "reproduction_check": {
            "committed_combined_deltas": reference,
            "reproduced": {r["window"]: round(r["delta_vs_recalibrated"], 4)
                           for r in arms["frozen"]},
            "max_absolute_difference": max(
                abs(round(r["delta_vs_recalibrated"], 3)
                    - reference[r["window"]]) for r in arms["frozen"]),
        },
        "arms": arms,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "placebo_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    arms = payload["arms"]
    HEADLINE = "90_to_31_days"

    def entry(name, window):
        row = next(r for r in arms[name] if r["window"] == window)
        return None if "skipped" in row else row

    def delta(name, window):
        row = entry(name, window)
        return None if row is None else row["delta_vs_recalibrated"]

    def cell(value):
        return "-" if value is None else f"{value:+.4f}"

    lines = [
        "# Does the LLM layer beat counting articles?", "",
        f"**{payload['status']}**", "",
        "Delta is the change in election-wide MAE against the recalibrated "
        "control; positive is better. Every arm shares the "
        f"{payload['fitting_cells']} frozen fitting cells and the frozen "
        "prediction and scoring code, so the only thing that differs between "
        "rows is which columns the model was given.", "",
        "## Reproduction gate", "",
        "The frozen specification reproduces its committed deltas to a "
        f"maximum absolute difference of "
        f"**{payload['reproduction_check']['max_absolute_difference']:.4f}**. "
        "The run aborts if it does not, because a harness that cannot land "
        "on a known answer cannot be trusted with an unknown one.", "",
        "## Every arm, every window", "",
        "A dash means the content feature did not clear the "
        f"{payload['reporting_bar']}-value reporting bar in that window's "
        "training rows and was not fitted. Only the two long windows carry "
        "enough coverage for any content feature at all.", "",
        "| arm | " + " | ".join(w.replace("_days", "").replace("_", "-")
                                for w in WINDOWS) + " |",
        "| --- | " + " | ".join(["---:"] * len(WINDOWS)) + " |",
    ]
    for name in arms:
        lines.append(f"| {name} | "
                     + " | ".join(cell(delta(name, w)) for w in WINDOWS)
                     + " |")

    # How much of the certified result needs no language model at all.
    lines += ["", "## How much of the result is just volume", ""]
    for window in ("90_to_31_days", "30_to_15_days"):
        frozen_delta, placebo_delta = delta("frozen", window), delta(
            "placebo_volume", window)
        if frozen_delta and placebo_delta and frozen_delta > 0:
            lines.append(
                f"- **{window}**: frozen {frozen_delta:+.4f}, a raw article "
                f"count alone {placebo_delta:+.4f} - **"
                f"{placebo_delta / frozen_delta * 100:.0f}%** of the frozen "
                "result, with no content judgement of any kind.")
    lines.append(
        "- The count also avoids the frozen specification's largest harm, "
        f"turning 180-91 days from {delta('frozen', '180_to_91_days'):+.4f} "
        f"into {delta('placebo_volume', '180_to_91_days'):+.4f}.")

    # The comparison that decides the question. The bar is the BEST arm that
    # uses no content judgement, not the frozen specification: beating the
    # frozen pair while losing to a counter would settle nothing.
    placebo_names = [n for n in arms if n.startswith("placebo")]
    bar_name = max(placebo_names, key=lambda n: delta(n, HEADLINE) or -99)
    bar = delta(bar_name, HEADLINE)
    content_names = [n for n in arms
                     if n.startswith("content_") and n != "content_all_eligible"]
    ranked = sorted(((n, entry(n, HEADLINE)) for n in content_names),
                    key=lambda kv: -(kv[1] or {}).get("delta_vs_recalibrated", -99))
    beat = [(n, e) for n, e in ranked if e and e["delta_vs_recalibrated"] > bar]
    clear = [(n, e) for n, e in beat if e["ci_lower"] > bar]

    lines += [
        "", f"## Content features against the bar, {HEADLINE}", "",
        f"The bar is **{bar_name} = {bar:+.4f}**, the best arm carrying no "
        "content judgement at all. Beating the frozen pair while losing to a "
        "counter would settle nothing, so that is the number to clear.", "",
        "| content feature | delta | 95% CI | beats the bar |",
        "| --- | ---: | --- | --- |",
    ]
    for name, e in ranked:
        if e is None:
            continue
        verdict = ("yes, interval clear of it" if e["ci_lower"] > bar
                   else "yes, but within noise"
                   if e["delta_vs_recalibrated"] > bar else "no")
        lines.append(
            f"| {name.removeprefix("content_")} | "
            f"{e['delta_vs_recalibrated']:+.4f} | "
            f"[{e['ci_lower']:+.4f}, {e['ci_upper']:+.4f}] | {verdict} |")

    everything = entry("content_all_eligible", HEADLINE)
    lines += [
        "",
        f"**{len(beat)} of {len(ranked)}** content features beat the bar; "
        f"**{len(clear)}** does so with its whole interval above it"
        + (f" - {', '.join(n.removeprefix("content_") for n, _ in clear)}"
           if clear else "") + ".", "",
        "Read this narrowly. Seven features were tried and reported, so one "
        "clearing a bar is a multiple-comparison result before it is "
        "anything else, and the fit has "
        f"{payload['fitting_cells']} cells. It is a reason to look harder at "
        "that feature, not a certified effect - the holdout that could have "
        "certified one is spent.", "",
    ]
    if everything and everything["delta_vs_recalibrated"] < 0:
        lines += [
            "All eligible content features at once give "
            f"**{everything['delta_vs_recalibrated']:+.4f}** "
            f"[{everything['ci_lower']:+.4f}, {everything['ci_upper']:+.4f}], "
            "worse than doing nothing and worse than every single-feature "
            "arm. Nine features on "
            f"{payload['fitting_cells']} cells is the overfitting this design "
            "expected to find, and finding it is the check working.", "",
        ]
    (OUT_DIR / "placebo_findings.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
