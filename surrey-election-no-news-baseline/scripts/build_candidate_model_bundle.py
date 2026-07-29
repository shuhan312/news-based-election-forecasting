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

Everything tunable arrives as a :class:`BaselineConfig`
------------------------------------------------------
Paths, seeds, selection gates, the two county-strength thresholds and the
interaction switches are read from the configuration rather than from module
constants, and the resolved configuration is written into the bundle. A
bundle therefore records what it was built with, not what the defaults
happened to be on the day somebody read the source.

Usage (from the IRP repository root) — prefer the CLI:

    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
      -m no_news_baseline.cli train

Running this file directly still works and uses the default configuration.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import pickle
import platform
import subprocess
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from no_news_baseline.candidate_architecture_selection import (
    comparison_table,
    score_architecture,
    select_architecture,
)
from no_news_baseline.candidate_boosted_model import (
    boosting_params,
    fit_and_predict_boosted_fold,
    safe_feature_names,
    select_boosting_rounds,
)
from no_news_baseline.candidate_cohort import group_by_contest, is_within_candidate_cohort
from no_news_baseline.candidate_data_validation import (
    election_date_validation,
    seat_validation,
)
from no_news_baseline.candidate_evidence_layers import (
    EVIDENCE_LAYERS,
    evidence_layer_report,
)
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
from no_news_baseline.configuration import (
    DEFAULT_CONFIG_PATH,
    BaselineConfig,
    load_config,
)
from no_news_baseline.election_dates import parse_election_date
from no_news_baseline.logging_setup import configure_logging, get_logger

ARCHITECTURES = {
    "A_regularised_linear": fit_and_predict_fold,
    "C_partial_pooling": fit_and_predict_hierarchical_fold,
    "B_gradient_boosted_trees": fit_and_predict_boosted_fold,
}


def _write_csv(path: Path, rows: list[dict], written: set[str] | None = None) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty file: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    if written is not None:
        written.add(path.name)


def _fit_selected(architecture, train_rows, targets, *, boosting_seed=None):
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
        choice = select_boosting_rounds(train_rows, targets, seed=boosting_seed)
        safe, _ = safe_feature_names(design.column_names)
        params = boosting_params(boosting_seed)
        booster = lightgbm.train(
            params,
            lightgbm.Dataset(design.matrix, label=y, feature_name=list(safe)),
            num_boost_round=choice.num_boost_round,
        )
        return booster, encoder, {
            "num_boost_round": choice.num_boost_round,
            "selection_method": choice.method,
            "inner_validation_dates": list(choice.inner_validation_dates),
            "boosting_params": params,
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
        # The brief asks for seat counts and election dates to be validated.
        # Both decide something structural rather than merely descriptive: the
        # seat count decides which candidates are predicted elected, and the
        # date decides which fold a row lands in.
        "seat_validation": seat_validation(features),
        "election_date_validation": election_date_validation(features),
        # "Identify fields whose values are official, supplementary or
        # derived." Reported with the per-row provenance distributions for the
        # two fields that carry their own, because a single label would be a
        # claim about rows it is not true of.
        "evidence_layers": evidence_layer_report(features),
        "unknown_values_preserved": (
            "Unknown is never converted to No and missing is never converted to "
            "zero; every nullable predictor carries a separate indicator column."
        ),
    }


