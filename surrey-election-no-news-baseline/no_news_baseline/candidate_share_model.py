"""Architecture A: a regularised linear model of candidate vote share.

The brief's Architecture A is "an appropriate regularised regression or
generalised linear model ... Elastic Net regression on transformed vote
share". This module implements the ridge (L2) form on a transformed target,
because ridge has a closed-form solution that can be checked by hand, while a
correct elastic net needs an iterative solver whose convergence would itself
have to be argued for. Lasso-style selection over a wider candidate set is
documented future work, not a claim made here.

The target transformation
-------------------------
The model does not predict vote share directly. It predicts

    y = share * candidates_in_contest / 100

which reads as "how many times the contest's equal split did this candidate
receive". The inverse is share = y * 100 / candidates_in_contest.

This is not a convenience. Every election before 7 May 2026 was fought in
single-member divisions and the primary holdout is entirely two-member wards,
so on the raw scale the model would be fitted on contests averaging 4.6
candidates and 22.65 per cent per candidate and scored on contests averaging
10.4 and 9.75 - a systematic over-prediction of roughly a factor of two that
has nothing to do with politics.

The transformation removes it by construction rather than by hoping the model
learns it from candidate counts. Shares sum to 100 in every contest whatever
its size, so sum(y) = candidates_in_contest and mean(y) = 1 in every contest
without exception. Measured on the real release the single-member rows average
1.000 and the multi-member rows 1.001; on the raw scale those same groups
average 22.65 and 9.75.

Both scales are retained in every prediction record, so the transformation can
never hide a modelling fault: if predictions look wrong on one scale they can
be inspected on the other.

Penalty selection
-----------------
The L2 penalty is chosen inside each fold's own training rows, by holding out
that fold's most recent training polling day as an inner validation set. A
penalty chosen on the outer test rows would be a quiet form of leakage - the
model would have seen the answer once, through the hyperparameter. Where a
training fold has only one polling day no inner split exists, and the selected
penalty is recorded as a documented default rather than presented as a choice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from no_news_baseline.candidate_cohort import (
    allocate_contest,
    contest_key,
    group_by_contest,
    normalise_within_contest,
)
from no_news_baseline.candidate_features import CandidateFeatureEncoder, target_vector
from no_news_baseline.election_dates import parse_election_date


MODEL_ID = "ridge_candidate_share_v1"
TARGET_SCALE = "multiple_of_contest_equal_share"

# Pre-declared penalty grid. Widened once, before any outer test fold was
# scored, after the first inner search hit the top of a (0.1 ... 1000) grid in
# five of seven folds - a grid boundary is a diagnostic, not a result. The
# search space is not widened again in response to an outer score.
PENALTY_GRID: tuple[float, ...] = (
    0.1, 1.0, 10.0, 100.0, 1000.0, 10_000.0, 100_000.0,
)

# Used only where a training fold offers no usable inner validation split.
# Recorded explicitly in the fold record so it never reads as a choice.
DEFAULT_PENALTY = 1000.0

# An inner validation day must carry at least this many rows to be scored.
# Surrey by-elections produce polling days with three or four candidate rows,
# and a hyperparameter selected on three rows is noise: in the fold that
# trains through 2020, the most recent training polling day is the 2019
# Haslemere by-election with three rows, and selecting on it alone chose the
# heaviest penalty in the grid and nearly doubled outer test error.
MIN_INNER_VALIDATION_ROWS = 20

# How many qualifying polling days to average over. More than one, so a single
# unusual election cannot decide the penalty; few enough that the inner folds
# stay close in time to the outer test period.
MAX_INNER_FOLDS = 3


# --------------------------------------------------------------------------
# Target scale
# --------------------------------------------------------------------------


def to_relative_share(
    shares: Sequence[float], candidate_counts: Sequence[int]
) -> np.ndarray:
    """Vote share (0-100) to multiples of the contest's equal split."""

    shares_array = np.asarray(shares, dtype=float)
    counts = np.asarray(candidate_counts, dtype=float)
    if np.any(counts <= 0):
        raise ValueError("A contest cannot have zero candidates.")
    return shares_array * counts / 100.0


def to_vote_share(
    relative: Sequence[float], candidate_counts: Sequence[int]
) -> np.ndarray:
    """Inverse of ``to_relative_share``."""

    relative_array = np.asarray(relative, dtype=float)
    counts = np.asarray(candidate_counts, dtype=float)
    if np.any(counts <= 0):
        raise ValueError("A contest cannot have zero candidates.")
    return relative_array * 100.0 / counts


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------


