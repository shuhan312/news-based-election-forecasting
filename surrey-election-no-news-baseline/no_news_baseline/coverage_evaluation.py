"""Coverage-aware evaluation cohorts, derived entirely from existing fields.

Purpose
-------
``persistence_benchmark``, ``naive_benchmarks`` and ``regularised_models``
each report accuracy only on the rows they are able to score. None of them
answers a prior question the supervisor's brief and the wider forecasting
literature both treat as essential: out of every party-area contest that
COULD in principle need a prediction, what share does each model actually
cover, and why do the rest fall out? A model that is very accurate on a
small, easy subset is a different scientific claim from one that is
accurate across the whole electoral landscape (see
``docs/persistence_benchmark.md``, "Interpretation boundary": a model does
not show added value merely by scoring more or fewer rows without saying
so).

This module builds that missing accounting layer. It does not compute a
single new eligibility rule of its own. Every classification below is a
direct, documented re-expression of fields the extractor and the existing
benchmark modules already compute and already trust:

- ``baseline_eligibility`` is the exact field ``persistence_benchmark``
  itself uses (via ``is_within_share_cohort``) to decide whether a row gets
  a share prediction. Reusing it here - rather than re-deriving "is this
  party's history safe" from lower-level fields such as
  ``previous_party_vote_share_status`` - guarantees this module's cohort
  assignment can never silently disagree with what the benchmark that
  actually uses the data has already decided.
- ``geographic_reference_eligibility`` is the area-level field the
  extractor's geographic mapping/crosswalk decision layer already
  publishes, recording whether the CURRENT area has any administratively
  or analytically accepted predecessor at all, independent of any one
  party's history within it.

Verified against the live release (see
``docs/coverage_aware_evaluation_methodology.md``): every row where
``baseline_eligibility`` is the primary-eligible status also has
``geographic_reference_eligibility == "approved_historical_reference"``,
and no row anywhere in the release carries a numeric
``previous_party_vote_share`` while its area is flagged geographically
unsafe. The three-way split below is therefore an exhaustive, non-
overlapping partition of the real data, not merely a partition in theory.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from no_news_baseline.benchmark_metrics import assert_one_to_one_party_contest_release
from no_news_baseline.persistence_benchmark import (
    is_within_share_cohort,
    is_within_winner_cohort,
)
from no_news_baseline.temporal_validation import iter_temporal_folds


GEOGRAPHICALLY_SAFE_STATUS = "approved_historical_reference"

COHORT_HISTORICAL_CONTINUITY = "historical_continuity"
COHORT_PARTY_ENTRY_NO_LOCAL_HISTORY = "party_entry_no_local_history"
COHORT_GEOGRAPHICALLY_NON_COMPARABLE = "geographically_non_comparable"


def build_evaluation_universe(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return one evaluation-universe row per party-contest, cohort-tagged.

    Every row in the extractor's release is included, single-member and
    multi-member alike, so that "no prediction was possible here" remains
    visible rather than the row disappearing before it can be counted.
    """

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = assert_one_to_one_party_contest_release(feature_rows, target_rows)

    # A row is only N3-evaluable if its own election has at least one
    # strictly earlier election to train from. This reuses the exact fold
    # boundaries regularised_models.py already fits on, rather than
    # re-deriving "which elections have history" independently.
    evaluable_fold_election_ids = frozenset(
        fold.election_id for fold in iter_temporal_folds(feature_rows, target_rows)
    )

    rows = tuple(
        _evaluation_row(feature, target_by_id[str(feature["party_contest_id"])], evaluable_fold_election_ids)
        for feature in feature_rows
    )
    _assert_partition_is_exhaustive_and_disjoint(rows)
    _assert_cohort_c_never_carries_local_history(feature_rows, rows)
    return rows


