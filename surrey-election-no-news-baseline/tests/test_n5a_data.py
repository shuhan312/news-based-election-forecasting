"""Tests for the N5a fold-wise data preparation layer."""

import pytest

from no_news_baseline.n5a_data import (
    BY_ELECTION_CYCLE_INDEX,
    ROUNDED_ZERO_SHARE_FRACTION,
    UNSEEN_PARTY_INDEX,
    prepare_n5a_fold_data,
)


def _feature(
    contest_id: str,
    election_id: str,
    election_date: str,
    area: str,
    party: str,
    *,
    election_type: str = "County Council election",
    contest_structure: str = "single_member",
    baseline_eligibility: str = "eligible_primary_single_member_party_share",
    geographic_reference_eligibility: str = "approved_historical_reference",
    previous_party_vote_share: float | None = None,
    party_identity_scope: str = "reviewed_standard_party",
    party_group_key: str | None = None,
) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "election_id": election_id,
        "election_date": election_date,
        "election_year": int(election_date[-4:]),
        "election_type": election_type,
        "division_id": area,
        "division_name": area,
        "standard_party_name": party,
        "party_group_key": party_group_key or f"party:{party}",
        "contest_structure": contest_structure,
        "geographic_reference_eligibility": geographic_reference_eligibility,
        "party_identity_scope": party_identity_scope,
        "baseline_eligibility": baseline_eligibility,
        "previous_party_vote_share": previous_party_vote_share,
        "previous_party_vote_share_status": "derived_single_member_exact_label_prior_candidate_share",
        "party_was_previous_winner": None,
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


def _basic_fixture():
    features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A",
                 previous_party_vote_share=60.0),
        _feature("t-b", "2017", "4 May 2017", "area-t", "Party B",
                 previous_party_vote_share=40.0),
    )
    targets = (
        _target("h-a", "Party A", 60.0, "Yes"),
        _target("h-b", "Party B", 40.0, "No"),
        _target("t-a", "Party A", 55.0, "Yes"),
        _target("t-b", "Party B", 45.0, "No"),
    )
    return features, targets


def test_training_compositions_close_to_exactly_one() -> None:
    features, targets = _basic_fixture()

    folds = prepare_n5a_fold_data(features, targets)

    fold_2017 = next(fold for fold in folds if fold.election_id == "2017")
    assert len(fold_2017.train_contests) == 1
    shares = fold_2017.train_contests[0].observed_shares
    assert shares is not None
    assert sum(shares) == pytest.approx(1.0, abs=1e-12)


def test_rounded_zero_share_uses_hanretty_replacement_not_exclusion() -> None:
    # Party B stood but its published share is 0: it must stay in the
    # composition with the documented 1/40000 replacement, never dropped.
    features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A"),
    )
    targets = (
        _target("h-a", "Party A", 100.0, "Yes"),
        _target("h-b", "Party B", 0.0, "No"),
        _target("t-a", "Party A", 100.0, "Yes"),
    )

    folds = prepare_n5a_fold_data(features, targets)

    train = next(fold for fold in folds if fold.election_id == "2017").train_contests[0]
    assert train.observed_shares is not None
    assert len(train.observed_shares) == 2
    assert min(train.observed_shares) == pytest.approx(
        ROUNDED_ZERO_SHARE_FRACTION / (1.0 + ROUNDED_ZERO_SHARE_FRACTION)
    )
    assert sum(train.observed_shares) == pytest.approx(1.0, abs=1e-12)


def test_party_unseen_in_training_gets_the_sentinel_index() -> None:
    features, targets = _basic_fixture()
    features = features + (
        _feature("t-r", "2017", "4 May 2017", "area-t", "Reform UK"),
    )
    targets = targets + (_target("t-r", "Reform UK", 20.0, "No"),)

    folds = prepare_n5a_fold_data(features, targets)

    fold_2017 = next(fold for fold in folds if fold.election_id == "2017")
    test_rows = {
        row.party_group_key: row
        for contest in fold_2017.test_contests
        for row in contest.rows
    }
    assert test_rows["party:Reform UK"].party_index == UNSEEN_PARTY_INDEX
    assert test_rows["party:Party A"].party_index != UNSEEN_PARTY_INDEX


def test_ukip_and_reform_receive_distinct_party_indices() -> None:
    features = (
        _feature("h-u", "2013", "2 May 2013", "area-h", "UKIP"),
        _feature("h-r", "2013", "2 May 2013", "area-h", "Reform UK"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "UKIP"),
    )
    targets = (
        _target("h-u", "UKIP", 55.0, "Yes"),
        _target("h-r", "Reform UK", 45.0, "No"),
        _target("t-a", "UKIP", 100.0, "Yes"),
    )

    folds = prepare_n5a_fold_data(features, targets)

    fold_2017 = next(fold for fold in folds if fold.election_id == "2017")
    train_rows = {
        row.party_group_key: row.party_index
        for contest in fold_2017.train_contests
        for row in contest.rows
    }
    assert train_rows["party:UKIP"] != train_rows["party:Reform UK"]


