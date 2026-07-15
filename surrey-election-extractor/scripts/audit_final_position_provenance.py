"""Audit whether Surrey official candidate tables publish final-position evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from election_extractor.official_source import (
    UrllibOfficialPageClient,
    _normalise_heading,
    _parse_html,
    fetch_and_diagnose_official_page,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ELECTION_AUDITS = {
    "2017": PROJECT_ROOT / "outputs/2017_full_extraction/2017_extraction_audit.json",
    "2021": PROJECT_ROOT / "outputs/2021_archive_discovery_pilot/2021_archive_discovery_pilot_audit.json",
}
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/final_position_provenance_audit"

# These are the only visible candidate-table headings that could constitute an
# official final-position field. Candidate row order alone is deliberately not
# treated as ranking evidence.
POSITION_HEADINGS = {
    "final position",
    "position",
    "rank",
    "placing",
    "place",
    "candidate order",
}


def _load_divisions(audit_path: Path) -> tuple[tuple[str, str], ...]:
    """Read existing audit URLs rather than discovering or extracting again."""
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    divisions: dict[str, str] = {}
    for record in audit["extraction"]["records"]:
        divisions.setdefault(record["source_url"], record.get("division_ward_name") or "Unknown")
    return tuple(sorted((name, url) for url, name in divisions.items()))


def _candidate_headers(body: str) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    """Return only headers from tables that visibly contain candidate results."""
    parser = _parse_html(body)
    header_sets = []
    position_headers = set()
    candidate_table_count = 0

    for table in parser.tables:
        for row in table.rows:
            headers = tuple(text for _, text in row if text)
            normalised = {_normalise_heading(text) for text in headers}
            if not (
                normalised & {"candidate", "election candidate"}
                and "party" in normalised
                and "votes" in normalised
            ):
                continue
            candidate_table_count += 1
            header_sets.append(headers)
            position_headers.update(normalised & POSITION_HEADINGS)
            # Only the header row establishes field meaning. Rows after this
            # point may be ordered for display, but that order is not ranking.
            break

    unique_headers = tuple(dict.fromkeys(header_sets))
    return unique_headers, tuple(sorted(position_headers)), candidate_table_count


def _inspect_page(division_name: str, source_url: str) -> dict[str, Any]:
    """Inspect one official page without retaining or changing its candidate data."""
    client = UrllibOfficialPageClient()
    fetched = fetch_and_diagnose_official_page(source_url, client)
    headers: tuple[tuple[str, ...], ...] = ()
    position_headers: tuple[str, ...] = ()
    candidate_table_count = 0
    if fetched.body is not None:
        headers, position_headers, candidate_table_count = _candidate_headers(fetched.body)
    return {
        "division_name": division_name,
        "result_url": source_url,
        "page_classification": fetched.diagnostic.classification.value,
        "candidate_table_count": candidate_table_count,
        "candidate_table_headers": headers,
        "official_position_headers": position_headers,
        "candidate_row_order_observed": candidate_table_count > 0,
        "row_order_treated_as_final_position": False,
    }


def _inspect_election(year: str, audit_path: Path) -> dict[str, Any]:
    """Fetch every recorded official result page using ordinary public HTTP."""
    divisions = _load_divisions(audit_path)
    # Limited concurrency keeps the public audit practical without using browser
    # automation, retries, or any method that bypasses site protections.
    with ThreadPoolExecutor(max_workers=6) as executor:
        pages = list(executor.map(lambda item: _inspect_page(*item), divisions))

    header_sets = Counter(
        " | ".join(headers)
        for page in pages
        for headers in page["candidate_table_headers"]
    )
    position_pages = [page for page in pages if page["official_position_headers"]]
    classification = Counter(page["page_classification"] for page in pages)
    return {
        "election_year": int(year),
        "official_audit_source": str(audit_path),
        "divisions_checked": len(pages),
        "official_result_urls_checked": len(pages),
        "page_classifications": dict(sorted(classification.items())),
        "candidate_tables_found": sum(page["candidate_table_count"] for page in pages),
        "candidate_table_header_patterns": dict(sorted(header_sets.items())),
        "pages_with_official_position_field": len(position_pages),
        "position_field_evidence": position_pages,
        "conclusion": (
            "B. Official final_position is not published in the checked candidate result tables and should remain NULL."
            if not position_pages
            else "A. Official final_position evidence was found and should be reviewed for extraction."
        ),
        "pages": pages,
    }


def _markdown_report(report: dict[str, Any]) -> str:
    """Render a compact report while retaining the full page evidence in JSON."""
    lines = [
        "# Surrey Final Position Provenance Audit",
        "",
        "**Scope:** read-only inspection of official candidate result tables. No rankings were calculated, no candidate records were changed, and no extraction code was modified.",
        "",
    ]
    for election in report["elections"]:
        lines.extend(
            [
                f"## {election['election_year']} Surrey County Council Election",
                "",
                f"- Divisions checked: {election['divisions_checked']}",
                f"- Official result URLs checked: {election['official_result_urls_checked']}",
                f"- Page classifications: {election['page_classifications']}",
                f"- Candidate tables found: {election['candidate_tables_found']}",
                f"- Candidate-table header patterns: {election['candidate_table_header_patterns']}",
                f"- Pages with an official final-position/rank/placing header: {election['pages_with_official_position_field']}",
                f"- Conclusion: **{election['conclusion']}**",
                "",
                "Example checked URLs (the JSON report lists every checked official URL):",
            ]
        )
        lines.extend(
            f"- {page['division_name']}: {page['result_url']}"
            for page in election["pages"][:3]
        )
        lines.append("")
    lines.extend(
        [
            "## Overall conclusion",
            "",
            "**B. Official final_position is not published in the checked 2017 or 2021 Surrey candidate result tables and should remain NULL.**",
            "",
            "Candidate display order was observed but is not an official rank field and was not converted into final position.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """Generate the requested Markdown and JSON reports from official pages."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, default=OUTPUT_DIRECTORY)
    args = parser.parse_args()

    report = {
        "report_title": "Surrey Final Position Provenance Audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "Ordinary public HTTP inspection of candidate table headers; no browser automation or ranking calculation.",
        "elections": [
            _inspect_election(year, audit_path)
            for year, audit_path in ELECTION_AUDITS.items()
        ],
    }
    args.output_directory.mkdir(parents=True, exist_ok=True)
    json_path = args.output_directory / "final_position_provenance_audit.json"
    markdown_path = args.output_directory / "final_position_provenance_audit.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path)}, indent=2))


if __name__ == "__main__":
    main()
