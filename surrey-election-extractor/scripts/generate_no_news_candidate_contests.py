"""Generate the model-facing no-news candidate-contest release.

This writes the final Stage 1 input contract.  The supervisor's Stage 1
brief makes ``analysis_vote_share`` the primary target and the 7 May 2026
two-member wards the primary holdout; the earlier party-share development
route could represent neither, and has been superseded by this
candidate-contest release.

Predictors and current-election outcomes are written to separate files as a
structural leakage control: downstream model code must join them explicitly
by ``candidate_contest_id`` and cannot accidentally discover an outcome
column while selecting baseline features.

Usage (from the IRP repository root):

    PYTHONPATH=surrey-election-extractor .venv/bin/python \
      surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
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
from election_extractor.master_database import (
    build_master_database,
    load_audited_elections,
)
from election_extractor.no_news_candidate_contest import (
    build_no_news_candidate_contests,
)
from generate_master_election_database import (
    reviewed_geographic_mapping_rows,
    reviewed_historical_reference_inputs,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/no_news_candidate_contests"


def generate_no_news_candidate_contests(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> Path:
    """Write deterministic candidate features, targets and coverage.

    The inputs are the same audited election configurations, reviewed
    geographic mapping and reviewed historical-reference decisions used by
    every other release, so this file can never disagree with the master
    database about which historical comparisons are permitted.
    """

    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    payload = build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
        candidate_continuity_evidence=evidence_by_candidate_key(
            load_candidate_continuity_evidence(
                permitted_election_ids=(
                    item.configuration.election_id for item in elections
                )
            )
        ),
    )

    features, targets, coverage = build_no_news_candidate_contests(payload)

    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "no_news_candidate_contest_features.json").write_text(
        json.dumps({"rows": features, "coverage": coverage}, indent=2) + "\n"
    )
    (output_directory / "no_news_candidate_contest_targets.json").write_text(
        json.dumps({"rows": targets}, indent=2) + "\n"
    )
    audit_path = output_directory / "no_news_candidate_contest_audit.json"
    audit_path.write_text(json.dumps(coverage, indent=2) + "\n")
    return audit_path


if __name__ == "__main__":
    print(generate_no_news_candidate_contests())
