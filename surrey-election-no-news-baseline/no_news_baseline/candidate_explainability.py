"""Explainability for the candidate-level architectures.

The brief asks for global feature importance, fold-level feature importance,
Reform UK-specific feature importance, coefficients for interpretable models,
example contest explanations, and "warnings where feature effects are
unstable". All of those are here. SHAP is not, because it is specified for
tree-based models and no tree architecture exists yet; a linear model's
contribution decomposition is exact rather than approximated, so there is
nothing for SHAP to add to Architectures A and C.

What "importance" means here
----------------------------
Both architectures are linear on a standardised design matrix, so a
coefficient is already on a common scale: it is the change in the target, in
multiples of the contest's equal split, caused by moving that feature one
training standard deviation. That makes coefficients directly comparable
between features without any further normalisation, which is why they are
reported as the importance measure rather than a permutation score.

Two things this module refuses to do
------------------------------------
**Report a single global importance.** A coefficient fitted once on one
training set says nothing about whether the effect is real. Every importance
here is computed per fold and reported with the spread across folds, because
a feature whose coefficient changes sign between folds is not an effect - it
is noise that happened to fit. ``unstable_features`` names those explicitly.

**Present a contribution as a cause.** The brief is explicit: "Do not present
correlations as proof of causation." A contribution breakdown says which
features moved this prediction, not why a voter behaved as they did. Every
exported structure carries that wording so it travels with the numbers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from no_news_baseline.candidate_features import CandidateFeatureEncoder, target_vector
from no_news_baseline.candidate_hierarchical_model import (
    PartialPoolingShareModel,
    party_column_mask,
    select_hierarchical_penalties,
)
from no_news_baseline.candidate_share_model import (
    RidgeShareModel,
    select_penalty,
    to_relative_share,
)


INTERPRETATION_WARNING = (
    "These are model coefficients and contributions, not causal effects. They "
    "describe how this fitted model combines pre-election information; they do "
    "not establish why any voter behaved as they did."
)

# A coefficient that changes sign between folds is not a small effect measured
# imprecisely - it is an effect whose direction the data does not determine.
# Reported separately from merely large-variance features.
SIGN_FLIP = "sign_changes_between_folds"
HIGH_SPREAD = "spread_exceeds_mean_magnitude"


@dataclass(frozen=True)
class FoldCoefficients:
    """One fold's fitted coefficients, keyed by encoded column name."""

    split_id: str
    train_rows: int
    train_reform_rows: int
    coefficients: dict[str, float]
    intercept: float


def fit_fold_coefficients(
    *,
    split_id: str,
    train_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    architecture: str = "ridge",
) -> FoldCoefficients:
    """Refit one fold and return its coefficients by column name.

    Deliberately refits rather than accepting a fitted model, so that the
    coefficients reported are provably the ones produced by this fold's own
    training rows under this fold's own selected penalty. Accepting a model
    from elsewhere would make it possible to report coefficients from a fit
    that saw different data.
    """

    encoder = CandidateFeatureEncoder().fit(train_rows)
    design = encoder.transform(train_rows)
    counts = [int(row["candidate_count_in_contest"]) for row in train_rows]
    y = to_relative_share(target_vector(train_rows, targets), counts)

    if architecture == "ridge":
        penalty = select_penalty(train_rows, targets)
        model = RidgeShareModel(penalty.l2_penalty).fit(design.matrix, y)
        coefficients, intercept = model.coefficients, model.intercept
    elif architecture == "partial_pooling":
        choice = select_hierarchical_penalties(train_rows, targets)
        model = PartialPoolingShareModel(
            fixed_penalty=choice.fixed_penalty, party_penalty=choice.party_penalty
        ).fit(design.matrix, y, party_mask=party_column_mask(design.column_names))
        coefficients, intercept = model.coefficients, model.intercept
    else:
        raise ValueError(f"Unknown architecture: {architecture!r}")

    return FoldCoefficients(
        split_id=split_id,
        train_rows=len(train_rows),
        train_reform_rows=sum(1 for row in train_rows if row.get("is_reform_uk")),
        coefficients=dict(zip(design.column_names, (float(v) for v in coefficients))),
        intercept=float(intercept),
    )


