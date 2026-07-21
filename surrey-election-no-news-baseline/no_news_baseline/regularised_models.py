"""First fitted no-news model: fold-wise ridge regression on fundamentals.

Purpose
-------
Every benchmark built so far (``persistence_benchmark``, ``naive_benchmarks``)
is parameter-free. This module introduces the first model that actually
*learns* coefficients from history, so that the supervisor's comparison -
does pre-election news improve on what previous results already predict -
has a fitted no-news competitor, not only carry-forward rules.

It is deliberately an interpretable linear model over a small, pre-declared
set of electoral fundamentals, echoing Stoetzer, Neunhoeffer, Gschwend,
Munzert & Sternberg (2025)'s "fundamentals-only" comparator (previous vote
share, incumbency, new-party indicator). Hanretty (2021) uses lasso for
variable *selection*; that is intentionally NOT reproduced here, because a
correct lasso needs an iterative solver that is hard to verify by hand.
Ridge (L2) regression has a closed form, is numerically stable, and keeps
this first fitted model easy to audit. Lasso-style selection over a larger
candidate set is documented future work, not a claim made here.

Leakage discipline
------------------
The model is only ever fitted on a ``TemporalFold``'s training rows, which
``temporal_validation.py`` guarantees come strictly from earlier elections.
Feature standardisation uses training-row means and standard deviations
only; the held-out election is transformed with those fixed values and never
contributes to them. This mirrors the fold-only-imputation rule already
stated in ``docs/data_contract.md``.

Cohort
------
Fitting and scoring are restricted to the primary single-member lagged-share
cohort (``eligible_primary_single_member_party_share``) - the same rows
``persistence_benchmark`` scores for share - so the fitted model is compared
with the benchmarks on identical common support, never on a conveniently
easier subset.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from no_news_baseline.persistence_benchmark import PRIMARY_COHORT_STATUS


# The declared predictor set. Each entry is (feature_key, kind). "numeric"
# columns are used as-is; "boolean"/"yes_no" columns are mapped to 0/1. This
# list is fixed in code, not inferred from the data, so the model cannot
# silently pick up a newly added column - or a leaked outcome column - just
# because it appears in a future release.
#
# The set mirrors Stoetzer et al. (2025)'s fundamentals: prior strength
# (previous_party_vote_share), the local context it sits in (previous
# turnout and electorate), incumbency, and a new-party signal
# (party_previously_contested / first_appearance_of_party_in_area).
PREDICTOR_SPEC: tuple[tuple[str, str], ...] = (
    ("previous_party_vote_share", "numeric"),
    ("analysis_previous_turnout", "numeric"),
    ("previous_electorate", "numeric"),
    ("party_was_previous_winner", "boolean"),
    ("incumbent_candidate_any_yes_no", "yes_no"),
    ("incumbent_party_yes_no", "yes_no"),
    ("party_previously_contested", "boolean"),
    ("first_appearance_of_party_in_area", "boolean"),
)

BENCHMARK_ID = "ridge_fundamentals_v1"


class RidgeFundamentalsModel:
    """A ridge-regression fit over the declared fundamentals of one fold.

    The model stores the feature standardisation fitted on the training rows
    alongside the coefficients, so ``predict`` can only ever apply the exact
    transformation learned at fit time.
    """

    def __init__(self, l2_penalty: float = 1.0) -> None:
        # A single non-negative regularisation strength. It is a fixed
        # hyperparameter here rather than tuned, to keep this first fitted
        # model transparent; fold-internal tuning is future work.
        if l2_penalty < 0:
            raise ValueError("The ridge L2 penalty must be non-negative.")
        self._l2_penalty = l2_penalty
        self._feature_means: np.ndarray | None = None
        self._feature_stds: np.ndarray | None = None
        self._coefficients: np.ndarray | None = None
        self._intercept: float | None = None

    def fit(
        self,
        rows: Sequence[Mapping[str, object]],
        realised_shares: Sequence[float],
    ) -> "RidgeFundamentalsModel":
        """Fit standardisation and ridge coefficients on training rows only.

        ``realised_shares`` are the training elections' own party vote shares,
        supplied separately because they live in the target table rather than
        the feature table (the feature/target split is a leakage control, see
        ``docs/data_contract.md``). They are past, already-realised outcomes of
        strictly-earlier elections, so using them to fit is not leakage - it is
        exactly the historical evidence the model is allowed to learn from.
        """

        if not rows:
            raise ValueError("Cannot fit the ridge model on an empty training set.")
        if len(rows) != len(realised_shares):
            raise ValueError("Training rows and realised shares must align one-to-one.")
        design = _build_design_matrix(rows)
        target = np.array([float(share) for share in realised_shares], dtype=float)

        # Standardise each column to mean 0, SD 1 using ONLY these training
        # rows. A zero-variance column (e.g. a predictor constant across the
        # whole training fold) is left unscaled to avoid division by zero;
        # after centering it is all zeros and contributes nothing, which is
        # the correct behaviour for a feature with no training variation.
        means = design.mean(axis=0)
        stds = design.std(axis=0)
        safe_stds = np.where(stds == 0.0, 1.0, stds)
        standardised = (design - means) / safe_stds

        # Center the target so the intercept is handled separately and is NOT
        # shrunk by the L2 penalty - penalising the intercept would bias every
        # prediction toward zero share, which is not what regularisation is
        # meant to control.
        target_mean = float(target.mean())
        centered_target = target - target_mean

        # Closed-form ridge solution: w = (X'X + lambda I)^-1 X'y, computed by
        # solving the linear system rather than inverting explicitly for
        # numerical stability.
        n_features = standardised.shape[1]
        gram = standardised.T @ standardised + self._l2_penalty * np.eye(n_features)
        coefficients = np.linalg.solve(gram, standardised.T @ centered_target)

        self._feature_means = means
        self._feature_stds = safe_stds
        self._coefficients = coefficients
        self._intercept = target_mean
        return self

    def predict_one(self, row: Mapping[str, object]) -> float:
        """Predict a party vote share for a single row, clipped to [0, 100]."""

        if self._coefficients is None:
            raise ValueError("The ridge model must be fitted before predicting.")
        features = _row_to_vector(row)
        standardised = (features - self._feature_means) / self._feature_stds
        raw = float(standardised @ self._coefficients + self._intercept)
        # A vote share is bounded; an unconstrained linear model can predict
        # slightly outside [0, 100], so the prediction is clipped. This is a
        # presentation bound on the output, not a change to the fitted model.
        return min(100.0, max(0.0, raw))


def evaluate_ridge_over_folds(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
    l2_penalty: float = 1.0,
) -> tuple[dict[str, object], ...]:
    """Fit and score the ridge model on each temporal fold's held-out election.

    Imported lazily from ``temporal_validation`` to avoid a circular import at
    module load. Returns one prediction row per scored test-cohort contest,
    in the shape ``benchmark_metrics`` consumes, so the fitted model is scored
    by exactly the same MAE/RMSE code as the parameter-free benchmarks.
    """

    from no_news_baseline.temporal_validation import iter_temporal_folds

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = {str(row["party_contest_id"]): row for row in target_rows}

    predictions: list[dict[str, object]] = []
    for fold in iter_temporal_folds(feature_rows, target_rows):
        train_cohort = [row for row in fold.train_features if _in_share_cohort(row)]
        test_cohort = [row for row in fold.test_features if _in_share_cohort(row)]
        # A fold with no usable training rows (nothing in the share cohort yet)
        # cannot fit a model; its test rows are left unscored rather than
        # predicted from an unfitted model.
        if not train_cohort or not test_cohort:
            continue
        train_shares = [
            _required_share_from_target(target_by_id[str(row["party_contest_id"])])
            for row in train_cohort
        ]
        # Provenance recorded per prediction: exactly which earlier elections
        # the fitted model saw. Kept so a reviewer can confirm the held-out
        # election is never among them, without re-deriving the fold split.
        train_election_ids = tuple(
            sorted({str(row["election_id"]) for row in train_cohort})
        )
        model = RidgeFundamentalsModel(l2_penalty=l2_penalty).fit(train_cohort, train_shares)
        for row in test_cohort:
            target = target_by_id[str(row["party_contest_id"])]
            predicted = model.predict_one(row)
            actual = _required_share_from_target(target)
            error = predicted - actual
            predictions.append(
                {
                    "party_contest_id": row["party_contest_id"],
                    "election_id": row["election_id"],
                    "election_year": row["election_year"],
                    "election_type": row["election_type"],
                    "division_id": row["division_id"],
                    "division_name": row["division_name"],
                    "standard_party_name": row["standard_party_name"],
                    "benchmark_id": BENCHMARK_ID,
                    "predicted_party_vote_share": predicted,
                    "actual_party_vote_share": actual,
                    "share_error": error,
                    "absolute_share_error": abs(error),
                    "squared_share_error": error**2,
                    # This model does not emit a winner decision; winner
                    # comparison stays with the benchmarks that define one.
                    "predicted_party_elected": "Unknown",
                    "actual_party_elected": target["target_party_elected"],
                    "winner_prediction_correct": None,
                    "train_election_ids": train_election_ids,
                    "train_cohort_rows": len(train_cohort),
                }
            )
    return tuple(predictions)


def _in_share_cohort(row: Mapping[str, object]) -> bool:
    return row.get("baseline_eligibility") == PRIMARY_COHORT_STATUS


def _build_design_matrix(rows: Sequence[Mapping[str, object]]) -> np.ndarray:
    return np.array([_row_to_vector(row) for row in rows], dtype=float)


def _row_to_vector(row: Mapping[str, object]) -> np.ndarray:
    """Turn one feature row into the declared numeric predictor vector."""

    values: list[float] = []
    for key, kind in PREDICTOR_SPEC:
        value = row.get(key)
        if kind == "numeric":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"Predictor {key!r} is not numeric on a cohort row.")
            values.append(float(value))
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"Predictor {key!r} is not boolean on a cohort row.")
            values.append(1.0 if value else 0.0)
        elif kind == "yes_no":
            # Only an explicit "Yes"/"No" is accepted; an "Unknown" would be an
            # unresolved value that must not be silently read as False.
            if value not in ("Yes", "No"):
                raise ValueError(f"Predictor {key!r} is not a resolved Yes/No on a cohort row.")
            values.append(1.0 if value == "Yes" else 0.0)
        else:  # pragma: no cover - guards against a malformed PREDICTOR_SPEC
            raise ValueError(f"Unknown predictor kind {kind!r}.")
    return np.array(values, dtype=float)


def _required_share_from_target(target: Mapping[str, object]) -> float:
    value = target.get("target_party_vote_share")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("A cohort target row has no numeric target_party_vote_share.")
    return float(value)
