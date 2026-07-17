"""Generate the final non-mutating election-data release audit locally.

The generated JSON and Markdown are research outputs, so they belong in the
ignored ``outputs/`` directory or in the project's external data store.  The
committed code and reviewed evidence index are sufficient to reproduce them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.candidate_continuity_evidence import (
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)
from election_extractor.final_data_release_audit import (
    build_final_data_release_audit,
    final_data_release_audit_markdown,
    load_missing_field_evidence_index,
)
from election_extractor.master_database import build_master_database, load_audited_elections
from scripts.generate_master_election_database import (
    reviewed_geographic_mapping_rows,
    reviewed_historical_reference_inputs,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/final_election_data_release_audit"


def generate_final_data_release_audit(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[Path, Path, dict[str, object]]:
    """Build the existing master payload and audit it without rerunning extraction."""

    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    continuity_evidence = evidence_by_candidate_key(
        load_candidate_continuity_evidence(
            permitted_election_ids=(election.configuration.election_id for election in elections)
        )
    )
    payload = build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
        candidate_continuity_evidence=continuity_evidence,
    )
    report = build_final_data_release_audit(
        payload,
        evidence_index=load_missing_field_evidence_index(),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "final_election_data_release_audit.json"
    markdown_path = output_directory / "final_election_data_release_audit.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(final_data_release_audit_markdown(report), encoding="utf-8")
    return json_path, markdown_path, report


def main() -> None:
    """Write paths and compact counts for a reproducible local audit run."""

    json_path, markdown_path, report = generate_final_data_release_audit()
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "release_decision": report["release_decision"],
                "residual_missing_counts": report["residual_missing_counts"],
                "event_samples": report["reconciliation_summary"]["event_samples"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
