"""Leakage-safe temporal folds for validating models across election waves.

Purpose
-------
``persistence_benchmark.py`` and ``naive_benchmarks.py`` have no fitted
parameters, so every prediction they make is already an out-of-time
carry-forward by construction - there is nothing to "train" that could leak
future information into a prediction. That stops being true the moment a
model with fitted parameters is introduced (``regularised_models.py``,
planned next): fitting a regression's coefficients, or choosing a
regularisation strength, requires a defensible split between what the model
is allowed to see and what it is being scored against, or the "no news"
comparison this whole project is built around stops meaning anything.

This module builds that split once, as a small, independently testable
piece of infrastructure, before any parameter is ever fitted. It follows
Hanretty (2021, Sections 5.2-5.3)'s two validation designs for by-election
forecasting - leave-one-out, and walk-forward evaluation over expanding
windows of election history - adapted to this project's much sparser Surrey
release, which spans a handful of election waves rather than Hanretty's 468
post-war UK by-elections.

Fold design
-----------
For every distinct election in the release, ordered chronologically by its
own ``election_date``:

* the test set is that election's own party-contest rows;
* the training set is every party-contest row belonging to a STRICTLY
  earlier election, drawn from anywhere in Surrey, not only the same area.

An election with no strictly-earlier election at all (the first
chronological election in the release, in practice 2013) cannot be
evaluated this way and is silently excluded as a test fold - it remains
available as training data for every later fold. This reproduces, without a
special case, the same exclusion the extractor's own release notes describe
as "study start" (``docs/data_contract.md``).

Because Surrey elections are not evenly spaced (three or four large
"principal" polls plus scattered individual by-elections), this design
naturally interleaves both: a by-election gets a fold of its own, trained on
everything before it, exactly as a principal election does.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from no_news_baseline.benchmark_metrics import assert_one_to_one_party_contest_release
from no_news_baseline.election_dates import parse_election_date


@dataclass(frozen=True)
class TemporalFold:
    """One held-out election, and every row known strictly before it.

    ``train_features``/``train_targets`` are not narrowed to any one area or
    party - a future fitted model decides for itself which rows and columns
    to use. This dataclass only guarantees the temporal boundary between the
    two halves.
    """

    election_id: str
    election_date: datetime
    election_year: int
    election_type: str
    train_features: tuple[Mapping[str, object], ...]
    train_targets: tuple[Mapping[str, object], ...]
    test_features: tuple[Mapping[str, object], ...]
    test_targets: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class _ElectionInfo:
    date: datetime
    year: int
    type_: str


def iter_temporal_folds(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[TemporalFold, ...]:
    """Return one fold per election that has at least one earlier election.

    Folds are returned in chronological order. Every feature row appears in
    exactly one fold's test set (its own election's fold, if that election is
    evaluable) and in the training set of every later fold - the two halves
    of a single fold never overlap.
    """

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = assert_one_to_one_party_contest_release(feature_rows, target_rows)

    elections = _index_elections(feature_rows)
    ordered_election_ids = sorted(elections, key=lambda election_id: elections[election_id].date)

    folds: list[TemporalFold] = []
    for election_id in ordered_election_ids:
        current_date = elections[election_id].date
        # Two or more elections can share the same polling day - Surrey has
        # scheduled several county by-elections together, and the 2026 East
        # and West Surrey unitary elections were both held on 7 May 2026.
        # "Earlier" is therefore decided by comparing dates directly, never
        # by position in a list that only breaks same-day ties arbitrarily:
        # same-day elections must not train on each other, even though a
        # naive "everything before this list position" slice could
        # accidentally place one before the other.
        earlier_ids = frozenset(
            other_id for other_id, info in elections.items() if info.date < current_date
        )
        if not earlier_ids:
            # Nothing happened strictly before this election in the release,
            # so there is no legitimate historical evidence to score it
            # against.
            continue
        train_features = tuple(
            row for row in feature_rows if str(row["election_id"]) in earlier_ids
        )
        test_features = tuple(
            row for row in feature_rows if str(row["election_id"]) == election_id
        )
        info = elections[election_id]
        folds.append(
            TemporalFold(
                election_id=election_id,
                election_date=info.date,
                election_year=info.year,
                election_type=info.type_,
                train_features=train_features,
                train_targets=tuple(
                    target_by_id[str(row["party_contest_id"])] for row in train_features
                ),
                test_features=test_features,
                test_targets=tuple(
                    target_by_id[str(row["party_contest_id"])] for row in test_features
                ),
            )
        )

    _assert_folds_are_leakage_safe(folds)
    _assert_every_evaluable_row_covered_exactly_once(feature_rows, folds)
    return tuple(folds)


def summarise_folds(folds: Iterable[TemporalFold]) -> tuple[dict[str, object], ...]:
    """One descriptive row per fold, for reproducibility reporting."""

    return tuple(
        {
            "election_id": fold.election_id,
            "election_date": fold.election_date.date().isoformat(),
            "election_year": fold.election_year,
            "election_type": fold.election_type,
            "train_rows": len(fold.train_features),
            "test_rows": len(fold.test_features),
        }
        for fold in folds
    )


def _index_elections(feature_rows: list[Mapping[str, object]]) -> dict[str, _ElectionInfo]:
    """Build one date/year/type record per election_id, checking agreement.

    Every row sharing an election_id is expected to describe the same
    election event. A disagreement would mean the upstream release is
    internally inconsistent, which the fold builder must not paper over by
    arbitrarily picking one row's value.
    """

    info_by_election: dict[str, _ElectionInfo] = {}
    for row in feature_rows:
        election_id = str(row["election_id"])
        info = _ElectionInfo(
            date=parse_election_date(str(row["election_date"])),
            year=int(row["election_year"]),
            type_=str(row["election_type"]),
        )
        existing = info_by_election.get(election_id)
        if existing is None:
            info_by_election[election_id] = info
        elif existing != info:
            raise ValueError(
                f"Election {election_id!r} has inconsistent date/year/type across its own rows."
            )
    return info_by_election


def _assert_folds_are_leakage_safe(folds: list[TemporalFold]) -> None:
    # Re-derives the leakage check independently of the construction loop
    # above, so a future edit to that loop cannot silently break the
    # "source_date_precedes_target" rule without a test catching it here.
    for fold in folds:
        for train_row in fold.train_features:
            train_date = parse_election_date(str(train_row["election_date"]))
            if train_date >= fold.election_date:
                raise ValueError(
                    f"Fold {fold.election_id!r} contains training data that is not "
                    "strictly earlier than the held-out election."
                )
        test_election_ids = {str(row["election_id"]) for row in fold.test_features}
        if test_election_ids not in ({fold.election_id}, set()):
            raise ValueError(f"Fold {fold.election_id!r} test rows do not all belong to it.")


def _assert_every_evaluable_row_covered_exactly_once(
    feature_rows: list[Mapping[str, object]], folds: list[TemporalFold]
) -> None:
    # A row silently dropped from every fold's test set would shrink the
    # evaluation population without explanation; a row appearing in two
    # folds' test sets would double-count it. Both are treated as
    # construction bugs rather than tolerated silently.
    test_ids_seen: list[str] = []
    for fold in folds:
        test_ids_seen.extend(str(row["party_contest_id"]) for row in fold.test_features)
    if len(test_ids_seen) != len(set(test_ids_seen)):
        raise ValueError("A party-contest row was scored as a test row in more than one fold.")

    evaluable_election_ids = {fold.election_id for fold in folds}
    expected_test_ids = {
        str(row["party_contest_id"])
        for row in feature_rows
        if str(row["election_id"]) in evaluable_election_ids
    }
    if set(test_ids_seen) != expected_test_ids:
        raise ValueError("Fold construction lost or duplicated an evaluable party-contest row.")
