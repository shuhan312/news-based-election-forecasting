"""Tests for the Phase 7 Step 7 missing-news representation."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.llm_extraction.freeze_layer import sha256_file
from src.news_features.missing_news import (EVIDENCE_ITEMS, STATES,
                                            assess_cell,
                                            is_valid_combination)

GRID = Path("news_features/missing_news_representation.parquet")
AGG_CSV = Path("news_features/context_aggregated_features.csv")
CONTRIB = Path("news_features/context_aggregation_contributions.json")
WEIGHTED = Path("news_features/recency_weighted_features.parquet")
FROZEN = Path("llm_context/llm_context_layer_final.json")

# The frozen LLM context layer stays out of git (copyright; OneDrive copy),
# so a fresh clone skips the rebuild test that reads it.
_needs_frozen_llm = pytest.mark.skipif(
    not FROZEN.exists(),
    reason="requires llm_context_layer_final.json (OneDrive; README large-artefacts table)",
)
MANIFEST = Path("llm_context/llm_context_version_manifest.json")

KEY = ["election_id", "geographic_target_id", "focal_party_id",
       "window_type", "window", "scope_classification"]

needs_data = pytest.mark.skipif(
    not (GRID.exists() and AGG_CSV.exists()),
    reason="grid/aggregation files not present")


def _ev(**over):
    """All evidence satisfied unless overridden."""
    e = {k: True for k in EVIDENCE_ITEMS}
    e.update(over)
    return e


# ---- state assignment unit tests -----------------------------------

def test_observed_news_wins_and_keeps_pending_flag():
    r = assess_cell(valid=True, invalid_reason="", n_articles=3,
                    evidence=_ev(external_stage_complete=False))
    assert r["coverage_status"] == "observed_news"
    assert r["news_observed_indicator"] == 1
    assert r["zero_news_indicator"] == 0
    # the pending flag survives the precedence order
    assert r["pending_stage_indicator"] == 1


def test_confirmed_zero_requires_every_evidence_item():
    r = assess_cell(valid=True, invalid_reason="", n_articles=0,
                    evidence=_ev())
    assert r["coverage_status"] == "confirmed_zero_news"
    assert r["zero_news_indicator"] == 1
    assert r["coverage_confidence"] == 1.0
    # removing any single item must break the confirmed zero
    for k in EVIDENCE_ITEMS:
        broken = assess_cell(valid=True, invalid_reason="",
                             n_articles=0, evidence=_ev(**{k: False}))
        assert broken["coverage_status"] != "confirmed_zero_news", k
        assert broken["zero_news_indicator"] == 0, k


def test_incomplete_search_never_coded_as_zero():
    r = assess_cell(valid=True, invalid_reason="", n_articles=0,
                    evidence=_ev(ward_tier_search_executed=False))
    assert r["coverage_status"] == "insufficient_search_coverage"
    assert r["insufficient_coverage_indicator"] == 1
    assert r["zero_news_indicator"] == 0


def test_source_unavailable_handling():
    r = assess_cell(valid=True, invalid_reason="", n_articles=0,
                    evidence=_ev(no_search_failures=False))
    assert r["coverage_status"] == "source_unavailable"
    assert r["source_unavailable_indicator"] == 1


def test_stage_m_pending_handling():
    r = assess_cell(valid=True, invalid_reason="", n_articles=0,
                    evidence=_ev(external_stage_complete=False))
    assert r["coverage_status"] == "pending_external_stage"
    assert r["pending_stage_indicator"] == 1
    assert r["zero_news_indicator"] == 0


def test_unresolved_processing_handling():
    r = assess_cell(valid=True, invalid_reason="", n_articles=0,
                    evidence=_ev(extraction_complete=False))
    assert r["coverage_status"] == "unresolved_processing"
    assert r["unresolved_processing_indicator"] == 1


def test_not_applicable_asserts_nothing_else():
    r = assess_cell(valid=False, invalid_reason="ward x national",
                    n_articles=0, evidence=_ev())
    assert r["coverage_status"] == "not_applicable"
    assert r["not_applicable_indicator"] == 1
    assert sum(v for k, v in r.items()
               if k.endswith("_indicator")) == 1
    assert r["coverage_confidence"] is None


def test_validity_rules():
    ok, _ = is_valid_combination("ward", "ward_specific_local",
                                 "SCC-2021-05", "Conservative")
    assert ok
    bad, reason = is_valid_combination("ward", "national_political",
                                       "SCC-2021-05", "Conservative")
    assert not bad and "never attributed to a single ward" in reason
    bad2, reason2 = is_valid_combination("election_wide",
                                         "national_political",
                                         "SCC-2013-05", "Reform UK")
    assert not bad2 and "did not exist" in reason2


# ---- integrity tests against the real grid -------------------------

@pytest.fixture(scope="module")
def grid():
    return pd.read_parquet(GRID)


@needs_data
def test_expected_grid_unique_and_single_state(grid):
    assert not grid.duplicated(subset=KEY).any()
    assert set(grid["coverage_status"]) <= set(STATES)
    # exactly one primary state per cell is structural (one column);
    # the state must agree with its own primary indicator
    for state, col in (("observed_news", "news_observed_indicator"),
                       ("confirmed_zero_news", "zero_news_indicator"),
                       ("not_applicable", "not_applicable_indicator")):
        sub = grid[grid["coverage_status"] == state]
        if len(sub):
            assert (sub[col] == 1).all()


@needs_data
def test_observed_cells_reconcile_with_aggregation(grid):
    contrib = json.loads(CONTRIB.read_text())["contributions"]
    observed = grid[grid["coverage_status"] == "observed_news"]
    assert len(observed) == len(contrib)
    for key, ids in contrib.items():
        eid, target, pid, wtype, window, scope = key.split("|")
        row = observed[(observed["election_id"] == eid)
                       & (observed["geographic_target_id"] == target)
                       & (observed["focal_party_id"] == pid)
                       & (observed["window_type"] == wtype)
                       & (observed["window"] == window)
                       & (observed["scope_classification"] == scope)]
        assert len(row) == 1
        assert int(row["n_contributing_articles"].iloc[0]) == len(ids)


@needs_data
def test_confirmed_zero_cells_have_no_articles_and_full_evidence(grid):
    zero = grid[grid["coverage_status"] == "confirmed_zero_news"]
    assert (zero["n_contributing_articles"] == 0).all()
    if len(zero):
        assert (zero["coverage_confidence"] == 1.0).all()
        for k in EVIDENCE_ITEMS:
            assert (zero[f"evidence_{k}"] == 1).all()


@needs_data
def test_no_incomplete_cell_is_coded_zero(grid):
    incomplete = grid[(grid["insufficient_coverage_indicator"] == 1)
                      | (grid["source_unavailable_indicator"] == 1)
                      | (grid["pending_stage_indicator"] == 1)
                      | (grid["unresolved_processing_indicator"] == 1)]
    assert (incomplete["zero_news_indicator"] == 0).all()


@needs_data
def test_stage_m_sensitive_cells_remain_pending(grid):
    # not_applicable cells assert nothing at all (an invalid
    # combination cannot be "pending"), so only assessable cells
    # carry the Stage M flag
    assessable = grid[grid["coverage_status"] != "not_applicable"]
    assert (assessable.loc[assessable["stage_m_records_pending"] > 0,
                           "pending_stage_indicator"] == 1).all()
    assert (grid.loc[grid["evidence_external_stage_complete"] == 0,
                     "zero_news_indicator"] == 0).all()


@needs_data
def test_local_and_national_coverage_assessed_separately(grid):
    """Ward and national scopes are assessed on separate rows and do
    not share a state; national adequacy never stands in for ward
    coverage."""
    ward_local = grid[(grid["geographic_target_level"] == "ward")
                      & (grid["scope_classification"]
                         == "ward_specific_local")]
    nat = grid[(grid["geographic_target_level"] == "election_wide")
               & (grid["scope_classification"]
                  == "national_political")]
    assert set(ward_local["coverage_status"]) \
        != set(nat["coverage_status"])
    # a ward-tier search that never ran can never be a confirmed zero,
    # whatever the national arm looks like
    assert (ward_local.loc[ward_local[
        "evidence_ward_tier_search_executed"] == 0,
        "zero_news_indicator"] == 0).all()


@needs_data
def test_sampling_frame_scopes_the_ward_grid(grid):
    """Ward-tier collection was pre-registered over 17 divisions
    (supervisor to-do 7). Inside that frame the search actually ran;
    outside it the cells are not_applicable, not 'insufficient
    coverage' - they were never in scope."""
    ward = grid[grid["geographic_target_level"] == "ward"]
    inside = ward[ward["in_division_sample"] == 1]
    outside = ward[(ward["in_division_sample"] == 0)
                   & (ward["n_contributing_articles"] == 0)]
    assert len(inside) > 0 and len(outside) > 0
    assert (inside["evidence_ward_tier_search_executed"] == 1).all()
    assert (outside["coverage_status"] == "not_applicable").all()
    # an observation is never erased by the sampling frame
    observed_outside = ward[(ward["in_division_sample"] == 0)
                            & (ward["n_contributing_articles"] > 0)]
    if len(observed_outside):
        assert (observed_outside["coverage_status"]
                == "observed_news").all()


