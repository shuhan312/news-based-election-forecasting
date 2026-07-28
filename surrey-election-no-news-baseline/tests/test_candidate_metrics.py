"""Tests for the candidate-level evaluation metrics."""

import numpy as np
import pytest

from no_news_baseline.candidate_metrics import (
    bootstrap_contest_interval,
    equal_split_reference,
    evaluate,
    rank_metrics,
    reform_report,
    seat_metrics,
    share_metrics,
    _mae,
)


def _record(
    row_id: str,
    *,
    election_id: str = "2021",
    division_id: str = "d1",
    party: str = "Conservative",
    predicted: float | None = 40.0,
    observed: float | None = 45.0,
    candidates: int = 4,
    predicted_rank: int = 1,
    observed_rank: int = 1,
    predicted_elected: bool = True,
    observed_elected: bool = True,
    structure: str = "single_member",
    reform: bool = False,
    ukip: bool = False,
) -> dict[str, object]:
    return {
        "candidate_contest_id": row_id,
        "election_id": election_id,
        "division_id": division_id,
        "standard_party_name": party,
        "contest_structure": structure,
        "candidate_count_in_contest": candidates,
        "predicted_vote_share": predicted,
        "observed_vote_share": observed,
        "predicted_rank": predicted_rank,
        "observed_rank": observed_rank,
        "predicted_elected": predicted_elected,
        "observed_elected": observed_elected,
        "is_reform_uk": reform,
        "is_ukip": ukip,
    }


def _contest(prefix: str, predicted: list[float], observed: list[float], **kwargs):
    """One contest, ranks derived from the values so they stay consistent."""

    p_rank = (np.argsort(np.argsort(-np.array(predicted))) + 1).tolist()
    o_rank = (np.argsort(np.argsort(-np.array(observed))) + 1).tolist()
    parties = ["Conservative", "Labour", "Liberal Democrats", "Reform UK"]
    return [
        _record(
            f"{prefix}{index}",
            division_id=f"div-{prefix}",
            party=parties[index % len(parties)],
            predicted=p,
            observed=o,
            candidates=len(predicted),
            predicted_rank=pr,
            observed_rank=orank,
            predicted_elected=pr == 1,
            observed_elected=orank == 1,
            reform=parties[index % len(parties)] == "Reform UK",
            **kwargs,
        )
        for index, (p, o, pr, orank) in enumerate(zip(predicted, observed, p_rank, o_rank))
    ]


# --- share error ----------------------------------------------------------


def test_share_metrics_reports_the_scale_the_error_sits_on() -> None:
    """MAE alone is unreadable across contest sizes, so the mean it is
    measured against travels with it."""

    rows = [_record("a", predicted=40.0, observed=45.0),
            _record("b", predicted=30.0, observed=25.0)]
    metrics = share_metrics(rows)

    assert metrics["mae"] == pytest.approx(5.0)
    assert metrics["rmse"] == pytest.approx(5.0)
    assert metrics["mean_observed_share"] == pytest.approx(35.0)
    assert metrics["relative_mae"] == pytest.approx(5.0 / 35.0)


def test_rows_without_a_prediction_or_outcome_are_excluded() -> None:
    rows = [_record("a", predicted=40.0, observed=45.0),
            _record("b", predicted=None),
            _record("c", observed=None)]
    assert share_metrics(rows)["rows"] == 1


def test_equal_split_reference_reports_a_negative_improvement_honestly() -> None:
    """A model worse than an equal split must show as negative, not zero."""

    # Equal split for four candidates is 25; the model says 5 when truth is 25.
    rows = [_record("a", predicted=5.0, observed=25.0, candidates=4)]
    reference = equal_split_reference(rows)

    assert reference["mae"] == pytest.approx(0.0)
    assert reference["model_mae"] == pytest.approx(20.0)
    assert reference["improvement_over_equal_split"] is None or reference[
        "improvement_over_equal_split"
    ] <= 0


def test_equal_split_improvement_is_positive_when_the_model_is_better() -> None:
    rows = [_record("a", predicted=44.0, observed=45.0, candidates=4)]
    reference = equal_split_reference(rows)
    assert reference["improvement_over_equal_split"] > 0


# --- rank -----------------------------------------------------------------


def test_perfect_ordering_gives_a_rank_correlation_of_one() -> None:
    rows = _contest("a", [40.0, 30.0, 20.0, 10.0], [45.0, 25.0, 20.0, 10.0])
    assert rank_metrics(rows)["mean_rank_correlation"] == pytest.approx(1.0)


def test_reversed_ordering_gives_minus_one() -> None:
    rows = _contest("a", [10.0, 20.0, 30.0, 40.0], [40.0, 30.0, 20.0, 10.0])
    assert rank_metrics(rows)["mean_rank_correlation"] == pytest.approx(-1.0)


def test_a_contest_where_every_value_ties_is_undefined_not_zero() -> None:
    rows = _contest("a", [25.0, 25.0, 25.0, 25.0], [40.0, 30.0, 20.0, 10.0])
    assert rank_metrics(rows)["contests"] == 0


# --- seats ----------------------------------------------------------------


