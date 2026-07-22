"""N4: coverage-expanding cold-start no-news baseline.

Purpose
-------
The coverage report (Task 3) quantified the gap this model exists to close:
``previous_result_persistence_v1`` and ``ridge_fundamentals_v1`` have zero
coverage on Cohort B (party entry / no local history) and Cohort C
(geographically non-comparable), because both require a safe previous LOCAL
party vote share. N4 deliberately drops that requirement. It predicts a
party's share from its Surrey-wide historical strength only, so a brand-new
entrant (most notably early Reform UK contests) and a changed-boundary 2026
ward still receive a real prediction instead of a structural blank.

Estimator
---------
For one target contest (election x area) with k contesting party rows:

    prior            = 100 / k                      (equal split of the ballot)
    n                = number of strictly earlier Surrey-wide observations
                       of this party's realised share
    historical_mean  = mean of those n realised shares
    w                = n / (n + lambda)
    strength         = w * historical_mean + (1 - w) * prior
    predicted share  = strength / sum(strengths in the contest) * 100

This is classical empirical-Bayes shrinkage: a party with lots of history is
scored by its history; a party with little history is pulled toward the
conservative equal-share prior; a party with NO history receives exactly the
prior. The final normalisation guarantees non-negative shares that sum to
100 within each contest (the "sum to one" requirement, expressed on this
repository's 0-100 share scale).

``lambda`` is fixed at 5.0 and NOT tuned on any data: the prior is worth
five pseudo-elections of evidence. A party seen in one prior election keeps
only 1/6 of its own mean; a party seen in twenty keeps 80%. The unsmoothed
ablation (lambda handled as w=1 whenever n>0) quantifies what the shrinkage
itself contributes, on identical folds and rows.

What N4 must never use
----------------------
- ``previous_party_vote_share`` or any other local-history field: N4 must
  be identical whether or not a row has safe local history (tested by an
  invariance test), otherwise its Cohort B/C predictions would be a
  disguised form of local-history reconstruction.
- Candidate-specific Independent identities: a generic "Independent" label
  is not one continuing party (see the repository's frozen identity rules),
  so independent rows are excluded from the history pool AND always scored
  as zero-history at prediction time. Pooling unrelated independents would
  manufacture a fake "Independent party" strength.
- Anything dated on or after the target election date. History construction
  reuses ``temporal_validation.iter_temporal_folds``, which already
  guarantees strictly-earlier training rows (including same-day
  separation); a further explicit date assertion is kept here anyway.
- UKIP results as Reform UK history (or vice versa): the pool is keyed by
  ``standard_party_name``, under which the two are permanently distinct.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from no_news_baseline.benchmark_metrics import assert_one_to_one_party_contest_release
from no_news_baseline.election_dates import parse_election_date
from no_news_baseline.temporal_validation import TemporalFold, iter_temporal_folds


COLD_START_MODEL_ID = "cold_start_shrunk_party_strength_v1"
DEFAULT_SHRINKAGE_LAMBDA = 5.0
CANDIDATE_SPECIFIC_INDEPENDENT = "candidate_specific_independent"
# A contest's normalised shares must reconstruct 100 percentage points to
# within floating-point noise; anything larger is a construction bug.
NORMALISATION_TOLERANCE = 1e-6


def evaluate_cold_start_over_folds(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
    shrinkage_lambda: float = DEFAULT_SHRINKAGE_LAMBDA,
    *,
    unsmoothed: bool = False,
) -> tuple[dict[str, object], ...]:
    """Predict every fold's test rows from strictly earlier Surrey history.

    ``unsmoothed=True`` is the ablation variant: any party with at least one
    historical observation uses its raw historical mean (w=1); only
    zero-history parties fall back to the prior. Everything else -folds,
    rows, normalisation - is identical, so the two variants are comparable
    row-for-row.
    """

    if shrinkage_lambda < 0:
        raise ValueError("The shrinkage lambda must be non-negative.")
    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = assert_one_to_one_party_contest_release(feature_rows, target_rows)

    predictions: list[dict[str, object]] = []
    for fold in iter_temporal_folds(feature_rows, target_rows):
        history_pool = _party_history_pool(fold, target_by_id)
        train_election_count = len(
            {str(row["election_id"]) for row in fold.train_features}
        )
        by_area: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
        for row in fold.test_features:
            by_area[(str(row["election_id"]), str(row["division_id"]))].append(row)
        for area_rows in by_area.values():
            predictions.extend(
                _predict_one_area(
                    area_rows=area_rows,
                    history_pool=history_pool,
                    shrinkage_lambda=shrinkage_lambda,
                    unsmoothed=unsmoothed,
                    fold=fold,
                    train_election_count=train_election_count,
                    target_by_id=target_by_id,
                )
            )

    _assert_predictions_well_formed(predictions)
    return tuple(predictions)


def _party_history_pool(
    fold: TemporalFold,
    target_by_id: Mapping[str, Mapping[str, object]],
) -> dict[str, tuple[float, ...]]:
    """Pool each party's realised shares from this fold's training rows only.

    Only realised single-member shares exist as observations (multi-member
    contests define no party share), and candidate-specific Independent rows
    are excluded: their results belong to unrelated people, not to one
    continuing party whose strength could be pooled.
    """

    pool: dict[str, list[float]] = defaultdict(list)
    for row in fold.train_features:
        if row.get("party_identity_scope") == CANDIDATE_SPECIFIC_INDEPENDENT:
            continue
        # Belt-and-braces temporal assertion on top of the fold guarantee:
        # a training observation must predate the held-out election.
        if parse_election_date(str(row["election_date"])) >= fold.election_date:
            raise ValueError("Cold-start history pool contains a non-prior observation.")
        share = target_by_id[str(row["party_contest_id"])].get("target_party_vote_share")
        if isinstance(share, (int, float)) and not isinstance(share, bool):
            pool[str(row["standard_party_name"])].append(float(share))
    return {party: tuple(values) for party, values in pool.items()}


def _predict_one_area(
    *,
    area_rows: Sequence[Mapping[str, object]],
    history_pool: Mapping[str, Sequence[float]],
    shrinkage_lambda: float,
    unsmoothed: bool,
    fold: TemporalFold,
    train_election_count: int,
    target_by_id: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Score one contest: shrink, normalise, and (single-member) call a winner."""

    contest_size = len(area_rows)
    prior = 100.0 / contest_size
    strengths: list[float] = []
    diagnostics: list[dict[str, object]] = []
    for row in area_rows:
        # Candidate-specific Independents are ALWAYS zero-history by design,
        # even if unrelated independents elsewhere have realised shares.
        independent = row.get("party_identity_scope") == CANDIDATE_SPECIFIC_INDEPENDENT
        observations = (
            () if independent else history_pool.get(str(row["standard_party_name"]), ())
        )
        n_history = len(observations)
        historical_mean = sum(observations) / n_history if n_history else None
        if unsmoothed:
            weight = 1.0 if n_history else 0.0
        elif n_history == 0 and shrinkage_lambda == 0.0:
            # Degenerate corner of the ablation grid: no history and no
            # prior weight. Fall back to the prior explicitly rather than
            # dividing zero by zero.
            weight = 0.0
        else:
            weight = n_history / (n_history + shrinkage_lambda)
        strength = (
            weight * historical_mean + (1.0 - weight) * prior
            if historical_mean is not None
            else prior
        )
        strengths.append(strength)
        diagnostics.append(
            {
                "historical_observation_count": n_history,
                "raw_historical_party_mean": historical_mean,
                "global_prior": prior,
                "shrinkage_weight": weight,
                "smoothed_party_strength": strength,
            }
        )

    total_strength = sum(strengths)
    if total_strength <= 0:
        # Only reachable in the unsmoothed ablation if every contesting
        # party's historical mean is exactly zero; the honest fallback is
        # the uninformed equal split, not a crash or a negative share.
        strengths = [prior] * contest_size
        total_strength = sum(strengths)

    predicted_shares = [strength / total_strength * 100.0 for strength in strengths]
    single_member = all(
        row.get("contest_structure") == "single_member" for row in area_rows
    )
    winner_status, winner_index = _winner_decision(predicted_shares, single_member)

    rows_out: list[dict[str, object]] = []
    for index, (row, share, diagnostic) in enumerate(
        zip(area_rows, predicted_shares, diagnostics, strict=True)
    ):
        target = target_by_id[str(row["party_contest_id"])]
        actual = target.get("target_party_vote_share")
        has_actual = isinstance(actual, (int, float)) and not isinstance(actual, bool)
        error = share - float(actual) if has_actual else None
        predicted_elected = (
            ("Yes" if index == winner_index else "No")
            if winner_index is not None
            else "Unknown"
        )
        rows_out.append(
            {
                "party_contest_id": row["party_contest_id"],
                "election_id": row["election_id"],
                "election_year": row["election_year"],
                "election_type": row["election_type"],
                "division_id": row["division_id"],
                "division_name": row["division_name"],
                "standard_party_name": row["standard_party_name"],
                "contest_structure": row["contest_structure"],
                "benchmark_id": COLD_START_MODEL_ID,
                # Diagnostics required by the task brief, one per prediction.
                **diagnostic,
                "predicted_party_vote_share": share,
                "actual_party_vote_share": float(actual) if has_actual else None,
                "share_error": error,
                "absolute_share_error": abs(error) if error is not None else None,
                "squared_share_error": error**2 if error is not None else None,
                # The cutoff is the held-out election's own date: everything
                # the model saw is strictly earlier than this.
                "prediction_information_cutoff": fold.election_date.date().isoformat(),
                "train_election_count": train_election_count,
                "winner_prediction_status": winner_status,
                "predicted_party_elected": predicted_elected,
                "actual_party_elected": target.get("target_party_elected"),
                "winner_prediction_correct": (
                    predicted_elected == target.get("target_party_elected")
                    if predicted_elected != "Unknown"
                    else None
                ),
            }
        )
    return rows_out