def _evaluation_row(
    feature: Mapping[str, object],
    target: Mapping[str, object],
    evaluable_fold_election_ids: frozenset[str],
) -> dict[str, object]:
    cohort, cohort_reason = _assign_primary_cohort(feature)
    share_eligible = is_within_share_cohort(feature)
    winner_eligible = is_within_winner_cohort(feature)
    ridge_eligible = share_eligible and str(feature["election_id"]) in evaluable_fold_election_ids
    single_member = feature["contest_structure"] == "single_member"

    return {
        # Identifiers, carried through unchanged from the authoritative
        # extractor release rather than re-derived.
        "party_contest_id": feature["party_contest_id"],
        "election_id": feature["election_id"],
        "election_date": feature["election_date"],
        "election_year": feature["election_year"],
        "election_type": feature["election_type"],
        "division_id": feature["division_id"],
        "division_name": feature["division_name"],
        "standard_party_name": feature["standard_party_name"],
        "contest_structure": feature["contest_structure"],
        # Cohort assignment (Task 2): a coarse three-way label derived
        # entirely from the two gate fields, plus the original detailed
        # reason fields preserved unchanged alongside it.
        "primary_cohort": cohort,
        "cohort_reason": cohort_reason,
        "baseline_eligibility": feature["baseline_eligibility"],
        "geographic_reference_eligibility": feature["geographic_reference_eligibility"],
        "previous_party_vote_share_status": feature.get("previous_party_vote_share_status"),
        "previous_party_vote_share": feature.get("previous_party_vote_share"),
        "party_was_previous_winner": feature.get("party_was_previous_winner"),
        # Target-side missingness is already a controlled field in the
        # extractor's own release; carried through, not re-derived.
        "actual_party_vote_share": target.get("target_party_vote_share"),
        "target_missingness_type": target.get("target_party_vote_share_status"),
        "actual_party_elected": target.get("target_party_elected"),
        # Model eligibility matrix (Task 3 input): each flag reuses the
        # existing per-model cohort predicate rather than a new rule.
        "eligible_n0_equal_share": single_member,
        "eligible_n1_party_historical_mean": single_member,
        "eligible_n2_persistence_share": share_eligible,
        "eligible_n2_persistence_winner": winner_eligible,
        "eligible_n3_ridge": ridge_eligible,
    }


def _assign_primary_cohort(feature: Mapping[str, object]) -> tuple[str, str]:
    """Map the two existing gate fields to one of the three cohorts.

    No new eligibility condition is introduced here: the two branches below
    read ``baseline_eligibility`` and ``geographic_reference_eligibility``
    exactly as they are already published.
    """

    if is_within_share_cohort(feature):
        return COHORT_HISTORICAL_CONTINUITY, str(feature["baseline_eligibility"])
    if feature["geographic_reference_eligibility"] == GEOGRAPHICALLY_SAFE_STATUS:
        # The area itself has an accepted predecessor, but this specific
        # party-contest row does not carry a usable lagged share within it
        # (new entrant, non-unique label, multi-member estimand, etc). The
        # existing exclusion string already names which of those applies.
        return COHORT_PARTY_ENTRY_NO_LOCAL_HISTORY, str(feature["baseline_eligibility"])
    # The area has no accepted predecessor at all, so no party within it can
    # have safe local history regardless of that party's own record.
    return COHORT_GEOGRAPHICALLY_NON_COMPARABLE, str(feature["geographic_reference_eligibility"])


def _assert_partition_is_exhaustive_and_disjoint(rows: tuple[dict[str, object], ...]) -> None:
    valid_cohorts = {
        COHORT_HISTORICAL_CONTINUITY,
        COHORT_PARTY_ENTRY_NO_LOCAL_HISTORY,
        COHORT_GEOGRAPHICALLY_NON_COMPARABLE,
    }
    if any(row["primary_cohort"] not in valid_cohorts for row in rows):
        raise ValueError("Evaluation universe assigned a row to an undeclared cohort.")


def _assert_cohort_c_never_carries_local_history(
    feature_rows: list[Mapping[str, object]], rows: tuple[dict[str, object], ...]
) -> None:
    # This is the one hard rule the task brief states explicitly: a
    # geographically non-comparable row must never carry a previous local
    # party vote share. Checked independently here rather than only assumed
    # from the branch above, so a future change to the gate fields cannot
    # silently violate it without a test catching it.
    for row in rows:
        if (
            row["primary_cohort"] == COHORT_GEOGRAPHICALLY_NON_COMPARABLE
            and row["previous_party_vote_share"] is not None
        ):
            raise ValueError(
                f"Cohort C row {row['party_contest_id']!r} carries a previous local "
                "party vote share; geographic non-comparability must exclude it."
            )
