"""Tests for leakage-safe temporal fold construction."""

import pytest

from no_news_baseline.naive_benchmarks import evaluate_equal_share_reference
from no_news_baseline.persistence_benchmark import evaluate_previous_result_persistence
from no_news_baseline.temporal_validation import iter_temporal_folds, summarise_folds


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
) -> dict[str, object]:
    # A superset of the fields the naive benchmarks and persistence_benchmark
    # each require, so the same helper can feed both the fold-construction
    # tests and the cross-check tests against already-tested benchmark code.
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
        "party_was_previous_winner": party_was_previous_winner,
        "historical_source_url": "https://official.example/previous",
    }


def _target(contest_id: str, party: str, share: float, elected: str) -> dict[str, object]:
    return {
        "party_contest_id": contest_id,
        "standard_party_name": party,
        "target_party_vote_share": share,
        "target_party_elected": elected,
        "target_source_urls": "https://official.example/current",
    }


def test_earliest_election_is_excluded_as_a_test_fold_but_kept_as_training_data() -> None:
    features = (
        _feature("e13", "2013", "2 May 2013", "area-a", "Party A"),
        _feature("e17", "2017", "4 May 2017", "area-a", "Party A"),
        _feature("e21", "2021", "6 May 2021", "area-a", "Party A"),
    )
    targets = (
        _target("e13", "Party A", 30.0, "Yes"),
        _target("e17", "Party A", 35.0, "Yes"),
        _target("e21", "Party A", 40.0, "Yes"),
    )

    folds = iter_temporal_folds(features, targets)

    assert [fold.election_id for fold in folds] == ["2017", "2021"]
    fold_2017 = folds[0]
    assert [row["party_contest_id"] for row in fold_2017.train_features] == ["e13"]
    assert [row["party_contest_id"] for row in fold_2017.test_features] == ["e17"]
    fold_2021 = folds[1]
    # By the 2021 fold, both earlier elections (2013 and 2017) are available
    # as training data, in whatever order the release happened to list them.
    assert {row["party_contest_id"] for row in fold_2021.train_features} == {"e13", "e17"}


def test_by_election_interspersed_between_principal_elections_gets_its_own_fold() -> None:
    # A by-election dated between 2017 and 2021 should slot into the
    # chronological sequence as its own fold, trained on everything before
    # it (2013 and 2017), exactly like a principal election would be.
    features = (
        _feature("e13", "2013", "2 May 2013", "area-a", "Party A"),
        _feature("e17", "2017", "4 May 2017", "area-a", "Party A"),
        _feature("by19", "by-2019-area-b", "10 October 2019", "area-b", "Party A"),
        _feature("e21", "2021", "6 May 2021", "area-a", "Party A"),
    )
    targets = (
        _target("e13", "Party A", 30.0, "Yes"),
        _target("e17", "Party A", 35.0, "Yes"),
        _target("by19", "Party A", 38.0, "Yes"),
        _target("e21", "Party A", 40.0, "Yes"),
    )

    folds = iter_temporal_folds(features, targets)

    assert [fold.election_id for fold in folds] == ["2017", "by-2019-area-b", "2021"]
    by_election_fold = folds[1]
    assert {row["party_contest_id"] for row in by_election_fold.train_features} == {"e13", "e17"}
    final_fold = folds[2]
    assert {row["party_contest_id"] for row in final_fold.train_features} == {
        "e13",
        "e17",
        "by19",
    }


def test_same_day_elections_do_not_train_on_each_other() -> None:
    # Surrey has genuinely scheduled multiple by-elections on the same day
    # (and the 2026 East/West Surrey unitary elections share a polling day).
    # Neither of a same-day pair happened strictly before the other, so
    # neither may appear in the other's training set, even though both are
    # evaluable once a later, genuinely later-dated election exists.
    features = (
        _feature("e17", "2017", "4 May 2017", "area-a", "Party A"),
        _feature("by-x", "by-x-2019", "10 October 2019", "area-x", "Party A"),
        _feature("by-y", "by-y-2019", "10 October 2019", "area-y", "Party A"),
        _feature("e21", "2021", "6 May 2021", "area-a", "Party A"),
    )
    targets = (
        _target("e17", "Party A", 35.0, "Yes"),
        _target("by-x", "Party A", 38.0, "Yes"),
        _target("by-y", "Party A", 42.0, "Yes"),
        _target("e21", "Party A", 40.0, "Yes"),
    )

    folds = iter_temporal_folds(features, targets)

    fold_by_x = next(fold for fold in folds if fold.election_id == "by-x-2019")
    fold_by_y = next(fold for fold in folds if fold.election_id == "by-y-2019")
    assert {row["party_contest_id"] for row in fold_by_x.train_features} == {"e17"}
    assert {row["party_contest_id"] for row in fold_by_y.train_features} == {"e17"}

    # By 2021, both same-day by-elections are safely in the past and should
    # both appear in the training set.
    fold_2021 = next(fold for fold in folds if fold.election_id == "2021")
    assert {row["party_contest_id"] for row in fold_2021.train_features} == {
        "e17",
        "by-x",
        "by-y",
    }


