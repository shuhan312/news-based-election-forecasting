"""Freeze the news layer's blinded 2026 predictions.

The supervisor's design ends in one test: "The most important test is whether
adding news context improves prediction on an election that was not used to
train the model", and it must be blinded — "predictions are saved first and
only then compared to reality".  This module produces that saved-first file.
It is the first news-layer code permitted to open the Stage 1 holdout file,
and it opens it for exactly one purpose: to copy the identity and *predicted*
columns of the 2026 candidate rows.  Every observed column is stripped at
load, and no function in this module computes an error, a metric or a
comparison of any kind.  Unblinding is a separate, later, single event.

Two fitting variants, both frozen here before any 2026 outcome is seen
----------------------------------------------------------------------
**pooled_2017_2021 (primary).**  The supervisor's split is train 2013-2019,
validation 2021, final test 2026.  With validation-based selection complete —
and it selected nothing: 0/18 confirmed-window comparisons improved — the
standard final step is to refit on train plus validation.  Pooling gives the
residual model up to eleven election x party fitting rows instead of five,
and, through 2021, its only Reform UK residual observation.  The choice of
this variant as primary is made now, blind, and recorded; it is not informed
by any 2026 outcome and cannot be revisited after unblinding.

**fit_2017_only (protocol replication).**  Exactly the frozen pre-2026
experiment's fit, applied unchanged to 2026 features.  Kept because the
pre-2026 conclusion was produced under this protocol, so the 2026 test of
that protocol must exist alongside the pooled refit.

Everything else is inherited unchanged from the frozen experiment: the three
frozen feature arms, the twelve periods, the fixed ridge penalty of 1.0, the
party-mean residual target (never per-candidate pseudo-replication), zero
substitution only for audited structural blanks, clip-negatives-then-
renormalise within each contest, and the rule that unsupported minor parties
receive no adjustment but stay in the denominator.

What this file does NOT do
--------------------------
It does not read observed 2026 vote shares, ranks or elected flags; it does
not compute any error; it does not choose between specifications.  The
declared unblinding structure (which comparisons are primary, which are
sensitivity) is written into the protocol JSON so the later comparison step
has no degrees of freedom left.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np

from news_modelling.news_estimator import RidgeModel
from news_modelling.production_news_experiment import (
    FIT_ELECTION,
    FIT_NEWS_ELECTION,
    FIXED_RIDGE_PENALTY,
    VALIDATION_ELECTION,
    VALIDATION_NEWS_ELECTION,
    ProductionExperimentError,
    _feature_index,
    _float_or_structural_zero,
    _truthy,
    aggregate_fitting_residuals,
    party_key,
    validate_inputs,
)

# The two Stage 1 elections held out for the final test.  Both map to the
# single news election ESWS-2026-05: the corpus was collected for the May
# 2026 event as a whole, and East/West is an administrative split of the
# same polling day, not two news environments.
HOLDOUT_ELECTIONS = (
    "surrey-county-council-2026-east-surrey",
    "surrey-county-council-2026-west-surrey",
)
HOLDOUT_NEWS_ELECTION = "ESWS-2026-05"
HOLDOUT_SPLIT_ROLE = "primary_holdout"

# Columns that carry, or are derived from, the 2026 result.  They are
# removed the moment the holdout file is read and must never appear in any
# output this module writes.  The blind is enforced twice: once at load
# (strip_outcome_columns) and once at write (assert_blind_fieldnames).
OUTCOME_COLUMNS = (
    "observed_vote_share",
    "observed_rank",
    "observed_elected",
    "error",
    "absolute_error",
    "squared_error",
)

# The primary fitting variant, declared before unblinding.  Changing this
# constant after the predictions file exists would be visible in git and is
# forbidden by the protocol it writes.
PRIMARY_VARIANT = "pooled_2017_2021"


class BlindingViolation(RuntimeError):
    """An input or output would expose 2026 outcomes to the news layer."""


def strip_outcome_columns(rows: Iterable[dict]) -> list[dict]:
    """Return copies of ``rows`` with every outcome column removed.

    The Stage 1 bundle scored its own holdout when it was trained, so the
    file on disk contains observed columns.  The news layer may not carry
    them any further than this function.
    """

    cleaned = []
    for row in rows:
        cleaned.append({
            key: value for key, value in row.items()
            if key not in OUTCOME_COLUMNS
        })
    return cleaned


def assert_blind_fieldnames(fieldnames: Iterable[str]) -> None:
    """Refuse any output schema that mentions an outcome column."""

    exposed = sorted(set(fieldnames) & set(OUTCOME_COLUMNS))
    if exposed:
        raise BlindingViolation(
            f"Output would contain outcome columns: {exposed}. The blinded "
            "prediction file may carry predictions only."
        )


def sanitise_holdout_rows(rows: list[dict]) -> list[dict]:
    """Filter the holdout file to the 2026 principal rows and blind them.

    Post-May-2026 by-elections also live in the holdout file, but the news
    layer scoped by-elections out on 30 July and has no feature rows for
    them, so they are excluded rather than silently given no adjustment.
    """

    principal = [
        row for row in rows if row.get("election_id") in HOLDOUT_ELECTIONS
    ]
    if not principal:
        raise ProductionExperimentError(
            "No 2026 principal-election rows found in the holdout file."
        )
    wrong_role = {
        str(row.get("split_role")) for row in principal
        if str(row.get("split_role")) != HOLDOUT_SPLIT_ROLE
    }
    if wrong_role:
        raise ProductionExperimentError(
            f"2026 principal rows carry unexpected split roles {sorted(wrong_role)}."
        )

    blinded = strip_outcome_columns(principal)

    # The strip must actually have worked; a renamed outcome column would
    # defeat it silently, so verify against the declared list.
    for row in blinded:
        leaked = sorted(set(row) & set(OUTCOME_COLUMNS))
        if leaked:
            raise BlindingViolation(f"Outcome columns survived the strip: {leaked}")

    identifiers = [str(row["candidate_contest_id"]) for row in blinded]
    if len(identifiers) != len(set(identifiers)):
        raise ProductionExperimentError(
            "Duplicate candidate_contest_id rows in the 2026 holdout input."
        )
    merged = [
        identifier for identifier, row in zip(identifiers, blinded)
        if _truthy(row.get("is_reform_uk")) and _truthy(row.get("is_ukip"))
    ]
    if merged:
        raise ProductionExperimentError(
            f"{len(merged)} 2026 row(s) merge Reform UK and UKIP."
        )
    return blinded


def aggregate_pooled_residuals(oof_rows: Iterable[dict]) -> list[dict]:
    """One residual row per (election, party) for 2017 and 2021 together.

    The same anti-pseudo-replication rule as the frozen experiment: news
    values exist per election x party, so the fit sees one mean residual per
    election x party, never hundreds of copied candidate rows.
    """

    residuals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in oof_rows:
        election = row.get("election_id")
        if election not in (FIT_ELECTION, VALIDATION_ELECTION):
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        residuals[(election, key)].append(
            float(row["observed_vote_share"]) - float(row["predicted_vote_share"])
        )

    # Reform UK did not exist in 2017; a 2017 Reform row would mean the
    # party join is broken and the scientific setup wrong.
    if (FIT_ELECTION, "reform_uk") in residuals:
        raise ProductionExperimentError("Unexpected Reform row in 2017 fitting data.")
    # The pooled variant's entire point includes the single 2021 Reform
    # observation.  Its absence would change what the primary variant means,
    # so it is asserted rather than tolerated.
    if (VALIDATION_ELECTION, "reform_uk") not in residuals:
        raise ProductionExperimentError("The 2021 Reform residual row is missing.")

    news_election = {
        FIT_ELECTION: FIT_NEWS_ELECTION,
        VALIDATION_ELECTION: VALIDATION_NEWS_ELECTION,
    }
    rows = [
        {
            "election_id": election,
            "news_election_id": news_election[election],
            "party_key": key,
            "candidate_rows": len(values),
            "mean_residual": float(np.mean(values)),
        }
        for (election, key), values in sorted(residuals.items())
    ]
    if len(rows) < 8:
        raise ProductionExperimentError(
            f"Only {len(rows)} pooled fitting rows; expected the 2017 and "
            "2021 party families together."
        )
    return rows


def _fitting_rows_for_variant(variant: str, oof_rows: list[dict]) -> list[dict]:
    """Return the frozen fitting rows for one declared variant."""

    if variant == "pooled_2017_2021":
        return aggregate_pooled_residuals(oof_rows)
    if variant == "fit_2017_only":
        # Reuse the experiment's own aggregator so the replication variant
        # cannot drift from the protocol it replicates.
        fitting = aggregate_fitting_residuals(oof_rows)
        return [
            {**row, "election_id": FIT_ELECTION,
             "news_election_id": FIT_NEWS_ELECTION}
            for row in fitting.values()
        ]
    raise ProductionExperimentError(f"Unknown fitting variant: {variant!r}")


def _fit_specification(
    fitting_rows: list[dict],
    feature_index: dict,
    *,
    period: str,
    feature_columns: list[str],
) -> tuple[RidgeModel, dict]:
    """Fit one arm/period ridge on the variant's party-mean residuals."""

    design = np.array([
        [
            _float_or_structural_zero(
                feature_index[(row["news_election_id"], row["party_key"], period)],
                column,
            )
            for column in feature_columns
        ]
        for row in fitting_rows
    ], dtype=float)
    target = np.array([row["mean_residual"] for row in fitting_rows], dtype=float)
    model = RidgeModel(FIXED_RIDGE_PENALTY).fit(design, target)
    record = {
        "training_rows": len(fitting_rows),
        "training_reform_rows": sum(
            1 for row in fitting_rows if row["party_key"] == "reform_uk"
        ),
        "intercept_mean_training_residual": model.intercept,
        "standardised_coefficients": {
            column: float(value)
            for column, value in zip(feature_columns, model.coefficients)
        },
    }
    return model, record


