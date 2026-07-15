"""Run the validated 2026 Surrey pipeline separately for East and West.

This entry point deliberately coordinates existing stages only.  It does not
change discovery, source parsing, validation, workbook generation, or the
master database.  Separate output directories prevent the two official 2026
map-index sources from overwriting one another's workbooks or audit evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = Path(__file__).resolve().parent

# Permit direct execution from the repository root while retaining imports
# from the existing script-based orchestration layer.
for import_directory in (PROJECT_ROOT, SCRIPTS_DIRECTORY):
    if str(import_directory) not in sys.path:
        sys.path.insert(0, str(import_directory))

from generate_layered_completeness_report import generate_report
from run_configured_election_pipeline import run as run_configured_election


ELECTION_OUTPUT_DIRECTORIES = {
    "surrey-county-council-2026-east-surrey": "2026_east_full_extraction",
    "surrey-county-council-2026-west-surrey": "2026_west_full_extraction",
}


PipelineRunner = Callable[[str, Path], tuple[Path, Path, Path, dict[str, object]]]
CompletenessReporter = Callable[
    [str, Path, Path], tuple[Path, Path, dict[str, object]]
]


def _region_name(election_id: str) -> str:
    """Return the configured regional label without deriving election data."""
    return "East Surrey" if election_id.endswith("east-surrey") else "West Surrey"


def _write_summary(
    election_id: str,
    output_directory: Path,
    pipeline_summary: dict[str, object],
    completeness_payload: dict[str, object],
) -> Path:
    """Write a concise, source-preserving guide to the detailed audit files.

    The full JSON extraction audit retains page and field evidence.  This
    Markdown file records only run-level counts, so it cannot introduce or
    alter any official candidate or Voting Summary value.
    """
    region = _region_name(election_id)
    layered_summary = completeness_payload["summary"]
    assert isinstance(layered_summary, dict)
    candidate_summary = layered_summary["candidate_completeness"]
    division_summary = layered_summary["division_completeness"]
    assert isinstance(candidate_summary, dict)
    assert isinstance(division_summary, dict)

    lines = [
        f"# 2026 Surrey County Council Election — {region} Extraction Summary",
        "",
        "## Coverage",
        "",
        f"- Official wards discovered: {pipeline_summary['divisions_discovered']}",
        f"- Official wards extracted: {pipeline_summary['divisions_extracted']}",
        f"- Candidate rows extracted: {pipeline_summary['candidate_records']}",
        f"- Failed extraction attempts: {pipeline_summary['failed_extraction_attempts']}",
        "",
        "## Validation and completeness",
        "",
        f"- Validation warnings: {pipeline_summary['validation_warnings']}",
        f"- Failed validation checks: {pipeline_summary['failed_validation_checks']}",
        f"- Election completeness: {layered_summary['election_completeness']}",
        f"- Candidate complete: {candidate_summary['complete']}",
        f"- Candidate incomplete: {candidate_summary['incomplete']}",
        f"- Ward complete: {division_summary['complete']}",
        f"- Ward incomplete: {division_summary['incomplete']}",
        f"- Missing official ward fields: {layered_summary['division_missing_fields'] or 'None'}",
        "",
        "## Provenance note",
        "",
        "All candidate and Voting Summary values are retained only when published on the official Surrey result page. Missing fields remain missing; this report does not infer Seats, turnout, rankings, or party names.",
        "",
    ]
    path = output_directory / f"2026_{region.lower().replace(' ', '_')}_extraction_summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_all(
    output_root: Path = PROJECT_ROOT / "outputs",
    *,
    pipeline_runner: PipelineRunner = run_configured_election,
    completeness_reporter: CompletenessReporter = generate_report,
) -> dict[str, dict[str, object]]:
    """Run and report the two configured 2026 map-index election sources.

    Each region receives its own workbook, extraction audit, validation report,
    and layered completeness report.  No master-database call is made here,
    which keeps 2026 separate until ward mapping is explicitly authorised.
    """
    results: dict[str, dict[str, object]] = {}
    for election_id, output_directory_name in ELECTION_OUTPUT_DIRECTORIES.items():
        output_directory = output_root / output_directory_name
        workbook_path, audit_path, validation_path, pipeline_summary = pipeline_runner(
            election_id,
            output_directory,
        )
        completeness_directory = output_root / output_directory_name.replace(
            "_full_extraction", "_layered_completeness"
        )
        completeness_json, completeness_markdown, completeness_payload = completeness_reporter(
            election_id,
            audit_path,
            completeness_directory,
        )
        summary_path = _write_summary(
            election_id,
            output_directory,
            pipeline_summary,
            completeness_payload,
        )
        results[election_id] = {
            "workbook": str(workbook_path),
            "extraction_audit": str(audit_path),
            "validation_report": str(validation_path),
            "layered_completeness_json": str(completeness_json),
            "layered_completeness_markdown": str(completeness_markdown),
            "summary_markdown": str(summary_path),
            "summary": pipeline_summary,
            "layered_summary": completeness_payload["summary"],
        }
    return results


def main() -> None:
    """Run the bounded 2026 East/West extraction and print output locations."""
    print(json.dumps(run_all(), indent=2))


if __name__ == "__main__":
    main()
