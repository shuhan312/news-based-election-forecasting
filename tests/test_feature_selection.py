"""Tests for the feature selection layer.

The tests that matter most here are the ones about leakage and about block
budgets. Everything else is arithmetic that would show up quickly in use; those
two would not - a selection contaminated by holdout outcomes still produces a
plausible column list, and a budget rule that starves the local arm still
produces a model that fits. Both fail silently and both change the answer to
the research question, so both are asserted directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from news_modelling.feature_selection import (
    MIN_TRAINING_OBSERVATIONS,
    SPECIFICATION_BLOCKS,
    TRAINING_SPLIT,
    ColumnVerdict,
    Selection,
    SelectionError,
    allocate_budgets,
    block_of,
    candidate_columns,
    rank_by_association,
    select_features,
    select_for_specification,
    selection_report,
    split_coverage,
    structural_screen,
)


def _frame(rows: int = 200, *, seed: int = 0) -> pd.DataFrame:
    """A small table with the same shape as the real one.

    Deliberately built so each structural rule has something to catch: one
    empty column, one constant, one sparse, one exact copy, and two genuinely
    informative columns of differing strength.
    """

    rng = np.random.default_rng(seed)
    signal = rng.normal(size=rows)

    frame = pd.DataFrame({
        "row_key": [f"r{index}" for index in range(rows)],
        "modelling_split": [TRAINING_SPLIT] * (rows // 2)
                           + ["validation_2021"] * (rows - rows // 2),
        "target__party_vote_share": signal * 2 + rng.normal(scale=0.3, size=rows),

        "national__window__strong": signal + rng.normal(scale=0.2, size=rows),
        "national__window__weak": rng.normal(size=rows),
        "national__window__empty": [np.nan] * rows,
        "national__window__constant": [7.0] * rows,
        "local__window__strong": signal + rng.normal(scale=0.5, size=rows),
        "coverage__window__searched": rng.integers(0, 5, size=rows),
    })

    # An exact copy, so the duplicate rule has a target.
    frame["national__window__strong_copy"] = frame["national__window__strong"]

    # Sparse: values on fewer rows than the floor allows.
    sparse = pd.Series([np.nan] * rows)
    sparse.iloc[: MIN_TRAINING_OBSERVATIONS - 5] = rng.normal(
        size=MIN_TRAINING_OBSERVATIONS - 5)
    frame["national__window__sparse"] = sparse

    return frame


IDENTIFIERS = ("row_key", "modelling_split")


# --------------------------------------------------------------------------
# Leakage: the property the whole two-tier split exists to guarantee.
# --------------------------------------------------------------------------

def test_ranking_refuses_rows_outside_the_training_split():
    """Ranking on holdout rows puts their outcomes into the feature set."""

    frame = _frame()
    with pytest.raises(SelectionError, match="outside the training split"):
        rank_by_association(
            frame, ["national__window__strong"], "target__party_vote_share")


def test_ranking_accepts_training_rows():
    frame = _frame()
    training = frame[frame["modelling_split"] == TRAINING_SPLIT]
    scores = rank_by_association(
        training, ["national__window__strong", "national__window__weak"],
        "target__party_vote_share")
    assert scores["national__window__strong"] > scores["national__window__weak"]


def test_selection_ignores_validation_rows_entirely():
    """Corrupting validation outcomes must not change the selected columns.

    The sharpest available test of the leakage rule: if any part of selection
    read the holdout, replacing its target with noise would move the result.
    """

    frame = _frame()
    baseline = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)

    corrupted = frame.copy()
    holdout = corrupted["modelling_split"] != TRAINING_SPLIT
    rng = np.random.default_rng(99)
    corrupted.loc[holdout, "target__party_vote_share"] = rng.normal(
        scale=500, size=int(holdout.sum()))
    corrupted.loc[holdout, "national__window__weak"] = rng.normal(
        scale=500, size=int(holdout.sum()))

    after = select_features(
        corrupted, "target__party_vote_share", identifiers=IDENTIFIERS)
    assert after.selected == baseline.selected


def test_target_columns_are_never_candidates():
    frame = _frame()
    candidates = candidate_columns(frame, IDENTIFIERS)
    assert not [c for c in candidates if c.startswith("target__")]


def test_identifier_columns_are_never_candidates():
    frame = _frame()
    assert "row_key" not in candidate_columns(frame, IDENTIFIERS)


def test_selection_fails_loudly_without_training_rows():
    frame = _frame()
    frame["modelling_split"] = "final_test_2026"
    with pytest.raises(SelectionError, match="nothing"):
        select_features(frame, "target__party_vote_share",
                        identifiers=IDENTIFIERS)


# --------------------------------------------------------------------------
# Structural screening: shape only, no outcome read.
# --------------------------------------------------------------------------

def test_structural_screen_removes_each_defect_with_its_own_reason():
    frame = _frame()
    training = frame[frame["modelling_split"] == TRAINING_SPLIT]
    kept, verdicts = structural_screen(
        training, candidate_columns(frame, IDENTIFIERS))

    reasons = {verdict.column: verdict.stage
               for verdict in verdicts if not verdict.kept}
    assert reasons["national__window__empty"] == "all_empty"
    assert reasons["national__window__constant"] == "constant"
    assert reasons["national__window__sparse"] == "too_sparse"
    assert reasons["national__window__strong_copy"] == "duplicate"
    assert "national__window__strong" in kept


def test_duplicate_survivor_is_the_alphabetically_first_name():
    """Determinism: the same input must select the same column every run."""

    frame = _frame()
    training = frame[frame["modelling_split"] == TRAINING_SPLIT]
    columns = candidate_columns(frame, IDENTIFIERS)

    kept_forward, _ = structural_screen(training, columns)
    kept_reversed, _ = structural_screen(training, list(reversed(columns)))
    assert sorted(kept_forward) == sorted(kept_reversed)
    assert "national__window__strong" in kept_forward


def test_duplicate_verdict_names_the_column_it_duplicates():
    frame = _frame()
    training = frame[frame["modelling_split"] == TRAINING_SPLIT]
    _, verdicts = structural_screen(
        training, candidate_columns(frame, IDENTIFIERS))
    duplicate = next(v for v in verdicts if v.stage == "duplicate")
    assert duplicate.duplicate_of == "national__window__strong"


def test_near_constant_column_is_removed():
    # One thousand rows so the training half is large enough for a single
    # differing value to sit below the 99.5% threshold rather than at it.
    frame = _frame(rows=1000)
    values = np.zeros(len(frame))
    values[0] = 1.0
    frame["national__window__flat"] = values
    training = frame[frame["modelling_split"] == TRAINING_SPLIT]
    _, verdicts = structural_screen(training, ["national__window__flat"])
    assert verdicts[0].stage == "near_constant"


def test_text_columns_drop_out_as_empty():
    """Non-numeric columns coerce to missing and leave by the all-empty rule."""

    frame = _frame()
    frame["national__window__label"] = ["some text"] * len(frame)
    training = frame[frame["modelling_split"] == TRAINING_SPLIT]
    _, verdicts = structural_screen(training, ["national__window__label"])
    assert verdicts[0].stage == "all_empty"


def test_sparsity_is_judged_on_training_rows_only():
    """A column populated only outside training cannot be learned from."""

    frame = _frame()
    holdout = frame["modelling_split"] != TRAINING_SPLIT
    values = pd.Series([np.nan] * len(frame))
    values[holdout.to_numpy()] = 1.0
    frame["national__window__holdout_only"] = values

    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    assert "national__window__holdout_only" not in selection.selected


# --------------------------------------------------------------------------
# Budgets: the rule that keeps the local arm answerable.
# --------------------------------------------------------------------------

def test_small_blocks_are_kept_whole():
    budgets = allocate_budgets({"local": 6, "national": 584}, 341)
    assert budgets["local"] == 6
    assert budgets["national"] == 335


def test_budget_is_never_exceeded():
    budgets = allocate_budgets({"a": 500, "b": 500, "c": 500}, 300)
    assert sum(budgets.values()) <= 300


def test_no_block_is_awarded_more_than_it_has():
    budgets = allocate_budgets({"a": 3, "b": 4}, 1000)
    assert budgets == {"a": 3, "b": 4}


def test_every_block_is_represented_when_slots_are_scarce():
    """With fewer slots than blocks, the smallest blocks still get one.

    Otherwise the arm that only just survived screening disappears, and its
    absence from the model would be read as evidence about the news.
    """

    budgets = allocate_budgets({"local": 2, "national": 400, "combined": 300}, 2)
    assert budgets["local"] == 1
    assert sum(budgets.values()) <= 2


def test_zero_budget_awards_nothing():
    assert allocate_budgets({"a": 10, "b": 10}, 0) == {"a": 0, "b": 0}


def test_equal_blocks_split_evenly():
    budgets = allocate_budgets({"a": 100, "b": 100}, 50)
    assert budgets == {"a": 25, "b": 25}


# --------------------------------------------------------------------------
# Redundancy and ranking.
# --------------------------------------------------------------------------

def test_redundant_column_is_dropped_and_the_stronger_one_kept():
    frame = _frame()
    frame["national__window__strong_shifted"] = (
        frame["national__window__strong"] * 3 + 1)

    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    kept = set(selection.selected)
    assert not {"national__window__strong",
                "national__window__strong_shifted"} <= kept


def test_verdicts_cover_every_candidate_exactly_once():
    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    seen = [verdict.column for verdict in selection.verdicts]
    assert len(seen) == len(set(seen)) == selection.candidate_columns


def test_selected_columns_carry_their_association():
    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    for verdict in selection.verdicts:
        if verdict.kept:
            assert verdict.association is not None


def test_selection_is_reproducible():
    frame = _frame()
    first = select_features(frame, "target__party_vote_share",
                            identifiers=IDENTIFIERS)
    second = select_features(frame, "target__party_vote_share",
                             identifiers=IDENTIFIERS)
    assert first.selected == second.selected


def test_missing_target_is_reported():
    frame = _frame()
    with pytest.raises(SelectionError, match="not in the frame"):
        rank_by_association(
            frame[frame["modelling_split"] == TRAINING_SPLIT],
            ["national__window__strong"], "target__does_not_exist")


# --------------------------------------------------------------------------
# Specifications: blocks that overlap must not be selected together.
# --------------------------------------------------------------------------

def test_specification_restricts_selection_to_its_own_blocks():
    frame = _frame()
    selection = select_for_specification(
        frame, "target__party_vote_share", "national",
        identifiers=IDENTIFIERS)
    assert all(block_of(column) in SPECIFICATION_BLOCKS["national"]
               for column in selection.selected)
    assert not [c for c in selection.selected if block_of(c) == "local"]


def test_baseline_specification_admits_no_news():
    frame = _frame()
    selection = select_for_specification(
        frame, "target__party_vote_share", "baseline",
        identifiers=IDENTIFIERS)
    assert all(block_of(column) in {"baseline", "coverage"}
               for column in selection.selected)


def test_combined_and_national_blocks_never_cooccur():
    """The combined block already contains the national coverage."""

    assert not (SPECIFICATION_BLOCKS["combined"] & {"national"})


def test_unknown_specification_is_rejected():
    frame = _frame()
    with pytest.raises(SelectionError, match="unknown specification"):
        select_for_specification(
            frame, "target__party_vote_share", "invented",
            identifiers=IDENTIFIERS)


# --------------------------------------------------------------------------
# Split coverage: the precondition for the comparison the brief asks for.
# --------------------------------------------------------------------------

def test_split_without_news_is_flagged_as_incomparable():
    frame = _frame()
    holdout = frame["modelling_split"] != TRAINING_SPLIT
    # Every news column, not a hand-listed few: a column left populated would
    # make the split look comparable and the test would pass for the wrong
    # reason. This mirrors the real 2021 split, where no news column is
    # populated at all.
    for column in candidate_columns(frame, IDENTIFIERS):
        if block_of(column) not in {"baseline", "coverage"}:
            frame.loc[holdout, column] = 0.0

    coverage = split_coverage(frame, identifiers=IDENTIFIERS)
    assert coverage["validation_2021"]["news_comparison_possible"] is False
    assert coverage[TRAINING_SPLIT]["news_comparison_possible"] is True


def test_split_coverage_counts_rows_not_columns():
    frame = _frame()
    coverage = split_coverage(frame, identifiers=IDENTIFIERS)
    assert coverage[TRAINING_SPLIT]["rows"] == 100


def test_split_coverage_needs_news_columns_to_exist():
    frame = _frame()[["row_key", "modelling_split", "target__party_vote_share"]]
    with pytest.raises(SelectionError, match="no news columns"):
        split_coverage(frame, identifiers=IDENTIFIERS)


# --------------------------------------------------------------------------
# Applying a fitted selection.
# --------------------------------------------------------------------------

def test_apply_returns_only_selected_columns():
    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    applied = selection.apply(frame)
    assert list(applied.columns) == selection.selected


def test_apply_reports_columns_the_frame_is_missing():
    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    with pytest.raises(SelectionError, match="absent from the frame"):
        selection.apply(frame.drop(columns=selection.selected[:1]))


def test_apply_works_on_holdout_rows():
    """Fitted on training, applied anywhere - that is the point of fit/apply."""

    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    holdout = frame[frame["modelling_split"] != TRAINING_SPLIT]
    assert len(selection.apply(holdout)) == len(holdout)


def test_report_records_the_rows_per_feature_ratio():
    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    report = selection_report(selection)
    assert report["rows_per_selected_feature"] >= 10
    assert report["selection_used_training_rows_only"] is True


def test_report_accounts_for_every_candidate():
    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    report = selection_report(selection)
    removed = sum(report["removed_by_stage"].values())
    assert removed + report["selected_columns"] == report["candidate_columns"]


def test_block_grouping_matches_the_selected_list():
    frame = _frame()
    selection = select_features(
        frame, "target__party_vote_share", identifiers=IDENTIFIERS)
    grouped = sum(len(columns) for columns in selection.by_block().values())
    assert grouped == len(selection.selected)


def test_block_of_handles_a_column_with_no_divider():
    assert block_of("plain") == "plain"


def test_dropped_returns_only_rejections():
    verdicts = [
        ColumnVerdict("a", "x", True, "selected", "kept"),
        ColumnVerdict("b", "x", False, "constant", "dropped"),
    ]
    selection = Selection("target__party_vote_share", ["a"], verdicts)
    assert [verdict.column for verdict in selection.dropped()] == ["b"]
