"""Generate the auditable no-news electoral baseline from reviewed inputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.master_database import build_master_database, load_audited_elections
from election_extractor.no_news_baseline import build_no_news_electoral_baseline
from generate_master_election_database import (
    reviewed_geographic_mapping_rows,
    reviewed_historical_reference_inputs,
)
from election_extractor.candidate_continuity_evidence import (
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/no_news_electoral_baseline"


def generate_no_news_baseline(output_directory: Path = OUTPUT_DIRECTORY) -> Path:
    """Write a reproducible model-input baseline without downloading sources."""

    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    payload = build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
        candidate_continuity_evidence=evidence_by_candidate_key(
            load_candidate_continuity_evidence(
                permitted_election_ids=(item.configuration.election_id for item in elections)
            )
        ),
    )
    rows, coverage = build_no_news_electoral_baseline(payload)
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / "no_news_electoral_baseline.json"
    path.write_text(json.dumps({"rows": rows, "coverage": coverage}, indent=2) + "\n")
    return path


if __name__ == "__main__":
    print(generate_no_news_baseline())
