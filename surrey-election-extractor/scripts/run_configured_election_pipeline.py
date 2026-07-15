"""Run the existing Surrey election pipeline for one configured election.

The script is deliberately orchestration-only: it does not add extraction
rules, alter source values, or repair missing data.  It writes the discovery,
extraction and validation evidence needed to audit one completed run.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from election_extractor.discovery import (
    UrllibOfficialArchiveClient,
    discover_election_areas,
)
from election_extractor.election_config import load_election_config
from election_extractor.extraction import (
    CandidateResultRecord,
    ExtractionStatus,
    extract_candidate_results,
)
from election_extractor.official_source import UrllibOfficialPageClient
from election_extractor.search_providers.mock_provider import MockSearchProvider
from election_extractor.validation import (
    PublishedVotingSummary,
    ValidationStatus,
    validate_election_results,
)
from election_extractor.workbook import generate_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _json_default(value: object) -> object:
    """Encode immutable pipeline records without removing their audit fields."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot write {type(value).__name__} to the audit JSON.")


def _published_summaries(
    records: tuple[CandidateResultRecord, ...],
) -> tuple[PublishedVotingSummary, ...]:
    """Keep one published voting-summary object per official result URL.

    The same summary values appear on every candidate row from a result page.
    This function only removes that repetition for validation; it never derives
    a total or substitutes a missing official field.
    """
    summaries: dict[str, PublishedVotingSummary] = {}
    for record in records:
        summaries.setdefault(
            record.source_url,
            PublishedVotingSummary(
                source_url=record.source_url,
                total_votes=record.total_votes,
                valid_votes=record.valid_votes,
            ),
        )
    return tuple(summaries.values())


def _missing_field_counts(records: tuple[CandidateResultRecord, ...]) -> dict[str, int]:
    """Count recorded absences rather than treating them as zero or complete."""
    return dict(sorted(Counter(field for record in records for field in record.missing_fields).items()))


def _run_summary(
    discovery_count: int,
    extraction_records: tuple[CandidateResultRecord, ...],
    extraction_attempts: tuple[Any, ...],
    validations: tuple[Any, ...],
    workbook_path: Path,
    audit_path: Path,
) -> dict[str, object]:
    """Create the requested completion metrics from existing pipeline outputs."""
    extracted_divisions = {record.source_url for record in extraction_records}
    validation_statuses = Counter(result.validation_status.value for result in validations)
    record_statuses = Counter(record.extraction_status.value for record in extraction_records)
    attempt_statuses = Counter(attempt.status.value for attempt in extraction_attempts)
    return {
        "divisions_discovered": discovery_count,
        "divisions_extracted": len(extracted_divisions),
        "candidate_records": len(extraction_records),
        "complete_records": record_statuses[ExtractionStatus.COMPLETE.value],
        "incomplete_records": record_statuses[ExtractionStatus.INCOMPLETE.value],
        "failed_records": record_statuses[ExtractionStatus.SEARCH_FAILED.value],
        "failed_extraction_attempts": attempt_statuses[ExtractionStatus.SEARCH_FAILED.value],
        "missing_fields": _missing_field_counts(extraction_records),
        "validation_statuses": dict(sorted(validation_statuses.items())),
        "validation_warnings": sum(len(result.warnings) for result in validations),
        "failed_validation_checks": sum(len(result.failed_checks) for result in validations),
        "workbook": str(workbook_path),
        "audit_log": str(audit_path),
    }


def run(election_id: str, output_directory: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    """Run one configured election from discovery through workbook generation."""
    configuration = next(
        (
            item
            for item in load_election_config()
            if item.election_id == election_id
        ),
        None,
    )
    if configuration is None:
        raise ValueError(f"No configured election has id {election_id!r}.")

    output_directory.mkdir(parents=True, exist_ok=True)
    # A mock provider prevents the run from silently mixing official page data
    # with search results. The official archive and official result-page clients
    # remain the only live sources used by this approved extraction run.
    discovery = discover_election_areas(
        configuration.official_url,
        MockSearchProvider({}),
        archive_client=UrllibOfficialArchiveClient(),
    )
    extraction = extract_candidate_results(
        discovery.areas,
        MockSearchProvider({}),
        official_page_client=UrllibOfficialPageClient(),
    )
    summaries = _published_summaries(extraction.records)
    validations = validate_election_results(extraction.records, summaries)

    # Output names come from the configured election rather than a hard-coded
    # year, so the same validated orchestration can write separate audit files
    # for each approved configured election.
    year = configuration.election_year
    workbook_path = output_directory / f"surrey_county_council_{year}.xlsx"
    audit_path = output_directory / f"{year}_extraction_audit.json"
    validation_path = output_directory / f"{year}_validation_report.json"
    generate_workbook(
        workbook_path,
        extraction.records,
        validations,
        discovery.areas,
        extraction.attempts,
        summaries,
    )
    summary = _run_summary(
        len(discovery.areas),
        extraction.records,
        extraction.attempts,
        validations,
        workbook_path,
        audit_path,
    )
    audit = {
        "configuration": asdict(configuration),
        "archive_url": configuration.official_url,
        "run_timestamp": datetime.now().astimezone().isoformat(),
        "discovery": discovery,
        "official_page_diagnostics": extraction.official_diagnostics,
        "extraction": {
            "records": extraction.records,
            "attempts": extraction.attempts,
        },
        "validation": validations,
        "pipeline_capabilities": {
            "original_published_party_name": "preserved in original_party_name",
            "standardised_party_name": "not available in the existing extraction record model",
            "reform_uk_and_ukip": "kept as distinct published party names",
        },
        "summary": summary,
    }
    validation_report = {
        "configuration": asdict(configuration),
        "run_timestamp": audit["run_timestamp"],
        "validation_results": validations,
        "summary": summary,
    }
    audit_path.write_text(json.dumps(audit, default=_json_default, indent=2) + "\n", encoding="utf-8")
    validation_path.write_text(
        json.dumps(validation_report, default=_json_default, indent=2) + "\n",
        encoding="utf-8",
    )
    return workbook_path, audit_path, validation_path, summary


def main() -> None:
    """Parse the bounded run options and print a compact completion summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--election-id",
        default="surrey-county-council-2017",
        help="Configured election identifier to run.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=PROJECT_ROOT / "outputs/2017_full_extraction",
        help="Directory for the workbook and audit reports.",
    )
    args = parser.parse_args()
    workbook_path, audit_path, validation_path, summary = run(
        args.election_id,
        args.output_directory,
    )
    print(json.dumps({
        "workbook": str(workbook_path),
        "extraction_audit": str(audit_path),
        "validation_report": str(validation_path),
        "summary": summary,
    }, indent=2))


if __name__ == "__main__":
    main()
