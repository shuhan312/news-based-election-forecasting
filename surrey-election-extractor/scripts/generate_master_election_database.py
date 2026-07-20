"""Build a unified analytical payload from audited Surrey election outputs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Running this file directly should use the checked-out project package,
    # not depend on an external installation or an editor-specific PYTHONPATH.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.master_database import (
    PROJECT_ROOT,
    audit_summary_markdown,
    build_master_database,
    load_audited_elections,
    payload_as_dict,
    schema_documentation_markdown,
)
from election_extractor.candidate_continuity_evidence import (
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)
from election_extractor.historical_baseline import (
    build_historical_baseline_features,
    classify_geographic_status,
    load_crosswalk_resolution,
)
from election_extractor.historical_reference_permissions import (
    build_historical_reference_permission_audit,
    permission_records_by_mapping_id,
)
from election_extractor.principal_election_continuity import (
    build_principal_election_continuity_audit,
)
from election_extractor.by_election_historical_reference import (
    build_by_election_historical_reference_audit,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/master_surrey_election_database"
CROSSWALK_PATH = (
    PROJECT_ROOT
    / "outputs/geographic_crosswalk_resolution/geographic_crosswalk_resolution_dataset.json"
)


def reviewed_geographic_mapping_rows() -> tuple[dict[str, object], ...]:
    """Return one explicit lookup row for every 2026 ward.

    The 24 permission-approved direct relationships retain their detailed
    evidence. Every other ward receives one aggregated blocked-status row, so
    absence from the table cannot be mistaken for a missing extraction. This
    aggregation describes topology only and never redistributes votes.
    """

    crosswalk_rows = load_crosswalk_resolution(CROSSWALK_PATH)
    permission_audit = build_historical_reference_permission_audit(crosswalk_rows)
    permissions = permission_records_by_mapping_id(permission_audit)
    crosswalk_by_id = {str(row["mapping_id"]): row for row in crosswalk_rows}
    rows: list[dict[str, object]] = []
    for mapping_id, permission in sorted(permissions.items()):
        if permission["historical_reference_status"] != "approved_for_historical_reference":
            continue
        crosswalk = crosswalk_by_id[mapping_id]
        evidence_summary = str(crosswalk["evidence_summary"])
        rows.append(
            {
                "mapping_id": mapping_id,
                "previous_election_id": permission["previous_election_id"],
                "previous_area_id": permission["previous_area_id"],
                "previous_area_name": permission["previous_area_name"],
                "current_election_id": permission["current_election_id"],
                "current_area_name": permission["current_area_name"],
                "current_area_id": permission["current_area_id"],
                # This is the reviewed crosswalk relationship (for example,
                # ``exact``). It is distinct from the separate permission
                # decision below and must not be left blank in the workbook.
                "relationship_type": crosswalk["relationship_type"],
                # The permission audit explicitly permits analytical reference;
                # it does not assert that two electoral areas have the same
                # legal identity after the 2024 boundary change.
                "administrative_identity": "not_confirmed",
                "analytical_comparability": crosswalk["analytical_status"],
                "ward_lookup_status": "accepted_direct",
                "historical_vote_share_status": "available_from_approved_direct_mapping",
                "confidence": crosswalk["confidence"],
                "decision": permission["historical_reference_status"],
                "overlap_area_m2": crosswalk["intersection_area_m2"],
                "previous_area_overlap_percentage": round(
                    float(crosswalk["source_overlap_ratio"]) * 100, 6
                ),
                "current_area_overlap_percentage": round(
                    float(crosswalk["target_overlap_ratio"]) * 100, 6
                ),
                "largest_previous_area_competitor_percentage": None,
                "largest_current_area_competitor_percentage": None,
                # These booleans and competitor percentages are already written
                # by the reviewed crosswalk audit. Parsing those labelled values
                # copies audit output only; it does not calculate a new GIS rule.
                "geometry_valid": _evidence_boolean(
                    evidence_summary, "geometry_valid"
                ),
                "boundary_sources_consistent": _evidence_boolean(
                    evidence_summary, "boundary_sources_consistent"
                ),
                "GIS_source": crosswalk["GIS_source"],
                "boundary_source": crosswalk["boundary_source"],
                "evidence_notes": permission["uncertainty"],
                "reviewer_reason": crosswalk["decision_reason"],
                "evidence_summary": permission["evidence_summary"],
                "historical_reference_status": permission["historical_reference_status"],
                "previous_winner_allowed": permission["previous_winner_allowed"],
                "candidate_history_allowed": permission["candidate_history_allowed"],
                "incumbency_allowed": permission["incumbency_allowed"],
                "party_vote_share_change_allowed": permission[
                    "party_vote_share_change_allowed"
                ],
                "permission_source_urls": "; ".join(permission["source_urls"]),
                "permission_uncertainty": permission["uncertainty"],
            }
        )
    # The source audit contains 167 relationships; the workbook needs one row
    # per current ward. Group by stable IDs rather than by similar names.
    by_current_ward: dict[tuple[str, str], list[dict[str, object]]] = {}
    for crosswalk in crosswalk_rows:
        key = (str(crosswalk["current_election_id"]), str(crosswalk["current_area_id"]))
        by_current_ward.setdefault(key, []).append(crosswalk)

    approved_current_wards = {
        (str(row["current_election_id"]), str(row["current_area_id"])) for row in rows
    }
    for current_key, ward_relationships in sorted(by_current_ward.items()):
        if current_key in approved_current_wards:
            continue
        status = classify_geographic_status(ward_relationships)
        if status == "partial_crosswalk_available":
            lookup_status = "changed_boundary_not_directly_comparable"
            reviewer_reason = (
                "Official GIS shows a split, merge or many-to-many relationship; "
                "no audited electorate weight supports vote redistribution."
            )
        elif status == "requires_review":
            lookup_status = "insufficient_weighted_crosswalk_evidence"
            reviewer_reason = (
                "The best one-to-one candidate fails the approved direct criteria "
                "and no validated electorate-weighted crosswalk is available."
            )
        else:
            lookup_status = "historical_vote_share_unavailable"
            reviewer_reason = (
                "Reviewed GIS relationships are non-structural and cannot support "
                "a historical electoral comparison."
            )
        first = ward_relationships[0]
        previous_names = sorted({str(item["previous_area_name"]) for item in ward_relationships})
        mapping_ids = sorted(str(item["mapping_id"]) for item in ward_relationships)
        relationship_types = sorted({
            str(item["crosswalk_relationship_type"] or item["relationship_type"])
            for item in ward_relationships
        })
        rows.append({
            "mapping_id": f"ward-geographic-lookup:{current_key[0]}:{current_key[1]}",
            "previous_election_id": first["previous_election_id"],
            "previous_area_id": None,
            "previous_area_name": "; ".join(previous_names),
            "current_election_id": current_key[0],
            "current_area_name": first["current_area_name"],
            "current_area_id": current_key[1],
            "relationship_type": "; ".join(relationship_types),
            "administrative_identity": "not_confirmed",
            "analytical_comparability": status,
            "ward_lookup_status": lookup_status,
            "historical_vote_share_status": "unavailable_after_gis_review",
            "confidence": "medium" if status == "partial_crosswalk_available" else "low",
            "decision": "blocked_from_direct_historical_reference",
            "overlap_area_m2": None,
            "previous_area_overlap_percentage": None,
            "current_area_overlap_percentage": None,
            "largest_previous_area_competitor_percentage": None,
            "largest_current_area_competitor_percentage": None,
            "geometry_valid": all(
                "geometry_valid=True" in str(item["evidence_summary"])
                for item in ward_relationships
            ),
            "boundary_sources_consistent": all(
                "boundary_sources_consistent=True" in str(item["evidence_summary"])
                for item in ward_relationships
            ),
            "GIS_source": "; ".join(sorted({str(item["GIS_source"]) for item in ward_relationships})),
            "boundary_source": "; ".join(sorted({str(item["boundary_source"]) for item in ward_relationships})),
            "evidence_notes": (
                f"{len(ward_relationships)} reviewed GIS relationship(s): "
                f"{'; '.join(mapping_ids)}."
            ),
            "reviewer_reason": reviewer_reason,
            "evidence_summary": (
                "Ward-level status aggregated from the complete relationship audit; "
                "numeric overlaps remain in the source GIS dataset."
            ),
            "historical_reference_status": lookup_status,
            "previous_winner_allowed": False,
            "candidate_history_allowed": False,
            "incumbency_allowed": False,
            "party_vote_share_change_allowed": False,
            "permission_source_urls": "",
            "permission_uncertainty": "No direct historical value is authorised for this ward.",
        })
    rows.sort(key=lambda row: (str(row["current_election_id"]), str(row["current_area_name"])))
    if len(rows) != 81:
        raise ValueError(f"Geographic lookup must contain all 81 current wards; found {len(rows)}.")
    return tuple(rows)


def _evidence_boolean(summary: str, label: str) -> bool | None:
    """Read one explicitly labelled boolean from a reviewed audit summary."""

    match = re.search(rf"\\b{re.escape(label)}=(True|False)\\b", summary)
    if match is None:
        return None
    return match.group(1) == "True"


def reviewed_historical_reference_inputs() -> tuple[
    dict[tuple[str, str], dict[str, object]],
    dict[tuple[str, str, str], dict[str, object]],
]:
    """Return only permission-approved historical values for the master tables.

    The historical baseline layer supplies the 24 separately reviewed
    2021-to-2026 relationships.  The legal-continuity audit supplies the
    explicit 2013-to-2017 and 2017-to-2021 relationships.  Both inputs remain
    evidence-gated, are keyed by exact published area names and deliberately
    do not attempt candidate matching or party-total reconstruction.
    """

    baseline = build_historical_baseline_features()
    area_keys: dict[str, tuple[str, str]] = {}
    division_references: dict[tuple[str, str], dict[str, object]] = {}
    for row in baseline["baseline_feature_table"]:
        election_id = row.get("election_id")
        area_id = row.get("area_id")
        area_name = row.get("area_name")
        reference = row.get("direct_historical_reference")
        if not isinstance(election_id, str) or not isinstance(area_id, str) or not isinstance(area_name, str):
            raise ValueError("Historical baseline rows require election, area ID and area name.")
        area_keys[area_id] = (election_id, area_name)
        if not isinstance(reference, dict):
            raise ValueError("Historical baseline rows require direct_historical_reference.")
        if reference.get("historical_reference_status") != "approved_for_historical_reference":
            continue
        key = (election_id, area_name)
        if key in division_references:
            raise ValueError(f"Duplicate approved historical reference for {key}.")
        division_references[key] = dict(reference)

    party_references: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in baseline["party_history_features"]:
        if row.get("provenance") != "deterministically_derived":
            continue
        area_id = row.get("area_id")
        party_name = row.get("original_party_name")
        if not isinstance(area_id, str) or not isinstance(party_name, str):
            raise ValueError("Approved party-history rows require an area ID and party name.")
        area_key = area_keys.get(area_id)
        if area_key is None or area_key not in division_references:
            raise ValueError("Approved party history requires an approved division reference.")
        key = (*area_key, party_name)
        if key in party_references:
            raise ValueError(f"Duplicate approved party-history reference for {key}.")
        party_references[key] = dict(row)
    # Pre-2024 principal elections are not a GIS shortcut for the 2026
    # crosswalk.  Their own statutory continuity audit proves only the two
    # adjacent transitions whose exact published division names are verified.
    continuity = build_principal_election_continuity_audit()
    continuity_references = continuity["division_references"]
    if not isinstance(continuity_references, list):
        raise ValueError("Principal-election continuity audit requires division references.")
    for row in continuity_references:
        if not isinstance(row, dict):
            raise ValueError("Principal-election continuity references must be objects.")
        election_id = row.get("current_election_id")
        area_name = row.get("current_area_name")
        if not isinstance(election_id, str) or not isinstance(area_name, str):
            raise ValueError("Principal-election continuity references require election and area names.")
        key = (election_id, area_name)
        if key in division_references:
            raise ValueError(f"Duplicate approved historical reference for {key}.")
        division_references[key] = dict(row)

    continuity_party_references = continuity["party_history_references"]
    if not isinstance(continuity_party_references, list):
        raise ValueError("Principal-election continuity audit requires party-history references.")
    for row in continuity_party_references:
        if not isinstance(row, dict):
            raise ValueError("Principal-election party-history references must be objects.")
        election_id = row.get("current_election_id")
        area_name = row.get("current_area_name")
        party_name = row.get("original_party_name")
        if not all(isinstance(value, str) for value in (election_id, area_name, party_name)):
            raise ValueError("Principal-election party-history references require election, area and party names.")
        key = (election_id, area_name, party_name)
        if key in party_references:
            raise ValueError(f"Duplicate approved party-history reference for {key}.")
        party_references[key] = dict(row)

    # Every by-election receives a recorded eligibility decision. Only the
    # evidence-validated same-statutory-division cases are added here;
    # excluded cases stay visibly unavailable in the master database. A case
    # may still carry a label-specific NULL where the prior exact label is not
    # unique (for example, two prior Independent candidates).
    by_election_audit = build_by_election_historical_reference_audit()
    for row in by_election_audit["division_references"]:
        key = (str(row["current_election_id"]), str(row["current_area_name"]))
        if key in division_references:
            raise ValueError(f"Duplicate by-election historical reference for {key}.")
        division_references[key] = dict(row)
    for row in by_election_audit["party_history_references"]:
        key = (str(row["current_election_id"]), str(row["current_area_name"]), str(row["original_party_name"]))
        if key in party_references:
            raise ValueError(f"Duplicate by-election party history for {key}.")
        party_references[key] = dict(row)
    return division_references, party_references


def generate_master_database_outputs(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[Path, Path, Path]:
    """Write reproducible payload and documentation without running extraction.

    The function reads completed local audits, including separately configured
    2026 East and West sources. It uses only the pre-existing official-boundary
    permission audit when exposing a limited direct historical reference.
    """

    # Input loading is intentionally limited to audited local files. No source
    # website is requested and no published election value is recalculated.
    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    # Personal history is opt-in.  The committed register contains only
    # manually reviewed official profile links and is passed separately so a
    # rebuild cannot silently create identity or incumbency claims.
    continuity_evidence = evidence_by_candidate_key(
        load_candidate_continuity_evidence(
            permitted_election_ids=(
                election.configuration.election_id for election in elections
            )
        )
    )
    # The workbook includes only the separately audited, explicitly approved
    # direct relationships.  The complete GIS review remains external so a
    # partial relationship cannot be mistaken for an electoral comparison.
    payload = build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
        candidate_continuity_evidence=continuity_evidence,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    payload_path = output_directory / "master_election_database_payload.json"
    summary_path = output_directory / "master_election_database_audit_summary.md"
    schema_path = output_directory / "master_election_database_schema.md"
    payload_path.write_text(
        json.dumps(payload_as_dict(payload), indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(audit_summary_markdown(payload), encoding="utf-8")
    schema_path.write_text(schema_documentation_markdown(payload), encoding="utf-8")
    return payload_path, summary_path, schema_path


def main() -> None:
    """Generate the JSON input and companion documentation for the workbook builder."""

    paths = generate_master_database_outputs()
    print(json.dumps({"payload": str(paths[0]), "audit_summary": str(paths[1]), "schema": str(paths[2])}, indent=2))


if __name__ == "__main__":
    main()