def summarise_across_folds(
    folds: Sequence[FoldCoefficients],
) -> tuple[dict[str, object], ...]:
    """Mean, spread and stability for every feature across folds.

    A feature absent from a fold - a party level that fold's training rows
    never contained - is recorded as absent rather than counted as zero.
    Treating "this fold could not estimate it" as "this fold estimated it at
    zero" would drag the mean toward zero and make a rare party look reliably
    unimportant.
    """

    names: set[str] = set()
    for fold in folds:
        names |= set(fold.coefficients)

    rows: list[dict[str, object]] = []
    for name in sorted(names):
        values = [
            fold.coefficients[name] for fold in folds if name in fold.coefficients
        ]
        if not values:
            continue
        array = np.array(values, dtype=float)
        mean = float(array.mean())
        spread = float(array.std())
        signs = {int(np.sign(v)) for v in array if v != 0.0}

        flags: list[str] = []
        if len(signs) > 1:
            flags.append(SIGN_FLIP)
        if abs(mean) > 0 and spread > abs(mean):
            flags.append(HIGH_SPREAD)

        rows.append(
            {
                "feature": name,
                "folds_present": len(values),
                "folds_absent": len(folds) - len(values),
                "mean_coefficient": mean,
                "coefficient_sd": spread,
                "min_coefficient": float(array.min()),
                "max_coefficient": float(array.max()),
                "mean_absolute_coefficient": float(np.abs(array).mean()),
                "stability_flags": flags,
                "stable": not flags,
            }
        )

    # Ranked by mean absolute coefficient: the question "which features move
    # the prediction most" is about magnitude, not direction.
    return tuple(
        sorted(rows, key=lambda row: -float(row["mean_absolute_coefficient"]))
    )


def unstable_features(
    summary: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """The brief's "warnings where feature effects are unstable"."""

    return tuple(row for row in summary if row["stability_flags"])


# --------------------------------------------------------------------------
# Row-level contributions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RowExplanation:
    """Why this model produced this prediction for this candidate."""

    candidate_contest_id: str
    election_id: str
    division_name: str
    standard_party_name: str
    is_reform_uk: bool
    predicted_relative_share: float
    intercept: float
    contributions: tuple[tuple[str, float], ...]
    interpretation_warning: str = INTERPRETATION_WARNING


def explain_rows(
    *,
    rows: Sequence[Mapping[str, object]],
    encoder: CandidateFeatureEncoder,
    coefficients: np.ndarray,
    intercept: float,
    design_means: np.ndarray,
    top_n: int = 12,
) -> tuple[RowExplanation, ...]:
    """Exact per-feature contributions for a linear model.

    For a centred linear model the prediction decomposes without residue:

        prediction = intercept + sum over features of (x - x_mean) * coefficient

    so the contributions returned here add up to the prediction exactly. That
    is why no approximation method is needed for Architectures A and C: the
    decomposition is the model, not an estimate of it.

    Only the ``top_n`` largest-magnitude contributions are returned per row,
    because a 107-column breakdown is unreadable; the intercept and the total
    are both carried so a reader can see how much the shown terms account for.
    """

    design = encoder.transform(rows)
    centred = design.matrix - design_means
    contributions = centred * coefficients

    explanations: list[RowExplanation] = []
    for position, row in enumerate(rows):
        values = contributions[position]
        order = np.argsort(-np.abs(values))[:top_n]
        explanations.append(
            RowExplanation(
                candidate_contest_id=str(row["candidate_contest_id"]),
                election_id=str(row["election_id"]),
                division_name=str(row["division_name"]),
                standard_party_name=str(row["standard_party_name"]),
                is_reform_uk=bool(row.get("is_reform_uk")),
                predicted_relative_share=float(values.sum() + intercept),
                intercept=float(intercept),
                contributions=tuple(
                    (design.column_names[index], float(values[index]))
                    for index in order
                ),
            )
        )
    return tuple(explanations)


def party_contribution_profile(
    explanations: Sequence[RowExplanation],
    *,
    party: str | None = None,
    reform_only: bool = False,
) -> dict[str, object]:
    """Average contribution per feature across a party's rows.

    The brief requires Reform UK-specific feature importance. A coefficient is
    the same for every row, so a party-specific *coefficient* does not exist in
    a linear model without interactions; what does exist, and what is asked
    for, is which features actually move that party's predictions. Averaging
    contributions answers exactly that: a large coefficient on a feature this
    party never has still contributes nothing to its predictions.
    """

    selected = [
        row
        for row in explanations
        if (row.is_reform_uk if reform_only else party is None or row.standard_party_name == party)
    ]
    if not selected:
        return {"rows": 0, "mean_contributions": [], "interpretation_warning": INTERPRETATION_WARNING}

    totals: dict[str, list[float]] = {}
    for row in selected:
        for name, value in row.contributions:
            totals.setdefault(name, []).append(value)

    profile = sorted(
        (
            {
                "feature": name,
                "rows_with_contribution": len(values),
                "mean_contribution": float(np.mean(values)),
                "mean_absolute_contribution": float(np.mean(np.abs(values))),
            }
            for name, values in totals.items()
        ),
        key=lambda item: -float(item["mean_absolute_contribution"]),
    )
    return {
        "rows": len(selected),
        "mean_predicted_relative_share": float(
            np.mean([row.predicted_relative_share for row in selected])
        ),
        "mean_contributions": profile,
        "interpretation_warning": INTERPRETATION_WARNING,
    }
