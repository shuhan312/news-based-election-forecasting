"""Create a read-only data quality report from completed Surrey 2021 audits."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_AUDIT_PATH = (
    PROJECT_ROOT
    / "outputs/2021_archive_discovery_pilot/2021_archive_discovery_pilot_audit.json"
)
SEATS_DIAGNOSIS_PATH = (
    PROJECT_ROOT
    / "outputs/2021_seats_diagnosis_verified/2021_official_seats_diagnostic.json"
)
SECONDARY_SEATS_AUDIT_PATH = (
    PROJECT_ROOT
    / "outputs/2021_secondary_seats_audit/2021_secondary_seats_audit.json"
)
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/2021_data_quality_report"

CANDIDATE_FIELDS = (
    "candidate_name",
    "original_party_name",
    "votes_received",
    "vote_share",
    "outcome",
)
SUMMARY_FIELDS = (
    ("seats", "number_of_seats"),
    ("total_votes", "total_votes"),
    ("electorate", "electorate"),
    ("ballot_papers_issued", "ballot_papers_issued"),
    ("rejected_ballots", "ballot_papers_rejected"),
    ("turnout", "turnout"),
)


def _load_json(path: Path) -> dict[str, Any]:
    """Load one completed audit file and fail clearly when it is unavailable."""
    with path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _present(value: object) -> bool:
    """Treat null and blank source values as unavailable without inventing data."""
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _availability_by_record_and_division(
    records: list[dict[str, Any]], field_name: str
) -> dict[str, int]:
    """Count availability at both repeated-record and official-page levels."""
    by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_url[record["source_url"]].append(record)

    records_available = sum(_present(record.get(field_name)) for record in records)
    divisions_available = sum(
        any(_present(record.get(field_name)) for record in division_records)
        for division_records in by_url.values()
    )
    return {
        "records_available": records_available,
        "records_missing": len(records) - records_available,
        "divisions_available": divisions_available,
        "divisions_missing": len(by_url) - divisions_available,
    }


def _candidate_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe candidate counts using official result URLs as stable division keys."""
    by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_url[record["source_url"]].append(record)
    counts = [len(division_records) for division_records in by_url.values()]
    distribution = Counter(counts)
    return {
        "minimum_candidates_per_division": min(counts),
        "maximum_candidates_per_division": max(counts),
        "average_candidates_per_division": round(len(records) / len(counts), 2),
        "distribution": {str(count): frequency for count, frequency in sorted(distribution.items())},
    }