def _normalise_contests(rows: list[dict], raw_column: str, output_column: str) -> int:
    """Clip negative raw shares and renormalise each contest to 100.

    Stage 1's own 2026 predictions sum to exactly 100 per contest
    (normalisation_status = 'normalised'), so 100 is the correct target and
    the news adjustment cannot quietly change the baseline's scale.  The
    contest key includes the election because East and West Surrey are
    separate Stage 1 elections.
    """

    by_contest: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_contest[(row["election_id"], row["division_id"])].append(row)

    clipped = 0
    for contest_rows in by_contest.values():
        raw = []
        for row in contest_rows:
            value = float(row[raw_column])
            if value < 0:
                clipped += 1
                value = 0.0
            raw.append(value)
        total = sum(raw)
        if total <= 0:
            raise ProductionExperimentError("A contest has no positive prediction.")
        for row, value in zip(contest_rows, raw):
            row[output_column] = 100.0 * value / total
    return clipped


def _assign_ranks(rows: list[dict], share_column: str, seats_column: str) -> None:
    """Deterministic within-contest rank and seat allocation.

    Ties are broken by candidate_contest_id so two runs of this module can
    never disagree; the tie-break is recorded in the protocol.  Elected means
    ranked within the contest's number of seats, which for 2026 is a
    pre-election fact (two-member wards).
    """

    by_contest: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_contest[(row["election_id"], row["division_id"])].append(row)

    for contest_rows in by_contest.values():
        seats = int(contest_rows[0][seats_column])
        ordered = sorted(
            contest_rows,
            key=lambda row: (-float(row[share_column]),
                             str(row["candidate_contest_id"])),
        )
        for position, row in enumerate(ordered, start=1):
            row["news_predicted_rank"] = position
            row["news_predicted_elected"] = position <= seats


