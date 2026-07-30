"""Run selection for every specification and write the results out.

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_feature_selection

Produces, per specification, the selected column list and the verdict for every
column considered; plus one split-coverage report covering all of them. The
verdict file is the larger and the more useful: a column list says what a model
will be fitted on, whereas the verdicts say why everything else was left out,
which is the part that can be checked by someone who disagrees.

Selection is run separately per specification rather than once globally,
because the blocks overlap - the combined block already contains the national
coverage - and a single global list would quietly place the same articles in a
model twice.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .feature_selection import (
    SPECIFICATION_BLOCKS,
    select_for_specification,
    selection_report,
    split_coverage,
)
from .ward_party_build import IDENTIFIER_COLUMNS

REPO = Path(__file__).resolve().parents[2]
FEATURE_TABLE = (REPO / "news_features/ward_party_election_features_v1"
                 / "ward_party_election_features.parquet")
OUTPUT_DIRECTORY = REPO / "news_features/feature_selection_v1"

# The primary outcome. Selection is fitted against this; the secondary outcomes
# the brief lists get their own runs once an estimator exists to use them, and
# are not selected for here because a feature set chosen against one target is
# not automatically right for another.
PRIMARY_TARGET = "target__party_vote_share"
LEGACY_OPT_IN = "--allow-legacy-pilot"


def write_verdicts(path: Path, selection) -> None:
    """One row per column considered, kept or not, with the reason."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "column", "block", "kept", "stage", "reason",
            "training_observations", "association", "duplicate_of"])
        writer.writeheader()
        for verdict in sorted(selection.verdicts,
                              key=lambda v: (not v.kept, v.block, v.column)):
            writer.writerow(asdict(verdict))


def main() -> None:
    # The v1 ward table is downstream of the 67-article pilot, whereas the
    # production feature table now carries a canonical release id for 1,632
    # articles. Do not silently turn a pilot selection report into the current
    # methodological conclusion. Explicit opt-in remains available solely for
    # exact reproduction of the historical analysis.
    if LEGACY_OPT_IN not in sys.argv:
        raise RuntimeError(
            "Blocked: feature_selection_v1 is a legacy 67-article pilot "
            "analysis. Use --allow-legacy-pilot only for reproduction; migrate "
            "selection to news_feature_table_v1 before fitting the news model."
        )

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(FEATURE_TABLE)

    coverage = split_coverage(frame, identifiers=IDENTIFIER_COLUMNS)
    (OUTPUT_DIRECTORY / "split_news_coverage.json").write_text(
        json.dumps(coverage, indent=2), encoding="utf-8")

    print("News present per split")
    for split, entry in sorted(coverage.items()):
        note = "" if entry["news_comparison_possible"] else "  <- no news"
        print(f"  {split:24s} {entry['rows_with_any_news']:5d} / "
              f"{entry['rows']:5d} rows{note}")

    summaries = {}
    print(f"\nSelection against {PRIMARY_TARGET}")
    for specification in SPECIFICATION_BLOCKS:
        selection = select_for_specification(
            frame, PRIMARY_TARGET, specification,
            identifiers=IDENTIFIER_COLUMNS)
        report = selection_report(selection)
        summaries[specification] = report

        (OUTPUT_DIRECTORY / f"selected_{specification}.json").write_text(
            json.dumps({"specification": specification,
                        "blocks": sorted(SPECIFICATION_BLOCKS[specification]),
                        **report,
                        "columns": selection.selected}, indent=2),
            encoding="utf-8")
        write_verdicts(
            OUTPUT_DIRECTORY / f"verdicts_{specification}.csv", selection)

        print(f"  {specification:9s} {report['candidate_columns']:6d} "
              f"considered -> {report['selected_columns']:3d} selected "
              f"({report['rows_per_selected_feature']:.0f} training rows each)")

    (OUTPUT_DIRECTORY / "selection_summary.json").write_text(
        json.dumps({"target": PRIMARY_TARGET,
                    "split_news_coverage": coverage,
                    "specifications": summaries}, indent=2),
        encoding="utf-8")

    print(f"\nWritten to {OUTPUT_DIRECTORY.relative_to(REPO)}")


if __name__ == "__main__":
    main()
