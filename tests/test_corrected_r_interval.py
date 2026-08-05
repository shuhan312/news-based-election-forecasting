"""Guards on the attenuation-corrected r bootstrap interval."""

import json
from pathlib import Path

import pytest

RESULTS = Path("news_features/corrected_r_interval_v1/corrected_r_interval.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="corrected_r_interval not yet built")


@needs_results
def test_observed_r_is_positive():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["observed_r"] > 0


@needs_results
def test_reliability_between_zero_and_one():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert 0 < payload["reliability"] < 1


@needs_results
def test_corrected_r_larger_than_observed():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["corrected_r"] > payload["observed_r"]


@needs_results
def test_corrected_r_equals_observed_over_sqrt_reliability():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    import math
    expected = payload["observed_r"] / math.sqrt(payload["reliability"])
    assert abs(payload["corrected_r"] - round(expected, 4)) < 1e-3


@needs_results
def test_bootstrap_interval_contains_point_estimate():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    ci = payload["bootstrap_corrected_r"]
    assert ci["ci_lower"] <= payload["corrected_r"] <= ci["ci_upper"]


@needs_results
def test_corrected_interval_wider_than_observed():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    obs_width = (payload["bootstrap_observed_r"]["ci_upper"]
                 - payload["bootstrap_observed_r"]["ci_lower"])
    cor_width = (payload["bootstrap_corrected_r"]["ci_upper"]
                 - payload["bootstrap_corrected_r"]["ci_lower"])
    assert cor_width > obs_width
