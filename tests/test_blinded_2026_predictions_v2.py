"""Tests for the v2 (enrichment) blinded prediction freeze.

Only the new surface is tested here — the v2 fitting aggregator's guards.
Everything else (outcome stripping, normalisation, ranks, the freeze) is
v1 code already under test in test_blinded_2026_predictions.py.
"""

import pytest

from src.news_modelling.blinded_2026_predictions_v2 import (
    ProductionExperimentError,
    aggregate_v2_residuals,
)


def _row(election, party, predicted, observed, candidate):
    return {
        "candidate_contest_id": candidate,
        "election_id": election,
        "standard_party_name": party,
        "predicted_vote_share": str(predicted),
        "observed_vote_share": str(observed),
    }


from src.news_collection.run_byelection_stages import BYELECTION_POLLING_DAYS

BYELECTIONS = sorted(BYELECTION_POLLING_DAYS)
BYELECTION = "surrey-county-council-by-election-addlestone-2025-08-21"


def _fixture():
    rows = []
    parties = ("Conservative", "Labour", "Liberal Democrats",
               "UK Independence Party", "The Green Party")
    for election in ("surrey-county-council-2017", "surrey-county-council-2021"):
        for i, party in enumerate(parties):
            rows.append(_row(election, party, 30.0, 30.0 + i,
                             f"{election}-{party}"))
    # Real by-election ids so the FIT_ELECTION_MAP admits them; Reform
    # stands in exactly one, Conservative in all of them.
    for election in BYELECTIONS:
        for i in range(2):
            rows.append(_row(election, "Conservative", 40.0, 35.0,
                             f"{election}-con-{i}"))
    for i in range(10):
        rows.append(_row(BYELECTION, "Reform UK", 20.0, 25.0, f"bye-ref-{i}"))
    rows.append(_row(BYELECTION, "Labour", 10.0, 12.0, "bye-lab"))
    return rows


def test_v2_fit_requires_a_byelection_reform_cell():
    rows = [r for r in _fixture() if r["standard_party_name"] != "Reform UK"]
    with pytest.raises(ProductionExperimentError):
        aggregate_v2_residuals(rows)


def test_v2_fit_still_forbids_reform_in_2017():
    rows = _fixture() + [
        _row("surrey-county-council-2017", "Reform UK", 5.0, 6.0, "2017-ref")
    ]
    with pytest.raises(ProductionExperimentError):
        aggregate_v2_residuals(rows)


def test_v2_fit_aggregates_party_means_per_election():
    rows = aggregate_v2_residuals(_fixture() * 2)  # duplicates change nothing
    reform = [r for r in rows if r["party_key"] == "reform_uk"]
    assert len(reform) == 1
    assert reform[0]["election_id"] == BYELECTION
    assert reform[0]["mean_residual"] == pytest.approx(5.0)
    # One row per (election, party): 5 parties x 2 principals, Conservative
    # in all 8 by-elections, Reform and Labour in one of them.
    assert len(rows) == 10 + 8 + 2
