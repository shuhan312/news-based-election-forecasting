"""Report what each of the five specifications could be estimated from.

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_specification_coverage

Fits nothing. It answers the question that has to be settled before any model
comparison means anything: for each specification, how many candidate rows
carry news at all, how many of those are Reform UK, and which of the four
feature sources - local party, local context, national party, national
context - actually reached them.

A comparison run without this can report "news adds nothing" when the truth is
"no news was attached", and the two are indistinguishable in the output.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from news_modelling.news_arms import SPECIFICATIONS, arm_coverage
from news_modelling.residual_specifications import (
    build_specification_rows,
    specification_coverage,
)
from news_modelling.stage1_bundle import load_stage1_bundle

BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
CONTRACT = Path(
    "surrey-election-extractor/outputs/no_news_candidate_contests/"
    "no_news_candidate_contest_features.json")
NEWS = Path("news_features/context_aggregated_features.parquet")
ARTICLES = Path("news_features/article_level_news_features.parquet")
OUT = Path("news_features/specification_coverage")

# Coverage counts first. They are meaningful even where sentiment is too
# sparse to model, and they are what the archive-completeness controls need.
FEATURE_COLUMNS = [
    "cov_n_articles", "cov_n_publications", "cov_n_source_arms",
    "cov_total_party_mentions", "cov_total_candidate_mentions",
]

# The cumulative snapshots, which are what a forecast made N days out would
# have seen. The non-overlapping windows are kept for the timing analysis and
# are added once a specification has enough rows to support one.
WINDOWS = ["previous_7_days", "previous_30_days", "previous_90_days",
           "previous_180_days"]


def main() -> None:
    bundle = load_stage1_bundle(BUNDLE)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))["rows"]
    division_names = {str(r["division_id"]): str(r["division_name"])
                      for r in contract}
    election_dates = {str(r["election_id"]): pd.to_datetime(
        str(r["election_date"])).date() for r in contract}

    news = pd.read_parquet(NEWS).to_dict("records")
    # Party ids in the aggregation are opaque hashes; the article-level table
    # is where they carry a readable name, and the join to Stage 1 is on the
    # standardised name.
    articles = pd.read_parquet(ARTICLES)
    party_names = (articles.dropna(subset=["focal_party_id"])
                   .drop_duplicates("focal_party_id")
                   .set_index("focal_party_id")["focal_party_name"].to_dict())

    print(f"Stage 1: {bundle.selected_architecture}, "
          f"{len(bundle.out_of_fold)} out-of-fold rows")
    print(f"news: {len(news)} aggregated rows, "
          f"{len(party_names)} named parties\n")

    arms = arm_coverage(news)
    print("=== news rows by scope ===")
    for scope, count in arms["rows_by_scope"].items():
        print(f"  {scope:24s} {count:5d}")
    print(f"\narms present in fewer than three elections: "
          f"{arms['arms_with_too_few_elections'] or 'none'}\n")

    report = {"arms": arms, "specifications": {}}
    for specification in SPECIFICATIONS:
        rows = build_specification_rows(
            specification, list(bundle.out_of_fold), news, division_names,
            election_dates, party_names,
            feature_columns=FEATURE_COLUMNS, windows=WINDOWS)
        coverage = specification_coverage(rows)
        report["specifications"][specification] = coverage

        print(f"=== {specification} ===")
        print(f"  rows {coverage['rows']}, "
              f"Reform {coverage['reform_rows']}, "
              f"rows carrying news {coverage['rows_with_any_news']}, "
              f"Reform rows carrying news {coverage['reform_rows_with_news']}")
        if coverage.get("rows_by_feature_source"):
            for source, count in coverage["rows_by_feature_source"].items():
                print(f"    {source:20s} reached {count:5d} rows")
        for verdict in coverage["verdicts"]:
            print(f"  ! {verdict}")
        print()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "specification_coverage.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"written to {OUT}")


if __name__ == "__main__":
    main()
