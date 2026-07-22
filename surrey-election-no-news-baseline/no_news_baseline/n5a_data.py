"""Fold-wise data preparation for the N5a hierarchical Dirichlet model.

Pure, deterministic data preparation - no model code, no sampling - so
every leakage-sensitive decision lives and is tested in one place. Key
decisions (each enforced by a test):

- Modelling universe = the frozen Task-1 usability audit, reused verbatim.
- Party identity = ``party_group_key``: UKIP/Reform stay distinct and each
  Independent keeps their own identity; parties unseen in training get
  ``UNSEEN_PARTY_INDEX`` (drawn from the population prior, never another
  party's posterior).
- Standing parties with a published 0% share become 1/40,000 of the
  composition (Hanretty 2021's rounded-zero convention); absent parties
  have no row at all - no epsilon substitution.
- Compositions are renormalised from publication rounding (98-102) to sum
  exactly to 1.
- The previous-local-share predictor is standardised with training-fold
  statistics only; missing values become 0 plus an explicit indicator.
- Cycle structure: principal training elections get cycle indices;
  by-elections share one indicator (``BY_ELECTION_CYCLE_INDEX``) because
  the audit shows per-event effects would be confounded; a held-out
  principal election carries the new-cycle index so the model integrates
  over a fresh draw instead of peeking at a fitted effect.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from no_news_baseline.benchmark_metrics import assert_one_to_one_party_contest_release
from no_news_baseline.n5_specification_audit import build_contest_usability_audit
from no_news_baseline.temporal_validation import iter_temporal_folds


# Hanretty (2021)'s rounded-zero replacement: one part in 40,000 of the
# composition, i.e. smaller than one vote in the average electorate.
ROUNDED_ZERO_SHARE_FRACTION = 1.0 / 40000.0

UNSEEN_PARTY_INDEX = -1
BY_ELECTION_CYCLE_INDEX = -1
# The model reads "cycle index == number of training cycles" as "a new
# principal cycle not seen in training": integrate over a fresh draw.
BY_ELECTION_TYPE = "by-election"


@dataclass(frozen=True)
class ContestRow:
    """One party's slot within one contest, fully encoded for the model."""

    party_contest_id: str
    party_group_key: str
    standard_party_name: str
    party_index: int
    previous_share_z: float
    previous_share_missing: int


@dataclass(frozen=True)
class Contest:
    """One election x area contest with its complete encoded ballot."""

    election_id: str
    division_id: str
    division_name: str
    election_date: str
    is_by_election: bool
    cycle_index: int
    rows: tuple[ContestRow, ...]
    # Simplex-renormalised observed shares (fractions summing to 1) for
    # usable compositions; None when the contest cannot be scored (2026
    # multi-member wards have no defined party-share target).
    observed_shares: tuple[float, ...] | None


@dataclass(frozen=True)
class N5aFoldData:
    """Everything the model may see for one temporal fold, and nothing more."""

    election_id: str
    election_date_iso: str
    information_cutoff_iso: str
    train_contests: tuple[Contest, ...]
    test_contests: tuple[Contest, ...]
    party_count: int
    cycle_count: int
    new_cycle_index: int
    previous_share_mean: float
    previous_share_std: float


def prepare_n5a_fold_data(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[N5aFoldData, ...]:
    """Build the per-fold training/test structures for N5a.

    Training contests are the fold's strictly-earlier usable compositions
    (per the frozen audit). Test contests are every contest of the held-out
    election, scoreable or not, so prediction coverage stays visible even
    where no share target exists.
    """

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = assert_one_to_one_party_contest_release(feature_rows, target_rows)

    usable_contest_keys = {
        (str(row["election_id"]), str(row["division_id"]))
        for row in build_contest_usability_audit(feature_rows, target_rows)
        if row["usable_complete_composition"]
    }

    folds = []
    for fold in iter_temporal_folds(feature_rows, target_rows):
        train_grouped = _group_by_contest(fold.train_features)
        test_grouped = _group_by_contest(fold.test_features)

        # Party index and predictor scaling are fitted on training rows
        # only; both are frozen before any test row is touched.
        train_rows_flat = [row for rows in train_grouped.values() for row in rows]
        party_index = _build_party_index(train_rows_flat)
        share_mean, share_std = _fit_previous_share_scaling(train_rows_flat)
        cycle_index = _build_cycle_index(train_grouped)

        train_contests = tuple(
            _encode_contest(
                contest_key=key,
                rows=rows,
                party_index=party_index,
                cycle_index=cycle_index,
                new_cycle_index=len(cycle_index),
                share_mean=share_mean,
                share_std=share_std,
                target_by_id=target_by_id,
                usable_contest_keys=usable_contest_keys,
            )
            for key, rows in sorted(train_grouped.items())
            if key in usable_contest_keys
        )
        test_contests = tuple(
            _encode_contest(
                contest_key=key,
                rows=rows,
                party_index=party_index,
                cycle_index=cycle_index,
                new_cycle_index=len(cycle_index),
                share_mean=share_mean,
                share_std=share_std,
                target_by_id=target_by_id,
                usable_contest_keys=usable_contest_keys,
            )
            for key, rows in sorted(test_grouped.items())
        )
        folds.append(
            N5aFoldData(
                election_id=fold.election_id,
                election_date_iso=fold.election_date.date().isoformat(),
                information_cutoff_iso=fold.election_date.date().isoformat(),
                train_contests=train_contests,
                test_contests=test_contests,
                party_count=len(party_index),
                cycle_count=len(cycle_index),
                new_cycle_index=len(cycle_index),
                previous_share_mean=share_mean,
                previous_share_std=share_std,
            )
        )
    return tuple(folds)


def _group_by_contest(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], list[Mapping[str, object]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["election_id"]), str(row["division_id"]))].append(row)
    # Sort each ballot deterministically so run-to-run output is identical.
    return {
        key: sorted(value, key=lambda row: str(row["party_contest_id"]))
        for key, value in grouped.items()
    }


