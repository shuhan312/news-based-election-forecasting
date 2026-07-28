"""Compare the three architectures and select one, with the reason recorded.

The brief's selection criteria, in its own order:

    Reform UK vote-share MAE and RMSE. Reform UK ranking and elected-status
    accuracy. Overall candidate vote-share accuracy. Overall winner and
    seat-allocation accuracy. Calibration. Stability across chronological
    folds. Simplicity and explainability as a tie-breaker.

and the constraint that governs all of them:

    Do not select a complex model based on a negligible improvement.

That last sentence is the reason this module exists rather than an argmax over
a metric column. Left to itself, an argmax will always name the best number,
however small its lead and however unstable across folds; the brief asks for
the opposite default. So selection here has to clear two gates before a more
complex architecture can win, and the gates are declared before any number is
computed.

Gate 1 - material improvement
-----------------------------
A challenger must beat the incumbent by more than ``MATERIAL_IMPROVEMENT`` in
relative terms on the primary criterion. A 1 per cent MAE advantage on 838
holdout rows is not evidence of a better model; it is the noise floor of one
election.

Gate 2 - stability
------------------
A challenger must not lose on more than ``MAX_ADVERSE_FOLDS`` of the
development folds. The brief asks for "stability across chronological folds"
explicitly, and this project has already seen why: Architecture A wins the
2017 fold and loses the 2025 by-election folds badly, so a single-fold
comparison would have selected on the fold that happened to be looked at.

Complexity order
----------------
Simplicity is the tie-breaker, so the architectures are ranked by it and the
simplest is the incumbent that others must displace. Ridge is a closed-form
linear model; partial pooling is the same fit with one extra penalty; boosted
trees are several hundred trees whose behaviour can only be inspected through
importance and partial dependence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from no_news_baseline.candidate_metrics import (
    equal_split_reference,
    seat_metrics,
    share_metrics,
)


# Simplest first. The first entry is the incumbent; later entries must clear
# both gates to displace it.
COMPLEXITY_ORDER: tuple[str, ...] = (
    "A_regularised_linear",
    "C_partial_pooling",
    "B_gradient_boosted_trees",
)

# A challenger must improve the primary criterion by more than this fraction.
# Set from the holdout's own scale: 838 rows with a mean observed share near
# 10 per cent cannot distinguish models a few hundredths of a point apart.
MATERIAL_IMPROVEMENT = 0.05

# How many development folds a challenger may lose on and still be selected.
MAX_ADVERSE_FOLDS = 1

# A challenger with no shared development folds cannot demonstrate stability,
# and a gate that passes when there is nothing to check is not a gate. Such a
# challenger is refused rather than waved through, which is the same default
# that makes the simplest architecture the incumbent.
MIN_DEVELOPMENT_FOLDS = 2

# The brief names Reform UK vote-share MAE first among the selection criteria,
# and Reform UK is the study party, so it is the primary criterion here.
PRIMARY_CRITERION = "reform_vote_share_mae"


@dataclass(frozen=True)
class ArchitectureScore:
    """One architecture's performance on one split."""

    architecture: str
    split_id: str
    split_role: str
    rows: int
    mae: float | None
    rmse: float | None
    reform_rows: int
    reform_mae: float | None
    reform_rmse: float | None
    reform_improvement_over_equal_split: float | None
    winner_accuracy: float | None
    seat_set_accuracy: float | None

    def criterion(self, name: str) -> float | None:
        return {
            "reform_vote_share_mae": self.reform_mae,
            "vote_share_mae": self.mae,
            "winner_accuracy": None if self.winner_accuracy is None else -self.winner_accuracy,
        }[name]


def score_architecture(
    *,
    architecture: str,
    split_id: str,
    split_role: str,
    predictions: Sequence[Mapping[str, object]],
) -> ArchitectureScore:
    """Score one architecture on one split using the shared metric code.

    Uses ``candidate_metrics`` rather than recomputing anything, so a
    comparison between architectures can never turn on two slightly different
    definitions of MAE.
    """

    overall = share_metrics(predictions)
    seats = seat_metrics(predictions)
    reform = [row for row in predictions if row.get("is_reform_uk")]
    reform_metrics = share_metrics(reform)

    return ArchitectureScore(
        architecture=architecture,
        split_id=split_id,
        split_role=split_role,
        rows=int(overall["rows"]),
        mae=overall["mae"],
        rmse=overall["rmse"],
        reform_rows=int(reform_metrics["rows"]),
        reform_mae=reform_metrics["mae"],
        reform_rmse=reform_metrics["rmse"],
        reform_improvement_over_equal_split=(
            equal_split_reference(reform)["improvement_over_equal_split"]
        ),
        winner_accuracy=seats["winner_accuracy"],
        seat_set_accuracy=seats["seat_set_accuracy"],
    )


@dataclass(frozen=True)
class SelectionOutcome:
    """Which architecture was chosen, and every reason it was."""

    selected: str
    incumbent: str
    primary_criterion: str
    decision_split_id: str
    reasons: tuple[str, ...]
    challenger_reports: tuple[dict[str, object], ...]
    material_improvement_threshold: float
    max_adverse_folds: int
    min_development_folds: int