def build_bundle(
    config: BaselineConfig | None = None,
    *,
    logger: logging.Logger | None = None,
) -> dict:
    """Build and write the whole bundle. Returns a short summary of the run.

    ``config`` carries every tunable assumption; passing ``None`` uses the
    code defaults, which is what a bare script invocation does. A summary is
    returned rather than only printed so a caller - the CLI, or a test - can
    assert on the outcome without re-reading the files just written.
    """

    config = config or BaselineConfig.defaults()
    log = logger or get_logger("bundle")
    contract = config.paths.contract_directory
    out = config.paths.output_directory

    log.info("configuration: %s", config.source_path or "code defaults")
    log.info(
        "selection mode: %s | interactions reform=%s ukip=%s | boosting seed %s",
        config.selection.mode,
        config.features.reform_interactions,
        config.features.ukip_interactions,
        config.boosting_seed,
    )

    features = [
        row
        for row in json.loads((contract / "no_news_candidate_contest_features.json").read_text())["rows"]
        if is_within_candidate_cohort(row)
    ]
    targets = {
        str(row["candidate_contest_id"]): row
        for row in json.loads((contract / "no_news_candidate_contest_targets.json").read_text())["rows"]
    }
    log.info("contract: %d cohort rows, %d targets", len(features), len(targets))

    # Derived county-level history, then the Reform interaction terms that let
    # a linear model read it on a different slope. The date guard runs on the
    # published contract before anything is attached, so a violation stops the
    # build rather than reaching a model.
    assert_no_future_contribution(features, targets)
    contract_rows = list(features)
    features = list(attach_strength_features(
        features,
        targets,
        minimum_contests=config.features.county_strength_minimum_contests,
        pooling_window_years=config.features.county_strength_pooling_window_years,
    ))
    if config.features.reform_interactions or config.features.ukip_interactions:
        features = list(attach_interactions(
            features,
            include_reform=config.features.reform_interactions,
            include_ukip=config.features.ukip_interactions,
        ))
    splits = all_splits(features)

    # Only the architectures the configuration asks for. A manual choice is
    # still required to be among them, so this can never leave the shipped
    # architecture unscored.
    architectures = {
        name: runner
        for name, runner in ARCHITECTURES.items()
        if name in config.selection.compared
    }

    # --- 1. score every architecture on every split ----------------------
    fold_predictions: dict[str, dict[str, tuple]] = {name: {} for name in architectures}
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
        for name, runner in architectures.items():
            arguments = dict(split_id=split.split_id, split_role=split.role,
                             train_rows=train_rows, test_rows=test_rows, targets=targets)
            if name == "B_gradient_boosted_trees":
                arguments["seed"] = config.boosting_seed
            result = runner(**arguments)
            fold_predictions[name][split.split_id] = result.predictions
            scores.append(score_architecture(
                architecture=name, split_id=split.split_id,
                split_role=split.role, predictions=result.predictions,
            ))
        probability_predictions[split.split_id] = fit_and_predict_probability_fold(
            split_id=split.split_id, split_role=split.role,
            train_rows=train_rows, test_rows=test_rows, targets=targets,
        ).predictions
        log.debug("scored split %s (%d train, %d test)",
                  split.split_id, len(train_rows), len(test_rows))

    # --- 2. select, on development folds ---------------------------------
    # The gates run whether or not their verdict is used. A manual override
    # that suppressed the comparison would leave no record of what it
    # overrode, which is the opposite of what a manual mode is for.
    outcome = select_architecture(
        scores,
        decision_split_id=config.selection.decision_split_id,
        primary_criterion=config.selection.primary_criterion,
        material_improvement=config.selection.material_improvement,
        max_adverse_folds=config.selection.max_adverse_folds,
        min_development_folds=config.selection.min_development_folds,
    )
    if config.selection.is_automatic:
        selected = outcome.selected
        log.info("automatic selection on %s (%d rows): %s",
                 outcome.decision_basis, outcome.decision_rows, selected)
    else:
        selected = config.selection.mode
        log.warning(
            "manual override: shipping %s; the gates would have selected %s",
            selected, outcome.selected,
        )

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
    model, encoder, hyperparameters = _fit_selected(
        selected, final_train, targets, boosting_seed=config.boosting_seed
    )

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

    out.mkdir(parents=True, exist_ok=True)
    # Every file this run writes. The manifest hashes this set rather than
    # whatever happens to be sitting in the directory, because an output
    # directory is reused across rebuilds and a file left behind by an older
    # version would otherwise be hashed into a manifest as though the current
    # code had produced it - a bundle claiming files a rebuild cannot recreate.
    written: set[str] = set()
    for name, payload in (
        ("model.pkl", model),
        ("preprocessor.pkl", encoder),
        ("probability_model.pkl", probability_model),
        ("probability_preprocessor.pkl", probability_encoder),
    ):
        (out / name).write_bytes(pickle.dumps(payload))
        written.add(name)

    # --- 5. metrics, selection record, and the rest ----------------------
    # One bootstrap setting for every interval in the bundle, so two figures
    # in the same file are never resampled differently.
    resampling = {
        "resamples": config.evaluation.bootstrap_resamples,
        "seed": config.evaluation.bootstrap_seed,
    }
    primary_holdout_rows = fold_predictions[selected][primary.split_id]
    metrics = {
        "bundle_version": config.bundle_version,
        "selected_architecture": selected,
        "out_of_fold": evaluate(oof_rows, **resampling),
        "primary_holdout": evaluate(primary_holdout_rows, **resampling),
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
        "bundle_version": config.bundle_version,
        "selected_architecture": selected,
        "out_of_fold": reform_report(oof_rows, **resampling),
        "primary_holdout": reform_report(primary_holdout_rows, **resampling),
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
        "bundle_version": config.bundle_version,
        "selected_model_type": selected,
        "architectures_compared": list(config.selection.compared),
        "selection": {
            # Whether the gates decided this, or a person did. A bundle whose
            # architecture was overridden must say so on its face, otherwise
            # the reasons below read as the reasons it was shipped.
            "mode": config.selection.mode,
            "selected_automatically": config.selection.is_automatic,
            "gate_verdict": outcome.selected,
            "overridden": not config.selection.is_automatic
            and selected != outcome.selected,
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
            "material_improvement_threshold": config.selection.material_improvement,
            "max_adverse_folds": config.selection.max_adverse_folds,
            "min_development_folds": config.selection.min_development_folds,
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
        # Recorded for every architecture, not only the seeded one: "this
        # architecture has no randomness" is itself a fact worth stating, and
        # an absent key does not say it.
        "random_seed": config.boosting_seed,
        "random_seed_affects_selected_architecture":
            selected == "B_gradient_boosted_trees",
    }

    training_config = {
        "bundle_version": config.bundle_version,
        "contract_inputs": [str(contract / "no_news_candidate_contest_features.json"),
                            str(contract / "no_news_candidate_contest_targets.json")],
        # The whole resolved configuration, so a rebuild does not have to
        # reconstruct it from the flags somebody remembers typing.
        "resolved_configuration": config.as_record(),
        "architectures": list(architectures),
        "boosting_params": boosting_params(config.boosting_seed),
        "training_rows": len(final_train),
        "blinding_status": (
            "reported_holdout_not_blind: holdout metrics were read during "
            "development. No 2026 row entered training, no hyperparameter was "
            "chosen against the holdout, and selection ran on a development "
            "fold. See docs/candidate_model_card.md."
        ),
    }

    _write_csv(out / "out_of_fold_predictions.csv", oof_rows, written)
    _write_csv(out / "holdout_predictions.csv", holdout_rows, written)
    _write_csv(out / "architecture_comparison.csv", list(comparison_table(scores)), written)
    _write_csv(out / "contestation_records.csv", [r.as_row() for r in contestation], written)
    _write_csv(
        out / "out_of_fold_election_probabilities.csv",
        [r for split_id, preds in probability_predictions.items()
         if split_by_id[split_id].role == ROLLING_ORIGIN for r in preds],
        written,
    )
    # Restored: the rewrite dropped this file while still computing the
    # figures behind it, so the holdout's per-candidate probabilities were
    # summarised in metrics.json with no row-level export to check them
    # against.
    _write_csv(
        out / "holdout_election_probabilities.csv",
        [r for split_id, preds in probability_predictions.items()
         if split_by_id[split_id].role in {PRIMARY_HOLDOUT, SECONDARY_HOLDOUT}
         for r in preds],
        written,
    )
    _write_csv(
        out / "training_rows.csv",
        [{"candidate_contest_id": str(r["candidate_contest_id"]),
          "election_id": r["election_id"], "election_date": r["election_date"],
          "division_id": r["division_id"], "standard_party_name": r["standard_party_name"],
          "is_reform_uk": r["is_reform_uk"]} for r in final_train],
        written,
    )
    if uncovered:
        _write_csv(out / "rows_without_out_of_fold_prediction.csv", uncovered, written)
    _write_csv(
        out / "feature_dictionary.csv",
        [{"column": c, "role": FEATURE_COLUMNS[c][0], "source_sheet": FEATURE_COLUMNS[c][1],
          "earliest_availability_event": FEATURE_COLUMNS[c][2],
          "restrictions": FEATURE_COLUMNS[c][3], "permission_field": FEATURE_COLUMNS[c][4],
          "definition": FEATURE_COLUMNS[c][5],
          "used_as_predictor": FEATURE_COLUMNS[c][0] == "predictor",
          # The evidence layer sits beside the leakage verdict rather than
          # replacing it: "may be modelled" and "is an official value" are
          # different facts and a reader needs both.
          "evidence_layer": EVIDENCE_LAYERS[c][0],
          "evidence_layer_reason": EVIDENCE_LAYERS[c][1]}
         for c in sorted(FEATURE_COLUMNS)],
        written,
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
        (out / name).write_text(json.dumps(payload, indent=2) + "\n")
        written.add(name)

    # A lock file rather than the loose requirements list, so a rebuild can be
    # attempted against the exact versions these figures came from.
    frozen = subprocess.run(
        [".venv/bin/python", "-m", "pip", "freeze"],
        capture_output=True, text=True, check=False,
    )
    (out / "requirements-lock.txt").write_text(frozen.stdout or "pip freeze unavailable\n")
    written.add("requirements-lock.txt")

    for name in ("leakage_audit.csv", "split_manifest.csv"):
        source = config.paths.split_leakage_directory / name
        if source.exists():
            (out / name).write_text(source.read_text())
            written.add(name)
        else:
            log.warning("%s not found at %s; the bundle will not contain it", name, source)

    card = Path("surrey-election-no-news-baseline/docs/candidate_model_card.md")
    if card.exists():
        (out / "model_card.md").write_text(card.read_text())
        written.add("model_card.md")

    # A manifest of what was written, with hashes, so a later stage can prove
    # it loaded the same bundle these metrics describe.
    manifest = {
        "bundle_version": config.bundle_version,
        "selected_architecture": selected,
        "generated": date.today().isoformat(),
        "files": {
            name: hashlib.sha256((out / name).read_bytes()).hexdigest()
            for name in sorted(written)
        },
    }
    # Anything else in the directory came from somewhere other than this run.
    # training.log and the manifest itself are expected; the rest are reported
    # so a stale artefact cannot sit in a bundle looking current.
    strays = sorted(
        path.name for path in out.iterdir()
        if path.is_file()
        and path.name not in written
        and path.name not in {"bundle_manifest.json", "training.log"}
    )
    if strays:
        log.warning(
            "%d file(s) in %s were not written by this run and are excluded "
            "from the manifest: %s", len(strays), out, ", ".join(strays),
        )
    manifest["files_not_written_by_this_run"] = strays
    (out / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # --- summary ---------------------------------------------------------
    oof_block = metrics["out_of_fold"]["overall"]
    hold_block = metrics["primary_holdout"]["overall"]
    for reason in outcome.reasons:
        log.info("gate: %s", reason)
    log.info("out-of-fold %d rows  MAE %.2f  winner %.1f%%",
             len(oof_rows), oof_block["mae"], 100 * oof_block["winner_accuracy"])
    log.info("holdout     %d rows  MAE %.2f  winner %.1f%%",
             len(primary_holdout_rows), hold_block["mae"],
             100 * hold_block["winner_accuracy"])
    log.info("rows without out-of-fold prediction: %d", len(uncovered))
    log.info("wrote %d bundle files to %s", len(manifest["files"]), out)

    return {
        "selected_architecture": selected,
        "selected_automatically": config.selection.is_automatic,
        "gate_verdict": outcome.selected,
        "decision_basis": outcome.decision_basis,
        "decision_rows": outcome.decision_rows,
        "out_of_fold_rows": len(oof_rows),
        "out_of_fold_mae": oof_block["mae"],
        "primary_holdout_rows": len(primary_holdout_rows),
        "primary_holdout_mae": hold_block["mae"],
        "bundle_files": len(manifest["files"]),
        "output_directory": str(out),
    }


def main() -> None:
    """Direct invocation: read the default configuration file if it exists."""

    configure_logging()
    path = DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else None
    build_bundle(load_config(path))


if __name__ == "__main__":
    main()
