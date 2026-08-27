"""Architecture C: a group-aware model with partial pooling on party effects.

The brief's Architecture C asks for a model that recognises the nested
structure - candidates within contests, parties across elections - and offers
an explicit way out of a disproportionate implementation:

    "If a fully Bayesian implementation is disproportionate, implement a
    practical partial-pooling approximation and document it."

This module takes that route. A full hierarchical Dirichlet model sampled
with NUTS was specified but never implemented (its specification and
identifiability audit are retired to Git history); running that inside 19
chronological folds, each with its own hyperparameter search, is
disproportionate for a first comparison and would make the architecture
comparison rest on sampler diagnostics rather than on predictive accuracy.
What is implemented instead is the part that matters for this project's
binding constraint, in closed form.

Why partial pooling is the point, not a nicety
----------------------------------------------
Architecture A has 11 Reform UK training rows before 2026 — six from 2021 at
one to four per cent and five from 2025 by-elections — and it is the only
party where the fitted model does
worse than an equal split - by 27 per cent out of fold and 25 per cent on the
holdout. The brief names the remedy directly: "Because genuine Reform UK
history before 2026 is limited ... use regularisation or partial pooling."

A single ridge penalty shrinks every coefficient by the same amount regardless
of how much evidence stands behind it. Partial pooling makes the shrinkage
depend on the evidence: a party observed 400 times keeps most of its own
estimate, a party observed 11 times is pulled most of the way back to the
all-party mean, and no threshold has to be chosen for when a party is "too
rare to model".

How it is done in closed form
-----------------------------
For a one-hot party indicator, the ridge estimate of party p's intercept is

    alpha_p_hat = (n_p / (n_p + lambda_party)) * (party p's mean residual)

which is exactly the posterior mean of a normal hierarchical model with
alpha_p ~ Normal(0, sigma_party^2) and lambda_party = sigma_eps^2 /
sigma_party^2. So a ridge penalty applied *only* to the party columns, with
its own strength, is a partial-pooling estimator rather than an approximation
of one. The shrinkage factor n_p / (n_p + lambda_party) is reported per party,
because it is the interpretable quantity: it says what fraction of a party's
effect came from its own data rather than from the pool.

The model therefore splits the design into two blocks with two penalties:

* party-identity columns, penalised at ``party_penalty``;
* every other column, penalised at ``fixed_penalty``;

and both are chosen together on the same inner expanding-window validation the
other architectures use, so no fold's test rows influence either.

What is deliberately not modelled
---------------------------------
**Election-cycle effects.** The retired hierarchical specification included
a cycle effect gamma_e per election. It is omitted here because it cannot help a forecast:
the target election never appears in training, so its cycle effect would be
estimated as the pooled mean, which is zero, for every future contest. A cycle
effect improves in-sample fit and contributes nothing out of sample. Saying so
is more useful than including a term that is structurally zero where it is
needed.

**Contest-level random effects.** Same argument, more strongly: a held-out
contest has no observations of its own.
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
from no_news_baseline.candidate_share_model import (
    TARGET_SCALE,
    to_relative_share,
    to_vote_share,
)
from no_news_baseline.election_dates import parse_election_date


MODEL_ID = "partial_pooling_candidate_share_v1"

# Columns the encoder produces for party identity. These are the ones given
# their own, separately-tuned shrinkage; everything else keeps the ordinary
# penalty. Matching by prefix rather than by an explicit list means a future
# encoder change cannot silently move a party column into the fixed block.
PARTY_COLUMN_PREFIXES = ("standard_party_name__", "party_category__")

# Two grids, searched jointly. The party grid reaches higher because heavy
# pooling is the expected answer for a 40-party ballot seen 1,129 times.
FIXED_PENALTY_GRID: tuple[float, ...] = (1.0, 10.0, 100.0, 1000.0, 10_000.0)
PARTY_PENALTY_GRID: tuple[float, ...] = (1.0, 10.0, 100.0, 1000.0, 10_000.0)

DEFAULT_FIXED_PENALTY = 100.0
DEFAULT_PARTY_PENALTY = 100.0
MIN_INNER_VALIDATION_ROWS = 20
MAX_INNER_FOLDS = 3


def party_column_mask(column_names: Sequence[str]) -> np.ndarray:
    """True for columns carrying party identity."""

    return np.array(
        [name.startswith(PARTY_COLUMN_PREFIXES) for name in column_names], dtype=bool
    )


class PartialPoolingShareModel:
    """Ridge with a separate penalty on the party-identity block.

    Equivalent to a normal hierarchical model on party intercepts, fitted by
    its closed-form posterior mean rather than by sampling. Both sides are
    centred before solving, so the intercept is the training mean and is not
    shrunk.
    """

    def __init__(
        self,
        *,
        fixed_penalty: float = DEFAULT_FIXED_PENALTY,
        party_penalty: float = DEFAULT_PARTY_PENALTY,
    ) -> None:
        if fixed_penalty < 0 or party_penalty < 0:
            raise ValueError("Penalties must be non-negative.")
        self._fixed_penalty = float(fixed_penalty)
        self._party_penalty = float(party_penalty)
        self._coefficients: np.ndarray | None = None
        self._intercept: float | None = None
        self._design_means: np.ndarray | None = None
        self._party_mask: np.ndarray | None = None

    def fit(
        self,
        design: np.ndarray,
        target: np.ndarray,
        *,
        party_mask: np.ndarray,
    ) -> "PartialPoolingShareModel":
        if design.shape[0] != target.shape[0]:
            raise ValueError("Design matrix and target must align one-to-one.")
        if design.shape[0] == 0:
            raise ValueError("Cannot fit on an empty training set.")
        if party_mask.shape[0] != design.shape[1]:
            raise ValueError("The party mask must have one entry per column.")

        design_means = design.mean(axis=0)
        centered_design = design - design_means
        target_mean = float(target.mean())
        centered_target = target - target_mean

        # A diagonal penalty with two values: this is the whole difference
        # from Architecture A. Party columns are shrunk toward the pooled
        # all-party mean at their own rate; everything else keeps the ordinary
        # ridge penalty.
        penalties = np.where(party_mask, self._party_penalty, self._fixed_penalty)
        gram = centered_design.T @ centered_design + np.diag(penalties)
        self._coefficients = np.linalg.solve(gram, centered_design.T @ centered_target)
        self._design_means = design_means
        self._intercept = target_mean
        self._party_mask = party_mask.copy()
        return self

    def predict(self, design: np.ndarray) -> np.ndarray:
        if (
            self._coefficients is None
            or self._intercept is None
            or self._design_means is None
        ):
            raise ValueError("The model must be fitted before predicting.")
        return (design - self._design_means) @ self._coefficients + self._intercept

    def shrinkage_by_party(
        self, design: np.ndarray, column_names: Sequence[str]
    ) -> dict[str, dict[str, float]]:
        """How much of each party's effect came from its own data.

        The interpretable output of partial pooling. For a one-hot column with
        ``n_p`` training rows the shrinkage factor is

            n_p / (n_p + party_penalty)

        which is the weight the estimate places on that party's own evidence;
        one minus it is the weight placed on the pool. Reporting this makes the
        model's treatment of a rare party inspectable rather than implicit.
        """

        if self._party_mask is None:
            raise ValueError("The model has not been fitted.")
        report: dict[str, dict[str, float]] = {}
        for position, name in enumerate(column_names):
            if not self._party_mask[position]:
                continue
            # The design arrives standardised, so a one-hot column's "off"
            # rows sit at -mean/sd rather than at zero and counting non-zeros
            # would return every row. Standardisation is monotone, so the
            # "on" rows are those at the larger of the column's two values.
            column = design[:, position]
            distinct = np.unique(column)
            # A column with no training variation - a level the encoder
            # created but no training row activates, such as unseen_level -
            # is all zeros after centring and contributes nothing to the fit,
            # so it carries no evidence of its own either way.
            observations = (
                0
                if len(distinct) == 1
                else int(np.count_nonzero(column == distinct[-1]))
            )
            weight = observations / (observations + self._party_penalty)
            report[name] = {
                "training_rows_with_column_active": observations,
                "own_data_weight": float(weight),
                "pooled_weight": float(1.0 - weight),
                "coefficient": float(self._coefficients[position]),
            }
        return dict(sorted(report.items()))

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

    @property
    def penalties(self) -> tuple[float, float]:
        return self._fixed_penalty, self._party_penalty


# --------------------------------------------------------------------------
# Joint penalty selection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HierarchicalPenaltyChoice:
    fixed_penalty: float
    party_penalty: float
    method: str
    inner_validation_dates: tuple[str, ...]
    inner_validation_rows: int
    grid_scores: tuple[tuple[float, float, float], ...] = field(default=())
    hit_grid_boundary: bool = False


def select_hierarchical_penalties(
    train_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    *,
    fixed_grid: Sequence[float] = FIXED_PENALTY_GRID,
    party_grid: Sequence[float] = PARTY_PENALTY_GRID,
    min_inner_rows: int = MIN_INNER_VALIDATION_ROWS,
    max_inner_folds: int = MAX_INNER_FOLDS,
) -> HierarchicalPenaltyChoice:
    """Search both penalties on the same inner expanding-window validation.

    Jointly rather than one at a time, because the two trade off: heavier
    pooling of party effects leaves more of the signal to be carried by the
    historical covariates, and the best fixed penalty depends on how much of
    that work it is being asked to do.
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
        return HierarchicalPenaltyChoice(
            fixed_penalty=DEFAULT_FIXED_PENALTY,
            party_penalty=DEFAULT_PARTY_PENALTY,
            method="documented_default_no_inner_validation_day_large_enough",
            inner_validation_dates=(),
            inner_validation_rows=0,
        )

    folds = []
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
        design_train = encoder.transform(inner_train)
        folds.append(
            (
                design_train.matrix,
                to_relative_share(
                    target_vector(inner_train, targets),
                    [int(row["candidate_count_in_contest"]) for row in inner_train],
                ),
                encoder.transform(inner_test).matrix,
                to_relative_share(
                    target_vector(inner_test, targets),
                    [int(row["candidate_count_in_contest"]) for row in inner_test],
                ),
                party_column_mask(design_train.column_names),
            )
        )

    if not folds:
        return HierarchicalPenaltyChoice(
            fixed_penalty=DEFAULT_FIXED_PENALTY,
            party_penalty=DEFAULT_PARTY_PENALTY,
            method="documented_default_no_usable_inner_fold",
            inner_validation_dates=tuple(qualifying),
            inner_validation_rows=sum(len(by_day[day]) for day in qualifying),
        )

    scores: list[tuple[float, float, float]] = []
    for fixed in fixed_grid:
        for party in party_grid:
            errors = [
                float(
                    np.mean(
                        np.abs(
                            PartialPoolingShareModel(
                                fixed_penalty=fixed, party_penalty=party
                            )
                            .fit(x_tr, y_tr, party_mask=mask)
                            .predict(x_te)
                            - y_te
                        )
                    )
                )
                for x_tr, y_tr, x_te, y_te, mask in folds
            ]
            scores.append((float(fixed), float(party), float(np.mean(errors))))

    # Ties break toward heavier penalties, i.e. the simpler model.
    best = min(scores, key=lambda item: (item[2], -item[0], -item[1]))
    return HierarchicalPenaltyChoice(
        fixed_penalty=best[0],
        party_penalty=best[1],
        method="inner_expanding_window_validation_joint_grid",
        inner_validation_dates=tuple(qualifying),
        inner_validation_rows=sum(len(by_day[day]) for day in qualifying),
        grid_scores=tuple(scores),
        hit_grid_boundary=(
            best[0] in {min(fixed_grid), max(fixed_grid)}
            or best[1] in {min(party_grid), max(party_grid)}
        ),
    )


