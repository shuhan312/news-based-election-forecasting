"""Tests for the leakage-safe candidate-contest no-news publication.

The behaviour under test is the one that motivated the module: a multi-member
2026 ward must produce eligible prediction targets.  A party vote share is
undefined in such a contest, which is why the earlier party-contest
development route (since retired) could not score the 2026 holdout.
"""

from types import SimpleNamespace

import pytest

from election_extractor.no_news_candidate_contest import (
    LINKAGE_ONLY_FIELDS,
    TARGET_ONLY_FIELDS,
    build_no_news_candidate_contests,
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
        "historical_source_url": (
            "https://official.example/previous" if approved else None
        ),
        "historical_permission_source_urls": (
            "https://law.example/order" if approved else None
        ),
    }


def _candidate(
    election_id: str,
    division_id: str,
    candidate_id: str,
    party: str,
    *,
    share: float,
    votes: int,
    elected: str,
    rank: int,
    previous_share: float | None,
    category: str = "established",
) -> dict[str, object]:
    return {
        "election_id": election_id,
        "division_id": division_id,
        "candidate_id": candidate_id,
        "candidate_name": f"{candidate_id} Name",
        "standard_candidate_name": f"{candidate_id} Name",
        "original_party_name": party,
        "standard_party_name": party,
        "party_category": category,
        "source_url": f"https://official.example/{division_id}",
        "votes": votes,
        "analysis_vote_share": share,
        "analysis_vote_share_provenance": "official_result_page",
        "analysis_vote_share_status": "official_vote_share_retained",
        "elected_yes_no": elected,
        "derived_final_position": rank,
        "derived_final_position_tied": False,
        "derived_final_position_status": (
            "derived_competition_rank_from_complete_official_votes"
        ),
        "previous_party_vote_share": previous_share,
        "previous_party_vote_share_status": (
            "derived_single_member_exact_label_prior_candidate_share"
            if previous_share is not None
            else "not_derived_no_approved_exact_label_reference"
        ),
        "candidate_previously_stood": False,
        "candidate_history_status": "resolved_complete_prior_candidate_universe",
        "party_previously_contested": previous_share is not None,
        "first_appearance_of_party_in_area": previous_share is None,
        "party_history_status": (
            "approved_direct_exact_label" if previous_share is not None else "unavailable"
        ),
        "incumbent_candidate_yes_no": "No",
        "incumbent_candidate_yes_no_status": "resolved_from_prior_roster",
        "incumbent_party_yes_no": "Yes" if party == "Party A" else "No",
        "incumbent_party_yes_no_status": "derived_from_approved_previous_winner",
    }


