"""Generate the read-only Surrey historical-to-2026 mapping evidence audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Allow direct reproducible execution without requiring a user to manually
    # set PYTHONPATH. This changes only the import path, never audit data.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.geographic_mapping_audit import (
    audit_markdown,
    build_geographic_mapping_audit,
    load_geographic_mapping_audit_configuration,
)
from election_extractor.master_database import load_audited_elections


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/geographic_mapping_audit"


def generate_mapping_audit(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[Path, Path, dict[str, object]]:
    """Write compact audit reports without writing any mapping data to the database."""

    audit = build_geographic_mapping_audit(
        load_audited_elections(),
        load_geographic_mapping_audit_configuration(),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "historical_to_2026_mapping_audit.json"
    markdown_path = output_directory / "historical_to_2026_mapping_audit.md"
    json_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(audit_markdown(audit), encoding="utf-8")
    return json_path, markdown_path, audit


def main() -> None:
    """Generate the evidence audit and expose its status and output paths."""

    json_path, markdown_path, audit = generate_mapping_audit()
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "status": audit["status"],
                "mapping_rows": len(audit["verified_geographic_mapping_rows"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
