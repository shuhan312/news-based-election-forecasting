"""Tests for the reuse-only coverage evaluation cohort layer."""

import pytest

from no_news_baseline.coverage_evaluation import (
    COHORT_GEOGRAPHICALLY_NON_COMPARABLE,
    COHORT_HISTORICAL_CONTINUITY,
    COHORT_PARTY_ENTRY_NO_LOCAL_HISTORY,
    build_evaluation_universe,
)


def _feature(
    contest_id: str,
    election_id: str,
    election_date: str,
    area: str,
    party: str,
    *,
    contest_structure: str = "single_member",
    baseline_eligibility: str = "eligible_primary_single_member_party_share",
    geographic_reference_eligibility: str = "approved_historical_reference",
    previous_party_vote_share: float | None = None,
    party_was_previous_winner: bool | None = None,
    previous_party_vote_share_status: str = "derived_single_member_exact_label_prior_candidate_share",
) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "election_id": election_id,
        "election_date": election_date,
        "election_year": int(election_date[-4:]),
        "election_type": "County Council election",
        "division_id": area,
        "division_name": area,
        "standard_party_name": party,
        "contest_structure": contest_structure,
        "geographic_reference_eligibility": geographic_reference_eligibility,
        "party_identity_scope": "reviewed_standard_party",
        "baseline_eligibility": baseline_eligibility,
        "previous_party_vote_share": previous_party_vote_share,
        "previous_party_vote_share_status": previous_party_vote_share_status,
        "party_was_previous_winner": party_was_previous_winner,
        "historical_source_url": "https://official.example/previous",
    }


def _target(
    contest_id: str,
    party: str,
    share: float | None,
    elected: str,
    *,
    status: str = "analysis_candidate_share_equals_single_member_party_share",
) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "standard_party_name": party,
        "target_party_vote_share": share,
        "target_party_vote_share_status": status,
        "target_party_elected": elected,
        "target_source_urls": "https://official.example/current",
    }


def test_cohort_a_rows_have_safe_previous_local_history() -> None:
    features = (
        _feature(
            "a",
            "2017",
            "4 May 2017",
            "area-a",
            "Party A",
            previous_party_vote_share=55.0,
            party_was_previous_winner=True,
        ),
    )
    targets = (_target("a", "Party A", 52.0, "Yes"),)

    universe = build_evaluation_universe(features, targets)

    row = universe[0]
    assert row["primary_cohort"] == COHORT_HISTORICAL_CONTINUITY
    assert row["previous_party_vote_share"] == 55.0
    assert row["cohort_reason"] == "eligible_primary_single_member_party_share"


def test_cohort_b_rows_have_no_safe_previous_local_same_party_history() -> None:
    # Area has an accepted predecessor, but this party's own row is excluded
    # (e.g. a multi-member contest, so the share estimand is not defined).
    features = (
        _feature(
            "b",
            "2026",
            "7 May 2026",
            "area-b",
            "Reform UK",
            contest_structure="multi_member",
            baseline_eligibility="excluded_non_single_member_primary_estimand",
            geographic_reference_eligibility="approved_historical_reference",
            previous_party_vote_share=None,
            previous_party_vote_share_status="not_derived_no_approved_exact_label_reference",
        ),
    )
    targets = (
        _target(
            "b",
            "Reform UK",
            None,
            "No",
            status="not_defined_for_multi_member_party_contest",
        ),
    )

    universe = build_evaluation_universe(features, targets)

    row = universe[0]
    assert row["primary_cohort"] == COHORT_PARTY_ENTRY_NO_LOCAL_HISTORY
    assert row["previous_party_vote_share"] is None
    assert row["cohort_reason"] == "excluded_non_single_member_primary_estimand"


def test_cohort_c_rows_never_receive_a_previous_local_party_vote_share() -> None:
    features = (
        _feature(
            "c",
            "2026",
            "7 May 2026",
            "area-c",
            "Party A",
            baseline_eligibility="excluded_no_approved_historical_area_reference",
            geographic_reference_eligibility="no_approved_predecessor",
            previous_party_vote_share=None,
        ),
    )
    targets = (_target("c", "Party A", 40.0, "No"),)

    universe = build_evaluation_universe(features, targets)

    row = universe[0]
    assert row["primary_cohort"] == COHORT_GEOGRAPHICALLY_NON_COMPARABLE
    assert row["previous_party_vote_share"] is None


