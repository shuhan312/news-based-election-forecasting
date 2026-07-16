"""Build an evidence-gated historical baseline before any news modelling.

The layer is deliberately read-only over completed election and geographic
outputs.  It creates only historical information that was available before a
2026 ward result: source values, deterministic same-area summaries, and
explicitly unavailable fields.  It never redistributes votes, resolves a
candidate identity from a name, or promotes a partial crosswalk to a direct
electoral comparison.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from election_extractor.election_history import build_election_history


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CROSSWALK_RESOLUTION_PATH = (
    PROJECT_ROOT
    / "outputs/geographic_crosswalk_resolution/geographic_crosswalk_resolution_dataset.json"
)

DIRECT_STATUS = "accepted_direct"
PARTIAL_STATUS = "partial_crosswalk_available"
NOT_COMPARABLE_STATUS = "not_comparable"
REQUIRES_REVIEW_STATUS = "requires_review"
TARGET_ELECTION_PREFIX = "surrey-county-council-2026-"

# These features are unavailable regardless of a ward's mapping status.  They
# require inference, vote redistribution, or a verified personal identity that
# the completed source data does not provide.
ALWAYS_BLOCKED_FEATURES = (
    "vote_redistribution",
    "party_vote_share_change",
    "party_swing",
    "incumbency_transfer",
    "candidate_identity_transfer",
    "predecessor_councillor_transfer",
)
GEOGRAPHY_BLOCKED_FEATURES = (
    "previous_election_event",
    "previous_winning_party",
    "previous_winner_status",
    "previous_winning_candidate_vote_share",
    "previous_turnout",
    "previous_competitiveness",
    "area_specific_party_history",
)


FEATURE_SCHEMA: tuple[dict[str, str], ...] = (
    {
        "feature_name": "election_date",
        "feature_group": "source",
        "definition": "Published date of the target election event.",
        "source": "Completed official election event record.",
        "derivation_logic": "Copied unchanged.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "Remain NULL if unavailable in the source record.",
    },
    {
        "feature_name": "election_type",
        "feature_group": "source",
        "definition": "Configured type of the target election event.",
        "source": "Completed election configuration and event record.",
        "derivation_logic": "Copied unchanged.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "Remain NULL; never inferred from a year.",
    },
    {
        "feature_name": "number_of_candidates",
        "feature_group": "deterministically_derived",
        "definition": "Number of published candidate rows in the target ward.",
        "source": "Official target result-page candidate rows.",
        "derivation_logic": "Count candidate rows for one target area ID.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "NULL when candidate rows are unavailable; never zero-filled.",
    },
    {
        "feature_name": "number_of_parties_contesting",
        "feature_group": "deterministically_derived",
        "definition": "Number of distinct original published party labels in the target ward.",
        "source": "Official target result-page candidate rows.",
        "derivation_logic": "Count distinct non-null original party labels only.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "NULL when candidate rows are unavailable.",
    },
    {
        "feature_name": "number_of_seats",
        "feature_group": "source",
        "definition": "Official Seats value published for the target ward.",
        "source": "Official Voting Summary on the target result page.",
        "derivation_logic": "Consensus of unchanged source values across candidate rows.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "Remain NULL; never derived from election year or winners.",
    },
    {
        "feature_name": "candidate_competition_level",
        "feature_group": "deterministically_derived",
        "definition": "Single, two-candidate or multi-candidate contest indicator.",
        "source": "Official target candidate rows.",
        "derivation_logic": "Classify only the published candidate-row count.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "NULL when the count is unavailable.",
    },
    {
        "feature_name": "party_competition_level",
        "feature_group": "deterministically_derived",
        "definition": "Single, two-party or multi-party contest indicator.",
        "source": "Original official party labels in target candidate rows.",
        "derivation_logic": "Classify only the distinct published-party count.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "NULL when party labels are unavailable.",
    },
    {
        "feature_name": "turnout_available",
        "feature_group": "source_availability",
        "definition": "Whether an official turnout value is published for the target ward.",
        "source": "Official Voting Summary on the target result page.",
        "derivation_logic": "True only where all source rows agree on one non-null value.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "False/NULL reports availability only and never substitutes a turnout.",
    },
    {
        "feature_name": "electorate_available",
        "feature_group": "source_availability",
        "definition": "Whether an official electorate value is published for the target ward.",
        "source": "Official Voting Summary on the target result page.",
        "derivation_logic": "True only where all source rows agree on one non-null value.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "Reports availability only; no electorate is substituted.",
    },
    {
        "feature_name": "rejected_ballot_available",
        "feature_group": "source_availability",
        "definition": "Whether an official rejected-ballot value is published for the target ward.",
        "source": "Official Voting Summary on the target result page.",
        "derivation_logic": "True only where all source rows agree on one non-null value.",
        "geographic_requirements": "None.",
        "missing_value_behaviour": "Reports availability only; no rejected-ballot total is substituted.",
    },
    {
        "feature_name": "geographic_status",
        "feature_group": "source_governance",
        "definition": "Reviewed status of a historical-to-2026 geographic relationship.",
        "source": "Geographic Crosswalk Resolution Layer.",
        "derivation_logic": "Read unchanged from reviewed mapping evidence using the documented status hierarchy.",
        "geographic_requirements": "Not applicable; this field documents the requirement.",
        "missing_value_behaviour": "Use unmapped when no reviewed relationship is present; never infer one by name.",
    },
    {
        "feature_name": "historical_baseline_available",
        "feature_group": "source_governance",
        "definition": "Whether direct historical comparison fields may be used for a target ward.",
        "source": "Reviewed Geographic Crosswalk Resolution Layer.",
        "derivation_logic": "True only for exactly one accepted_direct mapping with explicit previous-winner permission.",
        "geographic_requirements": "Exactly one accepted_direct mapping and previous_winner_allowed=true.",
        "missing_value_behaviour": "False for all blocked, ambiguous or unmapped relationships.",
    },
    {
        "feature_name": "previous_election_event",
        "feature_group": "direct_geographic_reference",
        "definition": "Latest prior principal election for the approved directly matching historical area.",
        "source": "Official historical result data plus accepted_direct geographic evidence.",
        "derivation_logic": "Select the latest earlier principal event for exactly the mapped historical area.",
        "geographic_requirements": "Exactly one accepted_direct mapping with explicit previous-winner permission.",
        "missing_value_behaviour": "NULL for partial, not comparable, requires-review or absent mappings.",
    },
    {
        "feature_name": "previous_winning_party",
        "feature_group": "direct_geographic_reference",
        "definition": "Original published party label of one source-reported elected candidate in the prior event.",
        "source": "Official historical candidate outcome and party fields.",
        "derivation_logic": "Expose only when exactly one source-reported elected candidate exists; no vote ranking is calculated.",
        "geographic_requirements": "Exactly one accepted_direct mapping with explicit previous-winner permission.",
        "missing_value_behaviour": "NULL if geography or winner evidence is not unambiguous.",
    },
    {
        "feature_name": "previous_winning_candidate_vote_share",
        "feature_group": "direct_geographic_reference",
        "definition": "Published vote share of the source-reported elected candidate in the prior event.",
        "source": "Official historical candidate result row.",
        "derivation_logic": "Copied from the selected elected candidate; no change or swing is calculated.",
        "geographic_requirements": "Exactly one accepted_direct mapping with explicit previous-winner permission.",
        "missing_value_behaviour": "Remain NULL when unavailable.",
    },
    {
        "feature_name": "previous_turnout",
        "feature_group": "direct_geographic_reference",
        "definition": "Official turnout published for the latest earlier principal event in the mapped area.",
        "source": "Official historical Voting Summary.",
        "derivation_logic": "Retain one shared source value across the earlier event's candidate rows.",
        "geographic_requirements": "Exactly one accepted_direct mapping with explicit previous-winner permission.",
        "missing_value_behaviour": "Remain NULL if the official source did not publish turnout.",
    },
    {
        "feature_name": "previous_competitiveness",
        "feature_group": "direct_geographic_reference",
        "definition": "Candidate and party counts for the latest earlier principal event in the mapped area.",
        "source": "Official historical candidate rows.",
        "derivation_logic": "Count published rows and exact original party labels; no vote ordering is calculated.",
        "geographic_requirements": "Exactly one accepted_direct mapping with explicit previous-winner permission.",
        "missing_value_behaviour": "Remain NULL if earlier candidate rows are unavailable.",
    },
    {
        "feature_name": "party_previously_contested",
        "feature_group": "direct_geographic_reference",
        "definition": "Whether the exact original party label previously contested in the directly mapped historical area.",
        "source": "Official target and prior candidate party labels.",
        "derivation_logic": "Compare exact labels across earlier principal events in one approved direct lineage.",
        "geographic_requirements": "Exactly one accepted_direct mapping with explicit previous-winner permission.",
        "missing_value_behaviour": "NULL rather than false where geography is unresolved.",
    },
    {
        "feature_name": "candidate_appeared_in_previous_events",
        "feature_group": "unavailable",
        "definition": "Personal candidate continuity across events.",
        "source": "No explicit candidate identifier is present in completed source data.",
        "derivation_logic": "No name-only matching is permitted.",
        "geographic_requirements": "A direct area mapping alone is insufficient without explicit identity evidence.",
        "missing_value_behaviour": "Always NULL/unresolved in this layer.",
    },
    {
        "feature_name": "first_observed_appearance",
        "feature_group": "direct_geographic_reference",
        "definition": "Whether an exact original party label has no earlier recorded contest in the approved direct lineage.",
        "source": "Official target and earlier candidate party labels.",
        "derivation_logic": "Compare exact original labels across earlier principal events only.",
        "geographic_requirements": "Exactly one accepted_direct mapping.",
        "missing_value_behaviour": "NULL rather than true/false where geography is unresolved.",
    },
    {
        "feature_name": "party_vote_share_change",
        "feature_group": "unavailable",
        "definition": "Change in party vote share between elections.",
        "source": "Not generated in this layer.",
        "derivation_logic": "Blocked to prevent unsupported comparison or redistribution.",
        "geographic_requirements": "Not applicable.",
        "missing_value_behaviour": "Always NULL/unavailable.",
    },
)


def _normalise_area_name(name: str) -> str:
    """Normalise only terminal display suffixes; never fuzzy-match a place name."""

    collapsed = " ".join(name.casefold().split())
    return re.sub(r"\s+(?:ed|ward)$", "", collapsed)


def _present(value: object) -> bool:
    """Distinguish a published zero from a missing or blank source value."""

    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _consensus(values: Iterable[object]) -> object | None:
    """Return an unchanged shared value, otherwise preserve uncertainty as NULL."""

    observed = []
    for value in values:
        if _present(value) and value not in observed:
            observed.append(value)
    return observed[0] if len(observed) == 1 else None


def _competition_level(count: int | None, unit: str) -> str | None:
    """Describe observed contest size without using votes, ranks or predictions."""

    if count is None:
        return None
    if count == 1:
        return f"single_{unit}"
    if count == 2:
        return "two_parties" if unit == "party" else f"two_{unit}s"
    return "multi_parties" if unit == "party" else f"multi_{unit}s"


def load_crosswalk_resolution(
    path: str | Path = DEFAULT_CROSSWALK_RESOLUTION_PATH,
) -> tuple[dict[str, object], ...]:
    """Load reviewed GIS evidence; this function never reclassifies its rows."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("resolution_rows"), list):
        raise ValueError("Geographic crosswalk resolution output requires resolution_rows.")
    rows = []
    for row in payload["resolution_rows"]:
        if not isinstance(row, Mapping):
            raise ValueError("Geographic crosswalk resolution rows must be objects.")
        if row.get("analytical_status") not in {
            DIRECT_STATUS,
            PARTIAL_STATUS,
            NOT_COMPARABLE_STATUS,
            REQUIRES_REVIEW_STATUS,
        }:
            raise ValueError("Geographic crosswalk row has an unsupported analytical status.")
        rows.append(dict(row))
    return tuple(rows)


