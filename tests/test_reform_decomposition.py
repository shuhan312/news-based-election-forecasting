"""Guards on the Reform vs non-Reform delta decomposition."""

import json
from pathlib import Path

import pytest

RESULTS = Path("news_features/reform_decomposition_v1/reform_decomposition.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="reform_decomposition not yet built")


@needs_results
def test_all_three_arms_present():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert set(payload["arms"]) == {
        "frozen", "placebo_party_dummies", "placebo_reform_dummy"}


@needs_results
def test_six_windows_per_arm():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for arm_name, windows in payload["arms"].items():
        assert len(windows) == 6, f"{arm_name} has {len(windows)} windows"


@needs_results
def test_weighted_decomposition_is_exact():
    """n_all * delta_all == n_reform * delta_reform + n_non * delta_non."""
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for arm_name, windows in payload["arms"].items():
        for w in windows:
            lhs = w["all"]["n"] * w["all"]["delta"]
            rhs = (w["reform"]["n"] * w["reform"]["delta"]
                   + w["non_reform"]["n"] * w["non_reform"]["delta"])
            assert abs(lhs - rhs) < 0.5, (
                f"{arm_name} {w['window']}: {lhs:.2f} != {rhs:.2f}")


@needs_results
def test_party_dummies_reform_delta_negative():
    """The -0.29 claim: party dummies hurt Reform predictions."""
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for w in payload["arms"]["placebo_party_dummies"]:
        assert w["reform"]["delta"] < 0


@needs_results
def test_frozen_90_31_reform_negative_non_reform_positive():
    """Frozen arm at 90-31 days: Reform hurt, non-Reform helped."""
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    w = next(r for r in payload["arms"]["frozen"]
             if r["window"] == "90_to_31_days")
    assert w["reform"]["delta"] < 0
    assert w["non_reform"]["delta"] > 0


@needs_results
def test_row_counts_consistent():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for arm_name, windows in payload["arms"].items():
        for w in windows:
            assert w["all"]["n"] == w["reform"]["n"] + w["non_reform"]["n"]