def test_winner_and_seat_set_accuracy_are_different_questions() -> None:
    """In a two-seat contest the top pick can be right while the set is wrong."""

    rows = _contest("a", [40.0, 30.0, 20.0, 10.0], [45.0, 20.0, 25.0, 10.0])
    # Two seats: predicted winners are ranks 1-2, observed are the top two
    # observed shares, which differ.
    for row in rows:
        row["predicted_elected"] = int(row["predicted_rank"]) <= 2
        row["observed_elected"] = int(row["observed_rank"]) <= 2

    metrics = seat_metrics(rows)
    assert metrics["winner_accuracy"] == pytest.approx(1.0)
    assert metrics["seat_set_accuracy"] == pytest.approx(0.0)


def test_party_seat_total_error_sums_over_parties_within_an_election() -> None:
    rows = [
        _record("a", party="Conservative", predicted_elected=True, observed_elected=False),
        _record("b", division_id="d2", party="Labour",
                predicted_elected=False, observed_elected=True),
    ]
    metrics = seat_metrics(rows)
    # Conservative predicted 1 observed 0, Labour predicted 0 observed 1.
    assert metrics["party_seat_total_absolute_error"] == 2


# --- bootstrap ------------------------------------------------------------


def test_bootstrap_resamples_contests_not_rows() -> None:
    """With one contest there is nothing to resample, so no interval is
    invented from the correlated rows inside it."""

    rows = _contest("a", [40.0, 30.0, 20.0, 10.0], [45.0, 25.0, 20.0, 10.0])
    interval = bootstrap_contest_interval(rows, _mae, resamples=50)

    assert interval["contests"] == 1
    assert interval["lower"] is None
    assert interval["upper"] is None


def test_bootstrap_interval_brackets_the_point_estimate() -> None:
    rows = (
        _contest("a", [40.0, 30.0, 20.0, 10.0], [45.0, 25.0, 20.0, 10.0])
        + _contest("b", [50.0, 25.0, 15.0, 10.0], [40.0, 30.0, 20.0, 10.0])
        + _contest("c", [35.0, 35.0, 20.0, 10.0], [30.0, 40.0, 20.0, 10.0])
    )
    interval = bootstrap_contest_interval(rows, _mae, resamples=200)

    assert interval["contests"] == 3
    assert interval["lower"] <= interval["point_estimate"] <= interval["upper"]


def test_the_bootstrap_is_reproducible_from_its_seed() -> None:
    rows = (
        _contest("a", [40.0, 30.0, 20.0, 10.0], [45.0, 25.0, 20.0, 10.0])
        + _contest("b", [50.0, 25.0, 15.0, 10.0], [40.0, 30.0, 20.0, 10.0])
    )
    first = bootstrap_contest_interval(rows, _mae, resamples=100, seed=7)
    second = bootstrap_contest_interval(rows, _mae, resamples=100, seed=7)
    assert first["lower"] == second["lower"]
    assert first["upper"] == second["upper"]


# --- assembled reports ----------------------------------------------------


def test_evaluate_never_publishes_a_pooled_figure_without_the_structure_split() -> None:
    rows = (
        _contest("a", [40.0, 30.0, 20.0, 10.0], [45.0, 25.0, 20.0, 10.0])
        + _contest("b", [12.0] * 8, [10.0, 15.0, 12.0, 11.0, 13.0, 14.0, 12.0, 13.0],
                   structure="multi_member")
    )
    report = evaluate(rows, with_bootstrap=False)

    assert "overall" in report
    assert set(report["by_contest_structure"]) == {"single_member", "multi_member"}
    # And each structure carries its own scale.
    assert report["by_contest_structure"]["multi_member"]["mean_observed_share"] < (
        report["by_contest_structure"]["single_member"]["mean_observed_share"]
    )


def test_evaluate_separates_principal_elections_from_by_elections() -> None:
    rows = _contest("a", [40.0, 30.0, 20.0, 10.0], [45.0, 25.0, 20.0, 10.0])
    rows += _contest("b", [50.0, 30.0, 15.0, 5.0], [40.0, 30.0, 20.0, 10.0],
                     election_id="surrey-county-council-by-election-x-2025-08-21")
    report = evaluate(rows, with_bootstrap=False)

    assert set(report["by_election_type"]) == {"principal_election", "by_election"}


# --- Reform -------------------------------------------------------------


def test_reform_report_keeps_ukip_separate_and_never_sums_them() -> None:
    rows = [
        _record("r", party="Reform UK", reform=True, predicted=12.0, observed=15.0),
        _record("u", division_id="d2", party="UK Independence Party", ukip=True,
                predicted=8.0, observed=5.0),
    ]
    report = reform_report(rows, with_bootstrap=False)

    assert report["reform_uk"]["rows"] == 1
    assert report["ukip_separately"]["rows"] == 1
    # The UKIP row contributes nothing to the Reform figure.
    assert report["reform_uk"]["mae"] == pytest.approx(3.0)


def test_a_small_reform_sample_raises_the_warning_flag() -> None:
    """The brief requires warning where Reform estimates rest on few rows."""

    rows = [_record("r", party="Reform UK", reform=True)]
    assert reform_report(rows, with_bootstrap=False)["small_sample_warning"] is True


def test_a_large_reform_sample_clears_the_warning() -> None:
    rows = [
        _record(f"r{index}", division_id=f"d{index}", party="Reform UK", reform=True)
        for index in range(40)
    ]
    assert reform_report(rows, with_bootstrap=False)["small_sample_warning"] is False
