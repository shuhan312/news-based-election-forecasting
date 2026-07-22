"""Tests for the N4 cold-start shrunk-party-strength baseline."""

import pytest

from no_news_baseline.cold_start_model import (
    COLD_START_MODEL_ID,
    ablation_unsmoothed_vs_smoothed,
    evaluate_cold_start_over_folds,
    tag_universe_with_cold_start_eligibility,
)
from no_news_baseline.coverage_evaluation import build_evaluation_universe


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
    party_identity_scope: str = "reviewed_standard_party",
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


def _two_election_fixture():
    # 2013: Party A realises 60, Party B realises 40 (history pool).
    # 2017: same two parties contest the same area again (the test fold).
    features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A"),
        _feature("t-b", "2017", "4 May 2017", "area-t", "Party B"),
    )
    targets = (
        _target("h-a", "Party A", 60.0, "Yes"),
        _target("h-b", "Party B", 40.0, "No"),
        _target("t-a", "Party A", 55.0, "Yes"),
        _target("t-b", "Party B", 45.0, "No"),
    )
    return features, targets


def test_shrinkage_formula_matches_hand_computed_values() -> None:
    # With lambda=1 and one observation each: w = 1/2, prior = 50.
    # Party A strength = 0.5*60 + 0.5*50 = 55; Party B = 0.5*40 + 0.5*50 = 45.
    # Already summing to 100, normalisation leaves them unchanged.
    features, targets = _two_election_fixture()

    predictions = evaluate_cold_start_over_folds(features, targets, shrinkage_lambda=1.0)

    by_id = {row["party_contest_id"]: row for row in predictions}
    assert by_id["t-a"]["shrinkage_weight"] == 0.5
    assert by_id["t-a"]["predicted_party_vote_share"] == pytest.approx(55.0)
    assert by_id["t-b"]["predicted_party_vote_share"] == pytest.approx(45.0)
    assert by_id["t-a"]["absolute_share_error"] == pytest.approx(0.0)


def test_zero_history_party_receives_the_prior_not_a_missing_prediction() -> None:
    # Reform UK has no prior Surrey observation: its strength must be the
    # equal-share prior, giving a real prediction rather than a blank.
    features, targets = _two_election_fixture()
    features = features + (
        _feature("t-r", "2017", "4 May 2017", "area-t", "Reform UK"),
    )
    targets = targets + (_target("t-r", "Reform UK", 20.0, "No"),)

    predictions = evaluate_cold_start_over_folds(features, targets, shrinkage_lambda=1.0)

    reform = next(row for row in predictions if row["standard_party_name"] == "Reform UK")
    assert reform["historical_observation_count"] == 0
    assert reform["raw_historical_party_mean"] is None
    assert reform["shrinkage_weight"] == 0.0
    # prior = 100/3; strengths: A=0.5*60+0.5*33.33=46.67, B=36.67, R=33.33.
    assert reform["smoothed_party_strength"] == pytest.approx(100.0 / 3.0)
    assert reform["predicted_party_vote_share"] is not None


def test_contest_shares_are_normalised_to_sum_to_one_hundred() -> None:
    features, targets = _two_election_fixture()
    features = features + (
        _feature("t-r", "2017", "4 May 2017", "area-t", "Reform UK"),
    )
    targets = targets + (_target("t-r", "Reform UK", 20.0, "No"),)

    predictions = evaluate_cold_start_over_folds(features, targets)

    total = sum(
        float(row["predicted_party_vote_share"])
        for row in predictions
        if row["election_id"] == "2017"
    )
    assert total == pytest.approx(100.0, abs=1e-9)
    assert all(float(row["predicted_party_vote_share"]) >= 0 for row in predictions)


def test_predictions_ignore_previous_local_party_vote_share_entirely() -> None:
    # N4's defining constraint: local history must not matter. Flip the
    # previous_party_vote_share fields and the predictions must be identical.
    features, targets = _two_election_fixture()
    with_local = tuple(
        {**row, "previous_party_vote_share": 99.0} for row in features
    )
    without_local = tuple(
        {**row, "previous_party_vote_share": None} for row in features
    )

    predictions_with = evaluate_cold_start_over_folds(with_local, targets)
    predictions_without = evaluate_cold_start_over_folds(without_local, targets)

    shares_with = {
        row["party_contest_id"]: row["predicted_party_vote_share"]
        for row in predictions_with
    }
    shares_without = {
        row["party_contest_id"]: row["predicted_party_vote_share"]
        for row in predictions_without
    }
    assert shares_with == shares_without


