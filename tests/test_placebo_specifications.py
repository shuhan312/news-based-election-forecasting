"""Tests for the placebo comparison.

The risk this module carries is not that it crashes. It is that it quietly
becomes a machine for producing a favourable number: reporting the best of
seven features, fitting a feature on four distinct training values, or
drifting away from the committed specification it claims to extend. Each of
those is asserted against here.
"""

import json
from pathlib import Path

import pytest

from src.news_modelling.placebo_specifications import (CONTENT_FEATURES,
                                                       FROZEN,
                                                       MIN_DISTINCT_TRAINING_VALUES,
                                                       PLACEBOS)

RESULTS = Path("news_features/placebo_specifications_v1/placebo_results.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="placebo results not built")


@pytest.fixture(scope="module")
def payload():
    return json.loads(RESULTS.read_text())


# ---- the specification under test has not drifted -------------------

def test_the_frozen_arm_is_the_committed_specification():
    # If this pair ever changes, the reproduction gate would start checking
    # the wrong thing against the right reference and still pass.
    assert FROZEN == ["party_article_share", "net_portrayal_share"]


def test_the_headline_placebo_carries_no_content_judgement():
    # `party_article_count` is the whole point: a number obtainable without
    # asking a language model what any article was about.
    assert PLACEBOS["placebo_volume"] == ["party_article_count"]


@needs_results
def test_the_reproduction_gate_actually_held(payload):
    """The licence for every other number in the file."""
    check = payload["reproduction_check"]
    assert check["max_absolute_difference"] == 0
    assert set(check["reproduced"]) == set(check["committed_combined_deltas"])


# ---- the answer cannot have been shopped for ------------------------

@needs_results
def test_every_content_feature_is_reported(payload):
    """Winners and losers alike, or the table means nothing."""
    reported = {name.removeprefix("content_") for name in payload["arms"]
                if name.startswith("content_")
                and name != "content_all_eligible"}
    assert reported == set(CONTENT_FEATURES)


@needs_results
def test_losing_arms_are_present(payload):
    """A run where everything won would be the first thing to distrust."""
    headline = [
        next(r for r in payload["arms"][f"content_{c}"]
             if r["window"] == "90_to_31_days")
        for c in CONTENT_FEATURES]
    fitted = [r for r in headline if "skipped" not in r]
    bar = max(
        next(r for r in payload["arms"][p] if r["window"] == "90_to_31_days")
        ["delta_vs_recalibrated"] for p in PLACEBOS)
    assert any(r["delta_vs_recalibrated"] < bar for r in fitted), (
        "no content feature lost to the placebo bar; check the bar is the "
        "best content-free arm and not the frozen pair")


@needs_results
def test_no_arm_is_fitted_below_the_reporting_bar(payload):
    """Eligibility is per window, and skipping is recorded, not silent."""
    eligible = payload["eligible_content_features_by_window"]
    for column in CONTENT_FEATURES:
        for row in payload["arms"][f"content_{column}"]:
            fitted = "skipped" not in row
            assert fitted == (column in eligible[row["window"]]), (
                f"{column} in {row['window']}: fitted={fitted} but "
                f"eligibility says {column in eligible[row['window']]}")
            if not fitted:
                assert str(MIN_DISTINCT_TRAINING_VALUES) in row["skipped"]


@needs_results
def test_the_near_windows_admit_no_content_feature(payload):
    """Coverage thins to single digits, and the output should show it.

    If a future corpus change makes these windows eligible that is a real
    result, but it should be noticed rather than absorbed.
    """
    eligible = payload["eligible_content_features_by_window"]
    for window in ("30_to_15_days", "14_to_8_days", "7_to_4_days",
                   "final_72_hours"):
        assert eligible[window] == []


# ---- every reported delta carries its interval ----------------------

@needs_results
def test_every_fitted_arm_has_a_bootstrap_interval(payload):
    for name, rows in payload["arms"].items():
        for row in rows:
            if "skipped" in row:
                continue
            assert row["ci_lower"] is not None and row["ci_upper"] is not None
            assert row["ci_lower"] <= row["delta_vs_recalibrated"] <= row["ci_upper"]


@needs_results
def test_all_arms_share_the_same_fitting_cells(payload):
    """Only `feature_columns` may differ between arms."""
    counts = {row["training_rows"] for rows in payload["arms"].values()
              for row in rows if "skipped" not in row}
    assert counts == {payload["fitting_cells"]}
