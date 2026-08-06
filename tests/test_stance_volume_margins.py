"""Guards on the stance-volume margin computation."""

import json
from pathlib import Path

import pytest

RESULTS = Path("news_features/stance_volume_margins_v1/stance_volume_margins.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="stance_volume_margins not yet built")


@needs_results
def test_reproduction_gate_passed():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["reproduction_check_passed"]


@needs_results
def test_all_twelve_periods_present():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    windows = [m["window"] for m in payload["margins"]]
    assert len(windows) == 12
    assert len(set(windows)) == 12


@needs_results
def test_non_overlapping_and_cumulative_split():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    non_ov = [m for m in payload["margins"]
              if m["window_kind"] == "non_overlapping"]
    cumul = [m for m in payload["margins"]
             if m["window_kind"] == "cumulative"]
    assert len(non_ov) == 6
    assert len(cumul) == 6


@needs_results
def test_margin_is_stance_minus_volume():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for m in payload["margins"]:
        expected = m["stance_delta"] - m["volume_delta"]
        assert abs(m["margin"] - expected) < 1e-10, (
            f"{m['window']}: margin {m['margin']} != "
            f"stance {m['stance_delta']} - volume {m['volume_delta']}")


@needs_results
def test_volume_weighting_check_has_all_periods():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    check = payload["volume_weighting_check"]
    assert len(check) == 12


@needs_results
def test_headline_stance_wins():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    headline = next(m for m in payload["margins"]
                    if m["window"] == "90_to_31_days")
    assert headline["stance_wins"]
    assert headline["margin"] > 0