def test_inconsistent_election_metadata_across_rows_is_rejected() -> None:
    # Two rows claiming to belong to the same election_id but disagreeing on
    # its date point to an upstream data-contract error; the fold builder
    # must refuse to silently pick one value.
    features = (
        _feature("a", "2017", "4 May 2017", "area-a", "Party A"),
        _feature("b", "2017", "5 May 2017", "area-b", "Party B"),
    )
    targets = (
        _target("a", "Party A", 30.0, "Yes"),
        _target("b", "Party B", 30.0, "Yes"),
    )

    with pytest.raises(ValueError, match="inconsistent date/year/type"):
        iter_temporal_folds(features, targets)


def test_summarise_folds_reports_row_counts() -> None:
    features = (
        _feature("e13", "2013", "2 May 2013", "area-a", "Party A"),
        _feature("e17", "2017", "4 May 2017", "area-a", "Party A"),
    )
    targets = (
        _target("e13", "Party A", 30.0, "Yes"),
        _target("e17", "Party A", 35.0, "Yes"),
    )

    summary = summarise_folds(iter_temporal_folds(features, targets))

    assert summary == (
        {
            "election_id": "2017",
            "election_date": "2017-05-04",
            "election_year": 2017,
            "election_type": "County Council election",
            "train_rows": 1,
            "test_rows": 1,
        },
    )


def test_fold_restricted_prediction_matches_whole_dataset_prediction() -> None:
    # persistence_benchmark and the naive benchmarks are parameter-free, so
    # scoring a fold's test rows in isolation must give exactly the same
    # predictions as scoring the whole release and then filtering down to
    # that election. This cross-checks the fold boundaries against
    # already-tested benchmark code, rather than trusting the new module in
    # isolation.
    features = (
        _feature("e13", "2013", "2 May 2013", "area-a", "Party A"),
        _feature("e17-a", "2017", "4 May 2017", "area-a", "Party A"),
        _feature("e17-b", "2017", "4 May 2017", "area-a", "Party B"),
    )
    targets = (
        _target("e13", "Party A", 30.0, "Yes"),
        _target("e17-a", "Party A", 55.0, "Yes"),
        _target("e17-b", "Party B", 45.0, "No"),
    )

    folds = iter_temporal_folds(features, targets)
    fold_2017 = next(fold for fold in folds if fold.election_id == "2017")

    whole_predictions, _metrics, _audit = evaluate_equal_share_reference(features, targets)
    whole_2017 = {
        row["party_contest_id"]: row["predicted_party_vote_share"]
        for row in whole_predictions
        if row["election_id"] == "2017"
    }

    fold_predictions, _metrics, _audit = evaluate_equal_share_reference(
        fold_2017.train_features + fold_2017.test_features,
        fold_2017.train_targets + fold_2017.test_targets,
    )
    fold_2017_only = {
        row["party_contest_id"]: row["predicted_party_vote_share"]
        for row in fold_predictions
        if row["election_id"] == "2017"
    }

    assert fold_2017_only == whole_2017


def test_fold_matches_persistence_benchmark_for_a_single_area() -> None:
    features = (
        # 2013 is the study-start election: it has no approved predecessor of
        # its own, so it is not share-eligible under persistence_benchmark's
        # own cohort rule either.
        _feature(
            "e13",
            "2013",
            "2 May 2013",
            "area-a",
            "Party A",
            baseline_eligibility="excluded_no_approved_exact_label_previous_party_share",
        ),
        _feature(
            "e17",
            "2017",
            "4 May 2017",
            "area-a",
            "Party A",
            previous_party_vote_share=60.0,
            party_was_previous_winner=True,
        ),
    )
    targets = (
        _target("e13", "Party A", 60.0, "Yes"),
        _target("e17", "Party A", 55.0, "Yes"),
    )

    folds = iter_temporal_folds(features, targets)
    fold_2017 = folds[0]

    whole_predictions, _metrics, _audit = evaluate_previous_result_persistence(features, targets)
    whole_2017 = next(row for row in whole_predictions if row["election_id"] == "2017")

    fold_predictions, _metrics, _audit = evaluate_previous_result_persistence(
        fold_2017.train_features + fold_2017.test_features,
        fold_2017.train_targets + fold_2017.test_targets,
    )
    fold_2017_only = next(row for row in fold_predictions if row["election_id"] == "2017")

    assert fold_2017_only["predicted_party_vote_share"] == whole_2017["predicted_party_vote_share"]
