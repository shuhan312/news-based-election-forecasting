"""Reduce the feature table to a set a model can actually be fitted on.

The master table is 12,091 columns wide and 6,323 rows long. Columns outnumber
rows by roughly two to one, and the training split is 3,418 rows. Fitting
anything on that directly does not produce a weak model; it produces a model
that reproduces the training rows exactly and carries no information about any
election it has not seen. Selection is therefore not tuning, it is the step
that makes fitting meaningful at all.

The two tiers, and why the split matters
----------------------------------------
Selection is separated into two tiers by one criterion: whether the rule looks
at the outcome.

Tier one is structural. It asks only about the shape of a column - is it empty,
is it constant, is it a copy of another column. These questions can be answered
without ever reading a vote share, so their answers cannot carry information
about the outcome, and a column dropped for being empty is dropped for a reason
that would hold whatever the results turned out to be.

Tier two ranks columns by how strongly they move with the outcome. That is a
statement about the target, and computing it on rows the model will later be
tested on puts those rows' results into the feature set. The features would
then have been chosen partly because of the answers they are meant to predict,
and the holdout score would be optimistic by an amount nobody can measure after
the fact. So tier two reads training rows only, and the code enforces this
rather than trusting the caller: ``rank_by_association`` raises if it is handed
any row outside the training split.

Both tiers count on training rows. A column with five hundred values that all
sit in the 2026 holdout cannot be estimated from training data, so it is not a
usable predictor however well populated it looks overall.

Why each block gets its own budget
----------------------------------
The research question asks whether local Surrey news and UK national news have
different predictive value. That question cannot be answered if the two compete
for the same slots, because they do not arrive in comparable numbers: after
structural screening the national blocks hold 584 surviving columns and the
local blocks hold six. Rank them together and national takes every slot, local
is absent from the model by construction, and the finding "local news does not
help" would be a description of the selection rule rather than of the news.

So each block is allocated its own budget and selection happens within it. The
allocation is water-filling: a block that has fewer candidates than its fair
share takes what it has and releases the remainder to the blocks that can use
it. Small blocks are kept whole, large blocks compete for what is left over,
and no block is squeezed out by another's abundance.

What this module does not do
----------------------------
It does not fit a model, and it does not choose a target. It produces a column
list and a written reason for every column not on it.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Only training rows may inform selection. Named here so the guard and the
# documentation cannot drift apart.
TRAINING_SPLIT = "historical_training"

# Columns describing the outcome. Selection must never consider one as a
# predictor, and the prefix is the only marker - matching the rule the master
# table already uses so there is no second list to keep in step.
TARGET_PREFIX = "target__"

# A column needs enough training observations for any association estimated
# from it to mean something. Twenty is a working floor, not a theoretical one:
# below it a single unusual contest moves the correlation more than the signal
# does.
MIN_TRAINING_OBSERVATIONS = 20

# Rows per selected feature. Ten is the conventional floor for regression with
# regularisation; going below it is where coefficients start to be determined
# by which rows happened to land in the training split.
ROWS_PER_FEATURE = 10

# Two columns correlating above this are treated as the same measurement twice.
# Recency-weighted counts and their unweighted originals routinely sit here.
REDUNDANCY_THRESHOLD = 0.95

# A column whose commonest value covers this much of its training rows carries
# almost no contrast, even though it is not formally constant.
NEAR_CONSTANT_SHARE = 0.995

# Which blocks belong to which specification.
#
# This mapping exists because the blocks overlap in content: the combined block
# already contains the national coverage, so a model given both would be shown
# the same articles twice and its national coefficient would be split across
# two columns that are not independent. Selecting once across every block and
# fitting the result would silently do exactly that.
#
# Each specification therefore selects within its own blocks only, and the
# nine-way comparison the brief asks for is a comparison between separately
# selected feature sets rather than between subsets of one.
#
# The baseline and coverage blocks appear in every specification: the Stage 1
# prediction is the quantity the news is being asked to improve on, and the
# coverage block records how thoroughly each contest was searched, which is a
# property of the collection rather than of either news arm.
SPECIFICATION_BLOCKS: dict[str, frozenset[str]] = {
    "baseline": frozenset({"baseline", "coverage"}),
    "local": frozenset({
        "baseline", "coverage",
        "local", "local_context", "weighted_local", "weighted_local_context"}),
    "national": frozenset({
        "baseline", "coverage",
        "national", "national_context",
        "weighted_national", "weighted_national_context"}),
    "combined": frozenset({"baseline", "coverage", "combined"}),
    "full": frozenset({
        "baseline", "coverage",
        "local", "local_context", "weighted_local", "weighted_local_context",
        "national", "national_context",
        "weighted_national", "weighted_national_context"}),
}


class SelectionError(RuntimeError):
    """Raised when a selection rule is asked to do something unsound."""


@dataclass(frozen=True)
class ColumnVerdict:
    """Why one column was kept or dropped, and at which stage."""

    column: str
    block: str
    kept: bool
    stage: str
    reason: str
    training_observations: int = 0
    association: float | None = None
    duplicate_of: str | None = None


@dataclass
class Selection:
    """A fitted selection: the surviving columns plus the full reasoning."""

    target: str
    selected: list[str]
    verdicts: list[ColumnVerdict]
    budgets: dict[str, int] = field(default_factory=dict)
    training_rows: int = 0
    candidate_columns: int = 0

    def apply(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Return the selected columns from any frame with the same schema.

        Fitted on training rows and applied anywhere. Applying to validation or
        holdout rows is safe precisely because the column list was decided
        before those rows were read.
        """

        missing = [column for column in self.selected if column not in frame]
        if missing:
            raise SelectionError(
                f"{len(missing)} selected columns absent from the frame: "
                f"{missing[:5]}")
        return frame[self.selected]

    def by_block(self) -> dict[str, list[str]]:
        """Selected columns grouped by block, for reporting per news arm."""

        grouped: dict[str, list[str]] = defaultdict(list)
        for column in self.selected:
            grouped[block_of(column)].append(column)
        return dict(grouped)

    def dropped(self) -> list[ColumnVerdict]:
        return [verdict for verdict in self.verdicts if not verdict.kept]

    def stage_counts(self) -> dict[str, int]:
        """How many columns each stage removed, in the order stages ran."""

        counts: Counter[str] = Counter()
        for verdict in self.verdicts:
            if not verdict.kept:
                counts[verdict.stage] += 1
        return dict(counts)


