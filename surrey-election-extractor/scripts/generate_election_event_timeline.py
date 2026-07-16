"""Generate local event-history outputs without altering completed source audits."""

from __future__ import annotations

import json
from pathlib import Path

from election_extractor.election_history import (
    build_election_history,
    data_dictionary_markdown,
    event_coverage_markdown,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/election_event_timeline"


def run(output_directory: Path = OUTPUT_DIRECTORY) -> dict[str, Path]:
    """Write derived event data while keeping official extraction inputs read-only."""

    history = build_election_history()
    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "coverage_json": output_directory / "election_event_coverage_report.json",
        "coverage_markdown": output_directory / "election_event_coverage_report.md",
        "canonical_dataset": output_directory / "canonical_election_event_dataset.json",
        "chronology": output_directory / "election_chronology.json",
        "enrichment": output_directory / "safe_enrichment.json",
        "dictionary": output_directory / "election_history_data_dictionary.md",
    }
    files["coverage_json"].write_text(
        json.dumps(history["coverage_report"], indent=2) + "\n", encoding="utf-8"
    )
    files["coverage_markdown"].write_text(
        event_coverage_markdown(history["coverage_report"]), encoding="utf-8"
    )
    # Keep the event-level and candidate-level rows in one canonical derived
    # dataset.  By-election event metadata is therefore visible even when no
    # official candidate-result page has yet been retrieved for that event.
    files["canonical_dataset"].write_text(
        json.dumps(
            {
                "schema_version": history["schema_version"],
                "scope": history["scope"],
                "source_inputs": history["source_inputs"],
                "election_events": history["election_events"],
                "canonical_candidate_results": history["canonical_candidate_results"],
                "provenance_rules": history["provenance_rules"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    files["chronology"].write_text(
        json.dumps(history["election_chronology"], indent=2) + "\n", encoding="utf-8"
    )
    files["enrichment"].write_text(
        json.dumps(history["safe_enrichment"], indent=2) + "\n", encoding="utf-8"
    )
    files["dictionary"].write_text(data_dictionary_markdown(), encoding="utf-8")
    return files


def main() -> None:
    """Print generated paths to make the local audit run easy to verify."""

    for name, path in run().items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
