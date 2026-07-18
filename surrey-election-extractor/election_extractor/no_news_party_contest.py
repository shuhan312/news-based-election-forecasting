"""Build the party-contest modelling release for the no-news baseline.

The source-preserving master workbook is candidate-level, while the
supervisor's comparison concerns party vote share and whether a party wins.
This module therefore publishes one row per election, area and identifiable
party.  Predictors and outcomes are returned as separate tables so a later
modelling script cannot accidentally treat a current-election result as an
input feature.

Multi-member wards require a separate estimand.  Candidates from the same
registered party are grouped for an ``any candidate elected`` target, but no
party vote share is manufactured by summing candidate shares.  Independents
remain candidate-specific because the generic label does not establish a
shared political identity.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from hashlib import sha256

from election_extractor.master_database import MasterDatabasePayload
from election_extractor.no_news_baseline import build_no_news_electoral_baseline


# These names are outcomes observed at the target election.  They may appear
# only in the separately published target table, never in model features.
TARGET_ONLY_FIELDS = frozenset(
    {
        "target_party_vote_share",
        "target_best_candidate_vote_share",
        "target_party_elected",
        "target_party_seats_won",
    }
)


def build_no_news_party_contests(
    payload: MasterDatabasePayload,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...], dict[str, int]]:
    """Return leakage-safe feature rows, target rows and a coverage audit.

    A party-contest row is eligible for the primary vote-share experiment only
    when the current contest is single-member, the party has one candidate and
    an approved lagged exact-label party share is available.  Rows outside that
    cohort are retained with an explicit reason; they are not silently dropped.
    """

    elections = {str(row["election_id"]): row for row in payload.elections}
    divisions = {
        (str(row["election_id"]), str(row["division_id"])): row
        for row in payload.divisions_and_wards
    }
    division_baseline, _ = build_no_news_electoral_baseline(payload)
    baseline_by_division = {
        (str(row["election_id"]), str(row["division_id"])): row
        for row in division_baseline
    }

    grouped: dict[tuple[str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for candidate in payload.candidate_results:
        group_key = _party_group_key(candidate)
        grouped[
            (
                str(candidate["election_id"]),
                str(candidate["division_id"]),
                group_key,
            )
        ].append(candidate)

    features: list[dict[str, object]] = []
    targets: list[dict[str, object]] = []
    for (election_id, division_id, party_group_key), candidates in sorted(grouped.items()):
        election = elections[election_id]
        division = divisions[(election_id, division_id)]
        division_history = baseline_by_division[(election_id, division_id)]
        seats, seats_provenance = _analysis_seats(division)
        structure = _contest_structure(seats)
        party_contest_id = _party_contest_id(election_id, division_id, party_group_key)
        previous_share = _one_non_null_value(candidates, "previous_party_vote_share")
        previous_share_status = _one_value(candidates, "previous_party_vote_share_status")
        previous_party_eligible = (
            structure == "single_member"
            and len(candidates) == 1
            and previous_share is not None
            and division_history["baseline_eligibility"] == "approved_historical_reference"
        )

        # Candidate-incumbency is reduced to an auditable party-contest flag:
        # Yes if any candidate is verified incumbent, No only if every candidate
        # is verified No, and Unknown otherwise.
        incumbent_candidate = _aggregate_yes_no(
            candidate.get("incumbent_candidate_yes_no") for candidate in candidates
        )
        party_name = str(candidates[0]["standard_party_name"])
        original_labels = sorted({str(row["original_party_name"]) for row in candidates})
        source_urls = sorted({str(row["source_url"]) for row in candidates})
        party_was_previous_winner = _party_was_previous_winner(
            original_labels, party_name, division_history.get("previous_winning_party")
        )

        feature = {
            "party_contest_id": party_contest_id,
            "election_id": election_id,
            "election_date": election["election_date"],
            "election_year": election["election_year"],
            "election_type": election["election_type"],
            "authority": election["authority"],
            "division_id": division_id,
            "division_name": division["division_name"],
            "analysis_number_of_seats": seats,
            "analysis_number_of_seats_provenance": seats_provenance,
            "contest_structure": structure,
            "party_group_key": party_group_key,
            "party_identity_scope": _party_identity_scope(candidates[0]),
            "standard_party_name": party_name,
            "original_party_labels": "; ".join(original_labels),
            "party_category": _one_value(candidates, "party_category"),
            "candidate_count_for_party": len(candidates),
            "baseline_eligibility": (
                "eligible_primary_single_member_party_share"
                if previous_party_eligible
                else _baseline_exclusion_reason(
                    structure, candidates, previous_share, division_history
                )
            ),
            "previous_election_id": division_history["previous_election_id"],
            "previous_division_name": division_history["previous_division_name"],
            "historical_reference_status": division_history["historical_reference_status"],
            "geographic_reference_eligibility": division_history["baseline_eligibility"],
            "previous_party_vote_share": previous_share,
            "previous_party_vote_share_status": previous_share_status,
            "previous_winning_party": division_history["previous_winning_party"],
            "party_was_previous_winner": party_was_previous_winner,
            "analysis_previous_turnout": division_history["analysis_previous_turnout"],
            "analysis_previous_turnout_provenance": division_history[
                "analysis_previous_turnout_provenance"
            ],
            "previous_electorate": division_history["previous_electorate"],
            "party_previously_contested": _one_value(candidates, "party_previously_contested"),
            "first_appearance_of_party_in_area": _one_value(
                candidates, "first_appearance_of_party_in_area"
            ),
            "party_history_status": _one_value(candidates, "party_history_status"),
            "incumbent_candidate_any_yes_no": incumbent_candidate,
            "incumbent_party_yes_no": _one_value(candidates, "incumbent_party_yes_no"),
            "incumbent_party_yes_no_status": _one_value(
                candidates, "incumbent_party_yes_no_status"
            ),
            "historical_source_url": division_history["historical_source_url"],
            "historical_permission_source_urls": division_history[
                "historical_permission_source_urls"
            ],
            "current_result_source_urls": "; ".join(source_urls),
        }

        target_vote_share, vote_share_status = _target_party_vote_share(
            candidates, structure
        )
        target = {
            "party_contest_id": party_contest_id,
            "election_id": election_id,
            "division_id": division_id,
            "standard_party_name": party_name,
            "target_party_vote_share": target_vote_share,
            "target_party_vote_share_status": vote_share_status,
            # Best-candidate share is a named multi-member diagnostic, not a
            # substitute for party vote share or voter support.
            "target_best_candidate_vote_share": _max_numeric(
                candidate.get("analysis_vote_share") for candidate in candidates
            ),
            "target_party_elected": _aggregate_yes_no(
                candidate.get("elected_yes_no") for candidate in candidates
            ),
            "target_party_seats_won": sum(
                candidate.get("elected_yes_no") == "Yes" for candidate in candidates
            ),
            "target_source_urls": "; ".join(source_urls),
        }
        features.append(feature)
        targets.append(target)

    _assert_unique_ids(features, "feature")
    _assert_unique_ids(targets, "target")
    _assert_feature_target_separation(features)
    _assert_historical_time_order(features, elections)
    _assert_target_consistency(features, targets)
    audit = _coverage_audit(features, targets)
    return tuple(features), tuple(targets), audit


def _party_group_key(candidate: Mapping[str, object]) -> str:
    """Keep generic Independent labels candidate-specific."""

    if candidate.get("party_category") == "independent":
        return f"independent_candidate:{candidate['candidate_id']}"
    return f"party:{candidate['standard_party_name']}"


def _party_identity_scope(candidate: Mapping[str, object]) -> str:
    return (
        "candidate_specific_independent"
        if candidate.get("party_category") == "independent"
        else "reviewed_standard_party"
    )


def _party_contest_id(election_id: str, division_id: str, party_group_key: str) -> str:
    digest = sha256(f"{election_id}|{division_id}|{party_group_key}".encode()).hexdigest()[:16]
    return f"party-contest-{digest}"


def _analysis_seats(division: Mapping[str, object]) -> tuple[int | None, str]:
    if division.get("official_number_of_seats") is not None:
        return int(division["official_number_of_seats"]), "official_result_page"
    if division.get("secondary_number_of_seats") is not None:
        return int(division["secondary_number_of_seats"]), "supplementary_statutory_evidence"
    return None, "unavailable_after_permitted_layers"


def _contest_structure(seats: int | None) -> str:
    if seats == 1:
        return "single_member"
    if seats is not None and seats > 1:
        return "multi_member"
    return "unknown_seat_structure"


def _target_party_vote_share(
    candidates: list[Mapping[str, object]], structure: str
) -> tuple[object | None, str]:
    if structure != "single_member":
        return None, "not_defined_for_multi_member_party_contest"
    if len(candidates) != 1:
        return None, "not_defined_multiple_candidates_for_party"
    value = candidates[0].get("analysis_vote_share")
    if value is None:
        return None, "unavailable_after_permitted_vote_share_layers"
    return value, "analysis_candidate_share_equals_single_member_party_share"


def _baseline_exclusion_reason(
    structure: str,
    candidates: list[Mapping[str, object]],
    previous_share: object | None,
    division_history: Mapping[str, object],
) -> str:
    if structure != "single_member":
        return "excluded_non_single_member_primary_estimand"
    if len(candidates) != 1:
        return "excluded_multiple_candidates_for_party"
    if division_history["baseline_eligibility"] != "approved_historical_reference":
        return "excluded_no_approved_historical_area_reference"
    if previous_share is None:
        return "excluded_no_approved_exact_label_previous_party_share"
    return "excluded_unclassified_integrity_review"


def _aggregate_yes_no(values: Iterable[object]) -> str:
    observed = list(values)
    if any(value == "Yes" for value in observed):
        return "Yes"
    if observed and all(value == "No" for value in observed):
        return "No"
    return "Unknown"


def _party_was_previous_winner(
    original_labels: list[str], standard_party_name: str, previous_winner: object
) -> bool | None:
    if previous_winner is None:
        return None
    return str(previous_winner) in {*original_labels, standard_party_name}


def _one_non_null_value(rows: list[Mapping[str, object]], field: str) -> object | None:
    values = {row.get(field) for row in rows if row.get(field) is not None}
    if len(values) > 1:
        raise ValueError(f"Party-contest candidates disagree on {field}: {values!r}")
    return next(iter(values)) if values else None


def _one_value(rows: list[Mapping[str, object]], field: str) -> object | None:
    values = {row.get(field) for row in rows}
    if len(values) > 1:
        return "mixed_within_party_contest"
    return next(iter(values))


def _max_numeric(values: Iterable[object]) -> float | int | None:
    numeric = [value for value in values if isinstance(value, (int, float))]
    return max(numeric) if numeric else None


def _assert_unique_ids(rows: list[Mapping[str, object]], table_name: str) -> None:
    ids = [str(row["party_contest_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate party_contest_id in {table_name} table.")


def _assert_feature_target_separation(features: list[Mapping[str, object]]) -> None:
    leaked = set().union(*(set(row) for row in features)) & TARGET_ONLY_FIELDS
    if leaked:
        raise ValueError(f"Target leakage fields found in party features: {sorted(leaked)!r}")


def _assert_historical_time_order(
    features: list[Mapping[str, object]], elections: Mapping[str, Mapping[str, object]]
) -> None:
    dates = {
        election_id: _parse_election_date(str(row["election_date"]))
        for election_id, row in elections.items()
    }
    for row in features:
        previous_id = row.get("previous_election_id")
        if previous_id is None:
            continue
        if dates[str(previous_id)] >= dates[str(row["election_id"])]:
            raise ValueError("No-news feature references a non-prior election event.")


def _assert_target_consistency(
    features: list[Mapping[str, object]], targets: list[Mapping[str, object]]
) -> None:
    """Reconcile party targets to the official contest structure.

    Published percentages are often rounded to whole numbers, so a complete
    single-member contest may sum to 99, 100, 101 or, rarely, 102. Values
    outside that narrow publication tolerance are treated as an integrity
    failure rather than silently renormalised.
    """

    feature_by_id = {str(row["party_contest_id"]): row for row in features}
    by_area: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for target in targets:
        feature = feature_by_id[str(target["party_contest_id"])]
        for field in ("target_party_vote_share", "target_best_candidate_vote_share"):
            value = target.get(field)
            if value is not None and not 0 <= float(value) <= 100:
                raise ValueError(f"{field} is outside 0-100.")
        previous_share = feature.get("previous_party_vote_share")
        if previous_share is not None and not 0 <= float(previous_share) <= 100:
            raise ValueError("previous_party_vote_share is outside 0-100.")
        if (target["target_party_seats_won"] > 0) != (
            target["target_party_elected"] == "Yes"
        ):
            raise ValueError("Party elected target disagrees with party seats won.")
        by_area[(str(target["election_id"]), str(target["division_id"]))].append(target)

    for area_targets in by_area.values():
        feature = feature_by_id[str(area_targets[0]["party_contest_id"])]
        seats = feature["analysis_number_of_seats"]
        if seats is not None and sum(
            int(target["target_party_seats_won"]) for target in area_targets
        ) != seats:
            raise ValueError("Party target seats do not reconcile to available seats.")
        if feature["contest_structure"] == "single_member":
            total_share = sum(float(target["target_party_vote_share"]) for target in area_targets)
            if not 98 <= total_share <= 102:
                raise ValueError(
                    "Single-member party shares fall outside publication-rounding tolerance."
                )


def _parse_election_date(value: str) -> datetime:
    for date_format in ("%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    raise ValueError(f"Unsupported election date: {value!r}")


def _coverage_audit(
    features: list[Mapping[str, object]], targets: list[Mapping[str, object]]
) -> dict[str, int]:
    audit = Counter()
    target_by_id = {str(row["party_contest_id"]): row for row in targets}
    for row in features:
        audit["party_contest_rows"] += 1
        audit[f"structure_{row['contest_structure']}"] += 1
        audit[f"eligibility_{row['baseline_eligibility']}"] += 1
        target = target_by_id[str(row["party_contest_id"])]
        if target["target_party_vote_share"] is not None:
            audit["target_party_vote_share_available"] += 1
        if row["previous_party_vote_share"] is not None:
            audit["previous_party_vote_share_available"] += 1
        if target["target_party_elected"] != "Unknown":
            audit["target_party_elected_resolved"] += 1
    return dict(sorted(audit.items()))