def block_of(column: str) -> str:
    """The block a column belongs to - the segment before the first divider.

    Blocks are how local and national news are kept separately answerable, so
    the definition lives in one place.
    """

    return column.split("__", 1)[0] if "__" in column else column


def candidate_columns(frame: pd.DataFrame,
                      identifiers: Iterable[str] = (),
                      blocks: Iterable[str] | None = None) -> list[str]:
    """Every column eligible to be a predictor.

    A column qualifies if it is not an identifier and not a target. Stated as
    an exclusion rather than an inclusion list because a new feature block
    should arrive in the candidate set automatically, whereas a new target must
    be named deliberately.

    ``blocks`` narrows the candidates to one specification's blocks; leaving it
    unset considers every block, which is right for auditing the table and
    wrong for fitting a model on it.
    """

    excluded = set(identifiers)
    permitted = None if blocks is None else set(blocks)
    return sorted(
        column for column in frame.columns
        if column not in excluded
        and not column.startswith(TARGET_PREFIX)
        and "__" in column
        and (permitted is None or block_of(column) in permitted))


def _spearman(left: pd.Series, right: pd.Series) -> float:
    """Rank correlation over the rows where both series have a value.

    Returns zero rather than a missing value when the overlap is too small or
    when either side is constant across it. Both cases mean the same thing for
    selection - this column offers nothing to rank on - and collapsing them to
    zero keeps the ranking total, so no column is dropped merely for producing
    an undefined statistic.
    """

    usable = left.notna() & right.notna()
    if usable.sum() < MIN_TRAINING_OBSERVATIONS:
        return 0.0

    a, b = left[usable], right[usable]
    if a.nunique() <= 1 or b.nunique() <= 1:
        return 0.0

    correlation = a.corr(b, method="spearman")
    return 0.0 if pd.isna(correlation) else float(correlation)


