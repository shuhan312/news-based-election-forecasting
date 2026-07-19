"""Tests for the fundamentals row definition and leakage contract only."""

from copy import deepcopy

import pytest

import no_news_baseline.electoral_fundamentals_schema as schema


def test_predictors_and_current_election_evaluation_are_separate() -> None:
    schema.validate_schema_contract()

    assert set(schema.PREDICTOR_COLUMNS).isdisjoint(schema.EVALUATION_COLUMNS)
    assert not set(schema.PREDICTOR_COLUMNS) & schema.FORBIDDEN_CURRENT_OUTCOME_COLUMNS


def test_reform_and_ukip_have_separate_historical_columns() -> None:
    assert "previous_party_vote_share" in schema.PREDICTOR_COLUMNS
    assert "previous_ukip_vote_share_in_area" in schema.PREDICTOR_COLUMNS
    assert "previous_reform_or_ukip_vote_share" not in schema.PREDICTOR_COLUMNS


def test_election_area_standard_party_key_must_be_unique() -> None:
    row = {
        "election_id": "surrey-2021",
        "area_id": "area-a",
        "standard_party_name": "Party A",
    }

    with pytest.raises(ValueError, match="Duplicate"):
        schema.validate_unique_row_keys([row, deepcopy(row)])


def test_all_required_leakage_rules_are_declared() -> None:
    rule_ids = {rule.rule_id for rule in schema.LEAKAGE_RULES}

    assert rule_ids == {
        "source_date_precedes_target",
        "no_current_outcome_predictors",
        "no_same_election_surrey_wide_features",
        "reform_ukip_identity_separation",
        "approved_geography_only",
        "unique_election_area_party_row",
    }
