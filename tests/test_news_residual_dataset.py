"""Tests for the Stage 1 join and the Approach A residual dataset.

Two kinds of failure are worth guarding against here, and they are not equally
obvious.

The loud one is a broken join: nothing matches, the row count is zero, someone
notices. The quiet one is a *wrong* join — an article attached to the wrong
contest because a name was normalised too aggressively, or a residual computed
against an in-sample fit instead of an out-of-fold prediction. That produces a
plausible number about the wrong thing, so most of what follows tests the
quiet failures.
"""

from __future__ import annotations

from datetime import date

import pytest

from news_modelling.residual_dataset import (
    build_residual_rows,
    diagnose_coverage,
    normalise_division,
    reform_rows_by_fold,
)

ELECTION_DATES = {
    "surrey-county-council-2017": date(2017, 5, 4),
    "surrey-county-council-2021": date(2021, 5, 6),
    "surrey-county-council-by-election-x-2019-01-31": date(2019, 1, 31),
}


def oof_row(division_id="d1", party="Conservative", *, reform=False, ukip=False,
            election="surrey-county-council-2021", predicted=20.0, observed=25.0,
            row_id=None):
    return {
        "candidate_contest_id": row_id or f"{division_id}-{party}",
        "election_id": election,
        "election_date": "6 May 2021",
        "division_id": division_id,
        "standard_party_name": party,
        "is_reform_uk": reform,
        "is_ukip": ukip,
        "split_role": "rolling_origin_fold",
        "predicted_vote_share": predicted,
        "observed_vote_share": observed,
    }


def news_row(division="Guildford East", election="SCC-2021-05", window="previous_30_days",
             articles=3):
    return {
        "election_id": election,
        "geographic_target_id": f"{election}:{division}",
        "window": window,
        "window_type": "cumulative",
        "cov_n_articles": articles,
    }


# ---------------------------------------------------------------------------
# Name normalisation: conservative on purpose
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("a, b", [
    ("Guildford East", "guildford east"),
    ("Ashtead Ward", "Ashtead"),
    ("Bagshot, Windlesham & Chobham", "Bagshot, Windlesham and Chobham"),
    ("Walton South  and  Oatlands", "Walton South and Oatlands"),
])
def test_names_that_should_match_do(a, b):
    assert normalise_division(a) == normalise_division(b)


@pytest.mark.parametrize("a, b", [
    ("Guildford East", "Guildford West"),
    ("Woking South", "Woking North"),
    ("Epsom West", "Epsom Town"),
])
def test_names_that_should_not_match_do_not(a, b):
    """A wrongly matched division attaches an article to the wrong contest."""

    assert normalise_division(a) != normalise_division(b)


# ---------------------------------------------------------------------------
# Coverage diagnosis
# ---------------------------------------------------------------------------


def test_shared_elections_are_matched_on_polling_date_not_on_name():
    """The two identifier systems share no string, only a date."""

    diagnosis = diagnose_coverage(
        [oof_row()], [news_row()], {"d1": "Guildford East"}, ELECTION_DATES,
    )
    assert diagnosis.shared_elections == ("surrey-county-council-2021",)


def test_an_election_with_a_baseline_but_no_news_is_reported():
    diagnosis = diagnose_coverage(
        [oof_row(election="surrey-county-council-by-election-x-2019-01-31")],
        [news_row()], {"d1": "Guildford East"}, ELECTION_DATES,
    )
    assert diagnosis.stage1_only_elections == (
        "surrey-county-council-by-election-x-2019-01-31",
    )
    assert diagnosis.division_level_rows == 0


def test_a_division_in_an_election_without_a_baseline_is_not_called_unmatched():
    """The 2026 holdout has news and no out-of-fold baseline.

    Counting its wards as unmatched would suggest a broken join where there is
    only a missing baseline, and that misreading is what this asserts against.
    """

    diagnosis = diagnose_coverage(
        [oof_row()],
        [news_row(), news_row(division="Ash", election="ESWS-2026-05")],
        {"d1": "Guildford East"}, ELECTION_DATES,
    )
    assert diagnosis.unmatched_news_divisions == ()
    assert diagnosis.divisions_in_elections_without_baseline == 1


