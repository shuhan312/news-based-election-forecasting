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
from election_extractor.election_structure_metadata import load_secondary_seats_audit
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = {
    "surrey-county-council-2013": {
        "source_audit": PROJECT_ROOT / "outputs/2013_full_extraction/2013_extraction_audit.json",
        "output_directory": PROJECT_ROOT / "outputs/2013_layered_completeness",
        "secondary_seats_audit": None,
    },
    "surrey-county-council-2017": {
        "source_audit": PROJECT_ROOT / "outputs/2017_full_extraction/2017_extraction_audit.json",
        "output_directory": PROJECT_ROOT / "outputs/2017_layered_completeness",
        "secondary_seats_audit": None,
    },
    "surrey-county-council-2021": {
        "source_audit": PROJECT_ROOT / "outputs/2021_archive_discovery_pilot/2021_archive_discovery_pilot_audit.json",
        "output_directory": PROJECT_ROOT / "outputs/2021_layered_completeness",
        "secondary_seats_audit": PROJECT_ROOT / "outputs/2021_secondary_seats_audit/2021_secondary_seats_audit.json",
    },
}


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


def _legacy_record_statuses(records: tuple[CandidateResultRecord, ...]) -> dict[str, int]:
    """Report original extraction statuses without changing their meaning."""
    statuses = Counter(record.extraction_status.value for record in records)
    return {
        ExtractionStatus.COMPLETE.value: statuses[ExtractionStatus.COMPLETE.value],
        ExtractionStatus.INCOMPLETE.value: statuses[ExtractionStatus.INCOMPLETE.value],
        ExtractionStatus.SEARCH_FAILED.value: statuses[ExtractionStatus.SEARCH_FAILED.value],
    }


def _report_payload(
    election_id: str,
    source_audit: Path,
    records: tuple[CandidateResultRecord, ...],
    report: LayeredCompletenessReport,
) -> dict[str, object]:
    """Create a compact reporting payload independent of extraction execution."""
    return {
        "report_title": f"{election_id} Layered Completeness Report",
        "generated_at": datetime.now(UTC).isoformat(),
        "election_id": election_id,
        "source_extraction_audit": str(source_audit),
        "election": report.election,
        "divisions": report.divisions,
        "candidates": report.candidates,
        "summary": {
            "election_completeness": report.election.status.value,
            "legacy_candidate_record_statuses": _legacy_record_statuses(records),
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
            "supplementary_seats": {
                "divisions_with_secondary_seats": sum(
                    division.supplementary_seats is not None
                    and division.supplementary_seats.secondary_number_of_seats is not None
                    for division in report.divisions
                ),
                "official_seats_remain_missing": sum(
                    "number_of_seats" in division.missing_fields
                    for division in report.divisions
                ),
                "provenance_preserved_separately": True,
            },
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
    legacy = summary["legacy_candidate_record_statuses"]
    seats = summary["supplementary_seats"]
    assert isinstance(candidate, dict) and isinstance(division, dict) and isinstance(missing, dict)
    assert isinstance(legacy, dict) and isinstance(seats, dict)
    lines = [
        f"# {payload['election_id']} Layered Completeness Report",
        "",
        f"- Election completeness: `{summary['election_completeness']}`",
        f"- Before (legacy candidate records): {legacy}",
        f"- Candidate complete: {candidate['complete']}",
        f"- Candidate incomplete: {candidate['incomplete']}",
        f"- Division complete: {division['complete']}",
        f"- Division incomplete: {division['incomplete']}",
        f"- Division missing fields: {missing or 'None'}",
        f"- Secondary Seats values: {seats['divisions_with_secondary_seats']}",
        f"- Official Seats fields still missing: {seats['official_seats_remain_missing']}",
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
    secondary_seats_audit: Path | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    """Read a completed audit and generate only layered validation/reporting outputs."""
    audit = json.loads(source_audit.read_text(encoding="utf-8"))
    configuration = next(item for item in load_election_config() if item.election_id == election_id)
    records = tuple(
        _record_from_audit(item) for item in audit["extraction"]["records"]
    )
    # Secondary Seats evidence is an explicit reporting input. It remains a
    # separate metadata layer and is never copied into official Seats fields.
    structure_metadata = ()
    if secondary_seats_audit is not None:
        authority = next((record.authority for record in records if record.authority), None)
        structure_metadata = load_secondary_seats_audit(
            secondary_seats_audit,
            election_year=configuration.election_year,
            election_name=configuration.election_name,
            authority=authority,
        )
    layered = assess_layered_completeness(
        configuration,
        records,
        election_structure_metadata=structure_metadata,
    )
    payload = _report_payload(election_id, source_audit, records, layered)

    output_directory.mkdir(parents=True, exist_ok=True)
    year = configuration.election_year
    json_path = output_directory / f"{year}_layered_completeness_report.json"
    markdown_path = output_directory / f"{year}_layered_completeness_report.md"
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
        default=None,
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=None,
    )
    parser.add_argument("--secondary-seats-audit", type=Path, default=None)
    args = parser.parse_args()
    defaults = DEFAULT_INPUTS.get(args.election_id)
    if defaults is None and (args.source_audit is None or args.output_directory is None):
        raise ValueError("Provide source and output paths for an election without default inputs.")
    json_path, markdown_path, payload = generate_report(
        args.election_id,
        args.source_audit or defaults["source_audit"],
        args.output_directory or defaults["output_directory"],
        args.secondary_seats_audit or (defaults and defaults["secondary_seats_audit"]),
    )
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "summary": payload["summary"]}, indent=2))


if __name__ == "__main__":
    main()
