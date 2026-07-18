"""Tests for the leakage-safe party-contest no-news publication."""

from types import SimpleNamespace

import pytest

from election_extractor.no_news_party_contest import (
    TARGET_ONLY_FIELDS,
    build_no_news_party_contests,
)


def _division(
    election_id: str,
    division_id: str,
    name: str,
    *,
    seats: int,
    turnout: float,
    previous_election_id: str | None = None,
    previous_name: str | None = None,
) -> dict[str, object]:
    approved = previous_election_id is not None
    return {
        "election_id": election_id,
        "division_id": division_id,
        "division_name": name,
        "official_number_of_seats": seats,
        "secondary_number_of_seats": None,
        "turnout": turnout,
        "historical_reference_status": (
            "approved_pre_2024_legal_continuity"
            if approved
            else "not_approved_or_not_applicable"
        ),
        "previous_election_id": previous_election_id,
        "previous_division_name": previous_name,
        "previous_winning_party": "Party A" if approved else None,
        "previous_winning_candidate_vote_share": 50.0 if approved else None,
        "previous_electorate": 10_000 if approved else None,
        "historical_source_url": "https://official.example/previous" if approved else None,
        "historical_permission_source_urls": "https://law.example/order" if approved else None,
    }


def _candidate(
    election_id: str,
    division_id: str,
    candidate_id: str,
    party: str,
    *,
    share: float,
    elected: str,
    previous_share: float | None,
    category: str = "established",
) -> dict[str, object]:
    return {
        "election_id": election_id,
        "division_id": division_id,
        "candidate_id": candidate_id,
        "original_party_name": party,
        "standard_party_name": party,
        "party_category": category,
        "source_url": f"https://official.example/{division_id}",
        "analysis_vote_share": share,
        "elected_yes_no": elected,
        "previous_party_vote_share": previous_share,
        "previous_party_vote_share_status": (
            "derived_single_member_exact_label_prior_candidate_share"
            if previous_share is not None
            else "not_derived_no_approved_exact_label_reference"
        ),
        "party_previously_contested": previous_share is not None,
        "first_appearance_of_party_in_area": previous_share is None,
        "party_history_status": (
            "approved_direct_exact_label" if previous_share is not None else "unavailable"
        ),
        "incumbent_candidate_yes_no": "No",
        "incumbent_party_yes_no": "Yes" if party == "Party A" else "No",
        "incumbent_party_yes_no_status": "derived_from_approved_previous_winner",
    }


def _payload() -> SimpleNamespace:
    elections = (
        {
            "election_id": "2013",
            "election_date": "2 May 2013",
            "election_year": 2013,
            "election_type": "County Council election",
            "authority": "Council",
        },
        {
            "election_id": "2017",
            "election_date": "4 May 2017",
            "election_year": 2017,
            "election_type": "County Council election",
            "authority": "Council",
        },
        {
            "election_id": "2026",
            "election_date": "7 May 2026",
            "election_year": 2026,
            "election_type": "Unitary Council election",
            "authority": "New Council",
        },
    )
    divisions = (
        _division("2013", "2013:a", "A", seats=1, turnout=30.0),
        _division(
            "2017", "2017:a", "A", seats=1, turnout=35.0,
            previous_election_id="2013", previous_name="A",
        ),
        _division(
            "2026", "2026:a", "A Ward", seats=2, turnout=40.0,
            previous_election_id="2017", previous_name="A",
        ),
    )
    candidates = (
        _candidate("2013", "2013:a", "old-a", "Party A", share=50.0, elected="Yes", previous_share=None),
        _candidate("2013", "2013:a", "old-b", "Party B", share=50.0, elected="No", previous_share=None),
        _candidate("2017", "2017:a", "new-a", "Party A", share=55.0, elected="Yes", previous_share=50.0),
        _candidate("2017", "2017:a", "new-b", "Party B", share=45.0, elected="No", previous_share=40.0),
        _candidate("2026", "2026:a", "a-1", "Party A", share=30.0, elected="Yes", previous_share=55.0),
        _candidate("2026", "2026:a", "a-2", "Party A", share=25.0, elected="No", previous_share=55.0),
        _candidate("2026", "2026:a", "i-1", "Independent", share=10.0, elected="Yes", previous_share=None, category="independent"),
        _candidate("2026", "2026:a", "i-2", "Independent", share=8.0, elected="No", previous_share=None, category="independent"),
    )
    return SimpleNamespace(
        elections=elections,
        divisions_and_wards=divisions,
        candidate_results=candidates,
        supplementary_metadata=(),
    )


def test_party_contest_release_separates_features_and_targets() -> None:
    features, targets, coverage = build_no_news_party_contests(_payload())

    assert not (set(features[0]) & TARGET_ONLY_FIELDS)
    assert {row["party_contest_id"] for row in features} == {
        row["party_contest_id"] for row in targets
    }
    assert coverage["party_contest_rows"] == len(features)

    party_a_2017 = next(
        row for row in features
        if row["election_id"] == "2017" and row["standard_party_name"] == "Party A"
    )
    assert party_a_2017["baseline_eligibility"] == "eligible_primary_single_member_party_share"
    assert party_a_2017["previous_party_vote_share"] == 50.0
    target = next(
        row for row in targets if row["party_contest_id"] == party_a_2017["party_contest_id"]
    )
    assert target["target_party_vote_share"] == 55.0
    assert target["target_party_elected"] == "Yes"


def test_multi_member_party_is_grouped_without_inventing_party_vote_share() -> None:
    features, targets, _ = build_no_news_party_contests(_payload())

    party_a = next(
        row for row in features
        if row["election_id"] == "2026" and row["standard_party_name"] == "Party A"
    )
    assert party_a["candidate_count_for_party"] == 2
    assert party_a["contest_structure"] == "multi_member"
    assert party_a["baseline_eligibility"] == "excluded_non_single_member_primary_estimand"
    target = next(
        row for row in targets if row["party_contest_id"] == party_a["party_contest_id"]
    )
    assert target["target_party_vote_share"] is None
    assert target["target_best_candidate_vote_share"] == 30.0
    assert target["target_party_elected"] == "Yes"
    assert target["target_party_seats_won"] == 1


def test_generic_independents_remain_separate_party_contests() -> None:
    features, _, _ = build_no_news_party_contests(_payload())
    independents = [
        row for row in features
        if row["election_id"] == "2026" and row["standard_party_name"] == "Independent"
    ]
    assert len(independents) == 2
    assert all(row["party_identity_scope"] == "candidate_specific_independent" for row in independents)


def test_future_historical_reference_is_rejected() -> None:
    payload = _payload()
    divisions = list(payload.divisions_and_wards)
    divisions[1] = {
        **divisions[1],
        "previous_election_id": "2026",
        "previous_division_name": "A Ward",
    }
    payload.divisions_and_wards = tuple(divisions)

    with pytest.raises(ValueError, match="non-prior election"):
        build_no_news_party_contests(payload)