class RidgeShareModel:
    """Closed-form ridge regression on the transformed target.

    Standardisation of the design matrix happens in
    ``CandidateFeatureEncoder``; this class only centres the target so the
    intercept is not shrunk. Penalising the intercept would pull every
    prediction toward zero, which is not what regularisation is for.
    """

    def __init__(self, l2_penalty: float = DEFAULT_PENALTY) -> None:
        if l2_penalty < 0:
            raise ValueError("The ridge L2 penalty must be non-negative.")
        self._l2_penalty = float(l2_penalty)
        self._coefficients: np.ndarray | None = None
        self._intercept: float | None = None
        self._design_means: np.ndarray | None = None

    def fit(self, design: np.ndarray, target: np.ndarray) -> "RidgeShareModel":
        if design.shape[0] != target.shape[0]:
            raise ValueError("Design matrix and target must align one-to-one.")
        if design.shape[0] == 0:
            raise ValueError("Cannot fit on an empty training set.")

        # Both sides are centred on their training means before solving. The
        # encoder already standardises in production, which makes the design
        # centring a no-op there - but the class must not depend on a caller
        # having done it, or a future caller passing a raw matrix would get a
        # silently biased intercept rather than an error.
        design_means = design.mean(axis=0)
        centered_design = design - design_means
        target_mean = float(target.mean())
        centered_target = target - target_mean

        # w = (X'X + lambda I)^-1 X'y, solved as a linear system rather than
        # inverted explicitly, for numerical stability on a 107-column matrix
        # with many correlated one-hot columns. Centring keeps the intercept
        # out of the penalised system: it is the training mean, unshrunk.
        n_features = centered_design.shape[1]
        gram = (
            centered_design.T @ centered_design
            + self._l2_penalty * np.eye(n_features)
        )
        self._coefficients = np.linalg.solve(
            gram, centered_design.T @ centered_target
        )
        self._design_means = design_means
        self._intercept = target_mean
        return self

    def predict(self, design: np.ndarray) -> np.ndarray:
        if (
            self._coefficients is None
            or self._intercept is None
            or self._design_means is None
        ):
            raise ValueError("The model must be fitted before predicting.")
        if design.shape[1] != self._coefficients.shape[0]:
            raise ValueError("Design matrix has a different width than at fit time.")
        # The same centring learned at fit time, applied unchanged.
        return (design - self._design_means) @ self._coefficients + self._intercept

    @property
    def l2_penalty(self) -> float:
        return self._l2_penalty

    @property
    def coefficients(self) -> np.ndarray:
        if self._coefficients is None:
            raise ValueError("The model has not been fitted.")
        return self._coefficients.copy()

    @property
    def intercept(self) -> float:
        if self._intercept is None:
            raise ValueError("The model has not been fitted.")
        return self._intercept


# --------------------------------------------------------------------------
# Penalty selection, inside the training rows only
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PenaltyChoice:
    """Which penalty was chosen, how, and on what."""

    l2_penalty: float
    method: str
    inner_validation_dates: tuple[str, ...]
    inner_validation_rows: int
    grid_scores: tuple[tuple[float, float], ...] = field(default=())
    hit_grid_boundary: bool = False


