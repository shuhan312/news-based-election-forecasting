"""Tests for the by-election cost walk-through.

The properties tested are the ones that would silently mislead the
enrichment decision if wrong: holdout-period by-elections leaking into the
usable pool, cost arithmetic drifting from the declared conventions, and
the national-only scenario quietly keeping local costs.
"""

import pytest

from src.news_collection.walk_byelection_pipeline import (
    BATCH_MULTIPLIER,
    CACHE_READ_MULTIPLIER,
    OUTPUT_TOKENS_PER_REQUEST,
    PRICES,
    PROMPT_TOKENS_PER_REQUEST,
    _election_date,
    _llm_cost,
    project_stages,
)


def test_election_dates_parse_and_principal_ids_do_not():
    assert _election_date(
        "surrey-county-council-by-election-addlestone-2025-08-21"
    ).isoformat() == "2025-08-21"
    assert _election_date("SCC-2021-05") is None


def test_llm_cost_applies_batch_and_cache_conventions():
    cost = _llm_cost(100, 1_000, "claude-haiku-4-5")
    expected_input = 100 * (1_000 + PROMPT_TOKENS_PER_REQUEST * CACHE_READ_MULTIPLIER)
    assert cost["input_tokens"] == round(expected_input)
    assert cost["output_tokens"] == 100 * OUTPUT_TOKENS_PER_REQUEST
    price = PRICES["claude-haiku-4-5"]
    manual = (expected_input / 1e6 * price["input"]
              + cost["output_tokens"] / 1e6 * price["output"]) * BATCH_MULTIPLIER
    assert cost["usd_standard"] == pytest.approx(round(manual, 2))


def _rates():
    return {
        "review_pool_entry_rate": {
            "local": {"rate": 0.10, "from": "test"},
            "national": {"rate": 0.90, "from": "test"},
        },
        "include_rate_among_decided": {
            "local": {"rate": 0.40, "from": "test"},
            "national": {"rate": 0.60, "from": "test"},
        },
        "valid_stance_rate": {"rate": 0.80, "from": "test"},
        "date_investigation_rate": {"rate": 0.005, "from": "test"},
    }


def _corpus():
    return {
        "usable": {
            "articles": 1_100, "local": 1_000, "national": 100,
            "with_text": 1_000, "reform_mention_articles": 200,
        },
        "excluded_holdout_period": {"articles": 50},
        "article_tokens": {"mean": 800, "median": 700, "measured_articles": 1_000},
    }


def test_projection_pools_includes_and_manual_hours():
    projection = project_stages(_corpus(), _rates(), review_rows_per_hour=50)
    a = projection["scenario_a_both_arms"]
    # local pool 1000*0.1=100, national pool 100*0.9=90
    assert a["projected_review_pool"] == {"local": 100, "national": 90}
    assert a["projected_includes"] == round(100 * 0.4 + 90 * 0.6)
    assert a["manual_review_hours"] == pytest.approx(100 / 50, abs=0.1)
    assert a["stage_4_llm_eligibility"]["requests"] == 190


def test_national_only_scenario_has_no_local_costs():
    projection = project_stages(_corpus(), _rates(), review_rows_per_hour=50)
    b = projection["scenario_b_national_only"]
    assert b["projected_review_pool"]["local"] == 0
    assert b["manual_review_hours"] == 0
    assert b["gives_up"]


def test_reform_yield_is_labelled_an_estimate():
    projection = project_stages(_corpus(), _rates(), review_rows_per_hour=50)
    reform = projection["expected_reform_training_records"]
    assert reform["estimate"] == round(200 * 0.6 * 0.8)
    assert "Estimate" in reform["method"]
