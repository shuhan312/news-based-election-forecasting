"""SHAP explanations for Architecture B, the selected tree model.

The brief asks for "SHAP analysis for tree-based models". That requirement was
dormant while the only architectures were linear — a centred linear model's
contribution decomposition is already exact, so SHAP would have added nothing
but an approximation of something known in closed form. Selecting Architecture
B activated it.

Why LightGBM's own contributions rather than the `shap` package
---------------------------------------------------------------
LightGBM implements TreeSHAP internally and exposes it through
``predict(pred_contrib=True)``. That returns **exact** Shapley values for a
tree ensemble in polynomial time, which is the same algorithm the `shap`
package would run against a LightGBM booster. Using it avoids adding a
dependency whose only contribution here would be to call back into LightGBM,
and it keeps the explanation attached to the same booster object the bundle
ships.

The output has one extra column beyond the features: the expected value of the
model over the training distribution. Contributions plus that base value
reconstruct the prediction exactly, which ``test_candidate_tree_explainability``
asserts rather than assumes.

What a SHAP value is and is not
--------------------------------
It is the average marginal contribution of a feature to this row's prediction,
over all orderings in which features could be added. It answers "how much did
this feature move this prediction, relative to the model's average
prediction". It does not answer "what would happen if this feature changed" —
that is a causal question the model cannot support and the brief explicitly
forbids claiming.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from no_news_baseline.candidate_boosted_model import safe_feature_names
from no_news_baseline.candidate_explainability import INTERPRETATION_WARNING
from no_news_baseline.candidate_features import CandidateFeatureEncoder


@dataclass(frozen=True)
class ShapExplanation:
    """One row's exact tree contributions, on the model's own target scale."""

    candidate_contest_id: str
    election_id: str
    division_name: str
    standard_party_name: str
    is_reform_uk: bool
    base_value: float
    predicted_relative_share: float
    contributions: tuple[tuple[str, float], ...]
    interpretation_warning: str = INTERPRETATION_WARNING


def shap_contributions(
    *,
    booster,
    rows: Sequence[Mapping[str, object]],
    encoder: CandidateFeatureEncoder,
    top_n: int = 12,
) -> tuple[ShapExplanation, ...]:
    """Exact TreeSHAP values for each row, largest contributions first.

    ``top_n`` trims the returned list for readability; the base value and the
    reconstructed prediction are both carried so a reader can see how much of
    the prediction the shown terms account for.
    """

    design = encoder.transform(rows)
    # pred_contrib returns one column per feature plus a final base-value
    # column, in the booster's own feature order.
    contributions = np.asarray(
        booster.predict(design.matrix, pred_contrib=True), dtype=float
    )
    if contributions.shape[1] != len(design.column_names) + 1:
        raise ValueError(
            "Contribution matrix width does not match the encoder's columns "
            f"({contributions.shape[1]} against {len(design.column_names)} + 1). "
            "The booster and encoder are not the pair that were fitted together."
        )

    explanations: list[ShapExplanation] = []
    for position, row in enumerate(rows):
        values = contributions[position, :-1]
        base = float(contributions[position, -1])
        order = np.argsort(-np.abs(values))[:top_n]
        explanations.append(
            ShapExplanation(
                candidate_contest_id=str(row["candidate_contest_id"]),
                election_id=str(row["election_id"]),
                division_name=str(row["division_name"]),
                standard_party_name=str(row["standard_party_name"]),
                is_reform_uk=bool(row.get("is_reform_uk")),
                base_value=base,
                predicted_relative_share=float(values.sum() + base),
                contributions=tuple(
                    (design.column_names[index], float(values[index]))
                    for index in order
                ),
            )
        )
    return tuple(explanations)


def global_shap_importance(
    *,
    booster,
    rows: Sequence[Mapping[str, object]],
    encoder: CandidateFeatureEncoder,
) -> tuple[dict[str, object], ...]:
    """Mean absolute SHAP value per feature — the standard global summary.

    Reported alongside, not instead of, LightGBM's gain importance. The two
    answer different questions: gain says how much a feature improved the
    objective while the trees were being built, mean absolute SHAP says how
    much it actually moves predictions on the rows being explained. A feature
    can score highly on gain and near zero on SHAP if the rows it splits are
    rare in the set being explained.

    ``mean_contribution`` is signed and kept separate from the magnitude,
    because a feature that pushes some rows up and others down by the same
    amount averages to zero while being highly influential.
    """

    design = encoder.transform(rows)
    contributions = np.asarray(
        booster.predict(design.matrix, pred_contrib=True), dtype=float
    )[:, :-1]

    return tuple(
        sorted(
            (
                {
                    "feature": name,
                    "mean_absolute_shap": float(np.mean(np.abs(contributions[:, index]))),
                    "mean_shap": float(np.mean(contributions[:, index])),
                    "rows": len(rows),
                }
                for index, name in enumerate(design.column_names)
            ),
            key=lambda item: -float(item["mean_absolute_shap"]),
        )
    )


def party_shap_profile(
    *,
    booster,
    rows: Sequence[Mapping[str, object]],
    encoder: CandidateFeatureEncoder,
    reform_only: bool = False,
    party: str | None = None,
) -> dict[str, object]:
    """The brief's Reform UK-specific feature importance, for the tree model.

    Restricting the rows before computing the average is what makes this
    party-specific. A tree has no per-party coefficient, so "importance for
    Reform" can only mean "what moves the predictions of Reform rows", which
    is what averaging SHAP over exactly those rows measures.
    """

    selected = [
        row
        for row in rows
        if (row.get("is_reform_uk") if reform_only
            else party is None or row.get("standard_party_name") == party)
    ]
    if not selected:
        return {
            "rows": 0,
            "importance": [],
            "interpretation_warning": INTERPRETATION_WARNING,
        }

    importance = global_shap_importance(
        booster=booster, rows=selected, encoder=encoder
    )
    design = encoder.transform(selected)
    contributions = np.asarray(
        booster.predict(design.matrix, pred_contrib=True), dtype=float
    )
    return {
        "rows": len(selected),
        "base_value": float(np.mean(contributions[:, -1])),
        "mean_predicted_relative_share": float(np.mean(contributions.sum(axis=1))),
        "importance": list(importance),
        "interpretation_warning": INTERPRETATION_WARNING,
    }


def compare_gain_and_shap(
    *,
    booster,
    rows: Sequence[Mapping[str, object]],
    encoder: CandidateFeatureEncoder,
    top_n: int = 20,
) -> tuple[dict[str, object], ...]:
    """Rank features by both measures side by side.

    A large disagreement is worth reporting rather than resolving: it usually
    means a feature was useful for splitting rows that are rare in the set
    being explained, which is exactly the kind of instability the brief asks
    to be warned about.
    """

    design = encoder.transform(rows)
    safe_to_real = {
        safe: real for safe, real in
        zip(*[safe_feature_names(design.column_names)[0],
              design.column_names])
    }
    gains = dict(
        zip(
            (safe_to_real.get(name, name) for name in booster.feature_name()),
            (float(value) for value in booster.feature_importance(importance_type="gain")),
        )
    )
    shap = {
        entry["feature"]: entry["mean_absolute_shap"]
        for entry in global_shap_importance(booster=booster, rows=rows, encoder=encoder)
    }

    shap_rank = {name: rank for rank, name in enumerate(
        sorted(shap, key=lambda n: -shap[n]), start=1)}
    gain_rank = {name: rank for rank, name in enumerate(
        sorted(gains, key=lambda n: -gains[n]), start=1)}

    return tuple(
        sorted(
            (
                {
                    "feature": name,
                    "gain": gains.get(name, 0.0),
                    "gain_rank": gain_rank.get(name),
                    "mean_absolute_shap": shap.get(name, 0.0),
                    "shap_rank": shap_rank.get(name),
                    "rank_disagreement": (
                        None
                        if gain_rank.get(name) is None or shap_rank.get(name) is None
                        else abs(gain_rank[name] - shap_rank[name])
                    ),
                }
                for name in shap
            ),
            key=lambda item: -float(item["mean_absolute_shap"]),
        )[:top_n]
    )