@needs_data
def test_invalid_combinations_marked_not_applicable(grid):
    ward_nat = grid[(grid["geographic_target_level"] == "ward")
                    & (grid["scope_classification"].isin(
                        ["national_political", "regional"]))
                    & (grid["grid_source"] == "expected_grid")]
    assert len(ward_nat) > 0
    assert (ward_nat["coverage_status"] == "not_applicable").all()
    reform_2013 = grid[(grid["election_id"] == "SCC-2013-05")
                       & (grid["focal_party_name"] == "Reform UK")]
    assert len(reform_2013) > 0
    assert (reform_2013["coverage_status"] == "not_applicable").all()


@needs_data
@_needs_frozen_llm
def test_deterministic_rebuild_and_previous_outputs_unchanged():
    m = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == m["frozen_output_sha256"][FROZEN.name]
    agg_before = AGG_CSV.read_bytes()
    weighted_before = sha256_file(WEIGHTED)
    before = pd.read_parquet(GRID)
    from src.news_features.run_missing_news import build
    build()
    pd.testing.assert_frame_equal(pd.read_parquet(GRID), before)
    assert AGG_CSV.read_bytes() == agg_before
    assert sha256_file(WEIGHTED) == weighted_before


@needs_data
def test_re_execution_responds_to_new_articles():
    """Adding articles to a cell must flip it to observed_news
    deterministically - simulated at the assessment level so no
    frozen input is touched."""
    empty = assess_cell(valid=True, invalid_reason="", n_articles=0,
                        evidence=_ev(external_stage_complete=False))
    filled = assess_cell(valid=True, invalid_reason="", n_articles=2,
                         evidence=_ev(external_stage_complete=False))
    assert empty["coverage_status"] == "pending_external_stage"
    assert filled["coverage_status"] == "observed_news"
    # and once Stage M completes, an empty cell can finally confirm
    done = assess_cell(valid=True, invalid_reason="", n_articles=0,
                       evidence=_ev())
    assert done["coverage_status"] == "confirmed_zero_news"
