"""Tests for the candidate design-matrix encoder.

The properties under test are the leakage and missing-value rules, not the
arithmetic: an encoder that quietly turns Unknown into No, or a missing
previous share into zero, would still produce a matrix of the right shape.
"""

import numpy as np
import pytest

from no_news_baseline.candidate_features import (
    CandidateFeatureEncoder,
    DesignMatrix,
    target_vector,
)


def _row(
    row_id: str,
    *,
    party: str = "Conservative",
    previous_share: float | None = 40.0,
    incumbent_candidate: str = "No",
    stood_before: bool | None = False,
    reform: bool = False,
    ukip: bool = False,
    election_date: str = "6 May 2021",
    seats: int = 1,
) -> dict[str, object]:
    """A row carrying every permitted predictor the encoder consumes."""

    return {
        "candidate_contest_id": row_id,
        # identifiers and linkage: present in the release, must be ignored
        "election_id": "2021",
        "division_id": "d1",
        "candidate_id": "cand-1",
        "candidate_name": "A Name",
        "standard_candidate_name": "A Name",
        "division_name": "A Division",
        "current_result_source_url": "https://example/result",
        "historical_source_url": "https://example/previous",
        "historical_permission_source_urls": "https://example/order",
        "candidate_baseline_eligibility": "eligible_candidate_vote_share",
        "party_group_key": f"party:{party}",
        "party_identity_scope": "reviewed_standard_party",
        "original_party_name": party,
        "previous_election_id": "2017",
        "previous_division_name": "A Division",
        "historical_reference_status": "approved_pre_2024_legal_continuity",
        "previous_party_vote_share_status": "derived",
        "candidate_history_status": "resolved",
        "incumbent_candidate_yes_no_status": "resolved",
        "incumbent_party_yes_no_status": "resolved",
        "party_history_status": "approved",
        "analysis_number_of_seats_provenance": "official_result_page",
        "analysis_previous_turnout_provenance": "official",
        # permitted predictors
        "election_date": election_date,
        "election_year": 2021,
        "election_type": "County Council election",
        "authority": "Surrey County Council",
        "analysis_number_of_seats": seats,
        "contest_structure": "single_member" if seats == 1 else "multi_member",
        "candidate_count_in_contest": 4,
        "party_count_in_contest": 4,
        "party_candidate_count_in_contest": 1,
        "standard_party_name": party,
        "party_category": "established",
        "is_reform_uk": reform,
        "is_ukip": ukip,
        "previous_party_vote_share": previous_share,
        "analysis_previous_turnout": 35.0,
        "previous_electorate": 10_000,
        "previous_winning_party": "Conservative",
        "party_was_previous_winner": True,
        "candidate_previously_stood": stood_before,
        "incumbent_candidate_yes_no": incumbent_candidate,
        "incumbent_party_yes_no": "Yes",
        "party_previously_contested": True,
        "first_appearance_of_party_in_area": False,
        "historical_predictor_availability": "approved_previous_party_share",
        "geographic_reference_eligibility": "approved_historical_reference",
    }


def _train() -> list[dict[str, object]]:
    return [
        _row("r1", party="Conservative", previous_share=45.0),
        _row("r2", party="Labour", previous_share=30.0),
        _row("r3", party="Liberal Democrats", previous_share=20.0),
        _row("r4", party="Reform UK", previous_share=None, reform=True),
    ]


def _column(matrix: DesignMatrix, name: str) -> np.ndarray:
    return matrix.matrix[:, matrix.column_names.index(name)]


# --- what may enter the matrix -------------------------------------------


def test_only_permitted_predictors_are_consumed() -> None:
    encoder = CandidateFeatureEncoder().fit(_train())
    consumed = set(encoder.source_predictors)

    assert "previous_party_vote_share" in consumed
    assert "is_reform_uk" in consumed
    # Identity, provenance and cohort columns are present in the row but never
    # consumed, so the model cannot memorise a person or an area name.
    assert "candidate_id" not in consumed
    assert "candidate_name" not in consumed
    assert "division_name" not in consumed
    assert "current_result_source_url" not in consumed
    assert "historical_reference_status" not in consumed
    assert "candidate_baseline_eligibility" not in consumed


def test_a_target_column_smuggled_into_the_rows_is_never_encoded() -> None:
    rows = [{**row, "analysis_vote_share": 40.0} for row in _train()]
    encoder = CandidateFeatureEncoder().fit(rows)

    assert "analysis_vote_share" not in encoder.source_predictors
    assert not any("analysis_vote_share" in name for name in encoder.column_names)


# --- unknown is not No, missing is not zero ------------------------------


def test_unknown_incumbency_gets_its_own_column_and_is_not_read_as_no() -> None:
    train = _train() + [_row("r5", incumbent_candidate="Unknown")]
    encoder = CandidateFeatureEncoder(standardise=False).fit(train)
    matrix = encoder.transform(train)

    yes = _column(matrix, "incumbent_candidate_yes_no__yes")
    unknown = _column(matrix, "incumbent_candidate_yes_no__unknown")

    # The four "No" rows are the reference level: both indicators are zero.
    assert list(yes[:4]) == [0.0, 0.0, 0.0, 0.0]
    assert list(unknown[:4]) == [0.0, 0.0, 0.0, 0.0]
    # The Unknown row is distinguishable from them.
    assert unknown[4] == 1.0
    assert yes[4] == 0.0


def test_missing_previous_share_is_flagged_not_silently_zeroed() -> None:
    encoder = CandidateFeatureEncoder(standardise=False).fit(_train())
    matrix = encoder.transform(_train())

    missing = _column(matrix, "previous_party_vote_share__missing")
    value = _column(matrix, "previous_party_vote_share")

    assert list(missing) == [0.0, 0.0, 0.0, 1.0]
    # The Reform row's fill is the training median (30.0), never 0.0, because
    # zero is itself a meaningful vote share.
    assert value[3] == 30.0
    assert value[3] != 0.0


