"""Tests for the fold-by-fold benchmark report."""

from no_news_baseline.persistence_benchmark import evaluate_previous_result_persistence
from no_news_baseline.temporal_validation_report import score_benchmarks_across_folds


def _feature(
    contest_id: str,
    election_id: str,
    election_date: str,
    area: str,
    party: str,
    *,
    baseline_eligibility: str = "eligible_primary_single_member_party_share",
    previous_party_vote_share: float | None = None,
    party_was_previous_winner: bool | None = None,
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
        "contest_structure": "single_member",
        "geographic_reference_eligibility": "approved_historical_reference",
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


def test_report_has_one_row_per_evaluable_election_with_all_three_benchmarks() -> None:
    features = (
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
        _feature(
            "e21",
            "2021",
            "6 May 2021",
            "area-a",
            "Party A",
            previous_party_vote_share=55.0,
            party_was_previous_winner=True,
        ),
    )
    targets = (
        _target("e13", "Party A", 60.0, "Yes"),
        _target("e17", "Party A", 55.0, "Yes"),
        _target("e21", "Party A", 50.0, "Yes"),
    )

    report = score_benchmarks_across_folds(features, targets)

    assert [row["election_id"] for row in report] == ["2017", "2021"]
    for row in report:
        for benchmark_id in (
            "previous_result_persistence_v1",
            "equal_share_reference_v1",
            "party_historical_mean_reference_v1",
        ):
            assert benchmark_id in row
            assert "party_share_mae_percentage_points" in row[benchmark_id]

    # Single-candidate ballot every time: persistence carries the previous
    # share forward exactly, so its MAE on both folds should be the
    # difference between the previous and current share.
    row_2017 = report[0]
    assert (
        row_2017["previous_result_persistence_v1"]["party_share_mae_percentage_points"] == 5.0
    )


def test_fold_persistence_mae_matches_whole_dataset_grouped_metrics() -> None:
    # Cross-check against the already-tested whole-dataset benchmark: the
    # fold report's per-election MAE must equal what evaluate_previous_
    # result_persistence itself reports when grouped "by_election".
    features = (
        _feature(
            "e13",
            "2013",
            "2 May 2013",
            "area-a",
            "Party A",
            baseline_eligibility="excluded_no_approved_exact_label_previous_party_share",
        ),
        _feature(
            "e17-a",
            "2017",
            "4 May 2017",
            "area-a",
            "Party A",
            previous_party_vote_share=60.0,
            party_was_previous_winner=True,
        ),
        _feature(
            "e17-b",
            "2017",
            "4 May 2017",
            "area-a",
            "Party B",
            previous_party_vote_share=40.0,
            party_was_previous_winner=False,
        ),
    )
    targets = (
        _target("e13", "Party A", 60.0, "Yes"),
        _target("e17-a", "Party A", 55.0, "Yes"),
        _target("e17-b", "Party B", 45.0, "No"),
    )

    report = score_benchmarks_across_folds(features, targets)
    whole_predictions, whole_metrics, _audit = evaluate_previous_result_persistence(
        features, targets
    )
    whole_2017 = next(
        group for group in whole_metrics["by_election"] if group["election_id"] == "2017"
    )

    fold_2017 = next(row for row in report if row["election_id"] == "2017")
    assert (
        fold_2017["previous_result_persistence_v1"]["party_share_mae_percentage_points"]
        == whole_2017["party_share_mae_percentage_points"]
    )
