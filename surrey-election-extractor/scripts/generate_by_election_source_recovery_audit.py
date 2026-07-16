"""Render a local readable report for by-election official-source recovery."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from election_extractor.by_election_source_recovery import (
    load_by_election_source_recovery_audit,
    unresolved_source_recovery_ids,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/by_election_source_recovery"


def _markdown(records: list[dict[str, object]]) -> str:
    """Render evidence and unresolved fields without implying data completion."""

    lines = [
        "# Surrey County Council By-election Official-source Recovery Audit",
        "",
        "This is a read-only provenance audit. It does not calculate vote shares, infer candidates, or create candidate rows from winner-only documents.",
        "",
        "| Election ID | Evidence status | Candidate results integrated | Source | Remaining official information |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| {election_id} | {result_evidence_status} | {candidate_results_integrated} | {source_url} | {missing} |".format(
                **record,
                missing=", ".join(record["missing_official_information"]),
            )
        )
    return "\n".join(lines) + "\n"


def run(output_directory: Path = OUTPUT_DIRECTORY) -> dict[str, Path]:
    """Write small local audit outputs; detailed generated files remain untracked."""

    audit = load_by_election_source_recovery_audit()
    records = [asdict(item) for item in audit]
    payload = {
        "scope": "Official-source recovery audit only; no extraction or inference.",
        "records": records,
        "unresolved_event_ids": list(unresolved_source_recovery_ids(audit)),
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_directory / "by_election_source_recovery_audit.json",
        "markdown": output_directory / "by_election_source_recovery_audit.md",
    }
    paths["json"].write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    paths["markdown"].write_text(_markdown(records), encoding="utf-8")
    return paths


def main() -> None:
    """Print local report paths for the research audit trail."""

    for name, path in run().items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