def predict_specification(
    blinded_rows: list[dict],
    feature_index: dict,
    model: RidgeModel,
    *,
    period: str,
    feature_columns: list[str],
) -> tuple[list[dict], dict]:
    """Apply one fitted specification to every blinded 2026 candidate row.

    Mirrors the frozen experiment exactly: supported parties receive the
    model's adjustment (news features plus intercept), unsupported minor
    parties receive no adjustment but remain in the denominator, and both
    the recalibrated control and the news-enhanced predictions are clipped
    and renormalised per contest.
    """

    rows = [dict(row) for row in blinded_rows]
    for row in rows:
        key = party_key(row.get("standard_party_name"))
        row["party_key"] = key
        row["baseline_prediction"] = float(row["predicted_vote_share"])
        row["news_adjustment"] = 0.0
        if key is not None:
            feature = feature_index[(HOLDOUT_NEWS_ELECTION, key, period)]
            vector = np.array([[
                _float_or_structural_zero(feature, column)
                for column in feature_columns
            ]], dtype=float)
            row["news_adjustment"] = float(model.predict(vector)[0])
        row["raw_recalibrated"] = (
            row["baseline_prediction"]
            + (model.intercept if key is not None else 0.0)
        )
        row["raw_news_enhanced"] = (
            row["baseline_prediction"] + row["news_adjustment"]
        )

    clipped = {
        "recalibrated": _normalise_contests(
            rows, "raw_recalibrated", "recalibrated_prediction"
        ),
        "news_enhanced": _normalise_contests(
            rows, "raw_news_enhanced", "news_enhanced_prediction"
        ),
    }
    _assign_ranks(rows, "news_enhanced_prediction", "analysis_number_of_seats")
    return rows, clipped