def classify_geographic_status(rows: Sequence[Mapping[str, object]]) -> str:
    """Apply the approved status hierarchy without turning partial data into direct data.

    An accepted-direct row is usable even if a separate low-overlap relationship
    was retained for audit.  If no direct row exists, partial, review and
    not-comparable evidence remain distinct blocked categories.
    """

    statuses = {row.get("analytical_status") for row in rows}
    if DIRECT_STATUS in statuses:
        return DIRECT_STATUS
    if PARTIAL_STATUS in statuses:
        return PARTIAL_STATUS
    if REQUIRES_REVIEW_STATUS in statuses:
        return REQUIRES_REVIEW_STATUS
    if NOT_COMPARABLE_STATUS in statuses:
        return NOT_COMPARABLE_STATUS
    return "unmapped"


def _relationships_by_target(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], tuple[dict[str, object], ...]]:
    """Index every retained GIS relationship by its published 2026 ward label."""

    indexed: defaultdict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        election_id = row.get("current_election_id")
        area_name = row.get("current_area_name")
        if not isinstance(election_id, str) or not isinstance(area_name, str):
            raise ValueError("Geographic crosswalk row requires current election and area names.")
        indexed[(election_id, _normalise_area_name(area_name))].append(dict(row))
    return {key: tuple(value) for key, value in indexed.items()}


