"""Tests for adding approved previous-election fundamentals to row-index data."""

import json
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_history import (
    add_previous_election_features,
)
from no_news_baseline.electoral_fundamentals_rows import (
    build_fundamentals_row_index,
    load_party_feature_rows,
)
from contract_expectations import FUNDAMENTALS_INDEX_ROWS


def _source_feature(
    *,
    contest_id: str = "target-party-a",
    party: str = "Party A",
    approved: bool = True,
) -> dict[str, object]:
    """Create one predictor-side record with an optional approved predecessor."""

    # This fixture represents the extractor's feature-side contract. Switching
    # approved to False removes both the permission and predecessor identifiers,
    # which allows the tests to compare the two permitted code paths.
    return {
        "party_contest_id": contest_id,
        "election_id": "target-election",
        "election_date": "2021-05-06",
        "division_id": "target-area",
        "division_name": "Target Area",
        "standard_party_name": party,
        "original_party_labels": party,
        "historical_reference_status": (
            "approved_for_historical_reference"
            if approved
            else "not_approved_or_not_applicable"
        ),
        "geographic_reference_eligibility": (
            "approved_historical_reference" if approved else "no_approved_predecessor"
        ),
        "previous_election_id": "previous-election" if approved else None,
        "previous_division_name": "Previous Area" if approved else None,
        "previous_party_vote_share": 60.0 if approved else None,
        "party_was_previous_winner": True if approved else None,
        "analysis_previous_turnout": 42.0 if approved else None,
        "historical_source_url": "https://example.gov/previous" if approved else None,
    }


def _master_payload(*, previous_date: str = "2017-05-04") -> dict[str, object]:
    """Create the minimum master tables needed to retrieve the prior result."""

    # Party A wins the earlier election with 60%, Party B ranks second with
    # 40%, and the extractor's governed vote margin is 100 votes. These simple
    # values make an incorrect join or field selection visible in assertions.
    return {
        "Elections": [
            {"election_id": "previous-election", "election_date": previous_date},
            {"election_id": "target-election", "election_date": "2021-05-06"},
        ],
        "Divisions and Wards": [
            {
                "election_id": "previous-election",
                "division_id": "previous-area",
                "division_name": "Previous Area",
            }
        ],
        "Candidate Results": [
            {
                "election_id": "previous-election",
                "division_id": "previous-area",
                "original_party_name": "Party A",
                "standard_party_name": "Party A",
                "analysis_vote_share": 60.0,
                "derived_final_position": 1,
                "elected_yes_no": "Yes",
            },
            {
                "election_id": "previous-election",
                "division_id": "previous-area",
                "original_party_name": "Party B",
                "standard_party_name": "Party B",
                "analysis_vote_share": 40.0,
                "derived_final_position": 2,
                "elected_yes_no": "No",
            },
        ],
        "Analysis Voting Summary": [
            {
                "election_id": "previous-election",
                "division_id": "previous-area",
                "field_name": "analysis_winning_margin",
                "value": 100,
            }
        ],
    }


def _build(source_rows: list[dict[str, object]], payload: dict[str, object]):
    """Build the row index first, then add historical features under test."""

    row_index = build_fundamentals_row_index(source_rows)
    return add_previous_election_features(row_index, source_rows, payload)


def test_adds_approved_previous_election_predictors() -> None:
    """An approved predecessor should supply all six historical predictors."""

    row = _build([_source_feature()], _master_payload())[0]

    # Check both the historical party fields and the area-level/time fields so
    # the test covers the complete output of this construction stage.
    assert row["previous_party_vote_share"] == 60.0
    assert row["previous_party_rank"] == 1
    assert row["previous_party_was_winner"] is True
    assert row["previous_winning_margin"] == 100
    assert row["previous_turnout"] == 42.0
    assert row["days_since_previous_comparable_election"] == 1463
    assert row["previous_election_date"] == "2017-05-04"
    assert row["previous_area_id"] == "previous-area"


def test_unapproved_predecessor_keeps_historical_predictors_unknown() -> None:
    """A row without approved geography must not receive historical values."""

    row = _build([_source_feature(approved=False)], _master_payload())[0]

    # The row remains available for later descriptive fields, but every value
    # that would require an earlier comparable area stays unknown.
    assert row["previous_party_vote_share"] is None
    assert row["previous_party_rank"] is None
    assert row["previous_winning_margin"] is None
    assert row["days_since_previous_comparable_election"] is None
    assert row["historical_reference_status"] == "not_approved_or_not_applicable"


