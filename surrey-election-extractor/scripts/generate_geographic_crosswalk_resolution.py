"""Generate the read-only Surrey Geographic Crosswalk Resolution Layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Direct execution uses the checked-out source only. It does not open or
    # modify candidate results, election workbooks or historical features.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.geographic_crosswalk_resolution import (
    build_geographic_crosswalk_resolution,
    geographic_crosswalk_methodology_markdown,
    geographic_crosswalk_resolution_dataset,
    geographic_crosswalk_resolution_report_markdown,
    load_geographic_crosswalk_resolution_policy,
)
from election_extractor.geographic_mapping_decision import GeographicMappingDecisionRow
from scripts.generate_geographic_mapping_decision import (
    generate_geographic_mapping_decision_outputs,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/geographic_crosswalk_resolution"


def generate_geographic_crosswalk_resolution_outputs(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[dict[str, Path], dict[str, object]]:
    """Regenerate source-backed decisions, then classify topology without enrichment."""

    # The prior generator recreates the 167 GIS decision rows from configured
    # official sources. This prevents a hand-edited intermediate file becoming
    # the source for crosswalk classification.
    _, _, _, decision_dataset = generate_geographic_mapping_decision_outputs()
    raw_rows = decision_dataset["decision_rows"]
    if not isinstance(raw_rows, list):
        raise ValueError("Geographic mapping decision dataset must contain decision_rows.")
    decisions = tuple(GeographicMappingDecisionRow(**row) for row in raw_rows)
    policy = load_geographic_crosswalk_resolution_policy()
    rows = build_geographic_crosswalk_resolution(decisions, policy)
    dataset = geographic_crosswalk_resolution_dataset(rows, policy)

    output_directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        "full_dataset": output_directory / "geographic_crosswalk_resolution_dataset.json",
        "direct_dataset": output_directory / "final_direct_mapping_dataset.json",
        "crosswalk_dataset": output_directory / "analytical_crosswalk_dataset.json",
        "not_comparable_dataset": output_directory / "not_comparable_dataset.json",
        "report": output_directory / "geographic_crosswalk_resolution_report.md",
        "methodology": output_directory / "geographic_crosswalk_methodology.md",
    }
    outputs["full_dataset"].write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    for output_key, dataset_key in (
        ("direct_dataset", "final_direct_mapping_dataset"),
        ("crosswalk_dataset", "analytical_crosswalk_dataset"),
        ("not_comparable_dataset", "not_comparable_dataset"),
    ):
        outputs[output_key].write_text(
            json.dumps(dataset[dataset_key], indent=2) + "\n",
            encoding="utf-8",
        )
    outputs["report"].write_text(
        geographic_crosswalk_resolution_report_markdown(dataset),
        encoding="utf-8",
    )
    outputs["methodology"].write_text(
        geographic_crosswalk_methodology_markdown(policy),
        encoding="utf-8",
    )
    return outputs, dataset


def main() -> None:
    """Print compact status without exposing generated audit contents in the console."""

    outputs, dataset = generate_geographic_crosswalk_resolution_outputs()
    summary = dataset["summary"]
    assert isinstance(summary, dict)
    print(
        json.dumps(
            {
                "report": str(outputs["report"]),
                "methodology": str(outputs["methodology"]),
                "accepted_direct": summary["accepted_direct_mappings"],
                "partial_crosswalk": summary["partial_crosswalk_relationships"],
                "not_comparable": summary["not_comparable_relationships"],
                "requires_review": summary["requires_review_relationships"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
