"""Build a unified analytical payload from audited 2017 and 2021 outputs only."""

from __future__ import annotations

import json
from pathlib import Path

from election_extractor.master_database import (
    PROJECT_ROOT,
    audit_summary_markdown,
    build_master_database,
    load_audited_elections,
    payload_as_dict,
    schema_documentation_markdown,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/master_surrey_election_database"


def generate_master_database_outputs(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[Path, Path, Path]:
    """Write reproducible payload and documentation without running extraction."""

    # Input loading is intentionally limited to audited local files. No source
    # website is requested and no published election value is recalculated.
    payload = build_master_database(load_audited_elections())
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