def test_future_or_same_day_source_election_is_rejected() -> None:
    """Historical predictors require a source date strictly before the target."""

    # Using the target date as the alleged previous date directly exercises the
    # temporal leakage boundary required by the feature-table specification.
    with pytest.raises(ValueError, match="must precede"):
        _build([_source_feature()], _master_payload(previous_date="2021-05-06"))


def test_rank_uses_standardised_party_in_complete_previous_result() -> None:
    """Previous rank should come from the matched prior party, not row order."""

    # Party B is deliberately the second candidate in the complete previous
    # result. The expected rank comes from its stored derived position.
    source = _source_feature()
    source["previous_party_vote_share"] = 40.0
    source["party_was_previous_winner"] = False
    source["original_party_labels"] = "Party B"
    source["standard_party_name"] = "Party B"

    row = _build([source], _master_payload())[0]

    assert row["previous_party_rank"] == 2
    assert row["previous_party_was_winner"] is False


def test_zero_previous_share_has_no_previous_rank() -> None:
    """A party absent from the previous contest has share zero but no rank."""

    source = _source_feature(party="New Party")
    source["original_party_labels"] = "New Party"
    source["previous_party_vote_share"] = 0.0
    source["party_was_previous_winner"] = False

    row = _build([source], _master_payload())[0]

    # The complete previous table proves absence, so share is zero. Rank stays
    # NULL because a party that did not contest was never placed.
    assert row["previous_party_vote_share"] == 0.0
    assert row["previous_party_rank"] is None


def test_reviewed_standard_name_handles_published_label_variation() -> None:
    """A reviewed party standardisation should support the party-level history."""

    source = _source_feature(party="Party A")
    source["original_party_labels"] = "The Party A Candidate"
    # The source-side exact-label field is zero because the published labels
    # differ, but this table is explicitly organised by standardised party.
    source["previous_party_vote_share"] = 0.0

    row = _build([source], _master_payload())[0]

    # Party A is recovered through its reviewed standard name even though the
    # target election published a longer ballot label.
    assert row["previous_party_vote_share"] == 60.0
    assert row["previous_party_rank"] == 1
    assert row["previous_party_was_winner"] is True


def test_grouped_independents_do_not_inherit_one_persons_history() -> None:
    """A grouped Independent row must not transfer one candidate's prior identity."""

    first = _source_feature(contest_id="independent-a", party="Independent")
    second = _source_feature(contest_id="independent-b", party="Independent")
    for source in (first, second):
        source["original_party_labels"] = "Independent"
        source["previous_party_vote_share"] = None
        source["party_was_previous_winner"] = True

    row = _build([first, second], _master_payload())[0]

    # A generic label cannot prove either candidate is the earlier Independent,
    # so the three identity-dependent historical fields must remain unknown.
    assert row["previous_party_vote_share"] is None
    assert row["previous_party_rank"] is None
    assert row["previous_party_was_winner"] is None


def test_real_release_adds_only_earlier_approved_history() -> None:
    """The local extractor release should satisfy the complete historical join."""

    project_root = Path(__file__).resolve().parents[1]
    extractor_outputs = project_root.parent / "surrey-election-extractor" / "outputs"
    feature_path = (
        extractor_outputs
        / "no_news_party_contests/no_news_party_contest_features.json"
    )
    master_path = (
        extractor_outputs
        / "master_surrey_election_database/master_election_database_payload.json"
    )
    # Clean clones can regenerate these extractor-owned files. The synthetic
    # unit tests above still enforce every rule when local outputs are absent.
    if not feature_path.exists() or not master_path.exists():
        pytest.skip("Regenerate extractor outputs for integration QA.")

    source_rows = load_party_feature_rows(feature_path)
    row_index = build_fundamentals_row_index(source_rows)
    master_payload = json.loads(master_path.read_text(encoding="utf-8"))
    completed = add_previous_election_features(
        row_index, source_rows, master_payload
    )

    # The join must preserve the row population, use only positive historical
    # time gaps and attach a previous election to every populated party share.
    assert len(completed) == FUNDAMENTALS_INDEX_ROWS
    assert all(
        row["days_since_previous_comparable_election"] > 0
        for row in completed
        if row["days_since_previous_comparable_election"] is not None
    )
    assert all(
        row["previous_election_id"] is not None
        for row in completed
        if row["previous_party_vote_share"] is not None
    )
