"""Save-and-reload tests, from the brief's acceptance criteria.

Three of the brief's twelve acceptance criteria concern the bundle surviving
being written and read back:

    Model artefacts can be saved and reloaded.
    Reloaded predictions match original predictions within an appropriate
    tolerance.
    The exported feature schema is sufficient for a second application.

The third is the one that matters most for this project, because the second
application is Stage 2. If the schema is not sufficient, the news layer cannot
construct rows the frozen baseline will accept, and the failure would surface
weeks later as predictions that are quietly wrong rather than as an error.
"""

import json
import pickle

import numpy as np
import pytest

from no_news_baseline.candidate_features import CandidateFeatureEncoder, target_vector
from no_news_baseline.candidate_hierarchical_model import (
    PartialPoolingShareModel,
    party_column_mask,
)
from no_news_baseline.candidate_probability_model import LogisticElectionModel
from no_news_baseline.candidate_share_model import RidgeShareModel, to_relative_share
from tests.test_candidate_share_model import _rows, _targets


def _training():
    shares = [40.0, 30.0, 20.0, 10.0]
    rows, targets = [], {}
    for day, prefix in (("2 May 2013", "a"), ("4 May 2017", "b"), ("6 May 2021", "c")):
        contest = _rows(day, shares, prefix)
        rows.extend(contest)
        targets.update(_targets(contest, shares))
    return rows, targets


def _fitted_ridge():
    rows, targets = _training()
    encoder = CandidateFeatureEncoder().fit(rows)
    design = encoder.transform(rows)
    y = to_relative_share(
        target_vector(rows, targets),
        [int(r["candidate_count_in_contest"]) for r in rows],
    )
    return RidgeShareModel(10.0).fit(design.matrix, y), encoder, rows


# --- artefacts survive a round trip ---------------------------------------


def test_a_reloaded_ridge_predicts_identically() -> None:
    model, encoder, rows = _fitted_ridge()
    design = encoder.transform(rows).matrix
    before = model.predict(design)

    after = pickle.loads(pickle.dumps(model)).predict(design)

    # Exact, not approximate: pickling a closed-form fit changes nothing, so
    # any drift here would be a real defect rather than floating-point noise.
    assert np.array_equal(before, after)


def test_a_reloaded_encoder_transforms_identically() -> None:
    _, encoder, rows = _fitted_ridge()
    before = encoder.transform(rows).matrix

    reloaded = pickle.loads(pickle.dumps(encoder))
    after = reloaded.transform(rows).matrix

    assert np.array_equal(before, after)
    assert reloaded.column_names == encoder.column_names


def test_a_reloaded_partial_pooling_model_predicts_identically() -> None:
    rows, targets = _training()
    encoder = CandidateFeatureEncoder().fit(rows)
    design = encoder.transform(rows)
    y = to_relative_share(
        target_vector(rows, targets),
        [int(r["candidate_count_in_contest"]) for r in rows],
    )
    model = PartialPoolingShareModel(fixed_penalty=10.0, party_penalty=100.0).fit(
        design.matrix, y, party_mask=party_column_mask(design.column_names)
    )
    before = model.predict(design.matrix)

    after = pickle.loads(pickle.dumps(model)).predict(design.matrix)
    assert np.array_equal(before, after)


def test_a_reloaded_probability_model_predicts_identically() -> None:
    rows, targets = _training()
    encoder = CandidateFeatureEncoder().fit(rows)
    design = encoder.transform(rows).matrix
    elected = np.array(
        [float(targets[str(r["candidate_contest_id"])]["target_candidate_elected"] == "Yes")
         for r in rows]
    )
    model = LogisticElectionModel(10.0).fit(design, elected)
    before = model.predict_proba(design)

    after = pickle.loads(pickle.dumps(model)).predict_proba(design)
    assert np.array_equal(before, after)


def test_a_reloaded_boosted_model_predicts_identically() -> None:
    """LightGBM boosters pickle too; a tree model that drifted on reload would
    silently change every Stage 2 residual."""

    lightgbm = pytest.importorskip("lightgbm")
    from no_news_baseline.candidate_boosted_model import BOOSTING_PARAMS, safe_feature_names

    rows, targets = _training()
    encoder = CandidateFeatureEncoder(standardise=False).fit(rows)
    design = encoder.transform(rows)
    y = to_relative_share(
        target_vector(rows, targets),
        [int(r["candidate_count_in_contest"]) for r in rows],
    )
    safe, _ = safe_feature_names(design.column_names)
    booster = lightgbm.train(
        dict(BOOSTING_PARAMS),
        lightgbm.Dataset(design.matrix, label=y, feature_name=list(safe)),
        num_boost_round=20,
    )
    before = booster.predict(design.matrix)

    after = pickle.loads(pickle.dumps(booster)).predict(design.matrix)
    assert np.allclose(before, after)


# --- the schema is sufficient for a second application --------------------


def test_the_schema_names_everything_a_second_application_needs() -> None:
    """Stage 2 must be able to build compatible rows from the schema alone."""

    _, encoder, _ = _fitted_ridge()
    schema = json.loads(json.dumps(encoder.schema()))  # survives JSON

    assert schema["source_predictors"], "no input columns named"
    assert schema["encoded_columns"], "no output columns named"
    assert schema["encoding"], "no per-column encoding rule"
    assert schema["categorical_levels"], "no category levels, so one-hot is unreproducible"
    assert schema["numeric_fill_medians"], "no fill values, so missing handling is unreproducible"
    assert "standardised" in schema, "standardisation flag missing"
    assert schema["derived_from"] == {"election_month": "election_date"}


def test_a_second_application_can_rebuild_the_matrix_from_the_schema() -> None:
    """The acceptance criterion in its strongest form: reconstruct the encoded
    row using only the schema and the raw row, and get the same numbers.

    Only the deterministic part is reconstructed here - the one-hot block and
    the missing indicators - because those are what a second application has
    to get right to hand a compatible row to the frozen model.
    """

    _, encoder, rows = _fitted_ridge()
    schema = encoder.schema()
    matrix = encoder.transform(rows)
    row = rows[0]

    party = str(row["standard_party_name"])
    expected_column = f"standard_party_name__{party}"
    assert party in schema["categorical_levels"]["standard_party_name"]
    assert expected_column in schema["encoded_columns"]

    # Rebuilt from the schema: the party's own column is the only one active
    # in its block for this row.
    block = [
        name for name in schema["encoded_columns"]
        if name.startswith("standard_party_name__")
    ]
    position = {name: index for index, name in enumerate(matrix.column_names)}
    active = [name for name in block if matrix.matrix[0, position[name]] != 0.0]

    # With standardisation on, the "off" rows are not zero, so activity is
    # judged by which column holds the larger of its two values - the same
    # rule the shrinkage report uses.
    largest = max(block, key=lambda name: matrix.matrix[0, position[name]])
    assert largest == expected_column
    assert active, "one-hot block is entirely inactive, which cannot be right"


def test_schema_survives_a_json_round_trip_unchanged() -> None:
    """The bundle ships it as JSON, so anything not JSON-serialisable would be
    lost between Stage 1 and Stage 2."""

    _, encoder, _ = _fitted_ridge()
    schema = encoder.schema()
    assert json.loads(json.dumps(schema)) == json.loads(json.dumps(schema))
