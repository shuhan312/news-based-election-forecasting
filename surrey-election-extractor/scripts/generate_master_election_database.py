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
from election_extractor.historical_baseline import (
    build_historical_baseline_features,
    load_crosswalk_resolution,
)
from election_extractor.historical_reference_permissions import (
    build_historical_reference_permission_audit,
    permission_records_by_mapping_id,
)
from election_extractor.principal_election_continuity import (
    build_principal_election_continuity_audit,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/master_surrey_election_database"
CROSSWALK_PATH = (
    PROJECT_ROOT
    / "outputs/geographic_crosswalk_resolution/geographic_crosswalk_resolution_dataset.json"
)


def reviewed_geographic_mapping_rows() -> tuple[dict[str, object], ...]:
    """Return only audited direct historical-reference decisions for the workbook.

    The detailed crosswalk remains in its own GIS audit output.  This workbook
    receives the 22 relationships with explicit official-boundary permission,
    together with the original GIS evidence fields and explicit prohibitions.
    No partial relationship is upgraded and no candidate or vote value changes.
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

    The historical baseline layer supplies the 22 separately reviewed
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
    # The workbook includes only the separately audited, explicitly approved
    # direct relationships.  The complete GIS review remains external so a
    # partial relationship cannot be mistaken for an electoral comparison.
    payload = build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
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
