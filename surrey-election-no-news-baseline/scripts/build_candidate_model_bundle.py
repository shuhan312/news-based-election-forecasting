"""Run Architecture A over every split and write the Stage 1 model bundle.

Produces the files the brief names, into
``surrey-election-no-news-baseline/outputs/model_bundle_v1/``:

    model.pkl                     preprocessor.pkl
    architecture.json             feature_schema.json
    feature_dictionary.csv        training_rows.csv
    out_of_fold_predictions.csv   holdout_predictions.csv
    metrics.json                  reform_metrics.json
    fold_summary.csv

``leakage_audit.csv`` and ``split_manifest.csv`` are produced by
``build_candidate_split_and_leakage.py`` and copied in, so there is exactly
one implementation of each.

Out-of-fold predictions
-----------------------
The brief: "The model bundle must include out-of-fold baseline predictions for
every eligible historical row. These will be required by the second-stage news
model." Prompt 2 then requires the news layer to train on those rather than on
in-sample fitted values, because a residual computed against a prediction the
model has already seen the answer to is not a residual.

Out-of-fold coverage comes from the rolling-origin folds, which test one
polling day at a time. Two groups of rows can have no out-of-fold prediction,
and both are recorded rather than quietly missing:

* the first polling day in the release, which has no earlier election to
  train on - the study-start boundary;
* everything on or after 7 May 2026, which is the untouched holdout and is
  predicted by the separate holdout fit instead.

Usage (from the IRP repository root):

    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
      surrey-election-no-news-baseline/scripts/build_candidate_model_bundle.py
"""

from __future__ import annotations

import csv
import json
import pickle
import platform
from datetime import date
from pathlib import Path

import numpy as np

from no_news_baseline.candidate_cohort import is_within_candidate_cohort
from no_news_baseline.candidate_features import (
    CandidateFeatureEncoder,
    target_vector,
)
from no_news_baseline.candidate_leakage_audit import (
    FEATURE_COLUMNS,
    permitted_predictors,
)
from no_news_baseline.candidate_metrics import evaluate, reform_report
from no_news_baseline.candidate_probability_model import (
    MODEL_ID as PROBABILITY_MODEL_ID,
)
from no_news_baseline.candidate_probability_model import (
    LogisticElectionModel,
    fit_and_predict_probability_fold,
    probability_metrics,
    select_logistic_penalty,
)
from no_news_baseline.candidate_share_model import (
    MODEL_ID,
    PENALTY_GRID,
    TARGET_SCALE,
    RidgeShareModel,
    fit_and_predict_fold,
    select_penalty,
    to_relative_share,
)
from no_news_baseline.candidate_splits import (
    NAMED_SPLITS,
    PRIMARY_HOLDOUT,
    ROLLING_ORIGIN,
    SECONDARY_HOLDOUT,
    TEST,
    TRAIN,
    all_splits,
    assign_split,
)
from no_news_baseline.election_dates import parse_election_date

BUNDLE_VERSION = "candidate_model_bundle_v1"

