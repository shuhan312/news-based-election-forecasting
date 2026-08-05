"""Guards on the stance vs volume 2021 validation harness."""

import json
from pathlib import Path

import pytest

RESULTS = Path("news_features/stance_volume_2021_v1/stance_volume_2021.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="stance_volume_2021 not yet built")


@needs_results
def test_fit_election_is_2017():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["fit_election"] == "surrey-county-council-2017"


@needs_results
def test_validation_election_is_2021():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["validation_election"] == "surrey-county-council-2021"


@needs_results
def test_stance_wins_all_non_empty():
    """The 10-of-10 claim."""
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    s = payload["summary"]
    assert s["stance_wins_non_empty"] == s["total_non_empty"]


@needs_results
def test_at_least_five_non_empty():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["summary"]["total_non_empty"] >= 5


@needs_results
def test_margin_positive_when_stance_wins():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    for m in payload["margins"]:
        if m["stance_wins"]:
            assert m["margin"] > 0
