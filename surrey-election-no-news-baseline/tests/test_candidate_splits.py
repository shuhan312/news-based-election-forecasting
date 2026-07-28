"""Tests for the candidate-level chronological split design.

The properties under test are the brief's own evaluation rules, expressed so
that a future change breaking one of them fails here rather than in a result
table nobody re-derives.
"""

from datetime import date

import pytest

from no_news_baseline.candidate_splits import (
    DEVELOPMENT_FOLD,
    NAMED_SPLITS,
    PRIMARY_HOLDOUT,
    PRIMARY_HOLDOUT_DATE,
    SECONDARY_HOLDOUT,
    TEST,
    TRAIN,
    UNUSED,
    CandidateSplit,
    all_splits,
    assert_contest_integrity,
    assert_holdout_untouched,
    assign_split,
    build_rolling_origin_splits,
    build_split_manifest,
    split_summary,
)


def _row(
    row_id: str,
    election_id: str,
    election_date: str,
    division_id: str = "d1",
    *,
    reform: bool = False,
    ukip: bool = False,
    eligible: bool = True,
) -> dict[str, object]:
    return {
        "candidate_contest_id": row_id,
        "election_id": election_id,
        "division_id": division_id,
        "election_date": election_date,
        "is_reform_uk": reform,
        "is_ukip": ukip,
        "candidate_baseline_eligibility": (
            "eligible_candidate_vote_share" if eligible else "excluded_x"
        ),
    }


def _release() -> list[dict[str, object]]:
    """A miniature release with the shape that matters: several polling days,
    two elections sharing 7 May 2026, and a July 2026 by-election."""

    return [
        _row("a1", "2013", "2 May 2013"),
        _row("a2", "2013", "2 May 2013", division_id="d2"),
        _row("b1", "2017", "4 May 2017"),
        _row("c1", "2021", "6 May 2021", reform=True),
        _row("d1", "by-2025-08", "21 August 2025"),
        _row("e1", "by-2025-10", "16 October 2025", reform=True),
        # Three separate elections, one polling day.
        _row("f1", "2026-east", "7 May 2026", reform=True),
        _row("f2", "2026-west", "7 May 2026"),
        _row("f3", "by-warlingham-2026", "7 May 2026"),
        _row("g1", "by-haslemere-2026", "7 July 2026", reform=True),
    ]


# --- split definitions ----------------------------------------------------


def test_a_split_cannot_train_on_its_own_test_period() -> None:
    with pytest.raises(ValueError, match="train on its own test period"):
        CandidateSplit(
            split_id="bad",
            role=DEVELOPMENT_FOLD,
            description="",
            train_end=date(2021, 5, 6),
            test_start=date(2021, 5, 6),
            test_end=date(2021, 5, 6),
            rationale="",
        )


def test_every_named_split_leaves_a_gap_between_train_and_test() -> None:
    """Construction already asserts this; the test pins it for all seven."""

    for split in NAMED_SPLITS:
        assert split.train_end < split.test_start


def test_the_briefs_four_development_folds_are_present() -> None:
    development = [s for s in NAMED_SPLITS if s.role == DEVELOPMENT_FOLD]
    assert [s.split_id for s in development] == [
        "dev_through_2016_test_2017",
        "dev_through_2020_test_2021",
        "dev_through_2023_test_2025_by_elections",
        "dev_through_first_2025_test_later_2025",
    ]


# --- the same-day holdout rule -------------------------------------------


def test_no_7_may_2026_event_can_reach_training_of_the_primary_holdout() -> None:
    """The brief's hardest split rule: three elections share 7 May 2026 and
    none may train on another."""

    split = next(s for s in NAMED_SPLITS if s.role == PRIMARY_HOLDOUT)
    assignment = assign_split(_release(), split)

    assert assignment["f1"] == TEST
    assert assignment["f2"] == TEST
    assert assignment["f3"] == TEST
    # And the July by-election is not smuggled in either.
    assert assignment["g1"] == UNUSED
    assert split.train_end < PRIMARY_HOLDOUT_DATE


def test_the_two_secondary_holdouts_differ_only_in_their_train_boundary() -> None:
    before, after = [s for s in NAMED_SPLITS if s.role == SECONDARY_HOLDOUT]
    release = _release()

    assert assign_split(release, before)["f1"] == UNUSED  # 7 May results withheld
    assert assign_split(release, after)["f1"] == TRAIN     # deliberately retrained
    assert assign_split(release, before)["g1"] == TEST
    assert assign_split(release, after)["g1"] == TEST