CONTRACT = Path("surrey-election-extractor/outputs/no_news_candidate_contests")
SPLIT_LEAKAGE = Path("surrey-election-no-news-baseline/outputs/candidate_split_leakage")
OUT = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty file: {path}")
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    features = [
        row
        for row in json.loads((CONTRACT / "no_news_candidate_contest_features.json").read_text())["rows"]
        if is_within_candidate_cohort(row)
    ]
    targets = {
        str(row["candidate_contest_id"]): row
        for row in json.loads((CONTRACT / "no_news_candidate_contest_targets.json").read_text())["rows"]
    }
    by_id = {str(row["candidate_contest_id"]): row for row in features}
    splits = all_splits(features)

    # --- run every split --------------------------------------------------
    # Two models per fold on identical rows: the share model (Architecture A)
    # and the probability-of-election model. Fitting them on the same splits
    # means a share metric and a Brier score always describe the same fold.
    fold_results = []
    probability_results = []
    for split in splits:
        assignment = assign_split(features, split)
        train_rows = [row for row in features
                      if assignment[str(row["candidate_contest_id"])] == TRAIN]
        test_rows = [row for row in features
                     if assignment[str(row["candidate_contest_id"])] == TEST]
        if not train_rows or not test_rows:
            continue
        fold_results.append(
            (
                split,
                fit_and_predict_fold(
                    split_id=split.split_id,
                    split_role=split.role,
                    train_rows=train_rows,
                    test_rows=test_rows,
                    targets=targets,
                ),
            )
        )
        probability_results.append(
            (
                split,
                fit_and_predict_probability_fold(
                    split_id=split.split_id,
                    split_role=split.role,
                    train_rows=train_rows,
                    test_rows=test_rows,
                    targets=targets,
                ),
            )
        )

    # --- out-of-fold predictions -----------------------------------------
    # One row per historical candidate row, from the rolling-origin fold in
    # which that row's own polling day was the test set. Each row therefore
    # appears exactly once, predicted by a model that never saw it.
    oof_rows: list[dict] = []
    seen: set[str] = set()
    for split, result in fold_results:
        if split.role != ROLLING_ORIGIN:
            continue
        for record in result.predictions:
            row_id = str(record["candidate_contest_id"])
            if row_id in seen:
                raise ValueError(
                    f"Row {row_id} received two out-of-fold predictions; the "
                    "rolling folds are meant to partition the historical rows."
                )
            seen.add(row_id)
            oof_rows.append(record)

    # Rows deliberately without an out-of-fold prediction, with the reason.
    uncovered: list[dict] = []
    for row in features:
        row_id = str(row["candidate_contest_id"])
        if row_id in seen:
            continue
        election_day = parse_election_date(str(row["election_date"])).date()
        uncovered.append(
            {
                "candidate_contest_id": row_id,
                "election_id": row["election_id"],
                "election_date": row["election_date"],
                "reason": (
                    "held_out_primary_or_secondary_holdout"
                    if election_day >= date(2026, 5, 7)
                    else "study_start_no_earlier_election_to_train_on"
                ),
            }
        )

    # --- holdout predictions ---------------------------------------------
    holdout_rows = [
        record
        for split, result in fold_results
        if split.role in {PRIMARY_HOLDOUT, SECONDARY_HOLDOUT}
        for record in result.predictions
    ]

    # --- probability predictions, on the same folds -----------------------
    probability_oof = [
        record
        for split, result in probability_results
        if split.role == ROLLING_ORIGIN
        for record in result.predictions
    ]
    probability_holdout = [
        record
        for split, result in probability_results
        if split.role in {PRIMARY_HOLDOUT, SECONDARY_HOLDOUT}
        for record in result.predictions
    ]

    # --- the fitted model shipped in the bundle ---------------------------
    # Fitted on everything before the primary holdout, which is the model
    # whose holdout predictions are reported. Later folds exist to measure
    # stability, not to produce the shipped artefact.
    primary = next(split for split in NAMED_SPLITS if split.role == PRIMARY_HOLDOUT)
    assignment = assign_split(features, primary)
    final_train = [row for row in features
                   if assignment[str(row["candidate_contest_id"])] == TRAIN]

    penalty = select_penalty(final_train, targets)
    encoder = CandidateFeatureEncoder().fit(final_train)
    design = encoder.transform(final_train)
    y_train = to_relative_share(
        target_vector(final_train, targets),
        [int(row["candidate_count_in_contest"]) for row in final_train],
    )
    model = RidgeShareModel(penalty.l2_penalty).fit(design.matrix, y_train)

    # The probability model shipped alongside it, fitted on the same rows.
    elected_outcomes = {
        str(row["candidate_contest_id"]): targets[str(row["candidate_contest_id"])].get(
            "target_candidate_elected"
        )
        == "Yes"
        for row in features
    }
    probability_penalty = select_logistic_penalty(final_train, elected_outcomes)
    probability_model = LogisticElectionModel(probability_penalty.l2_penalty).fit(
        design.matrix,
        np.array([float(elected_outcomes[str(row["candidate_contest_id"])])
                  for row in final_train]),
    )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model.pkl").write_bytes(pickle.dumps(model))
    (OUT / "preprocessor.pkl").write_bytes(pickle.dumps(encoder))
    (OUT / "probability_model.pkl").write_bytes(pickle.dumps(probability_model))

    # --- metrics ----------------------------------------------------------
    metrics = {
        "bundle_version": BUNDLE_VERSION,
        "model_id": MODEL_ID,
        "out_of_fold": evaluate(oof_rows),
        "primary_holdout": evaluate(
            [record for split, result in fold_results
             if split.role == PRIMARY_HOLDOUT for record in result.predictions]
        ),
        "secondary_holdout": {
            split.split_id: evaluate(result.predictions, with_bootstrap=False)
            for split, result in fold_results
            if split.role == SECONDARY_HOLDOUT
        },
        "by_split": {
            split.split_id: evaluate(result.predictions, with_bootstrap=False)["overall"]
            for split, result in fold_results
        },
        # Brier, log loss and calibration, which the share model cannot
        # produce because it returns no probability.
        "election_probability": {
            "model_id": PROBABILITY_MODEL_ID,
            "out_of_fold": probability_metrics(probability_oof),
            "primary_holdout": probability_metrics(
                [record for split, result in probability_results
                 if split.role == PRIMARY_HOLDOUT for record in result.predictions]
            ),
            "by_split": {
                split.split_id: probability_metrics(result.predictions)
                for split, result in probability_results
            },
        },
    }
    reform = {
        "bundle_version": BUNDLE_VERSION,
        "out_of_fold": reform_report(oof_rows),
        "primary_holdout": reform_report(
            [record for split, result in fold_results
             if split.role == PRIMARY_HOLDOUT for record in result.predictions]
        ),
        # The brief requires the Reform sample size of every fold.
        "reform_rows_by_split": {
            split.split_id: {
                "train": result.train_reform_rows,
                "test": result.test_reform_rows,
                "estimable": bool(result.train_reform_rows),
            }
            for split, result in fold_results
        },
        # Reform-specific probability scoring, kept separate from the pooled
        # figure because 163 of the 174 Reform rows sit in the holdout.
        "election_probability": {
            "out_of_fold": probability_metrics(
                [row for row in probability_oof if row["is_reform_uk"]]
            ),
            "primary_holdout": probability_metrics(
                [row for split, result in probability_results
                 if split.role == PRIMARY_HOLDOUT
                 for row in result.predictions if row["is_reform_uk"]]
            ),
        },
    }

    # --- architecture and schema -----------------------------------------
    architecture = {
        "bundle_version": BUNDLE_VERSION,
        "selected_model_type": "regularised_linear_ridge",
        "model_id": MODEL_ID,
        "architecture_label": "Architecture A (regularised)",
        # Honest: no selection has happened because only one architecture
        # exists. The brief's auto-select requires B and C to be built first.
        "architecture_selection": "not_performed_single_architecture_available",
        "packages": {
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "hyperparameters": {
            "l2_penalty": penalty.l2_penalty,
            "penalty_grid": list(PENALTY_GRID),
            "selection_method": penalty.method,
            "inner_validation_dates": list(penalty.inner_validation_dates),
            "hit_grid_boundary": penalty.hit_grid_boundary,
        },
        "target": "target_candidate_vote_share",
        "target_transformation": TARGET_SCALE,
        "normalisation_method": "within_contest_rescale_to_100_after_clipping_negatives",
        "seat_allocation": "top_n_by_predicted_share_using_known_pre_election_seats",
        "selected_features": list(permitted_predictors(sorted(features[0]))),
        "categorical_features": [
            column
            for column in permitted_predictors(sorted(features[0]))
            if FEATURE_COLUMNS[column][0] == "predictor"
            and column in encoder.schema()["categorical_levels"]
        ],
        "encoded_column_count": len(encoder.column_names),
        "split_method": "date_bounded_chronological_folds_grouped_by_contest",
        "training_date": date.today().isoformat(),
        "random_seed": None,
        "random_seed_note": (
            "Closed-form ridge and a deterministic encoder use no randomness. "
            "The only seed in the pipeline is the evaluation bootstrap, "
            "recorded in metrics.json."
        ),
    }

    # --- write everything -------------------------------------------------
    _write_csv(OUT / "out_of_fold_predictions.csv", oof_rows)
    _write_csv(OUT / "holdout_predictions.csv", holdout_rows)
    _write_csv(OUT / "out_of_fold_election_probabilities.csv", probability_oof)
    _write_csv(OUT / "holdout_election_probabilities.csv", probability_holdout)
    _write_csv(
        OUT / "training_rows.csv",
        [
            {
                "candidate_contest_id": str(row["candidate_contest_id"]),
                "election_id": row["election_id"],
                "election_date": row["election_date"],
                "division_id": row["division_id"],
                "standard_party_name": row["standard_party_name"],
                "is_reform_uk": row["is_reform_uk"],
            }
            for row in final_train
        ],
    )
    _write_csv(
        OUT / "fold_summary.csv",
        [
            {
                "split_id": split.split_id,
                "split_role": split.role,
                "train_rows": result.train_rows,
                "test_rows": result.test_rows,
                "train_reform_rows": result.train_reform_rows,
                "test_reform_rows": result.test_reform_rows,
                "l2_penalty": result.penalty.l2_penalty,
                "penalty_method": result.penalty.method,
                "hit_grid_boundary": result.penalty.hit_grid_boundary,
                "encoded_columns": result.encoded_columns,
            }
            for split, result in fold_results
        ],
    )
    if uncovered:
        _write_csv(OUT / "rows_without_out_of_fold_prediction.csv", uncovered)
    _write_csv(
        OUT / "feature_dictionary.csv",
        [
            {
                "column": column,
                "role": FEATURE_COLUMNS[column][0],
                "source_sheet": FEATURE_COLUMNS[column][1],
                "earliest_availability_event": FEATURE_COLUMNS[column][2],
                "restrictions": FEATURE_COLUMNS[column][3],
                "permission_field": FEATURE_COLUMNS[column][4],
                "definition": FEATURE_COLUMNS[column][5],
                "used_as_predictor": FEATURE_COLUMNS[column][0] == "predictor",
            }
            for column in sorted(FEATURE_COLUMNS)
        ],
    )
    (OUT / "feature_schema.json").write_text(json.dumps(encoder.schema(), indent=2) + "\n")
    (OUT / "architecture.json").write_text(json.dumps(architecture, indent=2) + "\n")
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (OUT / "reform_metrics.json").write_text(json.dumps(reform, indent=2) + "\n")

    # Copy the two files owned by the split/leakage step, if they exist.
    for name in ("leakage_audit.csv", "split_manifest.csv"):
        source = SPLIT_LEAKAGE / name
        if source.exists():
            (OUT / name).write_text(source.read_text())

    # --- console summary --------------------------------------------------
    oof = metrics["out_of_fold"]["overall"]
    hold = metrics["primary_holdout"]["overall"]
    print(f"bundle: {OUT}")
    print(f"out-of-fold rows: {len(oof_rows)}   without OOF: {len(uncovered)}")
    print(f"holdout rows:     {len(holdout_rows)}")
    print()
    print(f"{'':22s} {'rows':>6s} {'MAE':>7s} {'rel':>6s} {'vs equal':>9s} {'winner':>8s}")
    for label, block in (("out-of-fold", oof), ("primary holdout", hold)):
        ref = block["equal_split_reference"]
        print(f"{label:22s} {block['rows']:6d} {block['mae']:7.2f} "
              f"{block['relative_mae']:6.2f} "
              f"{ref['improvement_over_equal_split']:8.1%} "
              f"{block['winner_accuracy']:7.1%}")
    interval = oof.get("mae_contest_bootstrap_95")
    if interval and interval.get("lower") is not None:
        print(f"\nOOF MAE 95% contest bootstrap: "
              f"{interval['lower']:.2f} - {interval['upper']:.2f} "
              f"({interval['contests']} contests)")
    print(f"\nReform OOF rows: {reform['out_of_fold']['reform_uk']['rows']}  "
          f"small-sample warning: {reform['out_of_fold']['small_sample_warning']}")
    print(f"Reform holdout rows: {reform['primary_holdout']['reform_uk']['rows']}  "
          f"MAE {reform['primary_holdout']['reform_uk']['mae']:.2f}")

    print("\nprobability of election (seat-constrained)")
    print(f"{'':22s} {'rows':>6s} {'Brier':>8s} {'base':>8s} {'logloss':>8s} {'slope':>7s} {'ECE':>7s}")
    for label, block in (
        ("out-of-fold", metrics["election_probability"]["out_of_fold"]),
        ("primary holdout", metrics["election_probability"]["primary_holdout"]),
    ):
        if not block.get("rows"):
            continue
        constrained = block["seat_constrained"]
        calibration = constrained["calibration"]
        print(f"{label:22s} {block['rows']:6d} {constrained['brier_score']:8.4f} "
              f"{block['base_rate_reference']['brier_score']:8.4f} "
              f"{constrained['log_loss']:8.4f} "
              f"{calibration['calibration_slope']:7.2f} "
              f"{calibration['expected_calibration_error']:7.4f}")
    reform_probability = reform["election_probability"]["primary_holdout"]
    if reform_probability.get("rows"):
        print(f"{'Reform holdout':22s} {reform_probability['rows']:6d} "
              f"{reform_probability['seat_constrained']['brier_score']:8.4f} "
              f"{reform_probability['base_rate_reference']['brier_score']:8.4f}")


if __name__ == "__main__":
    main()
