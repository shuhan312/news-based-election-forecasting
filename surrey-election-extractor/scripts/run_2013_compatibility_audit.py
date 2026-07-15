"""Run the bounded, read-only Surrey County Council Election 2013 audit."""

from __future__ import annotations

import json
from pathlib import Path

from election_extractor.compatibility_audit import (
    audit_markdown,
    build_2013_audit,
    inspect_official_result_page,
)
from election_extractor.election_compatibility import (
    UrllibCompatibilityPageClient,
    check_configured_election_compatibility,
)
from election_extractor.election_config import load_election_config
from election_extractor.discovery import UrllibOfficialArchiveClient
from election_extractor.search_providers.mock_provider import MockSearchProvider


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/2013_real_compatibility"
ELECTION_ID = "surrey-county-council-2013"


def run(output_directory: Path = OUTPUT_DIRECTORY) -> tuple[Path, Path, dict[str, object]]:
    """Inspect configuration, archive and three result pages without extraction."""

    configuration = next(
        item for item in load_election_config() if item.election_id == ELECTION_ID
    )
    # The mock provider prevents indexed-search fallback. The only live reads
    # are the configured public Surrey archive/index and three official result
    # pages selected by existing discovery.
    report = check_configured_election_compatibility(
        configuration,
        MockSearchProvider({}),
        UrllibOfficialArchiveClient(),
        UrllibCompatibilityPageClient(),
        sample_size=3,
    )
    page_client = UrllibCompatibilityPageClient()
    sample_urls = report.provenance.get("representative_result_page_urls", ())
    page_evidence = tuple(
        inspect_official_result_page(str(url), page_client) for url in sample_urls
    )
    audit = build_2013_audit(configuration, report, page_evidence)
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "surrey-county-council-2013_compatibility.json"
    markdown_path = output_directory / "surrey-county-council-2013_compatibility.md"
    json_path.write_text(json.dumps(audit, default=str, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(audit_markdown(audit), encoding="utf-8")
    return json_path, markdown_path, audit


def main() -> None:
    """Write the requested Markdown and JSON compatibility evidence files."""

    json_path, markdown_path, audit = run()
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "compatibility_status": audit["compatibility_status"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
