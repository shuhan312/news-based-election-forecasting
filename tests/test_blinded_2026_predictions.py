"""Tests for the blinded 2026 prediction freeze.

The properties tested here are the ones whose silent failure would break
the blind or the freeze: outcome columns surviving the load, an output
schema that could carry outcomes, Reform appearing in a fitting year it
did not contest, contests that stop summing to 100, and a frozen file
being overwritten.
"""

import csv
import json

import pytest

# ProductionExperimentError is taken from the module under test rather
# than imported by its own path: the repo is importable both as
# `src.news_modelling.*` and as `news_modelling.*`, and mixing the two
# yields two distinct exception classes that pytest.raises cannot match.
from src.news_modelling.blinded_2026_predictions import (
    BlindingViolation,
    OUTCOME_COLUMNS,
    ProductionExperimentError,
    aggregate_pooled_residuals,
    assert_blind_fieldnames,
    build_blinded_predictions,
    sanitise_holdout_rows,
    write_outputs,
)


WINDOW = "180_to_91_days"
CUMULATIVE = "previous_30_days"
PARTIES = ("conservative", "labour", "liberal_democrat", "ukip", "reform_uk")


def _holdout_row(candidate, party, share, division="D1",
                 election="surrey-county-council-2026-east-surrey",
                 role="primary_holdout"):
    return {
        "candidate_contest_id": candidate,
        "election_id": election,
        "division_id": division,
        "split_role": role,
        "standard_party_name": party,
        "is_reform_uk": str(party == "Reform UK"),
        "is_ukip": str(party == "UK Independence Party"),
        "analysis_number_of_seats": "2",
        "predicted_vote_share": str(share),
        # Outcome columns present on purpose: the loader must remove them.
        "observed_vote_share": "99.0",
        "observed_rank": "1",
        "observed_elected": "True",
        "error": "0.5",
        "absolute_error": "0.5",
        "squared_error": "0.25",
    }


def _oof_row(election, party, predicted, observed, candidate):
    return {
        "candidate_contest_id": candidate,
        "election_id": election,
        "division_id": "D-old",
        "split_role": "rolling_origin_fold",
        "standard_party_name": party,
        "is_reform_uk": str(party == "Reform UK"),
        "is_ukip": str(party == "UK Independence Party"),
        "predicted_vote_share": str(predicted),
        "observed_vote_share": str(observed),
    }


def _oof_fixture():
    labels = {
        "conservative": "Conservative",
        "labour": "Labour",
        "liberal_democrat": "Liberal Democrats",
        "ukip": "UK Independence Party",
        "reform_uk": "Reform UK",
    }
    rows = []
    for i, key in enumerate(("conservative", "labour", "liberal_democrat", "ukip")):
        rows.append(_oof_row("surrey-county-council-2017", labels[key],
                             30.0, 30.0 + i, f"2017-{key}"))
    for i, key in enumerate(("conservative", "labour", "liberal_democrat",
                             "reform_uk")):
        rows.append(_oof_row("surrey-county-council-2021", labels[key],
                             25.0, 25.0 - i, f"2021-{key}"))
    return rows


def _feature_rows():
    rows = []
    for election in ("SCC-2017-05", "SCC-2021-05", "ESWS-2026-05"):
        for party in PARTIES + ("green",):
            for period in (WINDOW, CUMULATIVE):
                rows.append({
                    "election_id": election,
                    "standard_party_key": party,
                    "period": period,
                    "party_article_share": "0.2",
                    "net_portrayal_share": "0.1",
                })
    return rows


def _audit():
    return {
        "status": "exploratory_news_modelling_permitted_with_limits",
        "holdout_protection": {"stage1_holdout_file_read": False},
        "feature_table": {"windows": [WINDOW],
                          "cumulative_periods": [CUMULATIVE]},
        "frozen_feature_sets": {
            "combined_exploratory": {
                "analysis_role": "exploratory_primary_comparison",
                "columns": ["party_article_share", "net_portrayal_share"],
            },
        },
        "canonical_release": {"release_id": "canonical-news-v1-test"},
    }


