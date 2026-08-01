"""Freeze the enrichment model's blinded 2026 predictions (v2).

The v1 freeze archived the pre-enrichment models. This module archives
the one thing enrichment changed: the fitting set. Everything else is
deliberately identical to v1 — the three frozen feature arms, the twelve
periods, the fixed ridge penalty, party-mean residual targets,
clip-and-renormalise post-processing, the outcome-column strip, the
refuse-to-overwrite freeze — and is imported from the v1 module rather
than copied, so the two freezes cannot drift apart.

What v2 adds
------------
One fitting variant, ``pooled_2017_2021_byelections``: party-mean Stage 1
residuals per (election x party) over the 2017 and 2021 principal
elections plus the eight pre-holdout by-elections. Through the 2025
by-elections this fit contains real Reform UK residual cells — the first
in the project — joined to news features from canonical release v2
(Reform training articles: 300 against v1's zero). Six of the eight
by-elections carry zero admitted articles; their cells enter with zero
counts and structurally-blank shares under the audited zero policy,
because a searched election with no eligible coverage is an observation,
not a gap.

The declared unblinding structure is unchanged and shared with v1: one
unblinding event; the confirmatory family is the combined and national
arms over the six confirmed windows, now under this variant, against the
recalibrated control; local, cumulative and every v1 variant are
sensitivity. Nothing may be selected after outcomes are seen.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np

from news_collection.run_byelection_stages import BYELECTION_POLLING_DAYS
from news_modelling.blinded_2026_predictions import (
    HOLDOUT_NEWS_ELECTION,
    PRIMARY_VARIANT as V1_PRIMARY_VARIANT,
    _fit_specification,
    predict_specification,
    sanitise_holdout_rows,
    write_outputs,
)
from news_modelling.production_news_experiment import (
    FIT_ELECTION,
    FIT_NEWS_ELECTION,
    FIXED_RIDGE_PENALTY,
    VALIDATION_ELECTION,
    VALIDATION_NEWS_ELECTION,
    ProductionExperimentError,
    _feature_index,
    party_key,
    validate_inputs,
)

V2_VARIANT = "pooled_2017_2021_byelections"

# Stage 1 election id -> news-table election id for every fitting election.
# Principal ids differ between the two systems; by-election ids are the same
# long-form string on both sides, which is asserted rather than assumed.
FIT_ELECTION_MAP = {
    FIT_ELECTION: FIT_NEWS_ELECTION,
    VALIDATION_ELECTION: VALIDATION_NEWS_ELECTION,
    **{election_id: election_id for election_id in BYELECTION_POLLING_DAYS},
}


def aggregate_v2_residuals(oof_rows: Iterable[dict]) -> list[dict]:
    """One residual row per (fitting election, party), by-elections included.

    Same anti-pseudo-replication rule as every fit before it: news exists
    per election x party, so the fit sees one mean residual per cell, never
    per candidate. The guards encode what the enrichment claims to deliver:
    Reform must be absent from 2017 (it did not exist) and present in at
    least one 2025 by-election cell (it stood in them; a fit without those
    cells would silently revert to the v1 party-generic design).
    """

    residuals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in oof_rows:
        election = row.get("election_id")
        if election not in FIT_ELECTION_MAP:
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        residuals[(election, key)].append(
            float(row["observed_vote_share"]) - float(row["predicted_vote_share"])
        )

    if (FIT_ELECTION, "reform_uk") in residuals:
        raise ProductionExperimentError("Unexpected Reform row in 2017 fitting data.")
    reform_byelection_cells = [
        election for (election, key) in residuals
        if key == "reform_uk" and election in BYELECTION_POLLING_DAYS
    ]
    if not reform_byelection_cells:
        raise ProductionExperimentError(
            "No Reform residual cell from any by-election; the v2 fit would "
            "not contain the enrichment it exists to add."
        )

    rows = [
        {
            "election_id": election,
            "news_election_id": FIT_ELECTION_MAP[election],
            "party_key": key,
            "candidate_rows": len(values),
            "mean_residual": float(np.mean(values)),
        }
        for (election, key), values in sorted(residuals.items())
    ]
    if len(rows) < 20:
        raise ProductionExperimentError(
            f"Only {len(rows)} v2 fitting rows; expected the 2017, 2021 and "
            "by-election party families together."
        )
    return rows


def build_v2_blinded_predictions(
    oof_rows: list[dict],
    holdout_rows: list[dict],
    features: list[dict],
    audit: dict,
    *,
    v1_manifest: dict,
    release_id: str,
) -> tuple[dict, list[dict]]:
    """Fit every frozen specification under the v2 variant and predict 2026.

    The specification grid, ridge penalty and post-processing come from the
    same frozen sources as v1; only the fitting rows differ. Nothing in the
    return value contains a 2026 outcome.
    """

    validate_inputs(oof_rows, audit)
    blinded = sanitise_holdout_rows(holdout_rows)
    feature_index = _feature_index(features)
    # Every fitting cell must resolve in the v2 table before any model is
    # fitted: a missing by-election cell would otherwise surface mid-fit as
    # a KeyError on one arbitrary specification.
    periods = (
        audit["feature_table"]["windows"]
        + audit["feature_table"]["cumulative_periods"]
    )
    fitting_rows = aggregate_v2_residuals(oof_rows)
    for row in fitting_rows:
        for period in periods:
            if (row["news_election_id"], row["party_key"], period) not in feature_index:
                raise ProductionExperimentError(
                    f"feature table v2 has no cell for "
                    f"{row['news_election_id']}/{row['party_key']}/{period}"
                )

    specification_records = []
    prediction_rows: list[dict] = []
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
                "fit_variant": V2_VARIANT,
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
                    "fit_variant": V2_VARIANT,
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

    reform_cells = [row for row in fitting_rows if row["party_key"] == "reform_uk"]
    protocol = {
        "status": "blinded_2026_predictions_v2_frozen",
        "canonical_release_id": release_id,
        "holdout_news_election": HOLDOUT_NEWS_ELECTION,
        "blinded_candidate_rows": len(blinded),
        "fit_variant": {
            V2_VARIANT: (
                "primary for the enrichment comparison: party-mean Stage 1 "
                "residuals per election x party over 2017, 2021 and the "
                "eight pre-holdout by-elections, joined to news feature "
                "table v2"
            ),
        },
        "fitting_rows": len(fitting_rows),
        "fitting_elections": sorted({row["election_id"] for row in fitting_rows}),
        "reform_fitting_cells": [
            {"election_id": row["election_id"],
             "candidate_rows": row["candidate_rows"]}
            for row in reform_cells
        ],
        "ridge_penalty": FIXED_RIDGE_PENALTY,
        "penalty_selection":
            "fixed_before_validation; unchanged from the frozen experiment",
        "periods": periods,
        "specifications": specification_records,
        "v1_freeze": {
            "predictions_sha256": v1_manifest["blinded_predictions.csv"],
            "protocol_sha256": v1_manifest["frozen_protocol.json"],
            "v1_primary_variant": V1_PRIMARY_VARIANT,
        },
        "unblinding_rule": (
            "One unblinding event covering the v1 and v2 files together. "
            "The enrichment's confirmatory family is the combined and "
            "national arms over the six confirmed windows under "
            f"{V2_VARIANT}, each against its recalibrated control on "
            "overall MAE, reported beside the v1 primary variant and the "
            "untouched baseline. The local arm, cumulative periods and all "
            "other variants are sensitivity. No specification, window, arm "
            "or variant may be selected or promoted after outcomes are "
            "seen. Reform UK rows are reported separately with their row "
            "count visible; v2 coefficients rest on "
            "real but few Reform fitting cells and are not causal."
        ),
    }
    return protocol, prediction_rows
