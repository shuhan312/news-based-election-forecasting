"""Boundary tests for the three news-window schemes.

Prompt 2 asks for "automated tests confirming the correct allocation of
articles at all boundary dates", and boundaries are exactly where the three
schemes disagree with each other. Most of what follows is therefore the same
article checked under more than one scheme, so a change of scheme cannot
quietly move an article without a test noticing.

The other half is leakage. An article published after polls close must never
reach a pre-election feature, and an article dated polling day with no
recorded time must not be assumed to precede the close.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from news_modelling.window_schemes import (
    AFTER_POLLING_DATE,
    AFTER_POLLS_CLOSED,
    BEFORE_COLLECTION_WINDOW,
    DEFAULT_SCHEME,
    ELECTION_DAY_TIME_UNKNOWN,
    ORIGINAL_EMAIL,
    SCHEMES,
    UNKNOWN_DATE,
    assign,
    compare_schemes,
    days_before_polling,
    scheme_summary,
)

POLL = date(2021, 5, 6)


def on(days_before: int) -> date:
    return date.fromordinal(POLL.toordinal() - days_before)


# ---------------------------------------------------------------------------
# Every scheme is internally coherent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(SCHEMES))
def test_windows_do_not_overlap(key):
    """Prompt 2: the same article must not appear in two non-overlapping windows."""

    SCHEMES[key].validate()


@pytest.mark.parametrize("key", sorted(SCHEMES))
def test_every_day_inside_the_horizon_lands_somewhere(key):
    """A gap in a scheme would silently drop articles."""

    scheme = SCHEMES[key]
    first_day = 0 if scheme.includes_election_day else 1
    for days in range(first_day, scheme.max_days + 1):
        result = assign(on(days), POLL, scheme=key,
                        published_time=time(9, 0) if days == 0 else None)
        assert result.window is not None, f"{key} has no window for day {days}"


def test_the_default_scheme_is_the_one_already_implemented():
    """Adding this module must not change any existing figure."""

    assert DEFAULT_SCHEME == ORIGINAL_EMAIL.key
    assert ORIGINAL_EMAIL.windows[0] == ("final_72_hours", 1, 3)


# ---------------------------------------------------------------------------
# Where the schemes disagree
# ---------------------------------------------------------------------------


def test_day_three_lands_in_a_different_window_under_each_scheme():
    """The clearest single illustration of the disagreement."""

    compared = compare_schemes(on(3), POLL)
    assert compared["original_email_180d"]["window"] == "final_72_hours"
    assert compared["prompt_1_and_2_30d"]["window"] == "7_to_2_days"
    assert compared["desktop_spec_30d"]["window"] == "final_week"


def test_day_one_is_its_own_window_in_two_schemes_but_not_the_third():
    compared = compare_schemes(on(1), POLL)
    assert compared["original_email_180d"]["window"] == "final_72_hours"
    assert compared["prompt_1_and_2_30d"]["window"] == "final_day"
    assert compared["desktop_spec_30d"]["window"] == "previous_day"


def test_an_article_60_days_out_is_modelled_by_one_scheme_and_excluded_by_two():
    """Not a labelling difference - it changes what the model may see."""

    compared = compare_schemes(on(60), POLL)
    assert compared["original_email_180d"]["included_in_influence_features"]
    assert compared["original_email_180d"]["window"] == "90_to_31_days"
    for key in ("prompt_1_and_2_30d", "desktop_spec_30d"):
        assert not compared[key]["included_in_influence_features"]
        assert compared[key]["exclusion_reason"] == BEFORE_COLLECTION_WINDOW


def test_only_the_desktop_scheme_has_an_election_day_window():
    compared = compare_schemes(on(0), POLL, published_time=time(9, 0))
    assert compared["desktop_spec_30d"]["window"] == "election_day"
    assert compared["original_email_180d"]["window"] is None
    assert compared["prompt_1_and_2_30d"]["window"] is None


# ---------------------------------------------------------------------------
# Leakage
# ---------------------------------------------------------------------------


def test_an_article_published_after_polling_day_is_excluded():
    result = assign(date(2021, 5, 7), POLL)
    assert not result.included
    assert result.exclusion_reason == AFTER_POLLING_DATE


def test_an_election_day_article_after_polls_close_is_excluded():
    result = assign(POLL, POLL, scheme="desktop_spec_30d",
                    published_time=time(22, 30))
    assert not result.included
    assert result.exclusion_reason == AFTER_POLLS_CLOSED


def test_an_election_day_article_exactly_at_poll_close_is_excluded():
    """22:00 is when the polls shut, so 22:00 itself is not before them."""

    result = assign(POLL, POLL, scheme="desktop_spec_30d",
                    published_time=time(22, 0))
    assert result.exclusion_reason == AFTER_POLLS_CLOSED


def test_an_election_day_article_with_no_time_is_not_assumed_to_be_early():
    """The one assumption that would let results coverage into a forecast."""

    result = assign(POLL, POLL, scheme="desktop_spec_30d", published_time=None)
    assert not result.included
    assert result.exclusion_reason == ELECTION_DAY_TIME_UNKNOWN


def test_an_article_with_no_publication_date_is_excluded_with_a_reason():
    result = assign(None, POLL)
    assert not result.included
    assert result.exclusion_reason == UNKNOWN_DATE
    assert result.days_before is None


# ---------------------------------------------------------------------------
# Cumulative snapshots
# ---------------------------------------------------------------------------


def test_cumulative_snapshots_nest():
    """An article two days out is in every snapshot that reaches back that far."""

    result = assign(on(2), POLL)
    assert "previous_72_hours" in result.cumulative
    assert "previous_7_days" in result.cumulative
    assert "previous_180_days" in result.cumulative


def test_an_article_outside_a_snapshot_is_not_in_it():
    result = assign(on(40), POLL)
    assert "previous_30_days" not in result.cumulative
    assert "previous_90_days" in result.cumulative


def test_cumulative_membership_is_empty_for_an_excluded_article():
    assert assign(date(2021, 5, 8), POLL).cumulative == ()


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


def test_days_before_polling_counts_calendar_days():
    assert days_before_polling(date(2021, 5, 5), POLL) == 1
    assert days_before_polling(POLL, POLL) == 0
    assert days_before_polling(date(2021, 5, 7), POLL) == -1


def test_the_summary_names_its_source_for_each_scheme():
    """The report to the supervisor has to say where each scheme came from."""

    for row in scheme_summary():
        assert row["source"]
        assert row["windows"]
