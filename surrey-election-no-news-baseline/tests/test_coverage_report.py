"""Tests for the Task 3 coverage/prediction join layer."""

from no_news_baseline.coverage_evaluation import build_evaluation_universe
from no_news_baseline.coverage_report import (
    N0,
    N1,
    N2,
    N3,
    REASON_ELIGIBLE_AND_PREDICTED,
    REASON_ELIGIBLE_MISSING_PREDICTION,
    REASON_ELIGIBLE_PREDICTED_NO_VALUE,
    REASON_INELIGIBLE_BUT_PREDICTED,
    REASON_NOT_ELIGIBLE,
    build_prediction_coverage_table,
    summarise_coverage,
    winner_coverage_metrics,
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
        "previous_party_vote_share_status": "derived_single_member_exact_label_prior_candidate_share",
        "party_was_previous_winner": party_was_previous_winner,
        "historical_source_url": "https://official.example/previous",
        # Only needed by ridge_fundamentals_v1 (regularised_models.py), but
        # included with harmless defaults so this one helper can also feed
        # the common-sample cross-check test below.
        "analysis_previous_turnout": 35.0,
        "previous_electorate": 10000,
        "incumbent_candidate_any_yes_no": "No",
        "incumbent_party_yes_no": "No",
        "party_previously_contested": True,
        "first_appearance_of_party_in_area": False,
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


def _small_universe():
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
        _feature(
            "b",
            "2026",
            "7 May 2026",
            "area-b",
            "Party B",
            baseline_eligibility="excluded_no_approved_historical_area_reference",
            geographic_reference_eligibility="no_approved_predecessor",
        ),
    )
    targets = (
        _target("a", "Party A", 52.0, "Yes"),
        _target("b", "Party B", 40.0, "No"),
    )
    return build_evaluation_universe(features, targets), features, targets


def test_stable_join_produces_one_row_per_universe_row_per_model() -> None:
    universe, _f, _t = _small_universe()
    predictions_by_model = {N0: (), N1: (), N2: (), N3: ()}

    rows, report = build_prediction_coverage_table(universe, predictions_by_model)

    assert len(rows) == len(universe) * 4
    assert report["universe_row_count"] == len(universe)
    ids = {(row["party_contest_id"], row["model_id"]) for row in rows}
    assert len(ids) == len(rows)


def test_eligibility_is_independent_of_whether_a_prediction_was_supplied() -> None:
    # Row "a" is theoretically eligible for N2, but no prediction is supplied
    # here at all. Eligibility must still read True - it is a property of
    # the universe row, not of whether a prediction happened to arrive.
    universe, _f, _t = _small_universe()
    predictions_by_model = {N0: (), N1: (), N2: (), N3: ()}

    rows, _report = build_prediction_coverage_table(universe, predictions_by_model)

    row_a_n2 = next(r for r in rows if r["party_contest_id"] == "a" and r["model_id"] == N2)
    assert row_a_n2["theoretically_eligible"] is True
    assert row_a_n2["prediction_present"] is False
    assert row_a_n2["reason"] == REASON_ELIGIBLE_MISSING_PREDICTION


def test_ineligible_row_with_no_prediction_is_classified_not_eligible() -> None:
    universe, _f, _t = _small_universe()
    predictions_by_model = {N0: (), N1: (), N2: (), N3: ()}

    rows, _report = build_prediction_coverage_table(universe, predictions_by_model)

    row_b_n2 = next(r for r in rows if r["party_contest_id"] == "b" and r["model_id"] == N2)
    assert row_b_n2["theoretically_eligible"] is False
    assert row_b_n2["reason"] == REASON_NOT_ELIGIBLE


def test_eligible_row_predicted_with_no_usable_value_is_classified_distinctly() -> None:
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (
            {
                "party_contest_id": "a",
                "predicted_party_vote_share": None,
            },
        ),
        N2: (),
        N3: (),
    }

    rows, _report = build_prediction_coverage_table(universe, predictions_by_model)

    row_a_n1 = next(r for r in rows if r["party_contest_id"] == "a" and r["model_id"] == N1)
    assert row_a_n1["prediction_present"] is True
    assert row_a_n1["prediction_valid"] is False
    assert row_a_n1["reason"] == REASON_ELIGIBLE_PREDICTED_NO_VALUE