def _payload() -> SimpleNamespace:
    """Three elections: two single-member, then a two-member 2026 ward.

    Shares within every contest sum to 100 exactly, matching the observed
    Surrey convention that a published candidate share divides by all votes
    cast in that contest - in two-member wards as well as single-member ones.
    """

    elections = (
        {
            "election_id": "2017",
            "election_date": "4 May 2017",
            "election_year": 2017,
            "election_type": "County Council election",
            "authority": "Council",
        },
        {
            "election_id": "2021",
            "election_date": "6 May 2021",
            "election_year": 2021,
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
        _division("2017", "2017:a", "A", seats=1, turnout=35.0),
        _division(
            "2021", "2021:a", "A", seats=1, turnout=40.0,
            previous_election_id="2017", previous_name="A",
        ),
        # The holdout shape: two seats, and no approved predecessor, which is
        # what a changed 2026 boundary looks like in the release.
        _division("2026", "2026:a", "A Ward", seats=2, turnout=45.0),
    )
    candidates = (
        _candidate(
            "2017", "2017:a", "old-a", "Party A",
            share=60.0, votes=600, elected="Yes", rank=1, previous_share=None,
        ),
        _candidate(
            "2017", "2017:a", "old-b", "Party B",
            share=40.0, votes=400, elected="No", rank=2, previous_share=None,
        ),
        _candidate(
            "2021", "2021:a", "mid-a", "Party A",
            share=55.0, votes=550, elected="Yes", rank=1, previous_share=60.0,
        ),
        _candidate(
            "2021", "2021:a", "mid-b", "Reform UK",
            share=45.0, votes=450, elected="No", rank=2, previous_share=None,
        ),
        # Two-member ward: Party A fields two candidates, so its support is
        # split across two ballot lines.
        _candidate(
            "2026", "2026:a", "a-1", "Party A",
            share=30.0, votes=300, elected="Yes", rank=1, previous_share=None,
        ),
        _candidate(
            "2026", "2026:a", "a-2", "Party A",
            share=25.0, votes=250, elected="Yes", rank=2, previous_share=None,
        ),
        _candidate(
            "2026", "2026:a", "r-1", "Reform UK",
            share=20.0, votes=200, elected="No", rank=3, previous_share=None,
        ),
        _candidate(
            "2026", "2026:a", "u-1", "UK Independence Party",
            share=15.0, votes=150, elected="No", rank=4, previous_share=None,
        ),
        _candidate(
            "2026", "2026:a", "i-1", "Independent",
            share=10.0, votes=100, elected="No", rank=5, previous_share=None,
            category="independent",
        ),
    )
    return SimpleNamespace(
        elections=elections,
        divisions_and_wards=divisions,
        candidate_results=candidates,
        supplementary_metadata=(),
    )


def test_release_separates_features_and_targets() -> None:
    features, targets, coverage = build_no_news_candidate_contests(_payload())

    # No outcome field may reach the feature table.
    assert not (set(features[0]) & TARGET_ONLY_FIELDS)
    # Features and targets cover exactly the same rows; no silent inner join.
    assert {row["candidate_contest_id"] for row in features} == {
        row["candidate_contest_id"] for row in targets
    }
    assert coverage["candidate_contest_rows"] == len(features) == 9


def test_multi_member_2026_rows_are_eligible_prediction_targets() -> None:
    """The regression this module exists to prevent.

    Every 2026 candidate must be an eligible target even though the ward
    returns two members and has no approved historical predecessor.
    """

    features, targets, coverage = build_no_news_candidate_contests(_payload())
    target_by_id = {row["candidate_contest_id"]: row for row in targets}

    rows_2026 = [row for row in features if row["election_id"] == "2026"]
    assert len(rows_2026) == 5
    assert all(row["contest_structure"] == "multi_member" for row in rows_2026)
    assert all(
        row["candidate_baseline_eligibility"] == "eligible_candidate_vote_share"
        for row in rows_2026
    )
    assert coverage["eligible_by_election_2026"] == 5
    assert coverage["eligible_by_structure_multi_member"] == 5

    # And they carry a real observed target.
    shares = {
        target_by_id[row["candidate_contest_id"]]["target_candidate_vote_share"]
        for row in rows_2026
    }
    assert shares == {30.0, 25.0, 20.0, 15.0, 10.0}


def test_missing_history_is_a_missingness_label_not_an_exclusion() -> None:
    """A changed boundary must not remove a row from the cohort."""

    features, _, _ = build_no_news_candidate_contests(_payload())

    row = next(
        row for row in features
        if row["election_id"] == "2026" and row["candidate_id"] == "a-1"
    )
    # No approved predecessor area...
    assert row["previous_party_vote_share"] is None
    assert row["historical_predictor_availability"] == "no_approved_area_reference"
    # ...but still a prediction target.
    assert row["candidate_baseline_eligibility"] == "eligible_candidate_vote_share"

    # Where history does exist it is labelled as such.
    row_2021 = next(
        row for row in features
        if row["election_id"] == "2021" and row["candidate_id"] == "mid-a"
    )
    assert row_2021["previous_party_vote_share"] == 60.0
    assert row_2021["historical_predictor_availability"] == "approved_previous_party_share"


def test_reform_and_ukip_carry_separate_indicators() -> None:
    features, _, coverage = build_no_news_candidate_contests(_payload())

    reform = [row for row in features if row["is_reform_uk"]]
    ukip = [row for row in features if row["is_ukip"]]

    assert len(reform) == 2
    assert len(ukip) == 1
    # Disjoint by construction: no row is ever both.
    assert not any(row["is_ukip"] for row in reform)
    assert not any(row["is_reform_uk"] for row in ukip)
    assert coverage["eligible_reform_uk_rows"] == 2
    assert coverage["eligible_ukip_rows"] == 1
    # Reform observations are reported per election, because fold-level Reform
    # sample size is the project's binding constraint.
    assert coverage["eligible_reform_uk_2026"] == 1


def test_contest_structure_counts_are_attached_to_every_row() -> None:
    features, _, _ = build_no_news_candidate_contests(_payload())

    party_a_2026 = [
        row for row in features
        if row["election_id"] == "2026" and row["standard_party_name"] == "Party A"
    ]
    assert len(party_a_2026) == 2
    for row in party_a_2026:
        assert row["analysis_number_of_seats"] == 2
        assert row["candidate_count_in_contest"] == 5
        # Party A fielded two of the five candidates; the mechanical share
        # split this causes is information the model receives explicitly.
        assert row["party_candidate_count_in_contest"] == 2
        # Two independents would be two identities; here there is one.
        assert row["party_count_in_contest"] == 4


def test_independents_stay_candidate_specific() -> None:
    features, _, _ = build_no_news_candidate_contests(_payload())

    independent = next(row for row in features if row["candidate_id"] == "i-1")
    assert independent["party_identity_scope"] == "candidate_specific_independent"
    assert independent["party_group_key"] == "independent_candidate:i-1"


def test_linkage_fields_are_published_but_declared_non_predictive() -> None:
    features, _, _ = build_no_news_candidate_contests(_payload())

    # Present, because historical linkage is impossible without them...
    assert LINKAGE_ONLY_FIELDS <= set(features[0])
    # ...and declared, so the modelling layer can drop them by contract.
    assert "candidate_id" in LINKAGE_ONLY_FIELDS
    assert "standard_candidate_name" in LINKAGE_ONLY_FIELDS


def test_secondary_targets_are_published_with_the_primary_target() -> None:
    _, targets, coverage = build_no_news_candidate_contests(_payload())

    elected = next(row for row in targets if row["candidate_id"] == "a-1")
    assert elected["target_candidate_elected"] == "Yes"
    assert elected["target_candidate_rank"] == 1
    assert elected["target_candidate_votes"] == 300
    assert coverage["target_rank_available"] == 9
    assert coverage["target_elected_resolved"] == 9


def test_unknown_seat_structure_is_excluded_with_a_reason() -> None:
    """Without seats the estimand cannot be normalised or a winner selected."""

    payload = _payload()
    divisions = list(payload.divisions_and_wards)
    divisions[2] = {
        **divisions[2],
        "official_number_of_seats": None,
        "secondary_number_of_seats": None,
    }
    payload.divisions_and_wards = tuple(divisions)

    features, _, coverage = build_no_news_candidate_contests(payload)
    rows_2026 = [row for row in features if row["election_id"] == "2026"]

    assert all(
        row["candidate_baseline_eligibility"] == "excluded_unknown_seat_structure"
        for row in rows_2026
    )
    # Excluded, but retained and counted - never silently dropped.
    assert len(rows_2026) == 5
    assert coverage["eligibility_excluded_unknown_seat_structure"] == 5


def test_missing_observed_share_is_excluded_with_a_reason() -> None:
    payload = _payload()
    candidates = list(payload.candidate_results)
    candidates[4] = {**candidates[4], "analysis_vote_share": None}
    payload.candidate_results = tuple(candidates)

    features, _, _ = build_no_news_candidate_contests(payload)
    row = next(row for row in features if row["candidate_id"] == "a-1")

    assert (
        row["candidate_baseline_eligibility"]
        == "excluded_no_observed_candidate_vote_share"
    )


def test_contest_shares_outside_publication_rounding_fail_the_build() -> None:
    """A gross reconciliation failure stops the release rather than being
    silently renormalised."""

    payload = _payload()
    candidates = list(payload.candidate_results)
    # Drive the 2026 contest sum far outside 100 +/- (2 + 0.5 * 5).
    candidates[4] = {**candidates[4], "analysis_vote_share": 80.0}
    payload.candidate_results = tuple(candidates)

    with pytest.raises(ValueError, match="do not reconcile to the contest total"):
        build_no_news_candidate_contests(payload)


def test_publication_rounding_within_tolerance_is_accepted() -> None:
    """Whole-percentage publication makes a real contest sum to 99 or 101."""

    payload = _payload()
    candidates = list(payload.candidate_results)
    candidates[4] = {**candidates[4], "analysis_vote_share": 31.0}
    payload.candidate_results = tuple(candidates)

    features, _, _ = build_no_news_candidate_contests(payload)
    assert len(features) == 9


def test_historical_reference_must_precede_the_target_election() -> None:
    payload = _payload()
    divisions = list(payload.divisions_and_wards)
    # Point 2017 at 2021 - a future election.
    divisions[0] = {
        **divisions[0],
        "previous_election_id": "2021",
        "previous_division_name": "A",
        "historical_reference_status": "approved_pre_2024_legal_continuity",
    }
    payload.divisions_and_wards = tuple(divisions)

    with pytest.raises(ValueError, match="non-prior election event"):
        build_no_news_candidate_contests(payload)
