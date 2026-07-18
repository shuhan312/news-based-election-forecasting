"""Generate a local, reproducible review queue for repeated candidate names.

The generated JSON and Markdown are local audit outputs. They are intentionally
not versioned as a large research-data artifact; this script and its tests are
the reproducible implementation committed to the repository.
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
from election_extractor.candidate_continuity_review import (
    build_candidate_continuity_review,
    review_as_dict,
)
from election_extractor.master_database import build_master_database, load_audited_elections, payload_as_dict
from generate_master_election_database import (
    reviewed_geographic_mapping_rows,
    reviewed_historical_reference_inputs,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/candidate_continuity_review"


def build_current_review() -> dict[str, object]:
    """Build from audited inputs so the queue reflects the current evidence register."""

    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    evidence = evidence_by_candidate_key(
        load_candidate_continuity_evidence(
            permitted_election_ids=(item.configuration.election_id for item in elections)
        )
    )
    payload = build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
        candidate_continuity_evidence=evidence,
    )
    rows = payload_as_dict(payload)["Candidate Results"]
    if not isinstance(rows, list):
        raise ValueError("Master payload must expose Candidate Results as a list.")
    return review_as_dict(build_candidate_continuity_review(rows, evidence))


def review_markdown(report: dict[str, object]) -> str:
    """Summarise the queue without turning tier C into an identity conclusion."""

    summary = report["summary"]
    assert isinstance(summary, dict)
    return "\n".join(
        (
            "# Candidate Continuity Review Queue",
            "",
            "This report groups exact repeated published names for manual review. A repeated name is not evidence that two records describe the same person.",
            "",
            f"- Repeated exact-name groups: {summary['repeated_exact_name_groups']}",
            f"- Candidate appearances in those groups: {summary['candidate_appearances_in_review']}",
            f"- Tier A rows (direct official profile): {summary['tier_a_direct_profile_rows']}",
            f"- Tier B rows (reviewed multi-source official evidence): {summary['tier_b_multi_source_rows']}",
            f"- Tier C rows (requires review; no identity claim): {summary['tier_c_review_required_rows']}",
            "",
            "Tier C records remain NULL for candidate history and incumbency. The JSON companion retains every occurrence, official result URL and any approved evidence URLs.",
            "",
        )
    )


def generate_review_outputs(output_directory: Path = OUTPUT_DIRECTORY) -> tuple[Path, Path]:
    """Write local JSON and Markdown audit files without contacting any website."""

    report = build_current_review()
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "candidate_continuity_review.json"
    markdown_path = output_directory / "candidate_continuity_review.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    markdown_path.write_text(review_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    """Create the local review queue and print only its paths."""

    paths = generate_review_outputs()
    print(json.dumps({"json": str(paths[0]), "markdown": str(paths[1])}, indent=2))


if __name__ == "__main__":
    main()
