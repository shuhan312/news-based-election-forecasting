"""N5 pre-implementation audit: what can the real data actually identify?

Purpose
-------
A hierarchical Bayesian Dirichlet model (the proposed N5) treats one whole
CONTEST - an election event x analytical area, with the complete set of
contesting parties - as a single compositional observation, not each party
row separately (Hanretty 2021 makes exactly this point for multiparty vote
shares). Before any such model is specified, three factual questions must
be answered from the real release, not assumed:

1. How many complete, closed compositions actually exist to fit on?
   (Task 1: contest usability audit.)
2. What outcome state is every party row in, reusing the repository's
   existing authoritative fields rather than inventing a competing
   missingness taxonomy? (Task 2.)
3. Which of the candidate random effects - election cycle, party, area -
   have enough repeated observations to be identifiable at all?
   (Task 3.) Chen, Garnett & Montgomery (2023) fit cycle-level effects to
   hundreds of US House elections; Surrey's release is far smaller, so
   each level's empirical support is counted rather than presumed.

This module only measures. It fits nothing, and none of its outputs feed
any model; they feed the written N5 specification
(``docs/n5_candidate_specifications.md``).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence

from no_news_baseline.benchmark_metrics import assert_one_to_one_party_contest_release
from no_news_baseline.election_dates import parse_election_date


# The extractor's own single-member reconciliation accepts published,
# rounded shares summing to 98..102 (see no_news_party_contest.py). The
# audit reuses that bound rather than inventing a stricter one that would
# reclassify contests the upstream release already accepted as complete.
SHARE_SUM_TOLERANCE_PP = 2.0

# Below this many usable contests, an individually estimated party effect
# would rest almost entirely on the prior; such parties are flagged as
# partial-pooling-only. The threshold is a documented audit convention,
# not a fitted quantity.
MIN_CONTESTS_FOR_INDIVIDUAL_PARTY_EFFECT = 20
MIN_ELECTIONS_FOR_INDIVIDUAL_PARTY_EFFECT = 2

GEOGRAPHICALLY_SAFE_STATUS = "approved_historical_reference"


def build_contest_usability_audit(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Task 1: one audit row per election x area contest.

    A contest is usable as a Dirichlet training composition only when every
    contesting party's share is observed and the shares close to a full
    composition within publication-rounding tolerance. Party rows are never
    treated as independent observations.
    """

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = assert_one_to_one_party_contest_release(feature_rows, target_rows)

    contests: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in feature_rows:
        contests[(str(row["election_id"]), str(row["division_id"]))].append(row)

    audit_rows: list[dict[str, object]] = []
    for (election_id, division_id), rows in sorted(contests.items()):
        shares = [
            target_by_id[str(row["party_contest_id"])].get("target_party_vote_share")
            for row in rows
        ]
        observed = [
            float(share)
            for share in shares
            if isinstance(share, (int, float)) and not isinstance(share, bool)
        ]
        structures = {str(row["contest_structure"]) for row in rows}
        all_observed = len(observed) == len(rows)
        share_sum = sum(observed) if all_observed else None
        sum_ok = (
            share_sum is not None
            and abs(share_sum - 100.0) <= SHARE_SUM_TOLERANCE_PP
        )
        usable, reason = _usability(structures, all_observed, sum_ok)
        audit_rows.append(
            {
                "election_id": election_id,
                "election_date": str(rows[0]["election_date"]),
                "election_type": str(rows[0]["election_type"]),
                "division_id": division_id,
                "division_name": str(rows[0]["division_name"]),
                "geographic_reference_eligibility": str(
                    rows[0]["geographic_reference_eligibility"]
                ),
                "contesting_party_count": len(rows),
                "observed_positive_share_count": sum(share > 0 for share in observed),
                "all_party_outcomes_observed": all_observed,
                "share_sum": round(share_sum, 6) if share_sum is not None else None,
                "share_sum_within_tolerance": sum_ok,
                "usable_complete_composition": usable,
                "unusable_reason": reason,
            }
        )
    return tuple(audit_rows)


def _usability(
    structures: set[str], all_observed: bool, sum_ok: bool
) -> tuple[bool, str | None]:
    if structures != {"single_member"}:
        # Multi-member party shares are undefined by the frozen estimand
        # rule, so no complete composition can exist for these contests.
        return False, "multi_member_party_share_estimand_undefined"
    if not all_observed:
        return False, "missing_party_share_outcome"
    if not sum_ok:
        return False, "share_sum_outside_publication_tolerance"
    return True, None


