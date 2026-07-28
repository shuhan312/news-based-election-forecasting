"""Tests for the tree model's SHAP explanations."""

import numpy as np
import pytest

from no_news_baseline.candidate_explainability import INTERPRETATION_WARNING
from no_news_baseline.candidate_features import CandidateFeatureEncoder, target_vector
from no_news_baseline.candidate_share_model import to_relative_share
from no_news_baseline.candidate_tree_explainability import (
    compare_gain_and_shap,
    global_shap_importance,
    party_shap_profile,
    shap_contributions,
)
from tests.test_candidate_share_model import _rows, _targets

lightgbm = pytest.importorskip("lightgbm")


@pytest.fixture(scope="module")
def fitted():
    """One small booster plus the encoder it was fitted with."""

    from no_news_baseline.candidate_boosted_model import BOOSTING_PARAMS, safe_feature_names

    shares = [40.0, 30.0, 20.0, 10.0]
    rows, targets = [], {}
    for day, prefix in (("2 May 2013", "a"), ("4 May 2017", "b"), ("6 May 2021", "c")):
        contest = _rows(day, shares, prefix)
        rows.extend(contest)
        targets.update(_targets(contest, shares))

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
        num_boost_round=30,
    )
    return booster, encoder, rows


# --- exactness ------------------------------------------------------------


def test_contributions_plus_base_value_reconstruct_the_prediction(fitted) -> None:
    """TreeSHAP is exact for a tree ensemble, so this is an identity rather
    than an approximation - which is why no separate SHAP package is needed."""

    booster, encoder, rows = fitted
    design = encoder.transform(rows)
    predicted = booster.predict(design.matrix)

    explanations = shap_contributions(
        booster=booster, rows=rows, encoder=encoder, top_n=999
    )
    reconstructed = [e.predicted_relative_share for e in explanations]

    assert reconstructed == pytest.approx(list(predicted), abs=1e-9)


def test_the_base_value_is_the_same_for_every_row(fitted) -> None:
    """The base value is the model's expected output over training, so it is a
    property of the model rather than of the row being explained."""

    booster, encoder, rows = fitted
    explanations = shap_contributions(booster=booster, rows=rows, encoder=encoder)
    bases = {round(e.base_value, 10) for e in explanations}
    assert len(bases) == 1


def test_a_mismatched_encoder_is_refused_rather_than_silently_wrong(fitted) -> None:
    """A booster explained with a different encoder would return contributions
    labelled with the wrong feature names.

    The mismatch has to be real: every contest in the fixture fields the same
    four parties, so an encoder fitted on one of them is the same width as one
    fitted on all three. A fifth party level is added here so the second
    encoder genuinely produces a wider matrix than the booster was trained on.
    """

    booster, _, rows = fitted
    extra = [{**rows[0], "candidate_contest_id": "extra",
              "standard_party_name": "The Green Party"}]
    wider = CandidateFeatureEncoder(standardise=False).fit(rows + extra)

    with pytest.raises(Exception):
        shap_contributions(booster=booster, rows=rows + extra, encoder=wider)


# --- global importance ----------------------------------------------------


def test_global_importance_separates_magnitude_from_direction(fitted) -> None:
    """A feature pushing some rows up and others down by the same amount
    averages to zero while being highly influential."""

    booster, encoder, rows = fitted
    importance = global_shap_importance(booster=booster, rows=rows, encoder=encoder)

    assert importance
    assert all(entry["mean_absolute_shap"] >= 0 for entry in importance)
    assert any("mean_shap" in entry for entry in importance)
    # Ranked by magnitude.
    magnitudes = [entry["mean_absolute_shap"] for entry in importance]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_importance_records_how_many_rows_it_was_measured_on(fitted) -> None:
    booster, encoder, rows = fitted
    importance = global_shap_importance(booster=booster, rows=rows, encoder=encoder)
    assert all(entry["rows"] == len(rows) for entry in importance)


# --- party profiles -------------------------------------------------------


def test_reform_profile_uses_only_reform_rows(fitted) -> None:
    """A tree has no per-party coefficient, so party importance can only mean
    what moves that party's rows."""

    booster, encoder, rows = fitted
    profile = party_shap_profile(
        booster=booster, rows=rows, encoder=encoder, reform_only=True
    )
    assert profile["rows"] == 3
    assert profile["importance"]
    assert profile["interpretation_warning"] == INTERPRETATION_WARNING


def test_an_empty_party_selection_returns_no_rows_rather_than_raising(fitted) -> None:
    booster, encoder, rows = fitted
    profile = party_shap_profile(
        booster=booster, rows=rows, encoder=encoder, party="A Party That Never Stood"
    )
    assert profile["rows"] == 0
    assert profile["importance"] == []


def test_the_profile_reports_the_prediction_it_decomposes(fitted) -> None:
    booster, encoder, rows = fitted
    profile = party_shap_profile(
        booster=booster, rows=rows, encoder=encoder, reform_only=True
    )
    design = encoder.transform([r for r in rows if r.get("is_reform_uk")])
    expected = float(np.mean(booster.predict(design.matrix)))
    assert profile["mean_predicted_relative_share"] == pytest.approx(expected, abs=1e-9)


# --- gain versus SHAP -----------------------------------------------------


def test_gain_and_shap_are_reported_side_by_side_with_their_disagreement(fitted) -> None:
    """The two measure different things, so a rank gap is a finding rather
    than an error to be resolved."""

    booster, encoder, rows = fitted
    table = compare_gain_and_shap(booster=booster, rows=rows, encoder=encoder, top_n=10)

    assert table
    entry = table[0]
    assert {"feature", "gain", "gain_rank", "mean_absolute_shap", "shap_rank",
            "rank_disagreement"} <= set(entry)
    assert all(
        e["rank_disagreement"] is None or e["rank_disagreement"] >= 0 for e in table
    )


def test_every_explanation_carries_the_interpretation_warning(fitted) -> None:
    booster, encoder, rows = fitted
    explanations = shap_contributions(booster=booster, rows=rows, encoder=encoder)
    assert explanations[0].interpretation_warning == INTERPRETATION_WARNING