def _winner_decision(
    predicted_shares: Sequence[float], single_member: bool
) -> tuple[str, int | None]:
    """Call a winner only for a single-member contest with a unique leader.

    Multi-member wards are excluded by the repository's frozen rule against
    converting party vote rankings into seat predictions; a tied maximum in
    a single-member contest yields an explicit Unknown, never a coin flip.
    """

    if not single_member:
        return "not_applicable_multi_member_contest", None
    best = max(predicted_shares)
    leaders = [index for index, share in enumerate(predicted_shares) if share == best]
    if len(leaders) != 1:
        return "unavailable_tied_smoothed_strengths", None
    return "eligible_unique_smoothed_strength_leader", leaders[0]


def _assert_predictions_well_formed(predictions: list[Mapping[str, object]]) -> None:
    if len({str(row["party_contest_id"]) for row in predictions}) != len(predictions):
        raise ValueError("Cold-start predictions contain duplicate identifiers.")
    per_area_totals: dict[tuple[str, str], float] = defaultdict(float)
    for row in predictions:
        share = float(row["predicted_party_vote_share"])
        if share < 0:
            raise ValueError("Cold-start produced a negative predicted share.")
        per_area_totals[(str(row["election_id"]), str(row["division_id"]))] += share
    for area_key, total in per_area_totals.items():
        if abs(total - 100.0) > NORMALISATION_TOLERANCE:
            raise ValueError(
                f"Cold-start shares for {area_key!r} sum to {total!r}, not 100."
            )


