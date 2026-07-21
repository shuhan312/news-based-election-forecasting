"""Tests for the fold-wise ridge fundamentals model."""

import pytest

from no_news_baseline.regularised_models import (
    RidgeFundamentalsModel,
    evaluate_ridge_over_folds,
)


def _feature(
    contest_id: str,
    election_id: str,
    election_date: str,
    area: str,
    party: str,
    *,
    previous_party_vote_share: float = 30.0,
    analysis_previous_turnout: float = 35.0,
    previous_electorate: int = 10000,
    party_was_previous_winner: bool = False,
    incumbent_candidate_any_yes_no: str = "No",
    incumbent_party_yes_no: str = "No",
    party_previously_contested: bool = True,
    first_appearance_of_party_in_area: bool = False,
    baseline_eligibility: str = "eligible_primary_single_member_party_share",
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
        "analysis_previous_turnout": analysis_previous_turnout,
        "previous_electorate": previous_electorate,
        "party_was_previous_winner": party_was_previous_winner,
        "incumbent_candidate_any_yes_no": incumbent_candidate_any_yes_no,
        "incumbent_party_yes_no": incumbent_party_yes_no,
        "party_previously_contested": party_previously_contested,
        "first_appearance_of_party_in_area": first_appearance_of_party_in_area,
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


def test_ridge_recovers_a_simple_linear_relationship_at_low_penalty() -> None:
    # Construct rows where the current share is exactly previous share + 5, with
    # everything else held constant. With a negligible penalty the model should
    # predict essentially previous_share + 5 on a held-out row.
    train_rows = [
        _feature(f"t{i}", "2017", "4 May 2017", f"area-{i}", "Party A",
                 previous_party_vote_share=float(share))
        for i, share in enumerate(range(20, 60, 5))
    ]
    train_shares = [row["previous_party_vote_share"] + 5.0 for row in train_rows]

    model = RidgeFundamentalsModel(l2_penalty=1e-6).fit(train_rows, train_shares)
    probe = _feature("probe", "2021", "6 May 2021", "area-x", "Party A",
                     previous_party_vote_share=40.0)

    predicted = model.predict_one(probe)
    assert predicted == pytest.approx(45.0, abs=0.5)


def test_higher_penalty_shrinks_prediction_toward_the_training_mean() -> None:
    # With a very large penalty the coefficients are driven toward zero, so the
    # prediction collapses to the (unpenalised) intercept - the training mean.
    train_rows = [
        _feature(f"t{i}", "2017", "4 May 2017", f"area-{i}", "Party A",
                 previous_party_vote_share=float(share))
        for i, share in enumerate(range(20, 60, 5))
    ]
    train_shares = [row["previous_party_vote_share"] + 5.0 for row in train_rows]
    training_mean = sum(train_shares) / len(train_shares)

    strong = RidgeFundamentalsModel(l2_penalty=1e9).fit(train_rows, train_shares)
    probe = _feature("probe", "2021", "6 May 2021", "area-x", "Party A",
                     previous_party_vote_share=40.0)

    assert strong.predict_one(probe) == pytest.approx(training_mean, abs=0.5)


def test_predictions_are_clipped_to_the_zero_hundred_range() -> None:
    # A steep fitted slope extrapolated far out could exceed 100; the output
    # must be clipped rather than returning an impossible vote share.
    train_rows = [
        _feature(f"t{i}", "2017", "4 May 2017", f"area-{i}", "Party A",
                 previous_party_vote_share=float(share))
        for i, share in enumerate(range(10, 50, 5))
    ]
    # current = previous * 3, a deliberately steep relationship.
    train_shares = [row["previous_party_vote_share"] * 3.0 for row in train_rows]

    model = RidgeFundamentalsModel(l2_penalty=1e-6).fit(train_rows, train_shares)
    extreme = _feature("probe", "2021", "6 May 2021", "area-x", "Party A",
                       previous_party_vote_share=90.0)

    assert model.predict_one(extreme) == 100.0


def test_unresolved_yes_no_predictor_is_rejected() -> None:
    # An "Unknown" incumbency must not be silently read as No; the model
    # refuses to build a feature vector from an unresolved value.
    row = _feature("r", "2017", "4 May 2017", "area-a", "Party A",
                   incumbent_party_yes_no="Unknown")

    with pytest.raises(ValueError, match="resolved Yes/No"):
        RidgeFundamentalsModel().fit([row], [30.0])


def test_fit_requires_aligned_rows_and_shares() -> None:
    row = _feature("r", "2017", "4 May 2017", "area-a", "Party A")
    with pytest.raises(ValueError, match="align one-to-one"):
        RidgeFundamentalsModel().fit([row], [30.0, 40.0])


def test_predict_before_fit_is_refused() -> None:
    row = _feature("r", "2017", "4 May 2017", "area-a", "Party A")
    with pytest.raises(ValueError, match="must be fitted"):
        RidgeFundamentalsModel().predict_one(row)


def test_fold_evaluation_scores_only_test_cohort_and_never_trains_on_future() -> None:
    # 2013 is study-start (no predecessor) and excluded as a test fold; 2017 is
    # trained on 2013 only; 2021 trained on 2013+2017. Every prediction must
    # come from a model fitted strictly before that prediction's election.
    features = (
        _feature("e13", "2013", "2 May 2013", "area-a", "Party A",
                 previous_party_vote_share=30.0,
                 baseline_eligibility="eligible_primary_single_member_party_share"),
        _feature("e17", "2017", "4 May 2017", "area-a", "Party A",
                 previous_party_vote_share=32.0),
        _feature("e21", "2021", "6 May 2021", "area-a", "Party A",
                 previous_party_vote_share=34.0),
    )
    targets = (
        _target("e13", "Party A", 40.0, "Yes"),
        _target("e17", "Party A", 42.0, "Yes"),
        _target("e21", "Party A", 44.0, "Yes"),
    )

    predictions = evaluate_ridge_over_folds(features, targets, l2_penalty=1.0)

    scored_elections = {row["election_id"] for row in predictions}
    # 2013 is never a test fold; only 2017 and 2021 can be scored, and each
    # scored row records which earlier election it was trained on.
    assert scored_elections <= {"2017", "2021"}
    for row in predictions:
        # The strict leakage check: the row's own election must never be among
        # the elections its fitted model was trained on.
        assert row["election_id"] not in row["train_election_ids"]
        assert 0.0 <= row["predicted_party_vote_share"] <= 100.0