def test_eligible_and_predicted_row_computes_absolute_error() -> None:
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: ({"party_contest_id": "a", "predicted_party_vote_share": 55.0},),
        N3: (),
    }

    rows, _report = build_prediction_coverage_table(universe, predictions_by_model)

    row_a_n2 = next(r for r in rows if r["party_contest_id"] == "a" and r["model_id"] == N2)
    assert row_a_n2["reason"] == REASON_ELIGIBLE_AND_PREDICTED
    assert row_a_n2["absolute_share_error"] == 3.0  # |55 - 52|


def test_duplicate_prediction_is_detected_and_reported_not_silently_dropped() -> None:
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: (
            {"party_contest_id": "a", "predicted_party_vote_share": 55.0},
            {"party_contest_id": "a", "predicted_party_vote_share": 999.0},
        ),
        N3: (),
    }

    _rows, report = build_prediction_coverage_table(universe, predictions_by_model)

    duplicate_mismatches = [
        m for m in report["mismatches"] if m["mismatch_type"] == "duplicate_prediction"
    ]
    assert len(duplicate_mismatches) == 1
    assert duplicate_mismatches[0]["party_contest_id"] == "a"


def test_prediction_without_a_matching_target_is_detected_not_silently_dropped() -> None:
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: ({"party_contest_id": "does-not-exist", "predicted_party_vote_share": 40.0},),
        N3: (),
    }

    _rows, report = build_prediction_coverage_table(universe, predictions_by_model)

    orphans = [m for m in report["mismatches"] if m["mismatch_type"] == "prediction_without_target"]
    assert len(orphans) == 1
    assert orphans[0]["party_contest_id"] == "does-not-exist"


def test_prediction_for_an_ineligible_row_is_detected_not_silently_dropped() -> None:
    universe, _f, _t = _small_universe()
    # Row "b" is not eligible for N2 (no approved area history), but a
    # prediction is supplied anyway - this must surface as a mismatch.
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: ({"party_contest_id": "b", "predicted_party_vote_share": 40.0},),
        N3: (),
    }

    _rows, report = build_prediction_coverage_table(universe, predictions_by_model)

    violations = [
        m for m in report["mismatches"] if m["mismatch_type"] == "prediction_for_ineligible_row"
    ]
    assert len(violations) == 1
    assert violations[0] == {
        "mismatch_type": "prediction_for_ineligible_row",
        "model_id": N2,
        "party_contest_id": "b",
    }


def test_present_entry_with_no_claimed_value_is_not_an_ineligibility_violation() -> None:
    # persistence_benchmark legitimately keeps a row present (for winner
    # tracking) with predicted_party_vote_share=None when that row is not
    # share-cohort-eligible. This must NOT be flagged as "prediction for an
    # ineligible row" - only an actual claimed value would be a violation.
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: ({"party_contest_id": "b", "predicted_party_vote_share": None},),
        N3: (),
    }

    rows, report = build_prediction_coverage_table(universe, predictions_by_model)

    violations = [
        m for m in report["mismatches"] if m["mismatch_type"] == "prediction_for_ineligible_row"
    ]
    assert violations == []
    row_b_n2 = next(r for r in rows if r["party_contest_id"] == "b" and r["model_id"] == N2)
    assert row_b_n2["reason"] == REASON_NOT_ELIGIBLE
    assert row_b_n2["prediction_present"] is True
    assert row_b_n2["prediction_valid"] is False


def test_coverage_denominators_are_target_universe_vs_eligibility_conditioned() -> None:
    # Two rows total; only one is eligible for N2, and that one is predicted.
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: ({"party_contest_id": "a", "predicted_party_vote_share": 55.0},),
        N3: (),
    }

    rows, _report = build_prediction_coverage_table(universe, predictions_by_model)
    summary = summarise_coverage(rows)[N2]["overall"]

    assert summary["target_count"] == 2
    assert summary["theoretically_eligible_count"] == 1
    assert summary["valid_prediction_count"] == 1
    assert summary["target_universe_coverage"] == 0.5
    assert summary["eligibility_conditioned_coverage"] == 1.0


