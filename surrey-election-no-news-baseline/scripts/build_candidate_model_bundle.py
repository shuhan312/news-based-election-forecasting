"""Run all three architectures, select one, and write the Stage 1 bundle.

Why this script was rewritten
-----------------------------
Its first version fitted Architecture A and shipped it. Once the architecture
comparison existed and selected Architecture B, the bundle was quietly
inconsistent with the model card: ``model.pkl`` held one architecture while
the documentation named another, and ``out_of_fold_predictions.csv`` held the
unselected model's residual baseline. Prompt 2 requires the news layer to
train on Stage 1's out-of-fold predictions, so that inconsistency would have
propagated into every later result. The selected architecture is now decided
here, before anything is written, and everything written is that
architecture's.

Order of operations, which is the point
---------------------------------------
1. Score all three architectures on every split.
2. Select one, on a **development fold**. Reading the holdout to choose an
   architecture spends the thing the holdout exists to protect.
3. Fit the selected architecture on everything before the primary holdout.
4. Export that architecture's out-of-fold and holdout predictions.
5. Write the comparison table, so the two rejected architectures remain
   visible rather than being replaced by their winner.

Usage (from the IRP repository root):

    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
      surrey-election-no-news-baseline/scripts/build_candidate_model_bundle.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import pickle
import platform
import subprocess
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from no_news_baseline.candidate_architecture_selection import (
    COMPLEXITY_ORDER,
    MATERIAL_IMPROVEMENT,
    MAX_ADVERSE_FOLDS,
    MIN_DEVELOPMENT_FOLDS,
    PRIMARY_CRITERION,
    comparison_table,
    score_architecture,
    select_architecture,
)
from no_news_baseline.candidate_boosted_model import (
    BOOSTING_PARAMS,
    fit_and_predict_boosted_fold,
    safe_feature_names,
    select_boosting_rounds,
)
from no_news_baseline.candidate_cohort import group_by_contest, is_within_candidate_cohort
from no_news_baseline.candidate_contestation import (
    build_contestation_records,
    contestation_summary,
)
from no_news_baseline.candidate_features import CandidateFeatureEncoder, target_vector
from no_news_baseline.candidate_historical_strength import (
    assert_no_future_contribution,
    attach_strength_features,
    coverage_report as strength_coverage,
)
from no_news_baseline.candidate_interactions import (
    attach_interactions,
    interaction_coverage,
)
from no_news_baseline.candidate_hierarchical_model import (
    PartialPoolingShareModel,
    fit_and_predict_hierarchical_fold,
    party_column_mask,
    select_hierarchical_penalties,
)
from no_news_baseline.candidate_leakage_audit import FEATURE_COLUMNS, permitted_predictors
from no_news_baseline.candidate_metrics import evaluate, reform_report
from no_news_baseline.candidate_probability_model import (
    LogisticElectionModel,
    fit_and_predict_probability_fold,
    probability_metrics,
    select_logistic_penalty,
)
from no_news_baseline.candidate_share_model import (
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

# Selection pools every development fold rather than reading one. Reading the
# last fold alone decided on three Reform rows, which could not separate the
# architectures; pooling raises it to sixteen row-slots over fourteen distinct
# Reform rows. None of them is the holdout, which is not a development fold.
DECISION_SPLIT_ID = None

ARCHITECTURES = {
    "A_regularised_linear": fit_and_predict_fold,
    "C_partial_pooling": fit_and_predict_hierarchical_fold,
    "B_gradient_boosted_trees": fit_and_predict_boosted_fold,
}

CONTRACT = Path("surrey-election-extractor/outputs/no_news_candidate_contests")
SPLIT_LEAKAGE = Path("surrey-election-no-news-baseline/outputs/candidate_split_leakage")
OUT = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty file: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fit_selected(architecture, train_rows, targets):
    """Fit the selected architecture on the pre-holdout training set.

    Returns the fitted object, the encoder it needs, and a record of how its
    hyperparameters were chosen. Each branch mirrors the fold code exactly, so
    the shipped model is the same model the comparison scored.
    """

    if architecture == "A_regularised_linear":
        encoder = CandidateFeatureEncoder().fit(train_rows)
        design = encoder.transform(train_rows)
        y = to_relative_share(
            target_vector(train_rows, targets),
            [int(r["candidate_count_in_contest"]) for r in train_rows],
        )
        choice = select_penalty(train_rows, targets)
        model = RidgeShareModel(choice.l2_penalty).fit(design.matrix, y)
        return model, encoder, {
            "l2_penalty": choice.l2_penalty, "selection_method": choice.method,
            "inner_validation_dates": list(choice.inner_validation_dates),
            "hit_grid_boundary": choice.hit_grid_boundary,
        }

    if architecture == "C_partial_pooling":
        encoder = CandidateFeatureEncoder().fit(train_rows)
        design = encoder.transform(train_rows)
        y = to_relative_share(
            target_vector(train_rows, targets),
            [int(r["candidate_count_in_contest"]) for r in train_rows],
        )
        choice = select_hierarchical_penalties(train_rows, targets)
        model = PartialPoolingShareModel(
            fixed_penalty=choice.fixed_penalty, party_penalty=choice.party_penalty
        ).fit(design.matrix, y, party_mask=party_column_mask(design.column_names))
        return model, encoder, {
            "fixed_penalty": choice.fixed_penalty,
            "party_penalty": choice.party_penalty,
            "selection_method": choice.method,
            "inner_validation_dates": list(choice.inner_validation_dates),
        }

    if architecture == "B_gradient_boosted_trees":
        import lightgbm

        # Standardisation off, exactly as in the fold code: trees split on
        # order and unscaled columns keep split thresholds readable.
        encoder = CandidateFeatureEncoder(standardise=False).fit(train_rows)
        design = encoder.transform(train_rows)
        y = to_relative_share(
            target_vector(train_rows, targets),
            [int(r["candidate_count_in_contest"]) for r in train_rows],
        )
        choice = select_boosting_rounds(train_rows, targets)
        safe, _ = safe_feature_names(design.column_names)
        booster = lightgbm.train(
            dict(BOOSTING_PARAMS),
            lightgbm.Dataset(design.matrix, label=y, feature_name=list(safe)),
            num_boost_round=choice.num_boost_round,
        )
        return booster, encoder, {
            "num_boost_round": choice.num_boost_round,
            "selection_method": choice.method,
            "inner_validation_dates": list(choice.inner_validation_dates),
            "boosting_params": dict(BOOSTING_PARAMS),
        }

    raise ValueError(f"Unknown architecture: {architecture!r}")


def _data_quality_report(features, targets) -> dict:
    """The machine-readable data-quality report the brief asks for.

    Modelling-side checks only. Source extraction quality is the extractor's
    own audit; what this covers is whether the contract the model consumes is
    internally consistent - identifiers unique, shares in range, contests
    reconciling to 100, and the party counts the brief wants reported by
    election.
    """

    contests = group_by_contest(features)
    share_by_id = {
        str(row["candidate_contest_id"]): row.get("target_candidate_vote_share")
        for row in targets.values()
    }

    out_of_range, unreconciled = [], []
    for key, rows in contests.items():
        shares = [share_by_id.get(str(r["candidate_contest_id"])) for r in rows]
        for row, share in zip(rows, shares):
            if share is not None and not 0 <= float(share) <= 100:
                out_of_range.append(str(row["candidate_contest_id"]))
        if any(s is None for s in shares):
            continue
        total = sum(float(s) for s in shares)
        tolerance = 2.0 + 0.5 * len(shares)
        if not 100 - tolerance <= total <= 100 + tolerance:
            unreconciled.append({"contest": f"{key[0]}|{key[1]}", "sum": total})

    predictors = permitted_predictors(sorted(features[0]))
    missing_by_field = {
        column: sum(1 for row in features if row.get(column) is None)
        for column in predictors
    }
    # The brief asks for missingness by field AND election. Pooling the two
    # hides the pattern that matters here: the 2026 wards are missing history
    # because they were reorganised, not at random.
    missing_by_election: dict[str, dict[str, int]] = defaultdict(dict)
    for row in features:
        election = str(row["election_id"])
        for column in predictors:
            if row.get(column) is None:
                missing_by_election[election][column] = (
                    missing_by_election[election].get(column, 0) + 1
                )
    by_election = defaultdict(lambda: {"rows": 0, "reform_uk": 0, "ukip": 0})
    for row in features:
        entry = by_election[str(row["election_id"])]
        entry["rows"] += 1
        entry["reform_uk"] += int(bool(row.get("is_reform_uk")))
        entry["ukip"] += int(bool(row.get("is_ukip")))

    ids = [str(row["candidate_contest_id"]) for row in features]
    return {
        "rows": len(features),
        "contests": len(contests),
        "elections": len({str(row["election_id"]) for row in features}),
        "duplicate_row_identifiers": len(ids) - len(set(ids)),
        "feature_target_identifier_mismatch": sorted(set(ids) ^ set(targets)),
        "vote_shares_out_of_range": out_of_range,
        "contests_not_reconciling_to_100": unreconciled,
        "missing_values_by_permitted_predictor": dict(sorted(missing_by_field.items())),
        "missing_values_by_election_and_predictor": {
            election: dict(sorted(columns.items()))
            for election, columns in sorted(missing_by_election.items())
        },
        # The brief asks for Reform UK and UKIP counts by election, separately.
        "party_counts_by_election": {k: dict(v) for k, v in sorted(by_election.items())},
        "historical_predictor_availability": dict(
            Counter(str(row["historical_predictor_availability"]) for row in features)
        ),
        "contest_structure": dict(
            Counter(str(row["contest_structure"]) for row in features)
        ),
        "unknown_values_preserved": (
            "Unknown is never converted to No and missing is never converted to "
            "zero; every nullable predictor carries a separate indicator column."
        ),
    }


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

    # Derived county-level history, then the Reform interaction terms that let
    # a linear model read it on a different slope. The date guard runs on the
    # published contract before anything is attached, so a violation stops the
    # build rather than reaching a model.
    assert_no_future_contribution(features, targets)
    contract_rows = list(features)
    features = list(attach_interactions(attach_strength_features(features, targets)))
    splits = all_splits(features)

    # --- 1. score every architecture on every split ----------------------
    fold_predictions: dict[str, dict[str, tuple]] = {name: {} for name in ARCHITECTURES}
    probability_predictions: dict[str, tuple] = {}
    scores = []
    split_by_id = {}

    for split in splits:
        assignment = assign_split(features, split)
        train_rows = [r for r in features if assignment[str(r["candidate_contest_id"])] == TRAIN]
        test_rows = [r for r in features if assignment[str(r["candidate_contest_id"])] == TEST]
        if not train_rows or not test_rows:
            continue
        split_by_id[split.split_id] = split
        for name, runner in ARCHITECTURES.items():
            result = runner(split_id=split.split_id, split_role=split.role,
                            train_rows=train_rows, test_rows=test_rows, targets=targets)
            fold_predictions[name][split.split_id] = result.predictions
            scores.append(score_architecture(
                architecture=name, split_id=split.split_id,
                split_role=split.role, predictions=result.predictions,
            ))
        probability_predictions[split.split_id] = fit_and_predict_probability_fold(
            split_id=split.split_id, split_role=split.role,
            train_rows=train_rows, test_rows=test_rows, targets=targets,
        ).predictions

    # --- 2. select, on a development fold --------------------------------
    outcome = select_architecture(scores, decision_split_id=DECISION_SPLIT_ID)
    print(f"selection basis: {outcome.decision_basis} ({outcome.decision_rows} rows)")
    selected = outcome.selected

    # --- 3. out-of-fold and holdout, from the selected architecture ------
    oof_rows, seen = [], set()
    for split_id, predictions in fold_predictions[selected].items():
        if split_by_id[split_id].role != ROLLING_ORIGIN:
            continue
        for record in predictions:
            row_id = str(record["candidate_contest_id"])
            if row_id in seen:
                raise ValueError(f"Row {row_id} received two out-of-fold predictions.")
            seen.add(row_id)
            oof_rows.append(record)

    holdout_rows = [
        record
        for split_id, predictions in fold_predictions[selected].items()
        if split_by_id[split_id].role in {PRIMARY_HOLDOUT, SECONDARY_HOLDOUT}
        for record in predictions
    ]
    uncovered = [
        {
            "candidate_contest_id": str(row["candidate_contest_id"]),
            "election_id": row["election_id"], "election_date": row["election_date"],
            "reason": (
                "held_out_primary_or_secondary_holdout"
                if parse_election_date(str(row["election_date"])).date() >= date(2026, 5, 7)
                else "study_start_no_earlier_election_to_train_on"
            ),
        }
        for row in features
        if str(row["candidate_contest_id"]) not in seen
    ]

    # --- 4. fit and ship the selected architecture -----------------------
    primary = next(s for s in NAMED_SPLITS if s.role == PRIMARY_HOLDOUT)
    assignment = assign_split(features, primary)
    final_train = [r for r in features if assignment[str(r["candidate_contest_id"])] == TRAIN]
    model, encoder, hyperparameters = _fit_selected(selected, final_train, targets)

    elected_outcomes = {
        str(row["candidate_contest_id"]):
            targets[str(row["candidate_contest_id"])].get("target_candidate_elected") == "Yes"
        for row in features
    }
    probability_penalty = select_logistic_penalty(final_train, elected_outcomes)
    probability_encoder = CandidateFeatureEncoder().fit(final_train)
    probability_model = LogisticElectionModel(probability_penalty.l2_penalty).fit(
        probability_encoder.transform(final_train).matrix,
        np.array([float(elected_outcomes[str(r["candidate_contest_id"])]) for r in final_train]),
    )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model.pkl").write_bytes(pickle.dumps(model))
    (OUT / "preprocessor.pkl").write_bytes(pickle.dumps(encoder))
    (OUT / "probability_model.pkl").write_bytes(pickle.dumps(probability_model))
    (OUT / "probability_preprocessor.pkl").write_bytes(pickle.dumps(probability_encoder))

    # --- 5. metrics, selection record, and the rest ----------------------
    primary_holdout_rows = fold_predictions[selected][primary.split_id]
    metrics = {
        "bundle_version": BUNDLE_VERSION,
        "selected_architecture": selected,
        "out_of_fold": evaluate(oof_rows),
        "primary_holdout": evaluate(primary_holdout_rows),
        "by_split": {
            split_id: evaluate(predictions, with_bootstrap=False)["overall"]
            for split_id, predictions in fold_predictions[selected].items()
        },
        "election_probability": {
            "out_of_fold": probability_metrics([
                r for split_id, preds in probability_predictions.items()
                if split_by_id[split_id].role == ROLLING_ORIGIN for r in preds
            ]),
            "primary_holdout": probability_metrics(probability_predictions[primary.split_id]),
        },
    }
    reform = {
        "bundle_version": BUNDLE_VERSION,
        "selected_architecture": selected,
        "out_of_fold": reform_report(oof_rows),
        "primary_holdout": reform_report(primary_holdout_rows),
        # Every architecture's Reform figures, so the rejected ones stay visible.
        "by_architecture_primary_holdout": {
            name: reform_report(preds[primary.split_id], with_bootstrap=False)["reform_uk"]
            for name, preds in fold_predictions.items()
        },
    }

    contestation = build_contestation_records(features)
    derived_coverage = {
        "county_strength": strength_coverage(contract_rows, targets),
        "reform_interactions": interaction_coverage(features),
    }
    quality = _data_quality_report(features, targets)

    architecture_json = {
        "bundle_version": BUNDLE_VERSION,
        "selected_model_type": selected,
        "architectures_compared": list(COMPLEXITY_ORDER),
        "selection": {
            "decision_split_id": outcome.decision_split_id,
            "decision_basis": outcome.decision_basis,
            # How much evidence the decision rests on. Recorded because the
            # earlier single-fold decision rested on three Reform rows and
            # nothing in the bundle made that visible.
            "decision_rows": outcome.decision_rows,
            "decision_rows_note": (
                "Row-slots pooled across development folds. Two folds test "
                "overlapping 2025 by-elections, so these are not independent "
                "observations; the distinct Reform rows number 14."
            ),
            "decision_split_role": "development_fold",
            "primary_criterion": outcome.primary_criterion,
            "material_improvement_threshold": MATERIAL_IMPROVEMENT,
            "max_adverse_folds": MAX_ADVERSE_FOLDS,
            "min_development_folds": MIN_DEVELOPMENT_FOLDS,
            "reasons": list(outcome.reasons),
            "challenger_reports": list(outcome.challenger_reports),
            "holdout_not_read_for_selection": True,
        },
        "packages": {"numpy": np.__version__, "python": platform.python_version()},
        "hyperparameters": hyperparameters,
        "target": "target_candidate_vote_share",
        "target_transformation": "multiple_of_contest_equal_share",
        "normalisation_method": "within_contest_rescale_to_100_after_clipping_negatives",
        "seat_allocation": "top_n_by_predicted_share_using_known_pre_election_seats",
        "selected_features": list(permitted_predictors(sorted(features[0]))),
        # Read from the fitted encoder rather than re-listed, so this can
        # never disagree with the columns that were actually one-hot encoded.
        "categorical_features": sorted(encoder.schema()["categorical_levels"]),
        "encoded_column_count": len(encoder.column_names),
        "split_method": "date_bounded_chronological_folds_grouped_by_contest",
        "training_date": date.today().isoformat(),
        "random_seed": BOOSTING_PARAMS["seed"] if selected == "B_gradient_boosted_trees" else None,
    }

    training_config = {
        "bundle_version": BUNDLE_VERSION,
        "contract_inputs": [str(CONTRACT / "no_news_candidate_contest_features.json"),
                            str(CONTRACT / "no_news_candidate_contest_targets.json")],
        "decision_split_id": DECISION_SPLIT_ID,
        "architectures": list(ARCHITECTURES),
        "selection_gates": {
            "material_improvement": MATERIAL_IMPROVEMENT,
            "max_adverse_folds": MAX_ADVERSE_FOLDS,
            "min_development_folds": MIN_DEVELOPMENT_FOLDS,
            "primary_criterion": PRIMARY_CRITERION,
        },
        "boosting_params": dict(BOOSTING_PARAMS),
        "training_rows": len(final_train),
        "blinding_status": (
            "reported_holdout_not_blind: holdout metrics were read during "
            "development. No 2026 row entered training, no hyperparameter was "
            "chosen against the holdout, and selection ran on a development "
            "fold. See docs/candidate_model_card.md."
        ),
    }

    _write_csv(OUT / "out_of_fold_predictions.csv", oof_rows)
    _write_csv(OUT / "holdout_predictions.csv", holdout_rows)
    _write_csv(OUT / "architecture_comparison.csv", list(comparison_table(scores)))
    _write_csv(OUT / "contestation_records.csv", [r.as_row() for r in contestation])
    _write_csv(
        OUT / "out_of_fold_election_probabilities.csv",
        [r for split_id, preds in probability_predictions.items()
         if split_by_id[split_id].role == ROLLING_ORIGIN for r in preds],
    )
    _write_csv(
        OUT / "training_rows.csv",
        [{"candidate_contest_id": str(r["candidate_contest_id"]),
          "election_id": r["election_id"], "election_date": r["election_date"],
          "division_id": r["division_id"], "standard_party_name": r["standard_party_name"],
          "is_reform_uk": r["is_reform_uk"]} for r in final_train],
    )
    if uncovered:
        _write_csv(OUT / "rows_without_out_of_fold_prediction.csv", uncovered)
    _write_csv(
        OUT / "feature_dictionary.csv",
        [{"column": c, "role": FEATURE_COLUMNS[c][0], "source_sheet": FEATURE_COLUMNS[c][1],
          "earliest_availability_event": FEATURE_COLUMNS[c][2],
          "restrictions": FEATURE_COLUMNS[c][3], "permission_field": FEATURE_COLUMNS[c][4],
          "definition": FEATURE_COLUMNS[c][5],
          "used_as_predictor": FEATURE_COLUMNS[c][0] == "predictor"}
         for c in sorted(FEATURE_COLUMNS)],
    )

    for name, payload in (
        ("feature_schema.json", encoder.schema()),
        ("architecture.json", architecture_json),
        ("metrics.json", metrics),
        ("reform_metrics.json", reform),
        ("data_quality_report.json", quality),
        ("training_config.yaml", training_config),
        ("contestation_summary.json", contestation_summary(contestation)),
        ("derived_feature_coverage.json", derived_coverage),
    ):
        (OUT / name).write_text(json.dumps(payload, indent=2) + "\n")

    # A lock file rather than the loose requirements list, so a rebuild can be
    # attempted against the exact versions these figures came from.
    frozen = subprocess.run(
        [".venv/bin/python", "-m", "pip", "freeze"],
        capture_output=True, text=True, check=False,
    )
    (OUT / "requirements-lock.txt").write_text(frozen.stdout or "pip freeze unavailable\n")

    for name in ("leakage_audit.csv", "split_manifest.csv"):
        source = SPLIT_LEAKAGE / name
        if source.exists():
            (OUT / name).write_text(source.read_text())

    card = Path("surrey-election-no-news-baseline/docs/candidate_model_card.md")
    if card.exists():
        (OUT / "model_card.md").write_text(card.read_text())

    # A manifest of what was written, with hashes, so a later stage can prove
    # it loaded the same bundle these metrics describe.
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "selected_architecture": selected,
        "generated": date.today().isoformat(),
        "files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(OUT.iterdir())
            if path.is_file() and path.name != "bundle_manifest.json"
        },
    }
    (OUT / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # --- console summary --------------------------------------------------
    print(f"selected architecture: {selected}")
    for reason in outcome.reasons:
        print(f"  • {reason}")
    oof_block = metrics["out_of_fold"]["overall"]
    hold_block = metrics["primary_holdout"]["overall"]
    print(f"\nout-of-fold {len(oof_rows)} rows  MAE {oof_block['mae']:.2f}  "
          f"winner {oof_block['winner_accuracy']:.1%}")
    print(f"holdout     {len(primary_holdout_rows)} rows  MAE {hold_block['mae']:.2f}  "
          f"winner {hold_block['winner_accuracy']:.1%}")
    print(f"rows without OOF: {len(uncovered)}")
    print(f"\nbundle files: {len(manifest['files'])} -> {OUT}")


if __name__ == "__main__":
    main()
