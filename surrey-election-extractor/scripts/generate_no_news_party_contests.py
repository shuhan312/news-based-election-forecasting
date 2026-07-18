"""Generate the model-facing no-news party-contest release.

The script writes predictors and current-election targets to separate files.
This is intentional research governance: downstream model code must join them
explicitly by ``party_contest_id`` and cannot accidentally discover outcome
columns while selecting baseline features.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.candidate_continuity_evidence import (
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)
from election_extractor.master_database import build_master_database, load_audited_elections
from election_extractor.no_news_party_contest import build_no_news_party_contests
from generate_master_election_database import (
    reviewed_geographic_mapping_rows,
    reviewed_historical_reference_inputs,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/no_news_party_contests"


def generate_no_news_party_contests(output_directory: Path = OUTPUT_DIRECTORY) -> Path:
    """Write deterministic features, targets and coverage from audited inputs."""

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
    features, targets, coverage = build_no_news_party_contests(payload)
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "no_news_party_contest_features.json").write_text(
        json.dumps({"rows": features, "coverage": coverage}, indent=2) + "\n"
    )
    (output_directory / "no_news_party_contest_targets.json").write_text(
        json.dumps({"rows": targets}, indent=2) + "\n"
    )
    audit_path = output_directory / "no_news_party_contest_audit.json"
    audit_path.write_text(json.dumps(coverage, indent=2) + "\n")
    return audit_path


if __name__ == "__main__":
    print(generate_no_news_party_contests())
