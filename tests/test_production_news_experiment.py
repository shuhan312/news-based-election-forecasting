"""Unit tests for the frozen 2017-to-2021 news experiment."""

import pytest

from src.news_modelling.production_news_experiment import (
    ProductionExperimentError,
    _normalise_contests,
    aggregate_fitting_residuals,
    party_key,
    render_findings,
    validate_inputs,
)


def test_party_mapping_keeps_reform_and_ukip_separate():
    assert party_key("Reform UK") == "reform_uk"
    assert party_key("UK Independence Party") == "ukip"
    assert party_key("Labour and Co-operative") == "labour"
    assert party_key("Independent") is None


def test_fitting_rows_are_aggregated_once_per_party():
    rows = [
        {
            "election_id": "surrey-county-council-2017",
            "standard_party_name": "Conservative",
            "predicted_vote_share": "20",
            "observed_vote_share": "24",
        },
        {
            "election_id": "surrey-county-council-2017",
            "standard_party_name": "Conservative",
            "predicted_vote_share": "30",
            "observed_vote_share": "32",
        },
        {
            "election_id": "surrey-county-council-2017",
            "standard_party_name": "Labour",
            "predicted_vote_share": "10",
            "observed_vote_share": "9",
        },
        {
            "election_id": "surrey-county-council-2017",
            "standard_party_name": "The Green Party",
            "predicted_vote_share": "5",
            "observed_vote_share": "5",
        },
    ]
    result = aggregate_fitting_residuals(rows)
    assert len(result) == 3
    assert result["conservative"]["candidate_rows"] == 2
    assert result["conservative"]["mean_residual"] == pytest.approx(3.0)


def test_reform_in_2017_is_rejected_instead_of_silently_reinterpreted():
    rows = [
        {
            "election_id": "surrey-county-council-2017",
            "standard_party_name": name,
            "predicted_vote_share": "10",
            "observed_vote_share": "11",
        }
        for name in ("Conservative", "Labour", "The Green Party", "Reform UK")
    ]
    with pytest.raises(ProductionExperimentError, match="Unexpected Reform"):
        aggregate_fitting_residuals(rows)


def test_2026_oof_row_is_rejected():
    audit = {
        "status": "exploratory_news_modelling_permitted_with_limits",
        "holdout_protection": {"stage1_holdout_file_read": False},
    }
    with pytest.raises(ProductionExperimentError, match="2026"):
        validate_inputs([{"election_id": "unsafe-2026"}], audit)


def test_contest_predictions_are_nonnegative_and_sum_to_100():
    rows = [
        {"division_id": "d1", "raw": -2.0},
        {"division_id": "d1", "raw": 30.0},
        {"division_id": "d1", "raw": 20.0},
    ]
    clipped = _normalise_contests(rows, "raw", "prediction")
    assert clipped == 1
    assert sum(row["prediction"] for row in rows) == pytest.approx(100.0)
    assert all(row["prediction"] >= 0 for row in rows)


def test_findings_report_does_not_select_a_best_window():
    result = {
        "analysis": "combined_exploratory",
        "period": "final_72_hours",
        "period_role": "confirmed_window",
        "validation_party_count_outside_training_feature_range": 0,
        "metrics": {
            "all_supported_parties": {
                "baseline": {"mae": 7.0},
                "recalibrated_without_news": {"mae": 7.5},
                "news_enhanced": {"mae": 7.5},
                "news_vs_recalibrated_mae": 0.0,
            },
            "reform_uk": {
                "news_enhanced": {"mae": 12.0},
                "news_vs_recalibrated_mae": 0.0,
            },
        },
        "bootstrap_news_vs_recalibrated": {
            "improvement_ci_lower": 0.0,
            "improvement_ci_upper": 0.0,
        },
    }
    report = {
        "fit_election": "2017",
        "validation_election": "2021",
        "training_party_rows": 5,
        "training_parties": ["a", "b", "c", "d", "e"],
        "specification_results": [result],
    }
    text = render_findings(report)
    assert "0 of 1 confirmed-window" in text
    assert "best window" not in text.lower()
