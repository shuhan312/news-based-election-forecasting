"""Guards on the Stage 1 party-intercept sensitivity analysis."""

import json
from pathlib import Path

import pytest

RESULTS = Path("news_features/stage1_party_sensitivity_v1/stage1_party_sensitivity.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="stage1_party_sensitivity not yet built")


@needs_results
def test_reproduction_gate_passed():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["reproduction_check_passed"]


@needs_results
def test_six_parties_have_mean_residuals():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    parties = set(payload["party_mean_residuals_all"])
    expected = {"conservative", "green", "labour", "liberal_democrat",
                "reform_uk", "ukip"}
    assert parties == expected


@needs_results
def test_established_means_are_subset():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    established = set(payload["party_mean_residuals_established"])
    expected = {"conservative", "green", "labour", "liberal_democrat"}
    assert established == expected


@needs_results
def test_party_means_are_nonzero():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    means = list(payload["party_mean_residuals_all"].values())
    assert any(abs(m) > 0.1 for m in means)


@needs_results
def test_both_variants_have_six_windows():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    expected_windows = {"180_to_91_days", "90_to_31_days", "30_to_15_days",
                        "14_to_8_days", "7_to_4_days", "final_72_hours"}
    for variant in ("established_only", "all_six"):
        comparisons = payload[variant]
        assert len(comparisons) == 6, f"{variant} has {len(comparisons)} windows"
        windows = {c["window"] for c in comparisons}
        assert windows == expected_windows, f"{variant} windows: {windows}"


@needs_results
def test_headline_original_delta_matches_certified():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for variant in ("established_only", "all_six"):
        headline = next(c for c in payload[variant]
                        if c["window"] == "90_to_31_days")
        assert abs(round(headline["original_delta"], 3) - 0.24) < 1e-9, (
            f"{variant}: original delta {headline['original_delta']}")


@needs_results
def test_established_survival_higher_than_all_six():
    """Removing only four parties' offsets should leave more signal than
    removing all six."""
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    est = next(c for c in payload["established_only"]
               if c["window"] == "90_to_31_days")
    full = next(c for c in payload["all_six"]
                if c["window"] == "90_to_31_days")
    if est["survival_fraction"] is not None and full["survival_fraction"] is not None:
        assert est["survival_fraction"] >= full["survival_fraction"]


@needs_results
def test_survival_fraction_is_consistent():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for variant in ("established_only", "all_six"):
        for c in payload[variant]:
            if c["original_delta"] == 0 or c["survival_fraction"] is None:
                continue
            expected = c["demeaned_delta"] / c["original_delta"]
            assert abs(c["survival_fraction"] - expected) < 1e-10, (
                f"{variant}/{c['window']}: survival {c['survival_fraction']} "
                f"!= {expected}")
