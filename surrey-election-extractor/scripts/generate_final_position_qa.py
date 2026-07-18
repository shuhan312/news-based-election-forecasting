"""Write the final-position QA release package without changing source data."""

from __future__ import annotations

import json
import sys
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.final_position_qa import build_final_position_qa
from election_extractor.master_database import load_audited_elections


def main() -> None:
    """Create JSON and concise Markdown outputs for review and release."""
    output = PROJECT_ROOT / "outputs/final_position_qa"
    package = build_final_position_qa(load_audited_elections())
    summary = package["summary"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "final_position_qa.json").write_text(json.dumps(package, indent=2) + "\n")
    # The standalone validation report is intentionally one official page per
    # row, so it can be opened directly in Excel without interpreting the
    # larger nested QA package.
    report_fields = list(package["page_validation"][0])
    with (output / "final_position_validation_report.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=report_fields)
        writer.writeheader()
        writer.writerows(package["page_validation"])
    (output / "final_position_validation_report.json").write_text(
        json.dumps(package["page_validation"], indent=2) + "\n"
    )
    lines = ["# Final Position QA Release Package", "", f"- Result pages: {summary['result_page_count']}", f"- Automatically validated pages: {summary['automatically_validated_pages']}", f"- Tie-review pages: {len(package['tie_page_context'])}", f"- Tied candidate rows: {summary['tied_candidate_rows']}", f"- Required independent official reviews: {summary['required_independent_official_reviews']}", f"- Fully verified independent official reviews: {summary['fully_verified_independent_official_reviews']}", f"- Outcome-only independent official reviews: {summary['outcome_only_independent_official_reviews']}", f"- Completed independent official reviews: {summary['completed_independent_official_reviews']}", f"- Pending independent official reviews: {summary['pending_independent_official_reviews']}", f"- Analysis readiness: `{summary['analysis_readiness_status']}`", f"- Secondary risk sample: `{summary['secondary_risk_sample_status']}`", "", "A verified row has a recorded declaration, Returning Officer file, official archive, official election map or official council announcement. Outcome-only corroboration is explicitly limited to the published winner/outcome; it is never treated as a complete candidate-rank table."]
    (output / "final_position_qa.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "tied_candidate_reviews": len(package["tie_candidate_review_list"]),
            }
        )
    )


if __name__ == "__main__":
    main()