def _build_party_index(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    """Index parties by party_group_key, training rows only.

    The group key keeps UKIP and Reform UK separate and gives each
    candidate-specific Independent an identity of their own, so no cross-
    identity pooling is possible through this index.
    """

    return {
        key: index
        for index, key in enumerate(
            sorted({str(row["party_group_key"]) for row in rows})
        )
    }


def _fit_previous_share_scaling(
    rows: Sequence[Mapping[str, object]],
) -> tuple[float, float]:
    observed = [
        float(row["previous_party_vote_share"])
        for row in rows
        if isinstance(row.get("previous_party_vote_share"), (int, float))
        and not isinstance(row.get("previous_party_vote_share"), bool)
    ]
    if not observed:
        # First evaluable fold trains on 2013 only, where no approved local
        # history exists; the predictor is then all-missing and its scale
        # is irrelevant (every z is 0 with the missing indicator set).
        return 0.0, 1.0
    mean = sum(observed) / len(observed)
    variance = sum((value - mean) ** 2 for value in observed) / len(observed)
    return mean, (variance**0.5) or 1.0


def _build_cycle_index(
    grouped: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
) -> dict[str, int]:
    """One index per PRINCIPAL election in training; by-elections excluded.

    This is the identifiable structure chosen from the cycle audit: each
    by-election is a singleton, so per-event effects would be confounded
    with the shared by-election indicator the model uses instead.
    """

    principal_elections = sorted(
        {
            str(rows[0]["election_id"])
            for rows in grouped.values()
            if str(rows[0]["election_type"]) != BY_ELECTION_TYPE
        }
    )
    return {election_id: index for index, election_id in enumerate(principal_elections)}


def _encode_contest(
    *,
    contest_key: tuple[str, str],
    rows: Sequence[Mapping[str, object]],
    party_index: Mapping[str, int],
    cycle_index: Mapping[str, int],
    new_cycle_index: int,
    share_mean: float,
    share_std: float,
    target_by_id: Mapping[str, Mapping[str, object]],
    usable_contest_keys: set[tuple[str, str]],
) -> Contest:
    election_id, division_id = contest_key
    is_by_election = str(rows[0]["election_type"]) == BY_ELECTION_TYPE
    if is_by_election:
        contest_cycle = BY_ELECTION_CYCLE_INDEX
    else:
        # A principal election absent from the training cycles is a NEW
        # cycle: the model must integrate over a fresh draw, never borrow a
        # fitted effect (that would require this election's own outcomes).
        contest_cycle = cycle_index.get(election_id, new_cycle_index)

    encoded_rows = tuple(
        ContestRow(
            party_contest_id=str(row["party_contest_id"]),
            party_group_key=str(row["party_group_key"]),
            standard_party_name=str(row["standard_party_name"]),
            party_index=party_index.get(str(row["party_group_key"]), UNSEEN_PARTY_INDEX),
            previous_share_z=_previous_share_z(row, share_mean, share_std),
            previous_share_missing=_previous_share_missing(row),
        )
        for row in rows
    )
    return Contest(
        election_id=election_id,
        division_id=division_id,
        division_name=str(rows[0]["division_name"]),
        election_date=str(rows[0]["election_date"]),
        is_by_election=is_by_election,
        cycle_index=contest_cycle,
        rows=encoded_rows,
        observed_shares=(
            _simplex_shares(rows, target_by_id)
            if contest_key in usable_contest_keys
            else None
        ),
    )


def _previous_share_missing(row: Mapping[str, object]) -> int:
    value = row.get("previous_party_vote_share")
    return 0 if isinstance(value, (int, float)) and not isinstance(value, bool) else 1


def _previous_share_z(
    row: Mapping[str, object], mean: float, std: float
) -> float:
    value = row.get("previous_party_vote_share")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0.0
    return (float(value) - mean) / std


def _simplex_shares(
    rows: Sequence[Mapping[str, object]],
    target_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[float, ...]:
    """Renormalise a usable composition onto the exact simplex.

    Published rounded zeros for STANDING parties become 1/40,000 of the
    composition (Hanretty 2021's convention) before renormalisation. A
    missing share inside a supposedly usable composition is a contract
    violation and fails loudly.
    """

    raw: list[float] = []
    for row in rows:
        share = target_by_id[str(row["party_contest_id"])].get("target_party_vote_share")
        if not isinstance(share, (int, float)) or isinstance(share, bool):
            raise ValueError(
                f"Usable composition is missing a share for {row['party_contest_id']!r}."
            )
        fraction = float(share) / 100.0
        raw.append(fraction if fraction > 0 else ROUNDED_ZERO_SHARE_FRACTION)
    total = sum(raw)
    if total <= 0:
        raise ValueError("Composition has no positive shares after zero handling.")
    return tuple(value / total for value in raw)