def test_partition_is_exhaustive_and_every_row_gets_exactly_one_cohort() -> None:
    features = (
        _feature("a", "2017", "4 May 2017", "area-a", "Party A", previous_party_vote_share=55.0),
        _feature(
            "b",
            "2026",
            "7 May 2026",
            "area-b",
            "Party B",
            contest_structure="multi_member",
            baseline_eligibility="excluded_non_single_member_primary_estimand",
        ),
        _feature(
            "c",
            "2026",
            "7 May 2026",
            "area-c",
            "Party C",
            baseline_eligibility="excluded_no_approved_historical_area_reference",
            geographic_reference_eligibility="no_approved_predecessor",
        ),
    )
    targets = (
        _target("a", "Party A", 52.0, "Yes"),
        _target("b", "Party B", None, "No", status="not_defined_for_multi_member_party_contest"),
        _target("c", "Party C", 40.0, "No"),
    )

    universe = build_evaluation_universe(features, targets)

    cohorts = {row["party_contest_id"]: row["primary_cohort"] for row in universe}
    assert cohorts == {
        "a": COHORT_HISTORICAL_CONTINUITY,
        "b": COHORT_PARTY_ENTRY_NO_LOCAL_HISTORY,
        "c": COHORT_GEOGRAPHICALLY_NON_COMPARABLE,
    }
    assert len({row["party_contest_id"] for row in universe}) == len(universe)


def test_ukip_and_reform_uk_are_never_merged() -> None:
    # UKIP and Reform UK must remain distinct standard_party_name values
    # throughout the universe; this module must not introduce any merging.
    features = (
        _feature("u", "2017", "4 May 2017", "area-a", "UKIP", previous_party_vote_share=10.0),
        _feature("r", "2021", "6 May 2021", "area-a", "Reform UK", previous_party_vote_share=None,
                 baseline_eligibility="excluded_no_approved_exact_label_previous_party_share"),
    )
    targets = (
        _target("u", "UKIP", 8.0, "No"),
        _target("r", "Reform UK", 25.0, "No"),
    )

    universe = build_evaluation_universe(features, targets)

    names = {row["party_contest_id"]: row["standard_party_name"] for row in universe}
    assert names == {"u": "UKIP", "r": "Reform UK"}


def test_n0_and_n1_eligibility_is_false_for_multi_member_contests() -> None:
    features = (
        _feature(
            "m",
            "2026",
            "7 May 2026",
            "area-m",
            "Party A",
            contest_structure="multi_member",
            baseline_eligibility="excluded_non_single_member_primary_estimand",
        ),
    )
    targets = (_target("m", "Party A", None, "No", status="not_defined_for_multi_member_party_contest"),)

    row = build_evaluation_universe(features, targets)[0]

    assert row["eligible_n0_equal_share"] is False
    assert row["eligible_n1_party_historical_mean"] is False


def test_n3_ridge_eligibility_requires_an_evaluable_fold_not_just_cohort_a() -> None:
    # 2013 is the study-start election: even a Cohort-A-shaped row there has
    # no earlier training data, so ridge cannot evaluate it, unlike
    # persistence-share eligibility which does not depend on fold structure.
    features = (
        _feature("e13", "2013", "2 May 2013", "area-a", "Party A", previous_party_vote_share=30.0),
        _feature("e17", "2017", "4 May 2017", "area-a", "Party A", previous_party_vote_share=32.0),
    )
    targets = (
        _target("e13", "Party A", 30.0, "Yes"),
        _target("e17", "Party A", 34.0, "Yes"),
    )

    universe = build_evaluation_universe(features, targets)
    by_id = {row["party_contest_id"]: row for row in universe}

    assert by_id["e13"]["eligible_n2_persistence_share"] is True
    assert by_id["e13"]["eligible_n3_ridge"] is False
    assert by_id["e17"]["eligible_n3_ridge"] is True


def test_no_duplicate_row_identifiers() -> None:
    features = (
        _feature("a", "2017", "4 May 2017", "area-a", "Party A", previous_party_vote_share=55.0),
        _feature("b", "2017", "4 May 2017", "area-a", "Party B", previous_party_vote_share=45.0),
    )
    targets = (
        _target("a", "Party A", 52.0, "Yes"),
        _target("b", "Party B", 48.0, "No"),
    )

    universe = build_evaluation_universe(features, targets)

    ids = [row["party_contest_id"] for row in universe]
    assert len(ids) == len(set(ids))


def test_mismatched_feature_and_target_ids_are_rejected() -> None:
    features = (_feature("a", "2017", "4 May 2017", "area-a", "Party A"),)
    targets = (_target("different", "Party A", 50.0, "Yes"),)

    with pytest.raises(ValueError, match="identifiers do not match"):
        build_evaluation_universe(features, targets)