def select_architecture(
    scores: Sequence[ArchitectureScore],
    *,
    decision_split_id: str,
    primary_criterion: str = PRIMARY_CRITERION,
    material_improvement: float = MATERIAL_IMPROVEMENT,
    max_adverse_folds: int = MAX_ADVERSE_FOLDS,
    min_development_folds: int = MIN_DEVELOPMENT_FOLDS,
) -> SelectionOutcome:
    """Apply the two gates in complexity order and record every verdict.

    ``decision_split_id`` names the split the primary criterion is read on.
    It is a parameter rather than a constant because the honest choice depends
    on what has been opened: before the holdout is unblinded the decision
    split must be a development fold, and afterwards it may be the holdout.
    Making it explicit stops the selection quietly reading a holdout it was
    not supposed to see.
    """

    by_architecture: dict[str, list[ArchitectureScore]] = {}
    for score in scores:
        by_architecture.setdefault(score.architecture, []).append(score)

    present = [name for name in COMPLEXITY_ORDER if name in by_architecture]
    if not present:
        raise ValueError("No scored architectures were supplied.")
    if len(present) < len(COMPLEXITY_ORDER):
        missing = [name for name in COMPLEXITY_ORDER if name not in by_architecture]
        raise ValueError(
            f"Architecture comparison is incomplete: {missing!r} were not "
            "scored. The brief requires all three to be compared before one "
            "is selected."
        )

    def decision_score(architecture: str) -> ArchitectureScore:
        for score in by_architecture[architecture]:
            if score.split_id == decision_split_id:
                return score
        raise ValueError(
            f"{architecture} has no score on decision split {decision_split_id!r}."
        )

    def development_scores(architecture: str) -> dict[str, ArchitectureScore]:
        return {
            score.split_id: score
            for score in by_architecture[architecture]
            if score.split_role == "development_fold"
        }

    incumbent = present[0]
    reasons: list[str] = [
        f"{incumbent} is the incumbent: architectures are ranked by simplicity "
        "and the simplest is displaced only on evidence."
    ]
    reports: list[dict[str, object]] = []

    for challenger in present[1:]:
        incumbent_value = decision_score(incumbent).criterion(primary_criterion)
        challenger_value = decision_score(challenger).criterion(primary_criterion)

        if incumbent_value is None or challenger_value is None:
            reports.append({
                "challenger": challenger, "accepted": False,
                "reason": "primary criterion unavailable for one architecture",
            })
            continue

        # Lower is better for every criterion exposed by ArchitectureScore.
        relative_gain = (
            (incumbent_value - challenger_value) / abs(incumbent_value)
            if incumbent_value else 0.0
        )
        material = relative_gain > material_improvement

        incumbent_folds = development_scores(incumbent)
        challenger_folds = development_scores(challenger)
        shared = sorted(set(incumbent_folds) & set(challenger_folds))
        adverse = [
            split_id
            for split_id in shared
            if (challenger_folds[split_id].criterion(primary_criterion) or np.inf)
            > (incumbent_folds[split_id].criterion(primary_criterion) or np.inf)
        ]
        # Enough shared folds to judge stability at all, and few enough
        # losses among them. Without the first condition the gate would pass
        # vacuously for a challenger that was never evaluated out of sample.
        comparable = len(shared) >= min_development_folds
        stable = comparable and len(adverse) <= max_adverse_folds

        accepted = material and stable
        report = {
            "challenger": challenger,
            "incumbent": incumbent,
            "decision_split_id": decision_split_id,
            "primary_criterion": primary_criterion,
            "incumbent_value": incumbent_value,
            "challenger_value": challenger_value,
            "relative_gain": relative_gain,
            "gate_material_improvement": material,
            "gate_stability": stable,
            "gate_enough_folds_to_judge": comparable,
            "development_folds_compared": len(shared),
            "development_folds_lost": adverse,
            "accepted": accepted,
        }
        reports.append(report)

        if accepted:
            reasons.append(
                f"{challenger} displaces {incumbent}: it improves "
                f"{primary_criterion} by {relative_gain:.1%} (threshold "
                f"{material_improvement:.0%}) and loses on {len(adverse)} of "
                f"{len(shared)} development folds (limit {max_adverse_folds})."
            )
            incumbent = challenger
        else:
            failed = []
            if not material:
                failed.append(
                    f"improvement {relative_gain:.1%} does not exceed "
                    f"{material_improvement:.0%}"
                )
            if not comparable:
                failed.append(
                    f"only {len(shared)} shared development folds, below the "
                    f"{min_development_folds} needed to judge stability"
                )
            elif not stable:
                failed.append(
                    f"loses on {len(adverse)} of {len(shared)} development folds"
                )
            reasons.append(f"{challenger} is not selected: " + "; ".join(failed) + ".")

    return SelectionOutcome(
        selected=incumbent,
        incumbent=present[0],
        primary_criterion=primary_criterion,
        decision_split_id=decision_split_id,
        reasons=tuple(reasons),
        challenger_reports=tuple(reports),
        material_improvement_threshold=material_improvement,
        max_adverse_folds=max_adverse_folds,
        min_development_folds=min_development_folds,
    )


def comparison_table(scores: Sequence[ArchitectureScore]) -> tuple[dict[str, object], ...]:
    """Every architecture on every split, for the report and the bundle."""

    return tuple(
        {
            "split_id": score.split_id,
            "split_role": score.split_role,
            "architecture": score.architecture,
            "rows": score.rows,
            "vote_share_mae": score.mae,
            "vote_share_rmse": score.rmse,
            "winner_accuracy": score.winner_accuracy,
            "seat_set_accuracy": score.seat_set_accuracy,
            "reform_rows": score.reform_rows,
            "reform_vote_share_mae": score.reform_mae,
            "reform_vote_share_rmse": score.reform_rmse,
            "reform_improvement_over_equal_split": (
                score.reform_improvement_over_equal_split
            ),
        }
        for score in sorted(
            scores, key=lambda s: (s.split_id, COMPLEXITY_ORDER.index(s.architecture))
        )
    )