def build_blinded_predictions(
    oof_rows: list[dict],
    holdout_rows: list[dict],
    features: list[dict],
    audit: dict,
) -> tuple[dict, list[dict]]:
    """Fit every frozen specification under both variants and predict 2026.

    Returns the protocol record and the prediction rows.  Nothing in the
    return value contains a 2026 outcome; ``sanitise_holdout_rows`` removed
    them before any prediction was formed.
    """

    validate_inputs(oof_rows, audit)
    blinded = sanitise_holdout_rows(holdout_rows)
    feature_index = _feature_index(features)
    periods = (
        audit["feature_table"]["windows"]
        + audit["feature_table"]["cumulative_periods"]
    )

    specification_records = []
    prediction_rows: list[dict] = []
    variants = ("pooled_2017_2021", "fit_2017_only")
    for variant in variants:
        fitting_rows = _fitting_rows_for_variant(variant, oof_rows)
        for analysis_name, specification in audit["frozen_feature_sets"].items():
            for period in periods:
                columns = list(specification["columns"])
                model, fit_record = _fit_specification(
                    fitting_rows, feature_index,
                    period=period, feature_columns=columns,
                )
                rows, clipped = predict_specification(
                    blinded, feature_index, model,
                    period=period, feature_columns=columns,
                )
                period_role = (
                    "confirmed_window" if "previous_" not in period
                    else "cumulative_sensitivity"
                )
                specification_records.append({
                    "fit_variant": variant,
                    "analysis": analysis_name,
                    "analysis_role": specification["analysis_role"],
                    "period": period,
                    "period_role": period_role,
                    "feature_columns": columns,
                    "ridge_penalty": FIXED_RIDGE_PENALTY,
                    "negative_raw_shares_clipped": clipped,
                    **fit_record,
                })
                for row in rows:
                    prediction_rows.append({
                        "fit_variant": variant,
                        "analysis": analysis_name,
                        "analysis_role": specification["analysis_role"],
                        "period": period,
                        "period_role": period_role,
                        "election_id": row["election_id"],
                        "candidate_contest_id": row["candidate_contest_id"],
                        "division_id": row["division_id"],
                        "standard_party_name": row["standard_party_name"],
                        "party_key": row["party_key"] or "",
                        "included_in_reported_metrics": row["party_key"] is not None,
                        "is_reform_uk": row["party_key"] == "reform_uk",
                        "is_ukip": row["party_key"] == "ukip",
                        "analysis_number_of_seats": row["analysis_number_of_seats"],
                        "baseline_prediction": row["baseline_prediction"],
                        "recalibrated_prediction": row["recalibrated_prediction"],
                        "news_adjustment_before_contest_normalisation":
                            row["news_adjustment"],
                        "news_enhanced_prediction": row["news_enhanced_prediction"],
                        "news_predicted_rank": row["news_predicted_rank"],
                        "news_predicted_elected": row["news_predicted_elected"],
                    })

    protocol = {
        "status": "blinded_2026_predictions_frozen",
        "canonical_release_id": audit["canonical_release"]["release_id"],
        "holdout_elections": list(HOLDOUT_ELECTIONS),
        "holdout_news_election": HOLDOUT_NEWS_ELECTION,
        "blinded_candidate_rows": len(blinded),
        "outcome_columns_stripped_at_load": list(OUTCOME_COLUMNS),
        "fit_variants": {
            "pooled_2017_2021": (
                "primary: refit on train plus completed validation (2017 + "
                "2021 election x party mean residuals), the supervisor's "
                "split structure; includes the single 2021 Reform residual row"
            ),
            "fit_2017_only": (
                "protocol replication of the frozen pre-2026 experiment "
                "(five 2017 party rows, no Reform); reported as sensitivity"
            ),
        },
        "primary_fit_variant": PRIMARY_VARIANT,
        "ridge_penalty": FIXED_RIDGE_PENALTY,
        "penalty_selection": "fixed_before_validation; unchanged from the frozen experiment",
        "tie_break_rule": (
            "within-contest ranks order by news-enhanced share descending, "
            "then candidate_contest_id ascending"
        ),
        "periods": periods,
        "specifications": specification_records,
        "unblinding_rule": (
            "One unblinding event only. Report every specification in this "
            "file. The primary confirmatory family is the combined and "
            "national arms over the six confirmed windows under the "
            "pooled_2017_2021 variant, each compared against its recalibrated "
            "control on overall MAE. The local arm, cumulative periods and "
            "the fit_2017_only variant are sensitivity results. No "
            "specification, window, arm or variant may be selected or "
            "promoted after outcomes are seen. Reform UK rows are reported "
            "separately with their row count visible; coefficients are "
            "party-generic, not Reform-specific, and not causal."
        ),
    }
    return protocol, prediction_rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_outputs(
    protocol: dict,
    predictions: list[dict],
    output_dir: str | Path,
    *,
    input_paths: dict[str, Path],
) -> dict:
    """Write the frozen protocol, the blinded predictions and their hashes.

    Refuses to overwrite: the whole value of this file is that it existed,
    unchanged, before anyone looked at the 2026 results.  A rebuild requires
    deleting the directory by hand, which git will show.
    """

    output = Path(output_dir)
    predictions_path = output / "blinded_predictions.csv"
    if predictions_path.exists():
        raise BlindingViolation(
            f"{predictions_path} already exists. The blinded prediction file "
            "is frozen once written; delete the directory manually only if "
            "the freeze is being deliberately and visibly redone."
        )
    output.mkdir(parents=True, exist_ok=True)

    fieldnames = list(predictions[0])
    assert_blind_fieldnames(fieldnames)
    with predictions_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(predictions)

    # Input hashes make the freeze auditable end to end: the exact feature
    # table, estimability report and Stage 1 files this run read.
    protocol = dict(protocol)
    protocol["input_sha256"] = {
        name: _sha256(path) for name, path in sorted(input_paths.items())
    }
    protocol_path = output / "frozen_protocol.json"
    protocol_path.write_text(
        json.dumps(protocol, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "blinded_predictions.csv": _sha256(predictions_path),
        "frozen_protocol.json": _sha256(protocol_path),
        "prediction_rows": len(predictions),
        "note": (
            "Record these hashes in the evidence register. Any change to "
            "either file after the freeze is detectable against them."
        ),
    }
    manifest_path = output / "sha256_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
