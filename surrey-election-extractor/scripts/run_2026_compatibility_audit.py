"""Run the bounded, read-only East/West Surrey 2026 compatibility audit."""

from __future__ import annotations

import json
from pathlib import Path

from election_extractor.election_2026_compatibility import (
    audit_markdown,
    build_2026_compatibility_audit,
)
from election_extractor.election_compatibility import UrllibCompatibilityPageClient
from election_extractor.election_config import load_election_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/2026_compatibility_audit"


def run(output_directory: Path = OUTPUT_DIRECTORY) -> tuple[Path, Path, dict[str, object]]:
    """Write 2026 evidence reports without running candidate extraction.

    Ordinary public HTTP is used only for the two configured map indexes and a
    bounded sample of their result pages. The function never writes election
    records or adds 2026 data to the master database.
    """

    configurations = load_election_config()
    audit = build_2026_compatibility_audit(
        configurations,
        UrllibCompatibilityPageClient(),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "surrey-county-council-2026_compatibility.json"
    markdown_path = output_directory / "surrey-county-council-2026_compatibility.md"
    json_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(audit_markdown(audit), encoding="utf-8")
    return json_path, markdown_path, audit


def main() -> None:
    """Generate the required 2026 Markdown and JSON diagnostic reports."""

    json_path, markdown_path, audit = run()
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "compatibility_status": audit["compatibility_status"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
