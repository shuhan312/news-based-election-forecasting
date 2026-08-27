"""Probability of election, with a seat-count constraint.

The brief asks for "a probability of election for each candidate where
supported by the model", and for Brier score, log loss and calibration. None
of those can be computed from the share model, which returns a point share and
a hard top-N elected flag. Turning a rank into a number between 0 and 1 would
produce something that looks like a probability and is not one, so this is a
separate fitted model: regularised logistic regression, which the brief names
under Architecture A.

The seat constraint
-------------------
An unconstrained logistic treats each candidate as an independent Bernoulli
draw, which is wrong here in a way that matters. Exactly ``seats`` candidates
win each contest - one in a division, two in a 2026 ward - so the probabilities
in a contest must sum to the seat count. A raw logistic fit will not do that:
on the 2026 holdout it can put ten candidates at 0.2 each and imply two
winners by luck, or at 0.05 each and imply half a seat.

The fix is a per-contest shift in log-odds, solved by bisection so that

    sum over candidates of sigmoid(logit(p_i) + delta) = seats

A single additive offset preserves the model's *ordering* and its relative
confidence between candidates; it only moves the overall level to respect a
fact that was known before polling. Rescaling probabilities proportionally
was rejected because it can push a value above 1 and distorts the ordering
near the top of the ballot.

Both versions are exported. The raw probability shows what the model believed
before the constraint; the calibrated one is what may be scored, because it is
the only one that respects the arithmetic of the contest.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from no_news_baseline.candidate_cohort import contest_key, group_by_contest
from no_news_baseline.candidate_features import CandidateFeatureEncoder
from no_news_baseline.election_dates import parse_election_date


MODEL_ID = "logistic_candidate_election_v1"

# Same shape of grid as the share model, chosen on log loss rather than MAE.
PENALTY_GRID: tuple[float, ...] = (
    0.1, 1.0, 10.0, 100.0, 1000.0, 10_000.0, 100_000.0,
)
DEFAULT_PENALTY = 1000.0
MIN_INNER_VALIDATION_ROWS = 20
MAX_INNER_FOLDS = 3

# Probabilities are clipped away from 0 and 1 before scoring. Log loss is
# infinite at a confident miss, and one such row would make the metric
# meaningless for the whole fold. The bound is recorded with the metric so the
# clipping is visible rather than silently applied.
PROBABILITY_CLIP = 1e-6


def _sigmoid(values: np.ndarray) -> np.ndarray:
    # Split by sign to avoid overflow in exp for large negative inputs.
    out = np.empty_like(values, dtype=float)
    positive = values >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_negative = np.exp(values[~positive])
    out[~positive] = exp_negative / (1.0 + exp_negative)
    return out


def _logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, PROBABILITY_CLIP, 1.0 - PROBABILITY_CLIP)
    return np.log(clipped / (1.0 - clipped))


class LogisticElectionModel:
    """L2-regularised logistic regression fitted by Newton-Raphson.

    Written out rather than imported because the package's declared
    dependencies are numpy and pytest, and adding a general machine
    -learning dependency for one closed-form-ish fit would be a large change
    for a small gain. The intercept is carried as an appended column and is
    not penalised, for the same reason the ridge intercept is not: shrinking
    it would bias every probability toward one half.
    """

    def __init__(
        self,
        l2_penalty: float = DEFAULT_PENALTY,
        *,
        max_iterations: int = 50,
        tolerance: float = 1e-8,
    ) -> None:
        if l2_penalty < 0:
            raise ValueError("The L2 penalty must be non-negative.")
        self._l2_penalty = float(l2_penalty)
        self._max_iterations = max_iterations
        self._tolerance = tolerance
        self._coefficients: np.ndarray | None = None
        self._iterations = 0
        self._converged = False

    def fit(self, design: np.ndarray, elected: np.ndarray) -> "LogisticElectionModel":
        if design.shape[0] != elected.shape[0]:
            raise ValueError("Design matrix and outcome must align one-to-one.")
        if design.shape[0] == 0:
            raise ValueError("Cannot fit on an empty training set.")

        target = np.asarray(elected, dtype=float)
        if not np.all(np.isin(target, (0.0, 1.0))):
            raise ValueError("The elected outcome must be binary.")

        augmented = np.hstack([np.ones((design.shape[0], 1)), design])
        # Penalise every coefficient except the intercept in column 0.
        penalty = self._l2_penalty * np.eye(augmented.shape[1])
        penalty[0, 0] = 0.0

        beta = np.zeros(augmented.shape[1])
        for iteration in range(1, self._max_iterations + 1):
            probabilities = _sigmoid(augmented @ beta)
            # Newton step on the penalised log-likelihood. The weight floor
            # keeps the Hessian invertible once probabilities saturate, which
            # happens quickly here because most candidates are not elected.
            weights = np.clip(probabilities * (1.0 - probabilities), 1e-10, None)
            gradient = augmented.T @ (target - probabilities) - penalty @ beta
            hessian = (augmented.T * weights) @ augmented + penalty
            step = np.linalg.solve(hessian, gradient)
            beta = beta + step
            self._iterations = iteration
            if np.max(np.abs(step)) < self._tolerance:
                self._converged = True
                break

        self._coefficients = beta
        return self

    def predict_proba(self, design: np.ndarray) -> np.ndarray:
        if self._coefficients is None:
            raise ValueError("The model must be fitted before predicting.")
        if design.shape[1] != self._coefficients.shape[0] - 1:
            raise ValueError("Design matrix has a different width than at fit time.")
        augmented = np.hstack([np.ones((design.shape[0], 1)), design])
        return _sigmoid(augmented @ self._coefficients)

    @property
    def l2_penalty(self) -> float:
        return self._l2_penalty

    @property
    def converged(self) -> bool:
        return self._converged

    @property
    def iterations(self) -> int:
        return self._iterations

    @property
    def coefficients(self) -> np.ndarray:
        if self._coefficients is None:
            raise ValueError("The model has not been fitted.")
        return self._coefficients.copy()


# --------------------------------------------------------------------------
# Seat constraint
# --------------------------------------------------------------------------


def calibrate_to_seats(
    probabilities: Sequence[float],
    seats: int,
    *,
    max_iterations: int = 200,
    tolerance: float = 1e-10,
) -> tuple[np.ndarray, str]:
    """Shift log-odds by one constant so the contest's probabilities sum to seats.

    Returns the adjusted probabilities and a status. Bisection is used rather
    than a solver because the objective is monotone in the offset - raising
    every candidate's log-odds can only raise the sum - so bisection is exact
    to machine precision and cannot fail to converge.

    Statuses:

    ``seat_constrained``
        The ordinary case.
    ``not_constrained_seats_unknown``
        No pre-election seat count, so no constraint can be applied without
        inventing one. Raw probabilities are returned unchanged.
    ``not_constrained_target_unreachable``
        The requested sum exceeds the number of candidates, or is not
        positive. Left unchanged rather than forced.
    """

    values = np.asarray(probabilities, dtype=float)
    if seats is None:
        return values, "not_constrained_seats_unknown"
    if seats <= 0 or seats >= len(values):
        return values, "not_constrained_target_unreachable"

    base = _logit(values)
    # A wide bracket: at -60 every probability is ~0, at +60 every one is ~1,
    # so the true offset is inside for any attainable seat count.
    low, high = -60.0, 60.0
    for _ in range(max_iterations):
        middle = 0.5 * (low + high)
        total = float(np.sum(_sigmoid(base + middle)))
        if abs(total - seats) < tolerance:
            break
        if total < seats:
            low = middle
        else:
            high = middle
    return _sigmoid(base + 0.5 * (low + high)), "seat_constrained"


# --------------------------------------------------------------------------
# Penalty selection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LogisticPenaltyChoice:
    l2_penalty: float
    method: str
    inner_validation_dates: tuple[str, ...]
    inner_validation_rows: int
    grid_scores: tuple[tuple[float, float], ...] = field(default=())
    hit_grid_boundary: bool = False


def select_logistic_penalty(
    train_rows: Sequence[Mapping[str, object]],
    outcomes: Mapping[str, bool],
    *,
    grid: Sequence[float] = PENALTY_GRID,
    min_inner_rows: int = MIN_INNER_VALIDATION_ROWS,
    max_inner_folds: int = MAX_INNER_FOLDS,
) -> LogisticPenaltyChoice:
    """Same expanding-window design as the share model, scored on log loss.

    Log loss rather than accuracy, because accuracy is nearly uninformative
    here: in a ten-candidate two-seat ward, predicting "not elected" for
    everyone is already 80 per cent accurate. Log loss rewards a probability
    that is both correct and appropriately confident, which is what the brief
    asks to be calibrated.
    """

    by_day: dict[str, list[Mapping[str, object]]] = {}
    for row in train_rows:
        day = parse_election_date(str(row["election_date"])).date().isoformat()
        by_day.setdefault(day, []).append(row)

    days = sorted(by_day)
    qualifying = [
        day
        for position, day in enumerate(days)
        if position > 0 and len(by_day[day]) >= min_inner_rows
    ][-max_inner_folds:]

    if not qualifying:
        return LogisticPenaltyChoice(
            l2_penalty=DEFAULT_PENALTY,
            method="documented_default_no_inner_validation_day_large_enough",
            inner_validation_dates=(),
            inner_validation_rows=0,
        )

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
        y_train = np.array(
            [float(outcomes[str(row["candidate_contest_id"])]) for row in inner_train]
        )
        # A fold where nobody (or everybody) was elected carries no signal for
        # a binary fit and is skipped rather than allowed to dominate.
        if len(np.unique(y_train)) < 2:
            continue
        encoder = CandidateFeatureEncoder().fit(inner_train)
        folds.append(
            (
                encoder.transform(inner_train).matrix,
                y_train,
                encoder.transform(inner_test).matrix,
                np.array(
                    [float(outcomes[str(row["candidate_contest_id"])]) for row in inner_test]
                ),
            )
        )

    if not folds:
        return LogisticPenaltyChoice(
            l2_penalty=DEFAULT_PENALTY,
            method="documented_default_no_usable_inner_fold",
            inner_validation_dates=tuple(qualifying),
            inner_validation_rows=sum(len(by_day[day]) for day in qualifying),
        )

    scores: list[tuple[float, float]] = []
    for penalty in grid:
        fold_losses = []
        for x_tr, y_tr, x_te, y_te in folds:
            model = LogisticElectionModel(penalty).fit(x_tr, y_tr)
            fold_losses.append(log_loss(y_te, model.predict_proba(x_te)))
        scores.append((float(penalty), float(np.mean(fold_losses))))

    best = min(scores, key=lambda item: (item[1], -item[0]))
    return LogisticPenaltyChoice(
        l2_penalty=best[0],
        method="inner_expanding_window_validation_log_loss",
        inner_validation_dates=tuple(qualifying),
        inner_validation_rows=sum(len(by_day[day]) for day in qualifying),
        grid_scores=tuple(scores),
        hit_grid_boundary=best[0] in {min(grid), max(grid)},
    )


# --------------------------------------------------------------------------
# Scoring rules
# --------------------------------------------------------------------------


def brier_score(observed: Sequence[float], predicted: Sequence[float]) -> float:
    """Mean squared error of a probability. Lower is better; 0.25 is the score
    of always predicting one half."""

    y = np.asarray(observed, dtype=float)
    p = np.asarray(predicted, dtype=float)
    return float(np.mean((p - y) ** 2))


def log_loss(observed: Sequence[float], predicted: Sequence[float]) -> float:
    """Negative log-likelihood per row, with predictions clipped away from
    0 and 1 so a single confident miss cannot return infinity."""

    y = np.asarray(observed, dtype=float)
    p = np.clip(np.asarray(predicted, dtype=float), PROBABILITY_CLIP, 1.0 - PROBABILITY_CLIP)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def calibration_report(
    observed: Sequence[float],
    predicted: Sequence[float],
    *,
    bins: int = 10,
) -> dict[str, object]:
    """Reliability bins plus the two summary numbers worth quoting.

    ``expected_calibration_error`` is the row-weighted mean gap between
    predicted and observed frequency across bins. ``calibration_slope`` and
    ``calibration_intercept`` come from regressing the observed outcome on the
    predicted log-odds: a slope near 1 with intercept near 0 is a calibrated
    model, a slope below 1 means the model is over-confident, and above 1 that
    it is under-confident.

    Empty bins are reported as such rather than dropped, because a model that
    never predicts above 0.5 is itself a finding.
    """

    y = np.asarray(observed, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if len(y) == 0:
        return {"rows": 0, "bins": [], "expected_calibration_error": None}

    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, object]] = []
    weighted_gap = 0.0
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        mask = (p >= low) & (p < high) if index < bins - 1 else (p >= low) & (p <= high)
        count = int(mask.sum())
        entry: dict[str, object] = {
            "bin_lower": float(low),
            "bin_upper": float(high),
            "rows": count,
            "mean_predicted": float(p[mask].mean()) if count else None,
            "observed_frequency": float(y[mask].mean()) if count else None,
        }
        if count:
            weighted_gap += count * abs(float(p[mask].mean()) - float(y[mask].mean()))
        rows.append(entry)

    # Calibration slope and intercept by a small logistic refit of the outcome
    # on the predicted log-odds. One predictor, so no penalty is needed.
    slope: float | None = None
    intercept: float | None = None
    if len(np.unique(y)) == 2:
        z = _logit(p).reshape(-1, 1)
        refit = LogisticElectionModel(0.0).fit(z, y)
        intercept = float(refit.coefficients[0])
        slope = float(refit.coefficients[1])

    return {
        "rows": len(y),
        "bins": rows,
        "expected_calibration_error": weighted_gap / len(y),
        "mean_predicted": float(p.mean()),
        "observed_frequency": float(y.mean()),
        "calibration_slope": slope,
        "calibration_intercept": intercept,
        "probability_clip": PROBABILITY_CLIP,
    }


def probability_metrics(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Brier, log loss and calibration for both raw and seat-constrained
    probabilities, plus the reference scores that make them readable.

    ``base_rate_brier`` is the score of predicting the observed base rate for
    every candidate. Without it a Brier of 0.09 is unreadable: in a ten
    -candidate two-seat ward, always predicting 0.2 already scores 0.16.
    """

    rows = [
        row
        for row in records
        if row.get("predicted_election_probability") is not None
        and row.get("observed_elected") is not None
    ]
    if not rows:
        return {"rows": 0}

    y = np.array([float(bool(row["observed_elected"])) for row in rows])
    raw = np.array([float(row["predicted_election_probability_raw"]) for row in rows])
    constrained = np.array([float(row["predicted_election_probability"]) for row in rows])
    base_rate = float(y.mean())

    return {
        "rows": len(rows),
        "observed_election_rate": base_rate,
        "seat_constrained": {
            "brier_score": brier_score(y, constrained),
            "log_loss": log_loss(y, constrained),
            "calibration": calibration_report(y, constrained),
        },
        "raw_unconstrained": {
            "brier_score": brier_score(y, raw),
            "log_loss": log_loss(y, raw),
            "calibration": calibration_report(y, raw),
        },
        "base_rate_reference": {
            "brier_score": brier_score(y, np.full_like(y, base_rate)),
            "log_loss": log_loss(y, np.full_like(y, base_rate)),
        },
    }