def test_unknown_boolean_is_distinct_from_false() -> None:
    train = _train() + [_row("r5", stood_before=None)]
    encoder = CandidateFeatureEncoder(standardise=False).fit(train)
    matrix = encoder.transform(train)

    true = _column(matrix, "candidate_previously_stood__true")
    unknown = _column(matrix, "candidate_previously_stood__unknown")

    assert list(true[:4]) == [0.0, 0.0, 0.0, 0.0]
    assert list(unknown[:4]) == [0.0, 0.0, 0.0, 0.0]
    assert unknown[4] == 1.0


# --- fitted on training rows only ----------------------------------------


def test_category_levels_come_only_from_training_rows() -> None:
    encoder = CandidateFeatureEncoder(standardise=False).fit(_train())

    assert "standard_party_name__Conservative" in encoder.column_names
    # The Green Party never appears in training, so it gets no column.
    assert "standard_party_name__The Green Party" not in encoder.column_names


def test_an_unseen_party_at_test_time_is_flagged_not_mapped_to_another() -> None:
    encoder = CandidateFeatureEncoder(standardise=False).fit(_train())
    unseen = [_row("t1", party="The Green Party")]
    matrix = encoder.transform(unseen)

    assert _column(matrix, "standard_party_name__unseen_level")[0] == 1.0
    # It is not silently attributed to any party seen in training.
    for name in matrix.column_names:
        if name.startswith("standard_party_name__") and not name.endswith("unseen_level"):
            assert _column(matrix, name)[0] == 0.0


def test_test_rows_never_change_the_transformation() -> None:
    """Standardisation and medians are fitted once; a test row cannot move
    them, so the same row transforms identically whatever it is scored with."""

    encoder = CandidateFeatureEncoder().fit(_train())
    alone = encoder.transform([_row("t1", previous_share=10.0)])
    with_others = encoder.transform(
        [_row("t1", previous_share=10.0), _row("t2", previous_share=90.0)]
    )
    assert np.allclose(alone.matrix[0], with_others.matrix[0])


def test_standardisation_leaves_a_constant_training_column_unscaled() -> None:
    """A zero-variance column must not be divided by zero; after centring it
    contributes nothing, which is correct for a feature training never varied."""

    encoder = CandidateFeatureEncoder().fit(_train())
    matrix = encoder.transform(_train())

    # authority is constant across the training fold.
    column = _column(matrix, "authority__Surrey County Council")
    assert np.all(np.isfinite(column))
    assert np.allclose(column, 0.0)


# --- derived features -----------------------------------------------------


def test_election_month_is_derived_from_the_polling_date() -> None:
    encoder = CandidateFeatureEncoder(standardise=False).fit(_train())
    matrix = encoder.transform(
        [_row("t1", election_date="6 May 2021"), _row("t2", election_date="21 August 2025")]
    )
    assert list(_column(matrix, "election_month")) == [5.0, 8.0]


def test_an_unparsable_date_is_flagged_rather_than_guessed() -> None:
    encoder = CandidateFeatureEncoder(standardise=False).fit(_train())
    matrix = encoder.transform([_row("t1", election_date="sometime in spring")])

    assert _column(matrix, "election_month__missing")[0] == 1.0


# --- shape, order and schema ---------------------------------------------


def test_matrix_rows_stay_joined_to_their_contest_ids() -> None:
    encoder = CandidateFeatureEncoder().fit(_train())
    matrix = encoder.transform(_train())

    assert matrix.row_ids == ("r1", "r2", "r3", "r4")
    assert matrix.matrix.shape == (4, len(matrix.column_names))


def test_column_order_is_deterministic_across_refits() -> None:
    first = CandidateFeatureEncoder().fit(_train()).column_names
    second = CandidateFeatureEncoder().fit(list(reversed(_train()))).column_names
    assert first == second


def test_schema_is_sufficient_to_rebuild_the_encoding_elsewhere() -> None:
    """The brief requires feature_schema.json to let a separate application
    construct compatible rows - which Stage 2 and the scenario tool need."""

    schema = CandidateFeatureEncoder().fit(_train()).schema()

    assert schema["encoded_columns"]
    assert "standard_party_name" in schema["categorical_levels"]
    assert "previous_party_vote_share" in schema["numeric_fill_medians"]
    assert schema["derived_from"] == {"election_month": "election_date"}


def test_transform_before_fit_raises() -> None:
    with pytest.raises(ValueError, match="must be fitted"):
        CandidateFeatureEncoder().transform(_train())


def test_fitting_on_no_rows_raises() -> None:
    with pytest.raises(ValueError, match="empty training set"):
        CandidateFeatureEncoder().fit([])


# --- targets --------------------------------------------------------------


def test_target_vector_follows_matrix_row_order() -> None:
    rows = _train()
    targets = {
        "r1": {"target_candidate_vote_share": 45.0},
        "r2": {"target_candidate_vote_share": 30.0},
        "r3": {"target_candidate_vote_share": 15.0},
        "r4": {"target_candidate_vote_share": 10.0},
    }
    assert list(target_vector(rows, targets)) == [45.0, 30.0, 15.0, 10.0]


def test_a_row_with_no_observed_share_raises_rather_than_defaulting() -> None:
    rows = [_row("r1")]
    targets = {"r1": {"target_candidate_vote_share": None}}
    with pytest.raises(ValueError, match="not an eligible prediction target"):
        target_vector(rows, targets)
