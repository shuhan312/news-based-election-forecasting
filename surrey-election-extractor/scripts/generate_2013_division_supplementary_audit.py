"""Generate the read-only 2013 division supplementary evidence audit."""

from __future__ import annotations

import json
from pathlib import Path

from election_extractor.division_supplementary_audit import (
    audit_2013_division_evidence,
    audit_markdown,
)
from election_extractor.master_database import AUDITED_ELECTION_INPUTS, _record_from_audit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/2013_division_supplementary_audit"


def generate_report(output_directory: Path = OUTPUT_DIRECTORY) -> tuple[Path, Path]:
    """Write audit outputs without calling discovery, extraction or validation."""

    audit_path = AUDITED_ELECTION_INPUTS["surrey-county-council-2013"]["audit_path"]
    payload = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    records = tuple(_record_from_audit(item) for item in payload["extraction"]["records"])
    audit = audit_2013_division_evidence(records)
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "2013_division_supplementary_audit.json"
    markdown_path = output_directory / "2013_division_supplementary_audit.md"
    json_path.write_text(json.dumps(audit.report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(audit_markdown(audit.report), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    """Generate and print the two local evidence-audit report paths."""

    paths = generate_report()
    print(json.dumps({"json": str(paths[0]), "markdown": str(paths[1])}, indent=2))


if __name__ == "__main__":
    main()