def select_penalty(
    train_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    *,
    grid: Sequence[float] = PENALTY_GRID,
    min_inner_rows: int = MIN_INNER_VALIDATION_ROWS,
    max_inner_folds: int = MAX_INNER_FOLDS,
) -> PenaltyChoice:
    """Pick an L2 penalty by expanding-window validation inside training rows.

    Each inner fold holds out one polling day and trains on everything
    strictly earlier, so the penalty is chosen for its ability to generalise
    *forward* - the same thing the outer evaluation will ask of the model.
    Scores are averaged over up to ``max_inner_folds`` of the most recent
    qualifying days.

    Two guards, both learned from a real failure rather than added
    defensively. A single small by-election as the only inner validation set
    chose the heaviest penalty in the grid and nearly doubled outer test error
    in the fold that trains through 2020, because that fold's most recent
    training polling day is a three-row by-election:

    * ``min_inner_rows`` excludes days too small to carry a signal;
    * averaging over several days stops one unusual election deciding alone.

    Nothing outside ``train_rows`` is touched, so the outer test fold cannot
    influence the penalty through the back door of hyperparameter selection.
    """

    by_day: dict[str, list[Mapping[str, object]]] = {}
    for row in train_rows:
        day = parse_election_date(str(row["election_date"])).date().isoformat()
        by_day.setdefault(day, []).append(row)

    days = sorted(by_day)
    # A day qualifies if it is large enough to score and has earlier data to
    # train on. The most recent qualifying days are preferred, because they
    # sit closest in time to the outer test period.
    qualifying = [
        day
        for position, day in enumerate(days)
        if position > 0 and len(by_day[day]) >= min_inner_rows
    ][-max_inner_folds:]

    if not qualifying:
        return PenaltyChoice(
            l2_penalty=DEFAULT_PENALTY,
            method="documented_default_no_inner_validation_day_large_enough",
            inner_validation_dates=(),
            inner_validation_rows=0,
        )

    # Score every penalty on every inner fold, then average. Building the
    # per-fold matrices once and reusing them across penalties keeps the
    # encoder fitted on inner-training rows only, as it must be.
    folds: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for day in qualifying:
        inner_train = [
            row
            for row in train_rows
            if parse_election_date(str(row["election_date"])).date().isoformat() < day
        ]
        inner_test = by_day[day]
        if not inner_train:
            continue
        encoder = CandidateFeatureEncoder().fit(inner_train)
        folds.append(
            (
                encoder.transform(inner_train).matrix,
                to_relative_share(
                    target_vector(inner_train, targets),
                    [int(row["candidate_count_in_contest"]) for row in inner_train],
                ),
                encoder.transform(inner_test).matrix,
                to_relative_share(
                    target_vector(inner_test, targets),
                    [int(row["candidate_count_in_contest"]) for row in inner_test],
                ),
            )
        )

    if not folds:
        return PenaltyChoice(
            l2_penalty=DEFAULT_PENALTY,
            method="documented_default_no_usable_inner_fold",
            inner_validation_dates=tuple(qualifying),
            inner_validation_rows=sum(len(by_day[day]) for day in qualifying),
        )

    scores: list[tuple[float, float]] = []
    for penalty in grid:
        fold_errors = [
            float(np.mean(np.abs(RidgeShareModel(penalty).fit(x_tr, y_tr).predict(x_te) - y_te)))
            for x_tr, y_tr, x_te, y_te in folds
        ]
        scores.append((float(penalty), float(np.mean(fold_errors))))

    # Ties break toward the larger penalty, i.e. the simpler model. The brief:
    # "Do not select a complex model based on a negligible improvement."
    best = min(scores, key=lambda item: (item[1], -item[0]))
    return PenaltyChoice(
        l2_penalty=best[0],
        method="inner_expanding_window_validation",
        inner_validation_dates=tuple(qualifying),
        inner_validation_rows=sum(len(by_day[day]) for day in qualifying),
        grid_scores=tuple(scores),
        # A chosen penalty at either end of the grid means the search was
        # bounded by the grid rather than by the data. Recorded so it can be
        # reported instead of silently accepted.
        hit_grid_boundary=best[0] in {min(grid), max(grid)},
    )


# --------------------------------------------------------------------------
# One fold: fit, predict, normalise, allocate
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FoldResult:
    """Everything one fold produced, including how it was configured."""

    split_id: str
    split_role: str
    train_rows: int
    test_rows: int
    train_reform_rows: int
    test_reform_rows: int
    penalty: PenaltyChoice
    encoded_columns: int
    predictions: tuple[dict[str, object], ...]