def tag_universe_with_cold_start_eligibility(
    universe: Sequence[Mapping[str, object]],
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Add N4's theoretical-eligibility flag to evaluation-universe rows.

    N4 is eligible wherever the party stood (every universe row is a
    contesting party by construction) and the election has at least one
    strictly earlier election to pool history from - the same fold
    evaluability rule the ridge model already uses, with no cohort or
    geography condition attached. Kept as a decorator over the frozen
    Task 2 universe rather than an edit to ``coverage_evaluation.py``.
    """

    evaluable_election_ids = frozenset(
        fold.election_id for fold in iter_temporal_folds(list(features), list(targets))
    )
    return tuple(
        {**row, "eligible_n4_cold_start": str(row["election_id"]) in evaluable_election_ids}
        for row in universe
    )


def ablation_unsmoothed_vs_smoothed(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
    shrinkage_lambda: float = DEFAULT_SHRINKAGE_LAMBDA,
) -> dict[str, object]:
    """Compare raw Surrey-wide means against the shrunk estimator, like for like.

    Both variants run on identical folds; MAE is computed over the exact
    intersection of rows both scored (in practice identical row sets, but
    the intersection is taken explicitly rather than assumed).
    """

    feature_rows = list(features)
    target_rows = list(targets)
    smoothed = evaluate_cold_start_over_folds(
        feature_rows, target_rows, shrinkage_lambda
    )
    raw = evaluate_cold_start_over_folds(
        feature_rows, target_rows, shrinkage_lambda, unsmoothed=True
    )
    scored_ids = {
        str(row["party_contest_id"])
        for row in smoothed
        if row["absolute_share_error"] is not None
    } & {
        str(row["party_contest_id"])
        for row in raw
        if row["absolute_share_error"] is not None
    }

    def _mae(rows: Sequence[Mapping[str, object]]) -> float | None:
        errors = [
            float(row["absolute_share_error"])
            for row in rows
            if str(row["party_contest_id"]) in scored_ids
        ]
        return sum(errors) / len(errors) if errors else None

    return {
        "shrinkage_lambda": shrinkage_lambda,
        "scored_row_count": len(scored_ids),
        "unsmoothed_party_mean_mae": _mae(raw),
        "smoothed_party_prior_mae": _mae(smoothed),
    }