def test_later_2025_fold_splits_the_two_by_election_dates() -> None:
    split = next(
        s for s in NAMED_SPLITS if s.split_id == "dev_through_first_2025_test_later_2025"
    )
    assignment = assign_split(_release(), split)

    assert assignment["d1"] == TRAIN  # 21 August 2025
    assert assignment["e1"] == TEST   # 16 October 2025


# --- rolling origin -------------------------------------------------------


def test_rolling_origin_skips_the_first_polling_day_and_stops_at_the_holdout() -> None:
    splits = build_rolling_origin_splits(_release())
    tested_days = [s.test_start.isoformat() for s in splits]

    # 2013 has nothing earlier, so it is not evaluable; it remains training
    # data for every later fold.
    assert "2013-05-02" not in tested_days
    assert tested_days == ["2017-05-04", "2021-05-06", "2025-08-21", "2025-10-16"]
    # The untouched holdout is never consumed by routine development.
    assert all(s.test_start < PRIMARY_HOLDOUT_DATE for s in splits)


def test_rolling_origin_trains_on_everything_strictly_earlier() -> None:
    splits = build_rolling_origin_splits(_release())
    fold_2021 = next(s for s in splits if s.test_start == date(2021, 5, 6))
    assignment = assign_split(_release(), fold_2021)

    assert assignment["a1"] == TRAIN
    assert assignment["b1"] == TRAIN
    assert assignment["c1"] == TEST
    assert assignment["d1"] == UNUSED


# --- manifest and integrity ----------------------------------------------


def test_manifest_covers_every_cohort_row_in_every_split() -> None:
    release = _release()
    splits = all_splits(release)
    manifest = build_split_manifest(release, splits)

    assert len(manifest) == len(release) * len(splits)
    assert {row["fold"] for row in manifest} <= {TRAIN, TEST, UNUSED}


def test_manifest_omits_rows_outside_the_cohort() -> None:
    release = _release() + [_row("x1", "2017", "4 May 2017", eligible=False)]
    manifest = build_split_manifest(release, NAMED_SPLITS)

    assert not [row for row in manifest if row["candidate_contest_id"] == "x1"]


def test_a_contest_never_straddles_two_folds() -> None:
    """The brief: all candidates from one contest stay in the same split."""

    release = [
        _row("p1", "2021", "6 May 2021", division_id="shared"),
        _row("p2", "2021", "6 May 2021", division_id="shared"),
        _row("p3", "2021", "6 May 2021", division_id="shared"),
    ]
    manifest = build_split_manifest(release, NAMED_SPLITS)
    assert_contest_integrity(manifest)

    fold_2021 = {
        row["candidate_contest_id"]: row["fold"]
        for row in manifest
        if row["split_id"] == "dev_through_2020_test_2021"
    }
    assert set(fold_2021.values()) == {TEST}


def test_contest_integrity_check_catches_a_deliberately_broken_manifest() -> None:
    broken = [
        {"split_id": "s", "contest_id": "e|d", "fold": TRAIN,
         "split_role": DEVELOPMENT_FOLD, "election_date": "6 May 2021"},
        {"split_id": "s", "contest_id": "e|d", "fold": TEST,
         "split_role": DEVELOPMENT_FOLD, "election_date": "6 May 2021"},
    ]
    with pytest.raises(ValueError, match="split across folds"):
        assert_contest_integrity(broken)


def test_no_development_fold_trains_on_the_primary_holdout() -> None:
    release = _release()
    manifest = build_split_manifest(release, all_splits(release))
    assert_holdout_untouched(manifest)


def test_holdout_guard_catches_a_development_fold_that_reaches_2026() -> None:
    leaky = [
        {"split_id": "s", "split_role": DEVELOPMENT_FOLD, "contest_id": "e|d",
         "fold": TRAIN, "election_date": "7 May 2026"},
    ]
    with pytest.raises(ValueError, match="at or after the primary holdout"):
        assert_holdout_untouched(leaky)


# --- summary --------------------------------------------------------------


def test_summary_reports_reform_rows_and_flags_unestimable_folds() -> None:
    release = _release()
    summaries = {row["split_id"]: row for row in split_summary(release, NAMED_SPLITS)}

    # Train through 2016: no Reform observation exists yet anywhere.
    fold_2017 = summaries["dev_through_2016_test_2017"]
    assert fold_2017["train_reform_uk_rows"] == 0
    assert fold_2017["reform_estimable"] is False

    # Train through 2020: still none, because Reform first appears in 2021.
    assert summaries["dev_through_2020_test_2021"]["train_reform_uk_rows"] == 0

    # The primary holdout trains on everything up to 6 May 2026.
    primary = summaries["primary_holdout_7_may_2026"]
    assert primary["train_reform_uk_rows"] == 2
    assert primary["reform_estimable"] is True
    assert primary["test_rows"] == 3
    assert primary["test_elections"] == 3
