"""Guards on the by-election enrichment analysis."""

import json
from pathlib import Path

import pytest

RESULTS = Path("news_features/byelection_enrichment_v1/byelection_enrichment.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="byelection_enrichment not yet built")


@needs_results
def test_total_cells_is_sum_of_subsets():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert (payload["general_election_cells"] + payload["by_election_cells"]
            == payload["total_cells"])


@needs_results
def test_eight_byelection_events():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert payload["by_election_events"] == 8


@needs_results
def test_general_elections_have_higher_reliability():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    s = payload["subsets"]
    assert (s["general_elections_only"]["reliability"]
            > s["all_45_cells"]["reliability"])


@needs_results
def test_byelection_cells_are_all_single_contest():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    s = payload["subsets"]["by_elections_only"]
    assert s["single_contest_cells"] == s["n_cells"]


@needs_results
def test_general_elections_have_no_single_contest():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    s = payload["subsets"]["general_elections_only"]
    assert s["single_contest_cells"] == 0
