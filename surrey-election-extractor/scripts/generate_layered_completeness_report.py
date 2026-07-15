"""Create a layered completeness report from an existing extraction audit only."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from election_extractor.completeness import (
    CompletenessStatus,
    LayeredCompletenessReport,
    assess_layered_completeness,
)
from election_extractor.election_config import load_election_config
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _record_from_audit(payload: dict[str, Any]) -> CandidateResultRecord:
    """Rebuild the minimal immutable record needed for reporting.

    This reads existing audit values only. It deliberately excludes field
    evidence because completeness assessment never modifies or reinterprets it.
    """
    return CandidateResultRecord(
        election_name=payload.get("election_name"),
        election_date=payload.get("election_date"),
        authority=payload.get("authority"),
        division_ward_name=payload.get("division_ward_name"),
        number_of_seats=payload.get("number_of_seats"),
        candidate_name=payload["candidate_name"],
        original_party_name=payload.get("original_party_name"),
        votes_received=payload.get("votes_received"),
        vote_share=payload.get("vote_share"),
        outcome=payload.get("outcome"),
        electorate=payload.get("electorate"),
        ballot_papers_issued=payload.get("ballot_papers_issued"),
        ballot_papers_rejected=payload.get("ballot_papers_rejected"),
        turnout=payload.get("turnout"),
        source_url=payload["source_url"],
        extraction_status=ExtractionStatus(payload["extraction_status"]),
        missing_fields=tuple(payload.get("missing_fields", ())),
        election_type=payload.get("election_type"),
        final_position=payload.get("final_position"),
        elected=payload.get("elected"),
        winning_candidate=payload.get("winning_candidate"),
        winning_party=payload.get("winning_party"),
        winning_margin=payload.get("winning_margin"),
        total_votes=payload.get("total_votes"),
        valid_votes=payload.get("valid_votes"),
    )


def _json_default(value: object) -> object:
    """Encode immutable report records without changing their field values."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot encode {type(value).__name__}.")


def _counts(items: tuple[Any, ...]) -> dict[str, int]:
    """Count complete and incomplete items for one report layer."""
    statuses = Counter(item.status.value for item in items)
    return {
        CompletenessStatus.COMPLETE.value: statuses[CompletenessStatus.COMPLETE.value],
        CompletenessStatus.INCOMPLETE.value: statuses[CompletenessStatus.INCOMPLETE.value],
    }


def _report_payload(
    election_id: str,
    source_audit: Path,
    report: LayeredCompletenessReport,
) -> dict[str, object]:
    """Create a compact reporting payload independent of extraction execution."""
    return {
        "report_title": "2017 Surrey Layered Completeness Report",
        "generated_at": datetime.now(UTC).isoformat(),
        "election_id": election_id,
        "source_extraction_audit": str(source_audit),
        "election": report.election,
        "divisions": report.divisions,
        "candidates": report.candidates,
        "summary": {
            "election_completeness": report.election.status.value,
            "candidate_completeness": _counts(report.candidates),
            "division_completeness": _counts(report.divisions),
            "division_missing_fields": dict(
                sorted(
                    Counter(
                        field
                        for division in report.divisions
                        for field in division.missing_fields
                    ).items()
                )
            ),
            "interpretation": (
                "Layered assessment does not alter extracted records or their legacy "
                "extraction_status values. Candidate completeness excludes election "
                "metadata and division Voting Summary fields."
            ),
        },
    }


def _markdown(payload: dict[str, object]) -> str:
    """Render the reporting summary without duplicating candidate-level data."""
    summary = payload["summary"]
    assert isinstance(summary, dict)
    candidate = summary["candidate_completeness"]
    division = summary["division_completeness"]
    missing = summary["division_missing_fields"]
    assert isinstance(candidate, dict) and isinstance(division, dict) and isinstance(missing, dict)
    lines = [
        "# 2017 Surrey Layered Completeness Report",
        "",
        f"- Election completeness: `{summary['election_completeness']}`",
        f"- Candidate complete: {candidate['complete']}",
        f"- Candidate incomplete: {candidate['incomplete']}",
        f"- Division complete: {division['complete']}",
        f"- Division incomplete: {division['incomplete']}",
        f"- Division missing fields: {missing or 'None'}",
        "",
        "## Interpretation",
        "",
        str(summary["interpretation"]),
        "",
        "The report is generated from the existing extraction audit only; it does not rerun discovery or extraction and does not fill missing official values.",
        "",
    ]
    return "\n".join(lines)


def generate_report(
    election_id: str,
    source_audit: Path,
    output_directory: Path,
) -> tuple[Path, Path, dict[str, object]]:
    """Read a completed audit and generate only layered validation/reporting outputs."""
    audit = json.loads(source_audit.read_text(encoding="utf-8"))
    configuration = next(
        item for item in load_election_config() if item.election_id == election_id
    )
    records = tuple(
        _record_from_audit(item) for item in audit["extraction"]["records"]
    )
    layered = assess_layered_completeness(configuration, records)
    payload = _report_payload(election_id, source_audit, layered)

    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "2017_layered_completeness_report.json"
    markdown_path = output_directory / "2017_layered_completeness_report.md"
    json_path.write_text(
        json.dumps(payload, default=_json_default, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def main() -> None:
    """Run reporting only; the existing audit supplies all candidate records."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--election-id", default="surrey-county-council-2017")
    parser.add_argument(
        "--source-audit",
        type=Path,
        default=PROJECT_ROOT / "outputs/2017_full_extraction/2017_extraction_audit.json",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=PROJECT_ROOT / "outputs/2017_layered_completeness",
    )
    args = parser.parse_args()
    json_path, markdown_path, payload = generate_report(
        args.election_id,
        args.source_audit,
        args.output_directory,
    )
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "summary": payload["summary"]}, indent=2))


if __name__ == "__main__":
    main()