def test_a_genuinely_unmatched_division_in_a_shared_election_is_reported():
    diagnosis = diagnose_coverage(
        [oof_row()],
        [news_row(), news_row(division="Nowhere Ward")],
        {"d1": "Guildford East"}, ELECTION_DATES,
    )
    assert diagnosis.unmatched_news_divisions == ("SCC-2021-05:nowhere",)


def test_zero_reform_rows_produces_an_explicit_verdict():
    """Zero is not a small sample, and the wording must not blur that."""

    diagnosis = diagnose_coverage(
        [oof_row()], [news_row()], {"d1": "Guildford East"}, ELECTION_DATES,
    )
    assert diagnosis.division_level_reform_rows == 0
    assert any("NO REFORM UK OBSERVATIONS" in v for v in diagnosis.verdicts())
    assert any("zero, not small" in v for v in diagnosis.verdicts())


def test_election_wide_collinearity_is_detected():
    """One feature value per election cannot be told apart from the election."""

    diagnosis = diagnose_coverage(
        [oof_row(), oof_row(division_id="d2", row_id="r2")],
        [{"election_id": "SCC-2021-05",
          "geographic_target_id": "SCC-2021-05:ELECTION_WIDE",
          "cov_n_articles": 5}],
        {"d1": "Guildford East", "d2": "Guildford West"}, ELECTION_DATES,
    )
    assert any("COLLINEAR WITH ELECTION IDENTITY" in v for v in diagnosis.verdicts())


# ---------------------------------------------------------------------------
# Residual construction
# ---------------------------------------------------------------------------


def test_residual_is_observed_minus_baseline():
    rows = build_residual_rows(
        [oof_row(predicted=20.0, observed=25.0)], [news_row()],
        {"d1": "Guildford East"}, ELECTION_DATES, feature_columns=["cov_n_articles"],
    )
    assert len(rows) == 1
    assert rows[0]["residual"] == pytest.approx(5.0)
    assert rows[0]["news__cov_n_articles"] == 3


def test_election_wide_news_never_enters_the_training_matrix():
    """It is constant within an election, so it would be an election indicator."""

    rows = build_residual_rows(
        [oof_row()],
        [{"election_id": "SCC-2021-05",
          "geographic_target_id": "SCC-2021-05:ELECTION_WIDE",
          "cov_n_articles": 9}],
        {"d1": "Guildford East"}, ELECTION_DATES, feature_columns=["cov_n_articles"],
    )
    assert rows == []


def test_a_row_with_no_baseline_prediction_is_dropped_not_imputed():
    """A residual against an unknown baseline is not a residual."""

    rows = build_residual_rows(
        [oof_row(predicted="")], [news_row()],
        {"d1": "Guildford East"}, ELECTION_DATES, feature_columns=["cov_n_articles"],
    )
    assert rows == []


def test_a_candidate_without_news_for_its_division_is_not_given_zero_news():
    """Absent coverage is not coverage of zero, so the row is simply absent."""

    rows = build_residual_rows(
        [oof_row(division_id="d1"), oof_row(division_id="d9", row_id="r9")],
        [news_row(division="Guildford East")],
        {"d1": "Guildford East", "d9": "Somewhere Else"},
        ELECTION_DATES, feature_columns=["cov_n_articles"],
    )
    assert [r["division_name"] for r in rows] == ["Guildford East"]


def test_window_filter_selects_one_window():
    rows = build_residual_rows(
        [oof_row()],
        [news_row(window="previous_30_days", articles=3),
         news_row(window="previous_7_days", articles=1)],
        {"d1": "Guildford East"}, ELECTION_DATES,
        feature_columns=["cov_n_articles"], window="previous_7_days",
    )
    assert rows[0]["news__cov_n_articles"] == 1


def test_reform_and_ukip_are_counted_separately_per_election():
    """Prompt 2 requires Reform observations reported per fold, never pooled with UKIP."""

    rows = build_residual_rows(
        [oof_row(party="Reform UK", reform=True, row_id="a"),
         oof_row(party="UKIP", ukip=True, row_id="b"),
         oof_row(row_id="c")],
        [news_row()], {"d1": "Guildford East"}, ELECTION_DATES,
        feature_columns=["cov_n_articles"],
    )
    counts = reform_rows_by_fold(rows)
    assert counts["surrey-county-council-2021"] == {
        "rows": 3, "reform_uk": 1, "ukip": 1,
    }