def test_independents_keep_candidate_specific_identities() -> None:
    # Two unrelated independents share the label but not the group key, so
    # they must receive different party indices.
    features = (
        _feature("h-i1", "2013", "2 May 2013", "area-h", "Independent",
                 party_identity_scope="candidate_specific_independent",
                 party_group_key="independent_candidate:alice"),
        _feature("h-i2", "2013", "2 May 2013", "area-h", "Independent",
                 party_identity_scope="candidate_specific_independent",
                 party_group_key="independent_candidate:bob"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A"),
    )
    targets = (
        _target("h-i1", "Independent", 55.0, "Yes"),
        _target("h-i2", "Independent", 45.0, "No"),
        _target("t-a", "Party A", 100.0, "Yes"),
    )

    folds = prepare_n5a_fold_data(features, targets)

    fold_2017 = next(fold for fold in folds if fold.election_id == "2017")
    indices = {
        row.party_group_key: row.party_index
        for contest in fold_2017.train_contests
        for row in contest.rows
    }
    assert indices["independent_candidate:alice"] != indices["independent_candidate:bob"]


def test_previous_share_scaling_is_fitted_on_training_rows_only() -> None:
    # Training rows (2013 wave feeding the 2021 fold) have shares 60/40:
    # mean 50, sd 10. The 2021 test row with previous share 70 must be
    # standardised with THOSE values: z = (70-50)/10 = 2.
    features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("m-a", "2017", "4 May 2017", "area-m", "Party A",
                 previous_party_vote_share=60.0),
        _feature("m-b", "2017", "4 May 2017", "area-m", "Party B",
                 previous_party_vote_share=40.0),
        _feature("t-a", "2021", "6 May 2021", "area-t", "Party A",
                 previous_party_vote_share=70.0),
    )
    targets = (
        _target("h-a", "Party A", 60.0, "Yes"),
        _target("h-b", "Party B", 40.0, "No"),
        _target("m-a", "Party A", 62.0, "Yes"),
        _target("m-b", "Party B", 38.0, "No"),
        _target("t-a", "Party A", 100.0, "Yes"),
    )

    folds = prepare_n5a_fold_data(features, targets)

    fold_2021 = next(fold for fold in folds if fold.election_id == "2021")
    assert fold_2021.previous_share_mean == pytest.approx(50.0)
    assert fold_2021.previous_share_std == pytest.approx(10.0)
    test_row = fold_2021.test_contests[0].rows[0]
    assert test_row.previous_share_z == pytest.approx(2.0)
    assert test_row.previous_share_missing == 0


def test_missing_previous_share_becomes_zero_with_indicator() -> None:
    features, targets = _basic_fixture()

    folds = prepare_n5a_fold_data(features, targets)

    fold_2017 = next(fold for fold in folds if fold.election_id == "2017")
    train_row = fold_2017.train_contests[0].rows[0]  # 2013 row: no history
    assert train_row.previous_share_missing == 1
    assert train_row.previous_share_z == 0.0


def test_by_election_contest_gets_sentinel_cycle_and_new_principal_gets_fresh_index() -> None:
    features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("by-a", "by-2015", "7 May 2015", "area-by", "Party A",
                 election_type="by-election"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A"),
        _feature("t-b", "2017", "4 May 2017", "area-t", "Party B"),
    )
    targets = (
        _target("h-a", "Party A", 60.0, "Yes"),
        _target("h-b", "Party B", 40.0, "No"),
        _target("by-a", "Party A", 100.0, "Yes"),
        _target("t-a", "Party A", 55.0, "Yes"),
        _target("t-b", "Party B", 45.0, "No"),
    )

    folds = prepare_n5a_fold_data(features, targets)

    by_fold = next(fold for fold in folds if fold.election_id == "by-2015")
    assert by_fold.test_contests[0].cycle_index == BY_ELECTION_CYCLE_INDEX

    fold_2017 = next(fold for fold in folds if fold.election_id == "2017")
    # Training cycles = {2013}; the held-out 2017 election is a new
    # principal cycle and must carry the fresh-draw index, never 2013's.
    assert fold_2017.cycle_count == 1
    test_principal = fold_2017.test_contests[0]
    assert test_principal.cycle_index == fold_2017.new_cycle_index
    # By-election training contests keep the sentinel inside training too.
    by_train = [
        contest for contest in fold_2017.train_contests if contest.is_by_election
    ]
    assert all(contest.cycle_index == BY_ELECTION_CYCLE_INDEX for contest in by_train)


def test_multi_member_test_contest_is_present_but_unscoreable() -> None:
    features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("m-a", "2026", "7 May 2026", "ward-m", "Party A",
                 contest_structure="multi_member",
                 baseline_eligibility="excluded_non_single_member_primary_estimand"),
        _feature("m-b", "2026", "7 May 2026", "ward-m", "Party B",
                 contest_structure="multi_member",
                 baseline_eligibility="excluded_non_single_member_primary_estimand"),
    )
    targets = (
        _target("h-a", "Party A", 60.0, "Yes"),
        _target("h-b", "Party B", 40.0, "No"),
        _target("m-a", "Party A", None, "Yes",
                status="not_defined_for_multi_member_party_contest"),
        _target("m-b", "Party B", None, "No",
                status="not_defined_for_multi_member_party_contest"),
    )

    folds = prepare_n5a_fold_data(features, targets)

    fold_2026 = next(fold for fold in folds if fold.election_id == "2026")
    assert len(fold_2026.test_contests) == 1
    contest = fold_2026.test_contests[0]
    assert contest.observed_shares is None  # never an invented target
    assert len(contest.rows) == 2  # but the ballot is fully encoded


def test_fold_preparation_is_deterministic() -> None:
    features, targets = _basic_fixture()

    assert prepare_n5a_fold_data(features, targets) == prepare_n5a_fold_data(
        features, targets
    )