def test_ukip_history_never_feeds_reform_uk() -> None:
    # UKIP realised 25 in 2013. Reform UK contests in 2017: it must be
    # scored as zero-history (prior), not as inheriting UKIP's mean.
    features = (
        _feature("h-u", "2013", "2 May 2013", "area-h", "UKIP"),
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("t-r", "2017", "4 May 2017", "area-t", "Reform UK"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A"),
    )
    targets = (
        _target("h-u", "UKIP", 25.0, "No"),
        _target("h-a", "Party A", 75.0, "Yes"),
        _target("t-r", "Reform UK", 30.0, "No"),
        _target("t-a", "Party A", 70.0, "Yes"),
    )

    predictions = evaluate_cold_start_over_folds(features, targets)

    reform = next(row for row in predictions if row["standard_party_name"] == "Reform UK")
    assert reform["historical_observation_count"] == 0
    assert reform["raw_historical_party_mean"] is None


def test_candidate_specific_independents_are_never_pooled() -> None:
    # An Independent realised 45 in 2013. A different Independent stands in
    # 2017: pooling them would fabricate an "Independent party" strength, so
    # the 2017 Independent must be zero-history.
    features = (
        _feature("h-i", "2013", "2 May 2013", "area-h", "Independent",
                 party_identity_scope="candidate_specific_independent"),
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("t-i", "2017", "4 May 2017", "area-t", "Independent",
                 party_identity_scope="candidate_specific_independent"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A"),
    )
    targets = (
        _target("h-i", "Independent", 45.0, "No"),
        _target("h-a", "Party A", 55.0, "Yes"),
        _target("t-i", "Independent", 40.0, "No"),
        _target("t-a", "Party A", 60.0, "Yes"),
    )

    predictions = evaluate_cold_start_over_folds(features, targets)

    independent = next(
        row for row in predictions if row["standard_party_name"] == "Independent"
    )
    assert independent["historical_observation_count"] == 0


def test_strict_temporal_cutoff_excludes_the_target_election_itself() -> None:
    # Party A's 2017 realised share (95) is wildly different from its 2013
    # history (60). If the model peeked at 2017 outcomes, its 2017 prediction
    # would move toward 95; it must instead be built from 2013 alone.
    features, targets = _two_election_fixture()
    targets = tuple(
        {**row, "target_party_vote_share": 95.0}
        if row["party_contest_id"] == "t-a"
        else row
        for row in targets
    )

    predictions = evaluate_cold_start_over_folds(features, targets, shrinkage_lambda=1.0)

    prediction_a = next(row for row in predictions if row["party_contest_id"] == "t-a")
    # Strength = 0.5*60 + 0.5*50 = 55 from 2013 history; unaffected by the 95.
    assert prediction_a["raw_historical_party_mean"] == 60.0
    assert prediction_a["predicted_party_vote_share"] == pytest.approx(55.0)
    assert prediction_a["prediction_information_cutoff"] == "2017-05-04"


def test_multi_member_contest_is_predicted_but_gets_no_winner_call() -> None:
    features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("m-a", "2026", "7 May 2026", "ward-m", "Party A",
                 contest_structure="multi_member",
                 baseline_eligibility="excluded_non_single_member_primary_estimand",
                 geographic_reference_eligibility="no_approved_predecessor"),
        _feature("m-b", "2026", "7 May 2026", "ward-m", "Party B",
                 contest_structure="multi_member",
                 baseline_eligibility="excluded_non_single_member_primary_estimand",
                 geographic_reference_eligibility="no_approved_predecessor"),
    )
    targets = (
        _target("h-a", "Party A", 60.0, "Yes"),
        _target("h-b", "Party B", 40.0, "No"),
        _target("m-a", "Party A", None, "Yes",
                status="not_defined_for_multi_member_party_contest"),
        _target("m-b", "Party B", None, "No",
                status="not_defined_for_multi_member_party_contest"),
    )

    predictions = evaluate_cold_start_over_folds(features, targets)

    ward_rows = [row for row in predictions if row["election_id"] == "2026"]
    assert len(ward_rows) == 2
    # Geography-agnostic prediction exists despite no approved predecessor...
    assert all(row["predicted_party_vote_share"] is not None for row in ward_rows)
    # ...but no share error (target undefined) and no winner call (repo rule
    # against converting vote rankings into seat predictions).
    assert all(row["absolute_share_error"] is None for row in ward_rows)
    assert {row["predicted_party_elected"] for row in ward_rows} == {"Unknown"}
    assert {row["winner_prediction_status"] for row in ward_rows} == {
        "not_applicable_multi_member_contest"
    }


def test_single_member_winner_is_unique_leader_and_ties_are_unknown() -> None:
    features, targets = _two_election_fixture()

    predictions = evaluate_cold_start_over_folds(features, targets, shrinkage_lambda=1.0)

    by_id = {row["party_contest_id"]: row for row in predictions}
    assert by_id["t-a"]["predicted_party_elected"] == "Yes"
    assert by_id["t-b"]["predicted_party_elected"] == "No"
    assert by_id["t-a"]["winner_prediction_correct"] is True

    # Symmetric two-party contest with identical histories ties exactly.
    tie_features = (
        _feature("h-a", "2013", "2 May 2013", "area-h", "Party A"),
        _feature("h-b", "2013", "2 May 2013", "area-h", "Party B"),
        _feature("t-a", "2017", "4 May 2017", "area-t", "Party A"),
        _feature("t-b", "2017", "4 May 2017", "area-t", "Party B"),
    )
    tie_targets = (
        _target("h-a", "Party A", 50.0, "Yes"),
        _target("h-b", "Party B", 50.0, "No"),
        _target("t-a", "Party A", 52.0, "Yes"),
        _target("t-b", "Party B", 48.0, "No"),
    )
    tie_predictions = evaluate_cold_start_over_folds(tie_features, tie_targets)
    tie_by_id = {row["party_contest_id"]: row for row in tie_predictions}
    assert tie_by_id["t-a"]["predicted_party_elected"] == "Unknown"
    assert tie_by_id["t-a"]["winner_prediction_correct"] is None


def test_deterministic_reproducibility() -> None:
    features, targets = _two_election_fixture()

    first = evaluate_cold_start_over_folds(features, targets)
    second = evaluate_cold_start_over_folds(features, targets)

    assert first == second


def test_ablation_reports_both_variants_on_identical_rows() -> None:
    features, targets = _two_election_fixture()

    ablation = ablation_unsmoothed_vs_smoothed(features, targets, shrinkage_lambda=1.0)

    assert ablation["scored_row_count"] == 2
    # Unsmoothed carries the raw 2013 means (60/40) into 2017 (actual 55/45):
    # MAE = 5. Smoothed (w=0.5) predicts 55/45 exactly: MAE = 0.
    assert ablation["unsmoothed_party_mean_mae"] == pytest.approx(5.0)
    assert ablation["smoothed_party_prior_mae"] == pytest.approx(0.0)


def test_universe_tagging_marks_study_start_election_ineligible() -> None:
    features, targets = _two_election_fixture()
    universe = build_evaluation_universe(features, targets)

    tagged = tag_universe_with_cold_start_eligibility(universe, features, targets)

    by_id = {row["party_contest_id"]: row for row in tagged}
    assert by_id["h-a"]["eligible_n4_cold_start"] is False  # 2013: no earlier data
    assert by_id["t-a"]["eligible_n4_cold_start"] is True


def test_integration_with_coverage_report_classification() -> None:
    # The generalised coverage join must accept N4 alongside N0-N3 and give
    # it 100% eligibility-conditioned coverage on this small fixture.
    from no_news_baseline.coverage_report import (
        ELIGIBILITY_FIELD_BY_MODEL,
        MODEL_IDS,
        build_prediction_coverage_table,
        summarise_coverage,
    )

    features, targets = _two_election_fixture()
    universe = tag_universe_with_cold_start_eligibility(
        build_evaluation_universe(features, targets), features, targets
    )
    n4_predictions = evaluate_cold_start_over_folds(features, targets)

    rows, report = build_prediction_coverage_table(
        universe,
        {COLD_START_MODEL_ID: n4_predictions},
        model_ids=(*MODEL_IDS, COLD_START_MODEL_ID),
        eligibility_field_by_model={
            **ELIGIBILITY_FIELD_BY_MODEL,
            COLD_START_MODEL_ID: "eligible_n4_cold_start",
        },
    )

    assert report["mismatch_count"] == 0
    summary = summarise_coverage(rows)[COLD_START_MODEL_ID]["overall"]
    assert summary["theoretically_eligible_count"] == 2
    assert summary["valid_prediction_count"] == 2
    assert summary["eligibility_conditioned_coverage"] == 1.0