# --------------------------------------------------------------------------
# One fold
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbabilityFoldResult:
    split_id: str
    split_role: str
    train_rows: int
    test_rows: int
    penalty: LogisticPenaltyChoice
    converged: bool
    iterations: int
    predictions: tuple[dict[str, object], ...]


def fit_and_predict_probability_fold(
    *,
    split_id: str,
    split_role: str,
    train_rows: Sequence[Mapping[str, object]],
    test_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    penalty: float | None = None,
) -> ProbabilityFoldResult:
    """Fit the probability model on one fold and predict its test rows.

    The order mirrors the share model: select the penalty inside training,
    fit the encoder on training only, fit, predict, then apply the seat
    constraint per contest. Seat counts are pre-election facts, so using them
    leaks nothing.
    """

    if not train_rows:
        raise ValueError(f"Split {split_id!r} has no training rows.")
    if not test_rows:
        raise ValueError(f"Split {split_id!r} has no test rows.")

    outcomes = {
        str(row["candidate_contest_id"]): targets[str(row["candidate_contest_id"])].get(
            "target_candidate_elected"
        )
        == "Yes"
        for row in list(train_rows) + list(test_rows)
    }

    choice = (
        select_logistic_penalty(train_rows, outcomes)
        if penalty is None
        else LogisticPenaltyChoice(
            l2_penalty=float(penalty),
            method="caller_supplied",
            inner_validation_dates=(),
            inner_validation_rows=0,
        )
    )

    encoder = CandidateFeatureEncoder().fit(train_rows)
    y_train = np.array(
        [float(outcomes[str(row["candidate_contest_id"])]) for row in train_rows]
    )
    model = LogisticElectionModel(choice.l2_penalty).fit(
        encoder.transform(train_rows).matrix, y_train
    )
    raw = model.predict_proba(encoder.transform(test_rows).matrix)
    raw_by_id = {
        str(row["candidate_contest_id"]): float(value)
        for row, value in zip(test_rows, raw)
    }

    constrained_by_id: dict[str, float] = {}
    status_by_id: dict[str, str] = {}
    for contest_rows in group_by_contest(test_rows).values():
        ids = [str(row["candidate_contest_id"]) for row in contest_rows]
        seats = contest_rows[0].get("analysis_number_of_seats")
        adjusted, status = calibrate_to_seats(
            [raw_by_id[row_id] for row_id in ids],
            None if seats is None else int(seats),
        )
        for row_id, value in zip(ids, adjusted):
            constrained_by_id[row_id] = float(value)
            status_by_id[row_id] = status

    records: list[dict[str, object]] = []
    for row in test_rows:
        row_id = str(row["candidate_contest_id"])
        election_id, division_id = contest_key(row)
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
                "predicted_election_probability_raw": raw_by_id[row_id],
                "predicted_election_probability": constrained_by_id[row_id],
                "seat_constraint_status": status_by_id[row_id],
                "observed_elected": outcomes[row_id],
            }
        )

    return ProbabilityFoldResult(
        split_id=split_id,
        split_role=split_role,
        train_rows=len(train_rows),
        test_rows=len(test_rows),
        penalty=choice,
        converged=model.converged,
        iterations=model.iterations,
        predictions=tuple(records),
    )