def fit_and_predict_fold(
    *,
    split_id: str,
    split_role: str,
    train_rows: Sequence[Mapping[str, object]],
    test_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    penalty: float | None = None,
) -> FoldResult:
    """Fit on one fold's training rows and predict its test rows.

    The order of operations is the whole point and is fixed here so no caller
    can reorder it:

    1. select the penalty inside the training rows;
    2. fit the encoder on the training rows only;
    3. fit ridge on the transformed training target;
    4. predict the test rows on the transformed scale;
    5. invert the transform to vote share;
    6. normalise within each test contest so shares sum to 100;
    7. rank and allocate seats using the known pre-election seat count.

    Steps 6 and 7 use the shared contest machinery in ``candidate_cohort`` so
    that this model, later architectures and the Stage 2 news layer all
    normalise and allocate identically.
    """

    if not train_rows:
        raise ValueError(f"Split {split_id!r} has no training rows.")
    if not test_rows:
        raise ValueError(f"Split {split_id!r} has no test rows.")

    choice = (
        select_penalty(train_rows, targets)
        if penalty is None
        else PenaltyChoice(
            l2_penalty=float(penalty),
            method="caller_supplied",
            inner_validation_date=None,
            inner_validation_rows=0,
        )
    )

    encoder = CandidateFeatureEncoder().fit(train_rows)
    design_train = encoder.transform(train_rows)
    design_test = encoder.transform(test_rows)

    train_counts = [int(row["candidate_count_in_contest"]) for row in train_rows]
    test_counts = [int(row["candidate_count_in_contest"]) for row in test_rows]

    y_train = to_relative_share(target_vector(train_rows, targets), train_counts)
    model = RidgeShareModel(choice.l2_penalty).fit(design_train.matrix, y_train)

    predicted_relative = model.predict(design_test.matrix)
    predicted_share_raw = to_vote_share(predicted_relative, test_counts)

    # --- contest normalisation and seat allocation -----------------------
    by_id = {str(row["candidate_contest_id"]): row for row in test_rows}
    raw_by_id = {
        str(row["candidate_contest_id"]): float(value)
        for row, value in zip(test_rows, predicted_share_raw)
    }
    relative_by_id = {
        str(row["candidate_contest_id"]): float(value)
        for row, value in zip(test_rows, predicted_relative)
    }

    normalised_by_id: dict[str, float | None] = {}
    normalisation_status: dict[str, str] = {}
    allocation_by_id: dict[str, object] = {}

    for _, contest_rows in group_by_contest(test_rows).items():
        payload = [
            {
                "candidate_contest_id": str(row["candidate_contest_id"]),
                "predicted_candidate_vote_share": raw_by_id[
                    str(row["candidate_contest_id"])
                ],
            }
            for row in contest_rows
        ]
        for item in normalise_within_contest(payload):
            normalised_by_id[item.candidate_contest_id] = item.normalised_prediction
            normalisation_status[item.candidate_contest_id] = item.normalisation_status

        # Allocation runs on the normalised values: ranking is unchanged by a
        # positive rescale, but using the same numbers everywhere means a
        # published rank always agrees with the published share.
        allocation_payload = [
            {
                "candidate_contest_id": str(row["candidate_contest_id"]),
                "predicted_candidate_vote_share": normalised_by_id[
                    str(row["candidate_contest_id"])
                ],
            }
            for row in contest_rows
        ]
        seats = contest_rows[0].get("analysis_number_of_seats")
        for item in allocate_contest(
            allocation_payload, seats=None if seats is None else int(seats)
        ):
            allocation_by_id[item.candidate_contest_id] = item

    # --- prediction records ----------------------------------------------
    records: list[dict[str, object]] = []
    for row in test_rows:
        row_id = str(row["candidate_contest_id"])
        target = targets[row_id]
        observed = target.get("target_candidate_vote_share")
        observed_value = None if observed is None else float(observed)
        normalised = normalised_by_id.get(row_id)
        allocation = allocation_by_id[row_id]
        election_id, division_id = contest_key(row)

        error = (
            None
            if normalised is None or observed_value is None
            else normalised - observed_value
        )
        records.append(
            {
                "split_id": split_id,
                "split_role": split_role,
                "model_id": MODEL_ID,
                "candidate_contest_id": row_id,
                "election_id": election_id,
                "election_date": row["election_date"],
                "division_id": division_id,
                "contest_structure": row["contest_structure"],
                "standard_party_name": row["standard_party_name"],
                "is_reform_uk": bool(row.get("is_reform_uk")),
                "is_ukip": bool(row.get("is_ukip")),
                "candidate_count_in_contest": row["candidate_count_in_contest"],
                "analysis_number_of_seats": row["analysis_number_of_seats"],
                # Both scales are kept so a fault can never hide behind the
                # transformation.
                "predicted_relative_share": relative_by_id[row_id],
                "predicted_vote_share_unnormalised": raw_by_id[row_id],
                "predicted_vote_share": normalised,
                "normalisation_status": normalisation_status[row_id],
                "predicted_rank": allocation.predicted_rank,
                "predicted_rank_tied": allocation.predicted_rank_tied,
                "predicted_elected": allocation.predicted_elected,
                "allocation_status": allocation.allocation_status,
                "observed_vote_share": observed_value,
                "observed_rank": target.get("target_candidate_rank"),
                "observed_elected": target.get("target_candidate_elected") == "Yes",
                "error": error,
                "absolute_error": None if error is None else abs(error),
                "squared_error": None if error is None else error * error,
            }
        )

    return FoldResult(
        split_id=split_id,
        split_role=split_role,
        train_rows=len(train_rows),
        test_rows=len(test_rows),
        train_reform_rows=sum(1 for row in train_rows if row.get("is_reform_uk")),
        test_reform_rows=sum(1 for row in test_rows if row.get("is_reform_uk")),
        penalty=choice,
        encoded_columns=len(encoder.column_names),
        predictions=tuple(records),
    )
