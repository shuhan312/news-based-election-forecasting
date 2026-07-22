"""Run the N5 pre-implementation audits and write their CSV/JSON outputs.

Measures only; fits nothing. The numbers written here feed the written N5
candidate specification (docs/n5_candidate_specifications.md) and the
data-requirements/risks record (docs/n5_data_requirements_and_risks.md).
"""

from __future__ import annotations

import csv
import json
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from no_news_baseline.coverage_evaluation import build_evaluation_universe
from no_news_baseline.n5_specification_audit import (
    area_identifiability_audit,
    build_contest_usability_audit,
    election_cycle_audit,
    party_identifiability_audit,
    reconcile_outcome_states,
)


REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_INPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/n5_specification"


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty audit table to {path}.")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_n5_specification_audit(
    feature_path: Path,
    target_path: Path,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
) -> tuple[Path, ...]:
    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    features = feature_payload.get("rows")
    targets = target_payload.get("rows")
    if not isinstance(features, list) or not isinstance(targets, list):
        raise ValueError("Feature and target JSON files must each contain a rows list.")

    contest_audit = build_contest_usability_audit(features, targets)
    outcome_states = reconcile_outcome_states(build_evaluation_universe(features, targets))
    cycles = election_cycle_audit(contest_audit)
    parties = party_identifiability_audit(features, targets, contest_audit)
    areas, repetition_distribution = area_identifiability_audit(contest_audit)

    output_directory.mkdir(parents=True, exist_ok=True)
    contest_path = output_directory / "n5_contest_usability_audit.csv"
    party_path = output_directory / "n5_party_identifiability_audit.csv"
    area_path = output_directory / "n5_area_identifiability_audit.csv"
    cycle_path = output_directory / "n5_election_cycle_audit.csv"
    summary_path = output_directory / "n5_audit_summary.json"

    _write_csv(contest_path, contest_audit)
    _write_csv(party_path, parties)
    _write_csv(area_path, areas)
    _write_csv(cycle_path, cycles)

    usable = [row for row in contest_audit if row["usable_complete_composition"]]
    summary_path.write_text(
        json.dumps(
            {
                "total_contests": len(contest_audit),
                "usable_complete_compositions": len(usable),
                "unusable_reasons": _count(contest_audit, "unusable_reason"),
                "outcome_states": outcome_states,
                "area_repetition_distribution": repetition_distribution,
                "parties_with_individual_effect_support": sum(
                    row["individual_effect_supported"] for row in parties
                ),
                "party_count_audited": len(parties),
                "areas_with_area_effect_support": sum(
                    row["area_effect_supported"] for row in areas
                ),
                "area_count_audited": len(areas),
                "cycles_individually_estimable": sum(
                    row["cycle_effect_individually_estimable"] for row in cycles
                ),
                "cycle_count_audited": len(cycles),
            },
            indent=2,
        )
        + "\n"
    )
    return contest_path, party_path, area_path, cycle_path, summary_path


def _count(rows: tuple[dict[str, object], ...], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(field)
        if value is not None:
            counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features", type=Path, default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_features.json"
    )
    parser.add_argument(
        "--targets", type=Path, default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_targets.json"
    )
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    for path in run_n5_specification_audit(
        arguments.features, arguments.targets, arguments.output_directory
    ):
        print(path)