def _holdout_fixture():
    return [
        _holdout_row("2026-ref", "Reform UK", 40.0),
        _holdout_row("2026-con", "Conservative", 35.0),
        _holdout_row("2026-ind", "Independent", 25.0),
        # A post-2026 by-election row that must be excluded, not adjusted.
        _holdout_row("2026-bye", "Conservative", 50.0,
                     election="surrey-county-council-by-election-warlingham-2026-05-07"),
    ]


def test_sanitise_strips_every_outcome_column_and_scopes_to_principal():
    rows = sanitise_holdout_rows(_holdout_fixture())
    assert len(rows) == 3
    for row in rows:
        assert not set(row) & set(OUTCOME_COLUMNS)


def test_output_schema_refuses_outcome_columns():
    with pytest.raises(BlindingViolation):
        assert_blind_fieldnames(["baseline_prediction", "observed_vote_share"])


def test_pooled_residuals_include_2021_reform_and_forbid_2017_reform():
    rows = aggregate_pooled_residuals(_oof_fixture())
    keys = {(row["election_id"], row["party_key"]) for row in rows}
    assert ("surrey-county-council-2021", "reform_uk") in keys
    assert len(rows) == 8

    poisoned = _oof_fixture() + [
        _oof_row("surrey-county-council-2017", "Reform UK", 5.0, 6.0, "2017-ref")
    ]
    with pytest.raises(ProductionExperimentError):
        aggregate_pooled_residuals(poisoned)


def test_missing_2021_reform_row_is_an_error_not_a_default():
    rows = [r for r in _oof_fixture() if r["candidate_contest_id"] != "2021-reform_uk"]
    with pytest.raises(ProductionExperimentError):
        aggregate_pooled_residuals(rows)


def test_build_produces_blind_normalised_ranked_predictions():
    protocol, predictions = build_blinded_predictions(
        oof_rows=_oof_fixture(),
        holdout_rows=_holdout_fixture(),
        features=_feature_rows(),
        audit=_audit(),
    )
    # 2 variants x 1 arm x 2 periods x 3 candidates.
    assert len(predictions) == 12
    assert not set(predictions[0]) & set(OUTCOME_COLUMNS)
    assert protocol["primary_fit_variant"] == "pooled_2017_2021"

    one_block = [
        row for row in predictions
        if row["fit_variant"] == "pooled_2017_2021" and row["period"] == WINDOW
    ]
    total = sum(row["news_enhanced_prediction"] for row in one_block)
    assert total == pytest.approx(100.0)
    # Two-member ward: exactly two candidates ranked electable.
    assert sum(row["news_predicted_elected"] for row in one_block) == 2
    # The unsupported party gets no direct adjustment.
    independent = next(r for r in one_block if r["party_key"] == "")
    assert independent["news_adjustment_before_contest_normalisation"] == 0.0
    assert independent["included_in_reported_metrics"] is False


def test_write_outputs_freezes_and_hashes(tmp_path):
    protocol, predictions = build_blinded_predictions(
        oof_rows=_oof_fixture(),
        holdout_rows=_holdout_fixture(),
        features=_feature_rows(),
        audit=_audit(),
    )
    inputs = {"features.csv": tmp_path / "features.csv"}
    inputs["features.csv"].write_text("stub", encoding="utf-8")

    manifest = write_outputs(protocol, predictions, tmp_path / "out",
                             input_paths=inputs)
    assert manifest["prediction_rows"] == 12

    with (tmp_path / "out" / "blinded_predictions.csv").open() as handle:
        fieldnames = csv.DictReader(handle).fieldnames
    assert not set(fieldnames) & set(OUTCOME_COLUMNS)

    written = json.loads(
        (tmp_path / "out" / "frozen_protocol.json").read_text()
    )
    assert written["input_sha256"]["features.csv"]

    # The freeze refuses a second write.
    with pytest.raises(BlindingViolation):
        write_outputs(protocol, predictions, tmp_path / "out",
                      input_paths=inputs)