def _target_events(history: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """Return only the two separate 2026 election regions as feature targets."""

    raw_events = history.get("election_events")
    if not isinstance(raw_events, list):
        raise ValueError("Election event history requires election_events.")
    targets = [
        dict(event)
        for event in raw_events
        if isinstance(event, Mapping)
        and isinstance(event.get("election_id"), str)
        and str(event["election_id"]).startswith(TARGET_ELECTION_PREFIX)
        and event.get("election_type") == "principal_election"
    ]
    if not targets:
        raise ValueError("Election event history contains no configured 2026 target wards.")
    return tuple(sorted(targets, key=lambda row: (str(row["election_id"]), str(row["area_name"]))))


def _records_by_area(history: Mapping[str, object]) -> dict[str, tuple[dict[str, object], ...]]:
    """Group unchanged canonical candidate rows by their source area identifier."""

    raw_records = history.get("canonical_candidate_results")
    if not isinstance(raw_records, list):
        raise ValueError("Election event history requires canonical_candidate_results.")
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for record in raw_records:
        if not isinstance(record, Mapping) or not isinstance(record.get("area_id"), str):
            raise ValueError("Canonical candidate records require an area_id.")
        grouped[str(record["area_id"])].append(dict(record))
    return {area_id: tuple(rows) for area_id, rows in grouped.items()}


def _historical_events_for_direct_mapping(
    history: Mapping[str, object],
    previous_area_name: str,
    target_date: str,
) -> tuple[dict[str, object], ...]:
    """Find earlier principal events for exactly one reviewed historical area label."""

    expected_key = f"historical:{_normalise_area_name(previous_area_name)}"
    events = history.get("election_events")
    if not isinstance(events, list):
        raise ValueError("Election event history requires election_events.")
    matched = [
        dict(event)
        for event in events
        if isinstance(event, Mapping)
        and event.get("election_type") == "principal_election"
        and event.get("geographic_identity_key") == expected_key
        and isinstance(event.get("election_date"), str)
        and str(event["election_date"]) < target_date
    ]
    return tuple(sorted(matched, key=lambda row: (str(row["election_date"]), str(row["election_id"]))))


def _structure_features(
    event: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Create same-event structure features without a geographic comparison."""

    record_count = len(records) if records else None
    parties = {
        str(record["original_party_name"])
        for record in records
        if _present(record.get("original_party_name"))
    }
    party_count = len(parties) if records else None
    values = {
        "election_date": event.get("election_date"),
        "election_type": event.get("election_type"),
        "number_of_candidates": record_count,
        "number_of_parties_contesting": party_count,
        "number_of_seats": _consensus(record.get("seats") for record in records),
        "candidate_competition_level": _competition_level(record_count, "candidate"),
        "party_competition_level": _competition_level(party_count, "party"),
        "turnout_available": _consensus(record.get("turnout") for record in records) is not None if records else None,
        "electorate_available": _consensus(record.get("electorate") for record in records) is not None if records else None,
        "rejected_ballot_available": _consensus(record.get("ballot_papers_rejected") for record in records) is not None if records else None,
    }
    return {
        **values,
        "feature_provenance": {
            "election_date": "source_reported",
            "election_type": "source_reported",
            "number_of_candidates": "deterministically_derived" if records else "unavailable",
            "number_of_parties_contesting": "deterministically_derived" if records else "unavailable",
            "number_of_seats": "source_reported" if values["number_of_seats"] is not None else "unavailable",
            "candidate_competition_level": "deterministically_derived" if record_count is not None else "unavailable",
            "party_competition_level": "deterministically_derived" if party_count is not None else "unavailable",
            # Availability is calculated from source values, so it is distinct
            # from the official turnout, electorate or rejected-ballot value.
            "turnout_available": "deterministically_derived" if records else "unavailable",
            "electorate_available": "deterministically_derived" if records else "unavailable",
            "rejected_ballot_available": "deterministically_derived" if records else "unavailable",
        },
    }


def _direct_reference_features(
    *,
    target_event: Mapping[str, object],
    direct_mapping: Mapping[str, object] | None,
    history: Mapping[str, object],
    records_by_area: Mapping[str, Sequence[Mapping[str, object]]],
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    """Create prior-event references only from one explicitly permitted mapping."""

    unavailable = {
        "previous_election_event_id": None,
        "previous_election_date": None,
        "previous_area_name": None,
        "previous_winner_status": None,
        "previous_winning_candidate_name": None,
        "previous_winning_party": None,
        "previous_winning_party_standardised": None,
        "previous_winning_candidate_vote_share": None,
        "previous_turnout": None,
        "previous_electorate": None,
        "previous_number_of_candidates": None,
        "previous_number_of_parties": None,
        "previous_candidate_competition_level": None,
        "source_election_id": None,
        "source_result_url": None,
        "geographic_mapping_id": None,
        "geographic_evidence": None,
        "derivation_method": "unavailable_without_one_accepted_direct_mapping",
        "provenance": "unavailable",
    }
    if direct_mapping is None:
        return unavailable, ()
    previous_name = direct_mapping.get("previous_area_name")
    target_date = target_event.get("election_date")
    if not isinstance(previous_name, str) or not isinstance(target_date, str):
        raise ValueError("Accepted direct mapping and target event require published area names and dates.")
    candidates = _historical_events_for_direct_mapping(history, previous_name, target_date)
    if not candidates:
        # The geographic relationship is valid, but source-election evidence is
        # still absent.  This remains a NULL feature rather than a fallback.
        return {
            **unavailable,
            "previous_area_name": previous_name,
            "geographic_mapping_id": direct_mapping.get("mapping_id"),
            "geographic_evidence": direct_mapping.get("evidence_summary"),
            "derivation_method": "accepted_direct_mapping_has_no_prior_principal_event",
        }, ()
    previous_event = candidates[-1]
    previous_records = tuple(records_by_area.get(str(previous_event["area_id"]), ()))
    elected = [
        record
        for record in previous_records
        if isinstance(record.get("elected_status"), str)
        and str(record["elected_status"]).casefold() == "elected"
    ]
    winner = elected[0] if len(elected) == 1 else None
    party_names = {
        str(record["original_party_name"])
        for record in previous_records
        if _present(record.get("original_party_name"))
    }
    candidate_count = len(previous_records) if previous_records else None
    return (
        {
            "previous_election_event_id": previous_event.get("election_id"),
            "previous_election_date": previous_event.get("election_date"),
            "previous_area_name": previous_event.get("area_name"),
            "previous_winner_status": winner.get("elected_status") if winner else None,
            "previous_winning_candidate_name": winner.get("candidate_name") if winner else None,
            "previous_winning_party": winner.get("original_party_name") if winner else None,
            "previous_winning_party_standardised": winner.get("standardised_party_name") if winner else None,
            "previous_winning_candidate_vote_share": winner.get("vote_share") if winner else None,
            "previous_turnout": _consensus(record.get("turnout") for record in previous_records),
            "previous_electorate": _consensus(record.get("electorate") for record in previous_records),
            "previous_number_of_candidates": candidate_count,
            "previous_number_of_parties": len(party_names) if previous_records else None,
            "previous_candidate_competition_level": _competition_level(candidate_count, "candidate"),
            "source_election_id": previous_event.get("election_id"),
            "source_result_url": previous_event.get("source_url"),
            "geographic_mapping_id": direct_mapping.get("mapping_id"),
            "geographic_evidence": direct_mapping.get("evidence_summary"),
            "derivation_method": "latest_prior_principal_event_in_one_accepted_direct_historical_area",
            "source_value_provenance": "source_reported",
            "provenance": "deterministically_derived",
        },
        previous_records,
    )


def _party_history_features(
    *,
    target_event: Mapping[str, object],
    target_records: Sequence[Mapping[str, object]],
    previous_records: Sequence[Mapping[str, object]],
    direct_available: bool,
) -> tuple[dict[str, object], ...]:
    """Create exact-label party-presence features without party alias inference."""

    grouped: defaultdict[tuple[object, object], list[Mapping[str, object]]] = defaultdict(list)
    for record in target_records:
        grouped[(record.get("original_party_name"), record.get("standardised_party_name"))].append(record)
    rows = []
    for (original_party, standardised_party), current_rows in sorted(
        grouped.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
    ):
        if not isinstance(original_party, str) or not original_party.strip():
            rows.append(
                {
                    "area_id": target_event["area_id"],
                    "election_id": target_event["election_id"],
                    "original_party_name": original_party,
                    "standardised_party_name": standardised_party,
                    "target_candidate_row_count": len(current_rows),
                    "party_previously_contested": None,
                    "previous_election_participation_count": None,
                    "first_observed_appearance": None,
                    "first_observed_event_id": None,
                    "first_observed_event_date": None,
                    "provenance": "unavailable",
                    "reason": "missing_original_published_party_name",
                }
            )
            continue
        if not direct_available:
            rows.append(
                {
                    "area_id": target_event["area_id"],
                    "election_id": target_event["election_id"],
                    "original_party_name": original_party,
                    "standardised_party_name": standardised_party,
                    "target_candidate_row_count": len(current_rows),
                    "party_previously_contested": None,
                    "previous_election_participation_count": None,
                    "first_observed_appearance": None,
                    "first_observed_event_id": None,
                    "first_observed_event_date": None,
                    "provenance": "unavailable",
                    "reason": "area_specific_history_blocked_by_geographic_status",
                }
            )
            continue
        prior = [
            record for record in previous_records if record.get("original_party_name") == original_party
        ]
        prior_events = sorted(
            {(str(record["election_id"]), str(record["election_date"])) for record in prior},
            key=lambda item: (item[1], item[0]),
        )
        first = prior_events[0] if prior_events else None
        rows.append(
            {
                "area_id": target_event["area_id"],
                "election_id": target_event["election_id"],
                "original_party_name": original_party,
                "standardised_party_name": standardised_party,
                "target_candidate_row_count": len(current_rows),
                "party_previously_contested": bool(prior_events),
                "previous_election_participation_count": len(prior_events),
                "first_observed_appearance": not prior_events,
                "first_observed_event_id": first[0] if first else None,
                "first_observed_event_date": first[1] if first else None,
                "provenance": "deterministically_derived",
                "source_value_provenance": "source_reported",
                "reason": "exact_original_party_label_in_accepted_direct_historical_lineage",
            }
        )
    return tuple(rows)


def _candidate_history_infrastructure(
    target_records: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Expose candidate-history fields as unresolved without matching names."""

    return tuple(
        {
            "candidate_result_id": record.get("candidate_result_id"),
            "area_id": record.get("area_id"),
            "election_id": record.get("election_id"),
            "candidate_name": record.get("candidate_name"),
            "candidate_identity_status": "unresolved_no_explicit_identifier",
            "candidate_appeared_in_previous_events": None,
            "previous_election_events_contested": None,
            "incumbent_candidate": None,
            "returning_councillor": None,
            "predecessor_councillor": None,
            "provenance": "unavailable",
            "reason": "identical_names_are_not_treated_as_identity_evidence",
        }
        for record in target_records
    )


def build_historical_baseline_features(
    *,
    history: Mapping[str, object] | None = None,
    crosswalk_resolution_path: str | Path = DEFAULT_CROSSWALK_RESOLUTION_PATH,
) -> dict[str, object]:
    """Build 2026 historical baseline features under all project safeguards."""

    event_history = history if history is not None else build_election_history()
    crosswalk_rows = load_crosswalk_resolution(crosswalk_resolution_path)
    target_relationships = _relationships_by_target(crosswalk_rows)
    records_by_area = _records_by_area(event_history)

    feature_rows = []
    readiness_rows = []
    party_rows = []
    candidate_rows = []
    for target in _target_events(event_history):
        key = (str(target["election_id"]), _normalise_area_name(str(target["area_name"])))
        relationships = target_relationships.get(key, ())
        geographic_status = classify_geographic_status(relationships)
        direct_rows = [
            row for row in relationships if row.get("analytical_status") == DIRECT_STATUS
        ]
        # GIS comparability and permission to transfer election-history fields
        # are distinct decisions.  ``accepted_direct`` means that the spatial
        # criteria passed; the crosswalk still requires an explicit true value
        # for ``previous_winner_allowed`` before this layer exposes a prior
        # winner, turnout or party-history value.  This prevents a technical
        # boundary decision from silently becoming an electoral assumption.
        permitted_direct_rows = [
            row for row in direct_rows if row.get("previous_winner_allowed") is True
        ]
        # One and only one explicitly permitted direct row is required.
        # Multiple candidates are a mapping ambiguity, not a choice to resolve.
        direct_mapping = (
            permitted_direct_rows[0] if len(permitted_direct_rows) == 1 else None
        )
        direct_available = direct_mapping is not None
        target_records = records_by_area.get(str(target["area_id"]), ())
        structure = _structure_features(target, target_records)
        reference, previous_records = _direct_reference_features(
            target_event=target,
            direct_mapping=direct_mapping,
            history=event_history,
            records_by_area=records_by_area,
        )
        support = [
            {
                "mapping_id": row.get("mapping_id"),
                "analytical_status": row.get("analytical_status"),
                "previous_area_name": row.get("previous_area_name"),
                "evidence_summary": row.get("evidence_summary"),
                "GIS_source": row.get("GIS_source"),
                "boundary_source": row.get("boundary_source"),
            }
            for row in relationships
        ]
        blocked = list(ALWAYS_BLOCKED_FEATURES)
        if not direct_available:
            blocked.extend(GEOGRAPHY_BLOCKED_FEATURES)
        feature_rows.append(
            {
                "area_id": target["area_id"],
                "area_name": target["area_name"],
                "election_id": target["election_id"],
                "geographic_status": geographic_status,
                "historical_baseline_available": direct_available,
                "structure_features": structure,
                "direct_historical_reference": reference,
                "blocked_features": blocked,
                "supporting_geographic_relationships": support,
                "provenance": "deterministically_derived" if direct_available else "unavailable",
            }
        )
        readiness_rows.append(
            {
                "area_id": target["area_id"],
                "area_name": target["area_name"],
                "election_id": target["election_id"],
                "geographic_status": geographic_status,
                "historical_relationship_exists": bool(relationships),
                "historical_baseline_available": direct_available,
                "available_historical_features": [
                    name
                    for name in (
                        "previous_election_event",
                        "previous_winning_party",
                        "previous_winner_status",
                        "previous_winning_candidate_vote_share",
                        "previous_turnout",
                        "previous_competitiveness",
                    )
                    if reference.get(
                        {
                            "previous_election_event": "previous_election_event_id",
                            "previous_winning_party": "previous_winning_party",
                            "previous_winner_status": "previous_winner_status",
                            "previous_winning_candidate_vote_share": "previous_winning_candidate_vote_share",
                            "previous_turnout": "previous_turnout",
                            "previous_competitiveness": "previous_number_of_candidates",
                        }[name]
                    ) is not None
                ],
                "blocked_features": blocked,
                "evidence_source": support,
            }
        )
        party_rows.extend(
            _party_history_features(
                target_event=target,
                target_records=target_records,
                previous_records=previous_records,
                direct_available=direct_available,
            )
        )
        candidate_rows.extend(_candidate_history_infrastructure(target_records))

    return {
        "schema_version": "1.0",
        "scope": "Historical election baseline only; no news features, prediction, redistribution, swing or incumbency inference.",
        "feature_schema": list(FEATURE_SCHEMA),
        "baseline_feature_table": feature_rows,
        "party_history_features": party_rows,
        "candidate_history_infrastructure": candidate_rows,
        "baseline_readiness_dataset": readiness_rows,
        "safeguards": {
            "direct_geographic_requirement": "Only one accepted_direct relationship with previous_winner_allowed=true can enable historical comparison features.",
            "blocked_geographic_statuses": [PARTIAL_STATUS, NOT_COMPARABLE_STATUS, REQUIRES_REVIEW_STATUS],
            "always_blocked_features": list(ALWAYS_BLOCKED_FEATURES),
            "candidate_identity_rule": "No candidate history is created from an identical name alone.",
            "party_rule": "Original party labels are preserved; UK Independence Party and Reform UK remain separate.",
            "missing_value_rule": "Unavailable values remain NULL and are never replaced with zero.",
        },
    }


def baseline_feature_dictionary_markdown() -> str:
    """Render the documented schema required before any future news experiment."""

    lines = [
        "# Historical Baseline Feature Dictionary",
        "",
        "The baseline represents election-history information available before adding news context. It is not a prediction model and it does not calculate vote redistribution, change, swing or incumbency.",
        "",
        "| Feature | Group | Definition | Source | Derivation | Geographic requirement | Missing-value behaviour |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        "| {feature_name} | {feature_group} | {definition} | {source} | {derivation_logic} | {geographic_requirements} | {missing_value_behaviour} |".format(**row)
        for row in FEATURE_SCHEMA
    )
    lines.extend(
        [
            "",
            "`accepted_direct` is necessary but not sufficient for direct historical comparison: the reviewed row must also have `previous_winner_allowed=true`. `partial_crosswalk_available`, `not_comparable`, `requires_review`, and unpermitted direct rows remain visible as evidence but leave comparison features NULL. Candidate names are never used as identity keys; UK Independence Party and Reform UK are separate exact party labels.",
            "",
        ]
    )
    return "\n".join(lines)


def baseline_methodology_markdown() -> str:
    """Explain the research role and safeguards of the historical baseline."""

    return """# Historical Baseline Feature Layer Methodology

## Purpose

This layer creates the election-history-only baseline needed for a later test of whether news context adds predictive information beyond past election information. It does not collect news, train a model or make a prediction.

## Geographic rule

Only a single reviewed `accepted_direct` historical-to-2026 relationship with
`previous_winner_allowed=true` can expose a prior-event reference. This explicit
permission is separate from the GIS decision: an accepted spatial match alone
does not authorise election-history transfer. Partial crosswalk, not-comparable,
requires-review and unpermitted direct relationships are retained in the
readiness dataset as evidence, but cannot create prior-winner, prior-vote-share,
turnout-comparison, candidate-transfer or incumbency features.

## Source and missing-value rule

Official published values are copied unchanged. Same-event counts are marked `deterministically_derived`. Reviewed exact party mappings are marked `manually_confirmed` in their source records. Unsupported values remain `NULL` with `unavailable` provenance; they are never zero-filled.

## Party and candidate safeguards

Party presence uses exact original published party labels in an accepted direct lineage. UK Independence Party and Reform UK remain separate. Candidate history is infrastructure only: an identical candidate name is not evidence of a shared person, so candidate continuity, incumbency and predecessor fields remain unresolved.
"""
