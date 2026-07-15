"""Tests for separate, bounded orchestration of the 2026 East and West runs."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts/run_2026_east_west_extraction.py"
)
SPEC = importlib.util.spec_from_file_location("run_2026_east_west_extraction", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
runner_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner_module)


def test_2026_runner_keeps_east_and_west_outputs_separate(tmp_path: Path) -> None:
    """The two map-index sources never share an output directory or workbook."""
    pipeline_calls: list[tuple[str, Path]] = []
    report_calls: list[tuple[str, Path, Path]] = []

    def fake_pipeline(election_id: str, output_directory: Path):
        output_directory.mkdir(parents=True, exist_ok=True)
        pipeline_calls.append((election_id, output_directory))
        return (
            output_directory / "surrey_county_council_2026.xlsx",
            output_directory / "2026_extraction_audit.json",
            output_directory / "2026_validation_report.json",
            {
                "divisions_discovered": 1,
                "divisions_extracted": 1,
                "candidate_records": 3,
                "failed_extraction_attempts": 0,
                "validation_warnings": 0,
                "failed_validation_checks": 0,
            },
        )

    def fake_report(election_id: str, audit_path: Path, output_directory: Path):
        output_directory.mkdir(parents=True, exist_ok=True)
        report_calls.append((election_id, audit_path, output_directory))
        return (
            output_directory / "2026_layered_completeness_report.json",
            output_directory / "2026_layered_completeness_report.md",
            {
                "summary": {
                    "election_completeness": "complete",
                    "candidate_completeness": {"complete": 3, "incomplete": 0},
                    "division_completeness": {"complete": 1, "incomplete": 0},
                    "division_missing_fields": {},
                }
            },
        )

    results = runner_module.run_all(
        tmp_path,
        pipeline_runner=fake_pipeline,
        completeness_reporter=fake_report,
    )

    assert [call[0] for call in pipeline_calls] == [
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    ]
    assert pipeline_calls[0][1] != pipeline_calls[1][1]
    assert pipeline_calls[0][1].name == "2026_east_full_extraction"
    assert pipeline_calls[1][1].name == "2026_west_full_extraction"
    assert [call[2].name for call in report_calls] == [
        "2026_east_layered_completeness",
        "2026_west_layered_completeness",
    ]
    assert set(results) == {
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }
    assert Path(results["surrey-county-council-2026-east-surrey"]["summary_markdown"]).exists()
    assert Path(results["surrey-county-council-2026-west-surrey"]["summary_markdown"]).exists()
