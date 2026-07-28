"""Tests for the formal leakage audit.

The brief asks for "automated tests that fail if a prohibited field enters the
feature matrix". These are those tests, plus checks that the audit itself
stays complete as the release evolves.
"""

import pytest

from no_news_baseline.candidate_leakage_audit import (
    EXCLUDED,
    EXCLUDED_BY_CONSTRUCTION,
    FEATURE_COLUMNS,
    PERMITTED,
    PREDICTOR,
    PROHIBITED_FIELDS,
    assert_no_prohibited_column,
    build_leakage_audit,
    permitted_predictors,
)


REQUIRED_COLUMNS = {
    "field_name",
    "source_sheet",
    "verdict",
    "reason",
    "earliest_availability_event",
    "restrictions",
    "permission_field",
}


def test_audit_emits_the_schema_the_brief_specifies() -> None:
    rows = build_leakage_audit(["election_year"], ["target_candidate_vote_share"])
    assert REQUIRED_COLUMNS <= set(rows[0])


def test_every_published_feature_column_receives_a_verdict() -> None:
    columns = ["election_year", "previous_party_vote_share", "candidate_id"]
    rows = build_leakage_audit(columns, [])
    feature_rows = [row for row in rows if row["table"] == "candidate_features"]

    assert {row["field_name"] for row in feature_rows} == set(columns)
    # Published columns are permitted to exist; whether they may be modelled
    # is the separate allowed_as_predictor verdict.
    assert all(row["verdict"] == PERMITTED for row in feature_rows)
    allowed = {row["field_name"]: row["allowed_as_predictor"] for row in feature_rows}
    assert allowed["previous_party_vote_share"] == "yes"
    assert allowed["candidate_id"] == "no"


def test_an_unclassified_column_stops_the_audit() -> None:
    """A new release column must not default to permitted."""

    with pytest.raises(ValueError, match="no leakage classification"):
        build_leakage_audit(["something_new_from_the_extractor"], [])


def test_target_columns_are_recorded_as_excluded() -> None:
    rows = build_leakage_audit([], ["target_candidate_vote_share"])
    row = next(r for r in rows if r["field_name"] == "target_candidate_vote_share")
    assert row["verdict"] == EXCLUDED
    assert row["allowed_as_predictor"] == "no"
    assert row["earliest_availability_event"] == "target_election_declaration"


def test_the_briefs_named_prohibitions_all_appear() -> None:
    """Silence is not evidence. Each prohibited field is listed even though
    the feature table never publishes it."""

    rows = build_leakage_audit([], [])
    excluded = {
        row["field_name"]
        for row in rows
        if row["verdict"] == EXCLUDED_BY_CONSTRUCTION
    }
    for field in (
        "votes", "vote_share", "analysis_vote_share", "outcome",
        "elected_yes_no", "final_position", "derived_final_position",
        "derived_final_position_tied", "winning_margin", "turnout",
        "ballot_papers_issued", "total_votes", "rejected_ballots",
        "change_in_vote_share",
    ):
        assert field in excluded


def test_change_in_vote_share_is_excluded_for_the_stated_reason() -> None:
    """It looks historical but contains the target by construction."""

    rows = build_leakage_audit([], [])
    row = next(r for r in rows if r["field_name"] == "change_in_vote_share")
    assert "contains the target by" in str(row["reason"])


def test_previous_and_current_turnout_are_treated_differently() -> None:
    rows = build_leakage_audit(["analysis_previous_turnout"], [])
    permitted_row = next(
        r for r in rows if r["field_name"] == "analysis_previous_turnout"
    )
    prohibited_row = next(r for r in rows if r["field_name"] == "turnout")

    assert permitted_row["allowed_as_predictor"] == "yes"
    assert prohibited_row["verdict"] == EXCLUDED_BY_CONSTRUCTION


# --- the feature-matrix guard --------------------------------------------


def test_prohibited_column_in_a_feature_matrix_raises() -> None:
    with pytest.raises(ValueError, match="Prohibited outcome columns"):
        assert_no_prohibited_column(["previous_party_vote_share", "analysis_vote_share"])


def test_identifier_and_linkage_columns_in_a_feature_matrix_raise() -> None:
    """Candidate identity must not become a high-cardinality predictor."""

    with pytest.raises(ValueError, match="Non-predictor columns"):
        assert_no_prohibited_column(["previous_party_vote_share", "candidate_id"])


def test_a_clean_feature_matrix_passes() -> None:
    assert_no_prohibited_column(
        ["previous_party_vote_share", "election_type", "is_reform_uk"]
    )


# --- the permitted predictor list ----------------------------------------


def test_permitted_predictors_excludes_identity_and_provenance() -> None:
    predictors = permitted_predictors()

    assert "previous_party_vote_share" in predictors
    assert "is_reform_uk" in predictors
    assert "is_ukip" in predictors
    assert "candidate_id" not in predictors
    assert "candidate_name" not in predictors
    assert "current_result_source_url" not in predictors
    assert "historical_reference_status" not in predictors
    assert "candidate_baseline_eligibility" not in predictors


def test_permitted_predictors_and_the_guard_agree() -> None:
    """The single source of truth: anything the list returns must pass the
    guard, so a model built from the list can never trip it."""

    assert_no_prohibited_column(permitted_predictors())


def test_reform_and_ukip_are_both_predictors_and_separately_documented() -> None:
    assert FEATURE_COLUMNS["is_reform_uk"][0] == PREDICTOR
    assert FEATURE_COLUMNS["is_ukip"][0] == PREDICTOR
    assert "Never combined" in FEATURE_COLUMNS["is_reform_uk"][3]
    assert "Strictly separate" in FEATURE_COLUMNS["is_ukip"][3]


def test_no_prohibited_field_is_also_a_published_feature() -> None:
    assert not set(PROHIBITED_FIELDS) & set(FEATURE_COLUMNS)
