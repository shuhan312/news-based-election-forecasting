"""Tests for the metric definitions shared by every no-news benchmark."""

from no_news_baseline.benchmark_metrics import (
    area_winner_accuracy,
    assert_one_to_one_party_contest_release,
    binary_classification_metrics,
    grouped_metrics,
    share_metrics_for_predictions,
)


def test_share_metrics_ignore_unscored_rows() -> None:
    # A row with no prediction (predicted_party_vote_share is None) must not
    # silently count as a zero-error observation; it should simply be
    # excluded from the average, exactly as an unscored row is excluded.
    rows = [
        {
            "predicted_party_vote_share": 40.0,
            "share_error": -10.0,
            "absolute_share_error": 10.0,
            "squared_share_error": 100.0,
        },
        {
            "predicted_party_vote_share": None,
            "share_error": None,
            "absolute_share_error": None,
            "squared_share_error": None,
        },
    ]

    metrics = share_metrics_for_predictions(rows)

    assert metrics["party_share_rows"] == 1
    assert metrics["party_share_mae_percentage_points"] == 10.0
    assert metrics["party_share_rmse_percentage_points"] == 10.0


def test_binary_classification_metrics_on_empty_input_returns_none() -> None:
    # No scored winner rows should report None rather than a division by
    # zero or a misleading 0.0/1.0 accuracy figure.
    result = binary_classification_metrics([])

    assert result["winner_party_row_accuracy"] is None
    assert result["winner_party_hard_brier_score"] is None


def test_area_winner_accuracy_rejects_area_without_exactly_one_actual_winner() -> None:
    # This protects the single-member estimand shared by every benchmark: a
    # scored area must contain exactly one official winner row.
    rows = [
        {
            "election_id": "2017",
            "division_id": "area-a",
            "predicted_party_elected": "Yes",
            "actual_party_elected": "Yes",
            "standard_party_name": "Party A",
        },
        {
            "election_id": "2017",
            "division_id": "area-a",
            "predicted_party_elected": "No",
            "actual_party_elected": "Yes",
            "standard_party_name": "Party B",
        },
    ]

    try:
        area_winner_accuracy(rows)
    except ValueError as error:
        assert "one predicted and actual winner" in str(error)
    else:
        raise AssertionError("Expected a ValueError for a malformed area.")


def test_grouped_metrics_applies_same_function_per_group() -> None:
    rows = [
        {"election_id": "2017", "predicted_party_vote_share": 40.0, "share_error": 0.0,
         "absolute_share_error": 0.0, "squared_share_error": 0.0},
        {"election_id": "2021", "predicted_party_vote_share": 50.0, "share_error": 10.0,
         "absolute_share_error": 10.0, "squared_share_error": 100.0},
    ]

    grouped = grouped_metrics(rows, "election_id", share_metrics_for_predictions)

    assert [group["election_id"] for group in grouped] == ["2017", "2021"]
    assert grouped[1]["party_share_mae_percentage_points"] == 10.0


def test_assert_one_to_one_release_detects_mismatched_identifiers() -> None:
    features = [{"party_contest_id": "a"}]
    targets = [{"party_contest_id": "different"}]

    try:
        assert_one_to_one_party_contest_release(features, targets)
    except ValueError as error:
        assert "identifiers do not match" in str(error)
    else:
        raise AssertionError("Expected a ValueError for mismatched identifiers.")