# --------------------------------------------------------------------------
# One fold
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HierarchicalFoldResult:
    split_id: str
    split_role: str
    train_rows: int
    test_rows: int
    train_reform_rows: int
    test_reform_rows: int
    penalty: HierarchicalPenaltyChoice
    shrinkage: dict[str, dict[str, float]]
    predictions: tuple[dict[str, object], ...]


def fit_and_predict_hierarchical_fold(
    *,
    split_id: str,
    split_role: str,
    train_rows: Sequence[Mapping[str, object]],
    test_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    penalties: tuple[float, float] | None = None,
) -> HierarchicalFoldResult:
    """Same fold order as Architecture A, so the two are directly comparable.

    Identical rows, identical encoder, identical target scale, identical
    contest normalisation and seat allocation. The only difference is how the
    party columns are penalised, which is what makes a comparison between the
    two architectures a statement about partial pooling rather than about four
    other things that also changed.
    """

    if not train_rows:
        raise ValueError(f"Split {split_id!r} has no training rows.")
    if not test_rows:
        raise ValueError(f"Split {split_id!r} has no test rows.")

    choice = (
        select_hierarchical_penalties(train_rows, targets)
        if penalties is None
        else HierarchicalPenaltyChoice(
            fixed_penalty=float(penalties[0]),
            party_penalty=float(penalties[1]),
            method="caller_supplied",
            inner_validation_dates=(),
            inner_validation_rows=0,
        )
    )

    encoder = CandidateFeatureEncoder().fit(train_rows)
    design_train = encoder.transform(train_rows)
    design_test = encoder.transform(test_rows)
    mask = party_column_mask(design_train.column_names)

    train_counts = [int(row["candidate_count_in_contest"]) for row in train_rows]
    test_counts = [int(row["candidate_count_in_contest"]) for row in test_rows]
    y_train = to_relative_share(target_vector(train_rows, targets), train_counts)

    model = PartialPoolingShareModel(
        fixed_penalty=choice.fixed_penalty, party_penalty=choice.party_penalty
    ).fit(design_train.matrix, y_train, party_mask=mask)

    predicted_relative = model.predict(design_test.matrix)
    predicted_share_raw = to_vote_share(predicted_relative, test_counts)

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
    for contest_rows in group_by_contest(test_rows).values():
        payload = [
            {
                "candidate_contest_id": str(row["candidate_contest_id"]),
                "predicted_candidate_vote_share": raw_by_id[str(row["candidate_contest_id"])],
            }
            for row in contest_rows
        ]
        for item in normalise_within_contest(payload):
            normalised_by_id[item.candidate_contest_id] = item.normalised_prediction
            normalisation_status[item.candidate_contest_id] = item.normalisation_status
        seats = contest_rows[0].get("analysis_number_of_seats")
        for item in allocate_contest(
            [
                {
                    "candidate_contest_id": str(row["candidate_contest_id"]),
                    "predicted_candidate_vote_share": normalised_by_id[
                        str(row["candidate_contest_id"])
                    ],
                }
                for row in contest_rows
            ],
            seats=None if seats is None else int(seats),
        ):
            allocation_by_id[item.candidate_contest_id] = item

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

    return HierarchicalFoldResult(
        split_id=split_id,
        split_role=split_role,
        train_rows=len(train_rows),
        test_rows=len(test_rows),
        train_reform_rows=sum(1 for row in train_rows if row.get("is_reform_uk")),
        test_reform_rows=sum(1 for row in test_rows if row.get("is_reform_uk")),
        penalty=choice,
        shrinkage=model.shrinkage_by_party(
            design_train.matrix, design_train.column_names
        ),
        predictions=tuple(records),
    )


TARGET_TRANSFORMATION = TARGET_SCALE
