"""Write the bounded 2013 supplementary-metadata policy audit."""

from __future__ import annotations

import json
from pathlib import Path

from election_extractor.supplementary_metadata_audit import (
    audit_markdown,
    build_2013_supplementary_metadata_audit,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/2013_supplementary_metadata_audit"


def run(output_directory: Path = OUTPUT_DIRECTORY) -> tuple[Path, Path]:
    """Generate reports from the audited policy without fetching or extracting data."""

    audit = build_2013_supplementary_metadata_audit()
    output_directory.mkdir(parents=True, exist_ok=True)
    markdown_path = output_directory / "2013_supplementary_metadata_audit.md"
    json_path = output_directory / "2013_supplementary_metadata_audit.json"
    markdown_path.write_text(audit_markdown(audit), encoding="utf-8")
    json_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return markdown_path, json_path


def main() -> None:
    """Print the report locations for a reproducible audit run."""

    markdown_path, json_path = run()
    print(f"Markdown: {markdown_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
