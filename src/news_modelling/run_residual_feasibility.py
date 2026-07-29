"""Diagnose whether Approach A can be estimated from the data as it stands.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_residual_feasibility

Why this exists as a separate step from training
------------------------------------------------
Every discussion so far about whether the news sample is large enough has run
on estimates. This produces the actual numbers: how many candidate rows carry
news, how many of those are Reform UK, which elections have both a baseline
and news, and what an election-wide news feature is collinear with.

It fits nothing. A feasibility check that trained a model would report a
score, and a score invites being quoted; the point here is to establish
whether a score would mean anything before one exists.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pandas as pd

from news_modelling.residual_dataset import (
    build_residual_rows,
    diagnose_coverage,
    reform_rows_by_fold,
)
from news_modelling.stage1_bundle import load_stage1_bundle

BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
CONTRACT = Path(
    "surrey-election-extractor/outputs/no_news_candidate_contests/"
    "no_news_candidate_contest_features.json"
)
NEWS = Path("news_features/context_aggregated_features.parquet")
OUT = Path("news_features/residual_feasibility")

# Coverage columns describe how much news was found and how reliable it is.
# They are the honest first candidates for a news feature set, because a
# coverage count is meaningful even where sentiment is too sparse to model.
CANDIDATE_FEATURES = [
    "cov_n_articles", "cov_n_publications", "cov_n_source_arms",
    "cov_n_full_text", "cov_total_party_mentions", "cov_total_candidate_mentions",
]


def _parse_election_date(text: str) -> date:
    """Contract dates arrive as '2 May 2013' or as ISO.

    Both are parsed without a dayfirst hint: the day-name form is
    unambiguous, and forcing dayfirst on an ISO string makes pandas warn
    about a interpretation it is not actually applying.
    """

    return pd.to_datetime(str(text)).date()


def main() -> None:
    bundle = load_stage1_bundle(BUNDLE)
    print(f"Stage 1 bundle loaded: {bundle.bundle_version}, "
          f"architecture {bundle.selected_architecture}, "
          f"{len(bundle.out_of_fold)} out-of-fold rows\n")

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))["rows"]
    division_names = {
        str(row["division_id"]): str(row["division_name"]) for row in contract
    }
    election_dates = {
        str(row["election_id"]): _parse_election_date(row["election_date"])
        for row in contract
    }

    news = pd.read_parquet(NEWS).to_dict("records")

    diagnosis = diagnose_coverage(
        list(bundle.out_of_fold), news, division_names, election_dates
    )
    record = diagnosis.as_record()

    print("=== Election coverage ===")
    print(f"  Stage 1 out-of-fold elections : {len(diagnosis.stage1_elections)}")
    print(f"  news elections                : {len(diagnosis.news_elections)}")
    print(f"  both                          : {len(diagnosis.shared_elections)}"
          f"  {list(diagnosis.shared_elections)}")
    print(f"  baseline but no news          : {len(diagnosis.stage1_only_elections)}")
    print(f"  news but no baseline          : {len(diagnosis.news_only_elections)}"
          f"  {list(diagnosis.news_only_elections)}")
    print(f"  divisions with news in those  : "
          f"{diagnosis.divisions_in_elections_without_baseline}"
          f"  (not a join failure - those elections have no baseline)")

    print("\n=== What Approach A could train on ===")
    print(f"  division-level  : {diagnosis.division_level_rows} candidate rows, "
          f"{diagnosis.division_level_reform_rows} Reform UK")
    print(f"                    divisions: {list(diagnosis.division_level_divisions)}")
    print(f"  election-wide   : {diagnosis.election_wide_rows} candidate rows, "
          f"{diagnosis.election_wide_reform_rows} Reform UK, "
          f"{diagnosis.election_wide_distinct_values} distinct feature value(s)")

    residuals = build_residual_rows(
        list(bundle.out_of_fold), news, division_names, election_dates,
        feature_columns=CANDIDATE_FEATURES,
    )
    by_fold = reform_rows_by_fold(residuals)
    record["residual_rows_built"] = len(residuals)
    record["rows_by_election"] = by_fold

    print(f"\n=== Residual rows actually built: {len(residuals)} ===")
    for election, counts in by_fold.items():
        print(f"  {election:52s} {counts['rows']:4d} rows  "
              f"Reform {counts['reform_uk']:3d}  UKIP {counts['ukip']:3d}")

    if residuals:
        values = [row["residual"] for row in residuals]
        record["residual_summary"] = {
            "rows": len(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }
        print(f"\n  residual mean {record['residual_summary']['mean']:+.3f} "
              f"(range {min(values):+.2f} to {max(values):+.2f})")

    print("\n=== Verdicts ===")
    for verdict in diagnosis.verdicts():
        print(f"  ! {verdict}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "coverage_diagnosis.json").write_text(
        json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8"
    )
    if residuals:
        with (OUT / "residual_rows.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(residuals[0]))
            writer.writeheader()
            writer.writerows(residuals)
    print(f"\nwritten to {OUT}")


if __name__ == "__main__":
    main()