def reconcile_outcome_states(
    universe: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    """Task 2: count rows per outcome state, from existing fields only.

    The mapping reads the Task-2/Task-3 evaluation universe
    (``coverage_evaluation.build_evaluation_universe``) and re-expresses
    fields it already carries. One factual property of the release matters
    here and is asserted rather than assumed: the party-contest universe
    contains one row per party that actually STOOD, so structural
    non-participation (a party absent from the ballot) has no row at all.
    A Dirichlet composition over the actual ballot therefore handles
    structural zeros by construction - no epsilon replacement is ever
    needed - and any future N5 must not invent rows for absent parties.
    """

    counts: Counter[str] = Counter()
    for row in universe:
        share = row.get("actual_party_vote_share")
        has_share = isinstance(share, (int, float)) and not isinstance(share, bool)
        if has_share:
            counts["observed_share_available"] += 1
        elif row.get("target_missingness_type") == "not_defined_for_multi_member_party_contest":
            counts["participating_party_share_undefined_multi_member"] += 1
        else:
            counts["other_authoritative_missingness"] += 1
        if row.get("primary_cohort") == "geographically_non_comparable":
            counts["geography_incomparable_prediction_target"] += 1
    counts["structural_non_participation_rows"] = 0  # absent parties have no row
    return dict(sorted(counts.items()))


def election_cycle_audit(
    contest_audit: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Task 3a: usable-contest support for an election-cycle random effect."""

    usable = [row for row in contest_audit if row["usable_complete_composition"]]
    by_election: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in usable:
        by_election[str(row["election_id"])].append(row)

    audit_rows = []
    for election_id, rows in sorted(
        by_election.items(), key=lambda item: parse_election_date(str(item[1][0]["election_date"]))
    ):
        contest_count = len(rows)
        audit_rows.append(
            {
                "election_id": election_id,
                "election_date": str(rows[0]["election_date"]),
                "election_type": str(rows[0]["election_type"]),
                "usable_contest_count": contest_count,
                # One contest cannot separate a cycle effect from its own
                # contest-level noise; such events can only borrow strength
                # through partial pooling across cycles.
                "cycle_effect_individually_estimable": contest_count >= 2,
            }
        )
    return tuple(audit_rows)


def party_identifiability_audit(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
    contest_audit: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Task 3b: repeated-observation support for party-level effects.

    Only rows inside usable complete compositions count as evidence, since
    only those rows can ever enter a Dirichlet likelihood. Candidate-
    specific Independents are excluded: they are not one continuing party,
    so no shared party effect could be defined for them. UKIP and Reform UK
    are distinct keys throughout.
    """

    usable_contests = {
        (str(row["election_id"]), str(row["division_id"]))
        for row in contest_audit
        if row["usable_complete_composition"]
    }
    feature_rows = list(features)
    assert_one_to_one_party_contest_release(feature_rows, list(targets))

    by_party: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in feature_rows:
        if (str(row["election_id"]), str(row["division_id"])) not in usable_contests:
            continue
        if row.get("party_identity_scope") == "candidate_specific_independent":
            continue
        by_party[str(row["standard_party_name"])].append(row)

    audit_rows = []
    for party, rows in sorted(by_party.items()):
        elections = {str(row["election_id"]) for row in rows}
        areas = {_area_key(row) for row in rows}
        dates = sorted(parse_election_date(str(row["election_date"])) for row in rows)
        individually_estimable = (
            len(rows) >= MIN_CONTESTS_FOR_INDIVIDUAL_PARTY_EFFECT
            and len(elections) >= MIN_ELECTIONS_FOR_INDIVIDUAL_PARTY_EFFECT
        )
        audit_rows.append(
            {
                "standard_party_name": party,
                "usable_contest_count": len(rows),
                "distinct_election_count": len(elections),
                "distinct_area_count": len(areas),
                "earliest_observation": dates[0].date().isoformat(),
                "latest_observation": dates[-1].date().isoformat(),
                "individual_effect_supported": individually_estimable,
                "pooling_recommendation": (
                    "individual_intercept_plausible"
                    if individually_estimable
                    else "partial_pooling_only"
                ),
            }
        )
    return tuple(audit_rows)


def area_identifiability_audit(
    contest_audit: Sequence[Mapping[str, object]],
) -> tuple[tuple[dict[str, object], ...], dict[str, int]]:
    """Task 3c: repeated, geographically safe observations per area.

    Areas are keyed by normalised division name - an audit-level
    approximation, adequate because Surrey's county divisions kept stable
    names over 2013-2025 and every 2026 changed-boundary ward is already
    excluded (multi-member, hence never a usable composition). A repeat
    only counts as SAFE evidence for an area effect when the later
    contest's own geographic gate is the approved status; study-start 2013
    contests anchor an area without asserting any cross-election link.
    """

    usable = [row for row in contest_audit if row["usable_complete_composition"]]
    by_area: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in usable:
        by_area[_area_key(row)].append(row)

    audit_rows = []
    for area, rows in sorted(by_area.items()):
        elections = {str(row["election_id"]) for row in rows}
        safe_linked = sum(
            row["geographic_reference_eligibility"] == GEOGRAPHICALLY_SAFE_STATUS
            for row in rows
        )
        audit_rows.append(
            {
                "area_key": area,
                "division_name": str(rows[0]["division_name"]),
                "usable_contest_count": len(rows),
                "distinct_election_count": len(elections),
                "geographically_safe_linked_contest_count": safe_linked,
                # An area effect needs at least two usable contests, of
                # which at least one carries an approved cross-election
                # link; a single observation cannot separate "this area is
                # distinctive" from ordinary contest-level noise.
                "area_effect_supported": len(rows) >= 2 and safe_linked >= 1,
            }
        )

    repetition_distribution = Counter(
        "1" if len(rows) == 1 else ("2" if len(rows) == 2 else "3_or_more")
        for rows in by_area.values()
    )
    return tuple(audit_rows), dict(sorted(repetition_distribution.items()))


def _area_key(row: Mapping[str, object]) -> str:
    return " ".join(str(row["division_name"]).lower().split())