def _numeric(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Coerce to numeric, turning unparseable entries into missing values.

    Text-valued columns become entirely missing and are removed by the
    all-empty rule, which is the intended outcome: this layer selects numeric
    predictors and a categorical column needs encoding before it is one.
    """

    return frame[list(columns)].apply(pd.to_numeric, errors="coerce")


def structural_screen(
        frame: pd.DataFrame,
        columns: Sequence[str],
        *,
        min_observations: int = MIN_TRAINING_OBSERVATIONS,
        near_constant_share: float = NEAR_CONSTANT_SHARE,
) -> tuple[list[str], list[ColumnVerdict]]:
    """Tier one: drop columns on shape alone, reading no outcome.

    Runs in increasing order of cost. The cheap counting rules remove the great
    majority of columns, so the duplicate check - which has to compare columns
    against each other - runs on a few hundred rather than twelve thousand.

    ``frame`` must already be restricted to training rows; the caller does that
    so the restriction is visible at the call site rather than hidden here.
    """

    numeric = _numeric(frame, columns)
    verdicts: list[ColumnVerdict] = []
    surviving: list[str] = []

    observations = numeric.notna().sum()
    distinct = numeric.nunique(dropna=True)

    for column in columns:
        count = int(observations[column])
        block = block_of(column)

        if count == 0:
            verdicts.append(ColumnVerdict(
                column, block, False, "all_empty",
                "no value on any training row", count))
            continue

        if int(distinct[column]) <= 1:
            verdicts.append(ColumnVerdict(
                column, block, False, "constant",
                "one distinct value, so no contrast to learn from", count))
            continue

        if count < min_observations:
            verdicts.append(ColumnVerdict(
                column, block, False, "too_sparse",
                f"{count} training observations, below the floor of "
                f"{min_observations}", count))
            continue

        values = numeric[column].dropna()
        dominant = values.value_counts().iloc[0] / len(values)
        if dominant >= near_constant_share:
            verdicts.append(ColumnVerdict(
                column, block, False, "near_constant",
                f"one value covers {dominant:.1%} of training rows", count))
            continue

        surviving.append(column)

    kept, duplicate_verdicts = _drop_exact_duplicates(numeric, surviving)
    verdicts.extend(duplicate_verdicts)
    return kept, verdicts


def _drop_exact_duplicates(
        numeric: pd.DataFrame,
        columns: Sequence[str]) -> tuple[list[str], list[ColumnVerdict]]:
    """Remove columns holding identical values to one already kept.

    Compared by hashing each column's values rather than by pairwise
    comparison: hashing is linear in the number of columns where comparison is
    quadratic, and exact duplicates are what the wide blocks actually contain -
    the same count reached by two naming routes. Near-duplicates are a
    different problem and are handled after ranking, where the stronger of the
    pair is known.

    The survivor of a duplicate group is the alphabetically first name, so the
    result does not depend on column order.
    """

    seen: dict[str, str] = {}
    kept: list[str] = []
    verdicts: list[ColumnVerdict] = []

    for column in sorted(columns):
        values = numeric[column].to_numpy(dtype="float64", copy=False)
        digest = hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()

        if digest in seen:
            verdicts.append(ColumnVerdict(
                column, block_of(column), False, "duplicate",
                f"identical training values to {seen[digest]}",
                int(np.isfinite(values).sum()), duplicate_of=seen[digest]))
            continue

        seen[digest] = column
        kept.append(column)

    return kept, verdicts


def rank_by_association(
        frame: pd.DataFrame,
        columns: Sequence[str],
        target: str,
        *,
        split_column: str = "modelling_split",
) -> dict[str, float]:
    """Tier two: rank columns by how strongly they move with the outcome.

    Uses Spearman rank correlation rather than Pearson. News features are
    counts with long right tails - most contests have none, a few have many -
    and Pearson on that shape is driven by the few large values. Rank
    correlation asks whether contests with more coverage tend to sit higher on
    the outcome, which is the question worth asking and is unaffected by how
    extreme the largest count happens to be.

    The split guard is the leakage control for this module. Ranking is the only
    place selection reads the target, so it is the only place a holdout row
    could contaminate the feature set, and the check is an assertion rather
    than a comment.
    """

    if split_column in frame.columns:
        splits = set(frame[split_column].dropna().unique())
        if splits - {TRAINING_SPLIT}:
            raise SelectionError(
                "association ranking was handed rows outside the training "
                f"split: {sorted(splits - {TRAINING_SPLIT})}. Selecting on "
                "them would put their outcomes into the feature set.")

    if target not in frame.columns:
        raise SelectionError(f"target column {target!r} is not in the frame")

    outcome = pd.to_numeric(frame[target], errors="coerce")
    numeric = _numeric(frame, columns)

    # Absolute value: a feature that moves against the outcome is as useful as
    # one that moves with it, and the sign belongs to the fitted model rather
    # than to the decision about whether to offer the column at all.
    return {column: abs(_spearman(numeric[column], outcome))
            for column in columns}


def allocate_budgets(candidates_per_block: Mapping[str, int],
                     total: int) -> dict[str, int]:
    """Divide a feature budget across blocks, keeping small blocks whole.

    Water-filling. Each round the blocks still unsettled would get an equal
    share of what is left; any block wanting less than its share is settled at
    what it wants and its unused portion returns to the pool. Repeat until
    every remaining block wants at least its share, then give them that.

    The effect is that a block with six candidates keeps all six instead of
    being handed two hundred slots it cannot fill, and the blocks with hundreds
    of candidates split the surplus. An equal division would waste most of the
    budget; a proportional one would hand almost all of it to the largest block
    and leave the local arm unrepresented.
    """

    if total <= 0:
        return {block: 0 for block in candidates_per_block}

    settled: dict[str, int] = {}
    pending = dict(candidates_per_block)
    remaining = total

    while pending:
        share = remaining // len(pending)
        if share == 0:
            # Fewer slots than blocks. Award one each, smallest blocks first,
            # so the arms that only just survive screening are still present.
            for block in sorted(pending, key=lambda b: (pending[b], b)):
                settled[block] = 1 if remaining > 0 else 0
                remaining -= settled[block]
            break

        undersized = {block: want for block, want in pending.items()
                      if want <= share}
        if not undersized:
            for block in pending:
                settled[block] = share
            break

        for block, want in undersized.items():
            settled[block] = want
            remaining -= want
            del pending[block]

    return {block: settled.get(block, 0) for block in candidates_per_block}


def _prune_redundant(numeric: pd.DataFrame,
                     ranked: Sequence[str],
                     budget: int,
                     threshold: float) -> tuple[list[str], list[ColumnVerdict]]:
    """Walk a ranked list, keeping columns that add something new.

    A column is skipped when it correlates above the threshold with one already
    kept. Because the walk runs strongest-first, the survivor of any redundant
    pair is the one more strongly associated with the outcome, and the column
    dropped is the weaker restatement of a signal already in the set.
    """

    kept: list[str] = []
    verdicts: list[ColumnVerdict] = []

    for column in ranked:
        if len(kept) >= budget:
            verdicts.append(ColumnVerdict(
                column, block_of(column), False, "over_budget",
                f"ranked below the {budget} kept for this block"))
            continue

        redundant_with = None
        for chosen in kept:
            if abs(_spearman(numeric[column], numeric[chosen])) >= threshold:
                redundant_with = chosen
                break

        if redundant_with is not None:
            verdicts.append(ColumnVerdict(
                column, block_of(column), False, "redundant",
                f"correlates at or above {threshold} with {redundant_with}",
                duplicate_of=redundant_with))
            continue

        kept.append(column)

    return kept, verdicts


def select_features(
        frame: pd.DataFrame,
        target: str,
        *,
        identifiers: Iterable[str] = (),
        blocks: Iterable[str] | None = None,
        split_column: str = "modelling_split",
        rows_per_feature: int = ROWS_PER_FEATURE,
        redundancy_threshold: float = REDUNDANCY_THRESHOLD,
        min_observations: int = MIN_TRAINING_OBSERVATIONS,
) -> Selection:
    """Run both tiers and return the surviving columns with their reasoning.

    The whole sequence, in order: take every non-target column, keep only the
    training rows, screen on shape, rank what survives against the outcome,
    give each block a budget, and walk each block's ranking dropping
    restatements of signal already kept.
    """

    training = frame[frame[split_column] == TRAINING_SPLIT]
    if training.empty:
        raise SelectionError(
            f"no rows carry split {TRAINING_SPLIT!r}; selection has nothing "
            "to learn from")

    candidates = candidate_columns(frame, identifiers, blocks)
    survivors, verdicts = structural_screen(
        training, candidates,
        min_observations=min_observations)

    scores = rank_by_association(
        training, survivors, target, split_column=split_column)

    per_block: dict[str, list[str]] = defaultdict(list)
    for column in survivors:
        per_block[block_of(column)].append(column)

    total_budget = max(1, len(training) // rows_per_feature)
    budgets = allocate_budgets(
        {block: len(columns) for block, columns in per_block.items()},
        total_budget)

    numeric = _numeric(training, survivors)
    selected: list[str] = []

    for block, columns in sorted(per_block.items()):
        # Strongest first; ties broken by name so reruns agree.
        ranked = sorted(columns, key=lambda c: (-scores[c], c))
        kept, block_verdicts = _prune_redundant(
            numeric, ranked, budgets[block], redundancy_threshold)
        verdicts.extend(block_verdicts)
        selected.extend(kept)

    observations = numeric.notna().sum()
    for column in selected:
        verdicts.append(ColumnVerdict(
            column, block_of(column), True, "selected",
            f"rank correlation {scores[column]:.3f} with {target}, "
            f"not redundant with a stronger column in its block",
            int(observations[column]), scores[column]))

    return Selection(
        target=target,
        selected=sorted(selected),
        verdicts=verdicts,
        budgets=budgets,
        training_rows=len(training),
        candidate_columns=len(candidates),
    )


def select_for_specification(
        frame: pd.DataFrame,
        target: str,
        specification: str,
        **options) -> Selection:
    """Select within one specification's blocks only.

    The entry point to use before fitting anything. ``select_features`` with no
    block filter is for auditing the table as a whole; using its output as a
    model's feature set would mix specifications that overlap in content.
    """

    if specification not in SPECIFICATION_BLOCKS:
        raise SelectionError(
            f"unknown specification {specification!r}; expected one of "
            f"{sorted(SPECIFICATION_BLOCKS)}")

    return select_features(
        frame, target, blocks=SPECIFICATION_BLOCKS[specification], **options)


def split_coverage(
        frame: pd.DataFrame,
        *,
        identifiers: Iterable[str] = (),
        news_blocks: Iterable[str] | None = None,
        split_column: str = "modelling_split",
) -> dict[str, dict]:
    """How many rows in each split carry any non-zero news signal.

    This is a precondition check rather than a summary statistic. A comparison
    between a baseline model and a news model is only informative on rows where
    the news features are able to differ from zero; where a split has no news,
    the two models receive identical inputs and must produce identical
    predictions, so an equal score on that split says nothing about whether
    news helps and should not be reported as though it did.

    Running this before selection is what turns "the news model scored the same
    as the baseline" from a finding into a description of the input data.
    """

    if news_blocks is None:
        news_blocks = {
            block for block in SPECIFICATION_BLOCKS["full"]
            if block not in {"baseline", "coverage"}}

    columns = candidate_columns(frame, identifiers, news_blocks)
    if not columns:
        raise SelectionError("no news columns found for the requested blocks")

    report: dict[str, dict] = {}
    for split, group in frame.groupby(split_column):
        values = _numeric(group, columns).fillna(0)
        with_news = int((values > 0).any(axis=1).sum())
        report[str(split)] = {
            "rows": len(group),
            "rows_with_any_news": with_news,
            "share_with_news": round(with_news / max(1, len(group)), 4),
            "news_comparison_possible": with_news > 0,
        }

    return report


def selection_report(selection: Selection) -> dict:
    """A summary fit to be written to disk and read by a person."""

    kept_per_block = {block: len(columns)
                      for block, columns in sorted(selection.by_block().items())}

    return {
        "target": selection.target,
        "training_rows": selection.training_rows,
        "candidate_columns": selection.candidate_columns,
        "selected_columns": len(selection.selected),
        "rows_per_selected_feature": round(
            selection.training_rows / max(1, len(selection.selected)), 1),
        "removed_by_stage": selection.stage_counts(),
        "budget_per_block": selection.budgets,
        "selected_per_block": kept_per_block,
        "selection_used_training_rows_only": True,
    }
