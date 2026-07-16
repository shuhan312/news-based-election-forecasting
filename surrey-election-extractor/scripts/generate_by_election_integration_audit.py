"""Generate local by-election integration and validation audit outputs.

This reporting script only reads the reviewed event catalogue and official-page
evidence register. It does not retrieve pages, modify raw extraction records,
or create values for catalogue events without verified candidate-result evidence.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from election_extractor.by_election_results import (
    evidence_audit_rows,
    load_by_election_result_evidence,
)
from election_extractor.validation import PublishedVotingSummary, validate_election_results


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/by_election_integration"


def _json_value(value: object) -> object:
    """Convert validation dataclasses and enums without losing null values."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def run(output_directory: Path = OUTPUT_DIRECTORY) -> dict[str, Path]:
    """Write reproducible local audit files for the integrated by-elections."""

    evidence = load_by_election_result_evidence()
    validation_results = []
    for item in evidence:
        representative = item.records[0]
        # The summary is a validation comparator only. It is not used to fill
        # a candidate record or to repair any unavailable official field.
        summaries = (
            PublishedVotingSummary(
                source_url=item.source_url,
                total_votes=representative.total_votes,
            ),
        )
        validation_results.extend(validate_election_results(item.records, summaries))

    audit_rows = evidence_audit_rows(evidence=evidence)
    payload = {
        "scope": "Surrey County Council by-election candidate-result integration audit.",
        "events_catalogued": len(audit_rows),
        "events_with_verified_official_candidate_results": len(evidence),
        "candidate_records_added": sum(len(item.records) for item in evidence),
        "events_without_verified_official_candidate_results": sum(
            row["candidate_record_count"] is None for row in audit_rows
        ),
        "event_provenance": audit_rows,
    }
    validation_payload = {
        "scope": "Read-only validation of candidate rows with published official candidate-result evidence.",
        "validation_results": _json_value(validation_results),
        "summary": {
            "passed": sum(item.validation_status.value == "Passed" for item in validation_results),
            "warnings": sum(item.validation_status.value == "Warning" for item in validation_results),
            "incomplete": sum(item.validation_status.value == "Incomplete" for item in validation_results),
            "failed": sum(item.validation_status.value == "Failed" for item in validation_results),
        },
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "integration_audit": output_directory / "by_election_integration_audit.json",
        "validation_report": output_directory / "by_election_validation_report.json",
    }
    files["integration_audit"].write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    files["validation_report"].write_text(
        json.dumps(validation_payload, indent=2) + "\n", encoding="utf-8"
    )
    return files


def main() -> None:
    """Print local output paths for the research audit trail."""

    for name, path in run().items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