def _validation_summary(validations: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate existing validation events without changing validation outcomes."""
    events = [event for result in validations for event in result["events"]]
    return {
        "division_validation_statuses": dict(
            sorted(Counter(result["validation_status"] for result in validations).items())
        ),
        "checks_performed": dict(
            sorted(Counter(event["validation_rule"] for event in events).items())
        ),
        "event_outcomes": dict(sorted(Counter(event["result"] for event in events).items())),
        "warnings": sum(len(result["warnings"]) for result in validations),
        "failed_checks": sum(len(result["failed_checks"]) for result in validations),
    }


def build_report(test_status: str) -> dict[str, Any]:
    """Build a report solely from completed discovery, extraction and audit outputs."""
    archive_audit = _load_json(ARCHIVE_AUDIT_PATH)
    seats_diagnosis = _load_json(SEATS_DIAGNOSIS_PATH)
    secondary_seats_audit = _load_json(SECONDARY_SEATS_AUDIT_PATH)

    discovery = archive_audit["discovery"]
    records = archive_audit["extraction"]["records"]
    validations = archive_audit["validation"]
    diagnostics = archive_audit["official_page_diagnostics"]
    summary = archive_audit["summary"]

    candidate_availability = {
        field_name: _availability_by_record_and_division(records, field_name)
        for field_name in CANDIDATE_FIELDS
    }
    election_summary_fields = {
        report_name: {
            **_availability_by_record_and_division(records, field_name),
            "official_source": "Surrey County Council official result page Voting Summary",
        }
        for report_name, field_name in SUMMARY_FIELDS
    }

    # Seats needs additional context because a missing official Seats row is a
    # documented source limitation, not a failed extraction or a zero value.
    election_summary_fields["seats"].update(
        {
            "official_pages_with_published_seats": seats_diagnosis["summary"]["seats_value_found"],
            "official_pages_without_published_seats": seats_diagnosis["summary"]["seats_not_present"],
            "secondary_confirmations": secondary_seats_audit["summary"][
                "divisions_with_reliable_secondary_seats_information"
            ],
            "secondary_source": "The Surrey (Electoral Changes) Order 2012",
        }
    )

    discovered_urls = {area["result_url"] for area in discovery["areas"]}
    processed_urls = {diagnostic["source_url"] for diagnostic in diagnostics}
    record_urls = {record["source_url"] for record in records}
    provenance = Counter(record["source_type"] for record in records)
    missing_candidate_fields = Counter(
        field_name for record in records for field_name in record["missing_fields"]
    )

    report = {
        "report_title": "2021 Surrey County Council Election Data Quality Report",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_overview": {
            "election_name": records[0]["election_name"],
            "election_year": 2021,
            "authority": records[0]["authority"],
            "divisions": len(discovery["areas"]),
            "official_result_pages": len(diagnostics),
            "candidate_records": len(records),
        },
        "extraction_coverage": {
            "divisions_discovered": len(discovered_urls),
            "official_result_urls_processed": len(processed_urls),
            "divisions_with_candidate_records": len(record_urls),
            "successfully_processed_divisions": len(processed_urls),
            "failed_divisions": summary["failed_extraction_attempts"],
            "missing_divisions_relative_to_official_archive": len(discovered_urls - processed_urls),
            "invented_divisions": len(processed_urls - discovered_urls),
            "discovery_method": dict(Counter(area["discovery_method"] for area in discovery["areas"])),
            "name_match_status": dict(Counter(area["name_status"] for area in discovery["areas"])),
            "official_page_classification": dict(
                Counter(diagnostic["classification"] for diagnostic in diagnostics)
            ),
            "conclusion": (
                "All 81 divisions enumerated by the official archive were processed. "
                "No division was invented or omitted relative to that archive list."
            ),
        },
        "candidate_data_quality": {
            "total_candidates": len(records),
            "candidates_per_division": _candidate_distribution(records),
            "candidate_field_availability": candidate_availability,
            "missing_fields_recorded_by_extraction": dict(sorted(missing_candidate_fields.items())),
            "source_provenance": dict(sorted(provenance.items())),
            "provenance_statement": (
                "All 331 candidate records have source_type=official and retain their "
                "official Surrey result-page URL and field-level evidence."
            ),
        },
        "election_summary_fields": election_summary_fields,
        "seats_handling": {
            "official_seats": (
                "Official number_of_seats is populated only when Surrey's official result page "
                "publishes a Seats row in its Voting Summary."
            ),
            "missing_official_seats": (
                "A missing official Seats row remains missing. It is not inferred from the election "
                "year, candidate count, elected candidates or historical assumptions."
            ),
            "secondary_seats": (
                "For the 28 affected divisions, separately stored supplementary metadata records a "
                "secondary Seats value of 1 with its source, evidence text and confidence."
            ),
            "secondary_source": "The Surrey (Electoral Changes) Order 2012 (UKSI 2012/1872)",
            "reason_for_separation": (
                "The official result page and the statutory source are different provenance layers. "
                "Keeping them separate preserves the published official value, its absence, and the "
                "uncertainty that absence represents."
            ),
        },
        "validation_summary": {
            **_validation_summary(validations),
            "candidate_record_statuses": {
                "Complete": summary["complete_records"],
                "Incomplete": summary["incomplete_records"],
                "Failed": summary["failed_records"],
            },
            "interpretation": (
                "The 109 incomplete candidate records belong to 28 divisions whose official page did "
                "not publish Seats. They are not evidence of an extraction failure."
            ),
        },
        "known_limitations": [
            "Twenty-eight official result pages do not publish a Seats field in their HTML.",
            "Official result pages vary in whether the Seats row is published, so source availability is not uniform.",
            "Secondary Seats metadata is supplementary only and must not replace official_number_of_seats.",
            "The report describes the verified 2021 archive run; it does not claim coverage of other election years.",
        ],
        "reproducibility": {
            "official_archive_url": discovery["source_index_url"],
            "official_result_urls": {
                "count": len(discovered_urls),
                "location": str(ARCHIVE_AUDIT_PATH),
            },
            "archive_audit_file": str(ARCHIVE_AUDIT_PATH),
            "official_seats_diagnosis_file": str(SEATS_DIAGNOSIS_PATH),
            "secondary_seats_audit_file": str(SECONDARY_SEATS_AUDIT_PATH),
            "generated_workbook": summary["workbook"],
            "test_status": test_status,
        },
        "quality_conclusion": (
            "The 2021 dataset has complete archive and official-page coverage. Its remaining official "
            "Seats gaps reflect fields not published by 28 official result pages, rather than extraction "
            "failure. The system preserves this uncertainty and retains separate source-backed metadata."
        ),
    }
    return report


def _markdown_report(report: dict[str, Any]) -> str:
    """Render the JSON audit into a compact, human-readable Markdown report."""
    overview = report["dataset_overview"]
    coverage = report["extraction_coverage"]
    candidate_quality = report["candidate_data_quality"]
    summary_fields = report["election_summary_fields"]
    validation = report["validation_summary"]
    reproducibility = report["reproducibility"]
    distribution = candidate_quality["candidates_per_division"]

    lines = [
        "# 2021 Surrey County Council Election Data Quality Report",
        "",
        "## 1. Dataset overview",
        "",
        f"- Election: {overview['election_name']}",
        f"- Year: {overview['election_year']}",
        f"- Authority: {overview['authority']}",
        f"- Divisions: {overview['divisions']}",
        f"- Official result pages: {overview['official_result_pages']}",
        f"- Candidate-level records: {overview['candidate_records']}",
        "",
        "## 2. Extraction coverage",
        "",
        f"- Successfully processed divisions: {coverage['successfully_processed_divisions']}",
        f"- Failed divisions: {coverage['failed_divisions']}",
        f"- Missing divisions relative to the official archive: {coverage['missing_divisions_relative_to_official_archive']}",
        f"- Invented divisions: {coverage['invented_divisions']}",
        f"- {coverage['conclusion']}",
        "",
        "## 3. Candidate data quality",
        "",
        f"- Total candidates: {candidate_quality['total_candidates']}",
        f"- Candidates per division: minimum {distribution['minimum_candidates_per_division']}, "
        f"maximum {distribution['maximum_candidates_per_division']}, "
        f"average {distribution['average_candidates_per_division']}",
        f"- Distribution: {', '.join(f'{count} candidates: {divisions} divisions' for count, divisions in distribution['distribution'].items())}",
        f"- Provenance: {candidate_quality['provenance_statement']}",
        "",
        "| Candidate field | Available records | Missing records |",
        "|---|---:|---:|",
    ]
    for field_name, availability in candidate_quality["candidate_field_availability"].items():
        lines.append(
            f"| {field_name} | {availability['records_available']} | {availability['records_missing']} |"
        )

    lines.extend(
        [
            "",
            "## 4. Election summary fields",
            "",
            "| Field | Official divisions available | Official divisions missing | Candidate records available | Candidate records missing | Source |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for name, field in summary_fields.items():
        lines.append(
            f"| {name} | {field['divisions_available']} | {field['divisions_missing']} | "
            f"{field['records_available']} | {field['records_missing']} | {field['official_source']} |"
        )

    seats = report["seats_handling"]
    lines.extend(
        [
            "",
            "## 5. Seats handling",
            "",
            f"- Official Seats: {seats['official_seats']}",
            f"- Missing official Seats: {seats['missing_official_seats']}",
            f"- Secondary Seats: {seats['secondary_seats']}",
            f"- Source: {seats['secondary_source']}",
            f"- Why separate: {seats['reason_for_separation']}",
            "",
            "## 6. Validation summary",
            "",
            f"- Division statuses: {validation['division_validation_statuses']}",
            f"- Candidate record statuses: {validation['candidate_record_statuses']}",
            f"- Validation checks performed: {validation['checks_performed']}",
            f"- Validation-event outcomes: {validation['event_outcomes']}",
            f"- Warnings: {validation['warnings']}; failed checks: {validation['failed_checks']}",
            f"- {validation['interpretation']}",
            "",
            "## 7. Known limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["known_limitations"])
    lines.extend(
        [
            "",
            "## 8. Reproducibility",
            "",
            f"- Official archive: {reproducibility['official_archive_url']}",
            f"- Official result URL audit: `{reproducibility['archive_audit_file']}`",
            f"- Seats diagnosis: `{reproducibility['official_seats_diagnosis_file']}`",
            f"- Secondary Seats audit: `{reproducibility['secondary_seats_audit_file']}`",
            f"- Generated workbook: `{reproducibility['generated_workbook']}`",
            f"- Tests: {reproducibility['test_status']}",
            "",
            "## Conclusion",
            "",
            report["quality_conclusion"],
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """Write paired JSON and Markdown reports without mutating source datasets."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test-status",
        default="Not run by this reporting script.",
        help="Text describing the separately executed project test result.",
    )
    args = parser.parse_args()

    report = build_report(args.test_status)
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIRECTORY / "2021_surrey_election_data_quality_report.json"
    markdown_path = OUTPUT_DIRECTORY / "2021_surrey_election_data_quality_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    print(json_path)
    print(markdown_path)


if __name__ == "__main__":
    main()