def test_valid_prediction_with_undefined_target_counts_for_coverage_not_mae() -> None:
    # A model can validly predict a contest whose actual share is undefined
    # (N4 on multi-member wards). The row must count toward coverage but be
    # excluded from MAE - and must not crash the summary.
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: (
            {"party_contest_id": "a", "predicted_party_vote_share": 55.0},
        ),
        N3: (),
    }

    rows, _report = build_prediction_coverage_table(universe, predictions_by_model)
    # Simulate the undefined-target case directly on the joined row: the
    # prediction is valid but no error could be computed.
    for row in rows:
        if row["party_contest_id"] == "a" and row["model_id"] == N2:
            row["actual_party_vote_share"] = None
            row["share_error"] = None
            row["absolute_share_error"] = None
            row["squared_share_error"] = None

    summary = summarise_coverage(rows)[N2]["overall"]

    assert summary["valid_prediction_count"] == 1
    assert summary["share_scored_row_count"] == 0
    assert summary["own_covered_sample_mae"] is None


def test_cohort_specific_summary_isolates_each_cohort() -> None:
    # Row "a" is historical_continuity, row "b" is geographically_non_
    # comparable; the cohort-level summaries must not mix them.
    universe, _f, _t = _small_universe()
    predictions_by_model = {
        N0: (),
        N1: (),
        N2: ({"party_contest_id": "a", "predicted_party_vote_share": 55.0},),
        N3: (),
    }

    rows, _report = build_prediction_coverage_table(universe, predictions_by_model)
    by_cohort = summarise_coverage(rows)[N2]["by_cohort"]

    assert by_cohort["historical_continuity"]["target_count"] == 1
    assert by_cohort["geographically_non_comparable"]["target_count"] == 1
    assert by_cohort["historical_continuity"]["valid_prediction_count"] == 1
    assert by_cohort["geographically_non_comparable"]["valid_prediction_count"] == 0


def test_winner_coverage_requires_a_complete_area_level_prediction_set() -> None:
    # Two parties share one area. Only one gets a real Yes/No; persistence's
    # own area-level gate should therefore leave the WHOLE area unpredicted
    # for winner purposes, not half-predicted.
    features = (
        _feature(
            "x-a",
            "2017",
            "4 May 2017",
            "area-x",
            "Party A",
            previous_party_vote_share=60.0,
            party_was_previous_winner=True,
        ),
        _feature(
            "x-b",
            "2017",
            "4 May 2017",
            "area-x",
            "Party B",
            previous_party_vote_share=40.0,
            party_was_previous_winner=False,
        ),
    )
    targets = (
        _target("x-a", "Party A", 58.0, "Yes"),
        _target("x-b", "Party B", 42.0, "No"),
    )

    winner_metrics = winner_coverage_metrics(features, targets)

    persistence_winner = winner_metrics[N2]
    assert persistence_winner["available"] is True
    assert persistence_winner["winner_eligible_area_count"] == 1
    assert persistence_winner["winner_predicted_area_count"] == 1
    assert persistence_winner["winner_coverage"] == 1.0
    assert persistence_winner["winner_accuracy"] == 1.0

    # N0 and N3 never attempt a winner classification and must say so
    # explicitly rather than reporting a misleading zero.
    assert winner_metrics[N0]["available"] is False
    assert winner_metrics[N3]["available"] is False


def test_common_sample_uses_identical_target_identifiers_across_models() -> None:
    # Reuses model_comparison's own intersection logic; this test checks the
    # wiring, not re-implements the intersection.
    from no_news_baseline.coverage_report import common_sample_metrics

    features = (
        _feature("a1", "2017", "4 May 2017", "area-a", "Party A",
                 previous_party_vote_share=55.0, party_was_previous_winner=True),
        _feature("a2", "2017", "4 May 2017", "area-a", "Party B",
                 previous_party_vote_share=45.0, party_was_previous_winner=False),
        _feature("b1", "2021", "6 May 2021", "area-a", "Party A",
                 previous_party_vote_share=52.0, party_was_previous_winner=True),
        _feature("b2", "2021", "6 May 2021", "area-a", "Party B",
                 previous_party_vote_share=48.0, party_was_previous_winner=False),
    )
    targets = (
        _target("a1", "Party A", 55.0, "Yes"),
        _target("a2", "Party B", 45.0, "No"),
        _target("b1", "Party A", 50.0, "Yes"),
        _target("b2", "Party B", 50.0, "No"),
    )

    result = common_sample_metrics(features, targets, l2_penalty=1.0)

    assert set(result["common_support_share_metrics"]) == {N0, N1, N2, N3}
    for metrics in result["common_support_share_metrics"].values():
        assert metrics["party_share_rows"] == result["shared_contest_count"]
