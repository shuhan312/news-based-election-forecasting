"""Tests for the leave-one-party-out stability audit."""

import pytest

from src.news_modelling.production_news_lopo import (
    _coefficient_sign_flips,
    _sign,
    render_findings,
)


def test_sign_uses_a_tolerance_for_numerical_zero():
    assert _sign(1.0) == 1
    assert _sign(-1.0) == -1
    assert _sign(1e-14) == 0


def test_coefficient_direction_changes_are_named():
    full = {"standardised_coefficients": {"volume": 1.0, "tone": -2.0}}
    omitted = {"standardised_coefficients": {"volume": -0.5, "tone": -1.0}}
    assert _coefficient_sign_flips(full, omitted) == ["volume"]


def test_findings_calls_improvements_sensitivity_not_selection():
    comparison = {
        "omitted_party": "ukip",
        "analysis": "national_exploratory",
        "period": "14_to_8_days",
        "full_model_news_vs_recalibrated_mae": -1.0,
        "lopo_news_vs_recalibrated_mae": 0.2,
        "change_from_full_model": 1.2,
        "lopo_reform_news_vs_recalibrated_mae": 0.5,
        "coefficient_sign_flips": ["tone"],
        "creates_overall_improvement": True,
    }
    report = {
        "omitted_parties": ["ukip"],
        "by_omission": {
            "ukip": {
                "comparisons": 1,
                "overall_improvements": 1,
                "coefficient_sign_flips": 1,
                "minimum_news_vs_recalibrated_mae": 0.2,
                "maximum_news_vs_recalibrated_mae": 0.2,
            }
        },
        "comparison_results": [comparison],
        "robustness_verdict": "unstable_single_party_omissions_create_improvements",
        "total_comparisons": 1,
        "overall_improvements_after_omission": 1,
    }
    text = render_findings(report)
    assert "must not be selected" in text
    assert "alternative models" in text
