"""Tests for the identity placebo.

The risk here is not a crash. It is that an arm which claims to know
nothing about news quietly learns something it should not: a prior share
taken from the election it is predicting, a tone centre estimated using
the holdout, or a party indicator that has stopped indicating a party.
Each of those would turn a null into a headline, so each is asserted
against directly.
"""

import json
from pathlib import Path

import pytest

from src.news_modelling.blinded_2026_predictions import HOLDOUT_NEWS_ELECTION
from src.news_modelling.identity_placebos import (ARMS, DUMMY_COLUMNS,
                                                  PARTIES, PRIOR_ELECTION)

RESULTS = Path(
    "news_features/identity_placebos_v1/identity_placebo_results.json")

needs_results = pytest.mark.skipif(
    not RESULTS.exists(), reason="identity placebo results not built")


@pytest.fixture(scope="module")
def payload():
    return json.loads(RESULTS.read_text())


# ---- no arm may read its own outcome ---------------------------------

def test_every_prior_election_is_earlier_than_the_one_it_feeds():
    # A prior share drawn from the target election would make the placebo a
    # leak rather than a control, and it would win for the wrong reason.
    years = {
        "SCC-2013-05": 2013,
        "SCC-2017-05": 2017,
        "surrey-county-council-2017": 2017,
        "SCC-2021-05": 2021,
        "surrey-county-council-2021": 2021,
        HOLDOUT_NEWS_ELECTION: 2026,
    }

    def year_of(election_id: str) -> int:
        if election_id in years:
            return years[election_id]
        return int(election_id.rsplit("-", 3)[-3])

    for election, source in PRIOR_ELECTION.items():
        assert year_of(source) < year_of(election), (
            f"{election} draws its prior share from {source}")


def test_the_holdout_does_not_supply_its_own_prior_share():
    assert PRIOR_ELECTION[HOLDOUT_NEWS_ELECTION] == "surrey-county-council-2021"


@needs_results
def test_tone_centres_come_only_from_fitting_parties(payload):
    # The centring parameter is estimated on the 45 fitting cells. A centre
    # keyed to anything else would mean the holdout helped define a feature
    # that is then scored on the holdout.
    for key in payload["tone_centres_from_fitting_cells"]:
        party, _window = key.split("/", 1)
        assert party in PARTIES


# ---- the arms are what they claim to be ------------------------------

def test_the_identity_arms_read_no_news_column(payload):
    news_free = ("placebo_party_dummies", "placebo_reform_dummy",
                 "placebo_prior_vote_share")
    for name in news_free:
        for column in ARMS[name]:
            assert column in DUMMY_COLUMNS + ["prior_party_vote_share"], (
                f"{name} reads {column}, which is not an identity column")


def test_there_is_one_indicator_per_fitted_party():
    assert DUMMY_COLUMNS == [f"party_is_{name}" for name in PARTIES]
    assert "reform_uk" in PARTIES and "ukip" in PARTIES, (
        "Reform and UKIP must stay separate; the supervisor's constraint "
        "is not negotiable and a merged indicator would silently break it")


@needs_results
def test_news_free_arms_do_not_vary_by_window(payload):
    # An identity feature has the same value in every window by
    # construction. If one of these arms moved across windows, it would be
    # reading something window-dependent - which is to say, news.
    for name in ("placebo_party_dummies", "placebo_reform_dummy",
                 "placebo_prior_vote_share"):
        deltas = {round(r["delta_vs_recalibrated"], 9)
                  for r in payload["arms"][name]}
        assert len(deltas) == 1, f"{name} varies by window: {deltas}"


# ---- the run is anchored to the committed result ---------------------

@needs_results
def test_the_frozen_arm_still_reproduces_its_committed_deltas(payload):
    assert payload["reproduction_check"]["max_absolute_difference"] == 0.0


@needs_results
def test_the_variance_split_is_the_stated_reason_for_the_run(payload):
    # The claim this module is built on is that tone separates parties more
    # than it separates elections. If that ever stopped being true the
    # module's premise would be gone and its findings text would be wrong.
    split = payload["variance_split"]["90_to_31_days/net_portrayal_share"]
    assert split["between_party_share"] > split["within_party_share"]
