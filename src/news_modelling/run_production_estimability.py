"""Create the production news-modelling estimability report.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_production_estimability

This is the required gate between feature construction and model fitting.  It
does not inspect 2026 outcomes and does not fit or choose a model.
"""

from __future__ import annotations

from pathlib import Path

from news_modelling.production_estimability import (
    build_estimability_report,
    write_report,
)


FEATURE_TABLE = Path("news_features/news_feature_table_v1.csv")
FEATURE_METADATA = Path("news_features/news_feature_table_v1_metadata.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUTPUT = Path("news_features/production_estimability_v1/estimability_report.json")


def main() -> None:
    report = build_estimability_report(
        FEATURE_TABLE,
        FEATURE_METADATA,
        BUNDLE / "out_of_fold_predictions.csv",
    )
    write_report(report, OUTPUT)

    overlap = report["baseline_overlap"]
    print(f"canonical corpus : {report['canonical_release']['articles']} articles")
    print(f"feature grid     : {report['feature_table']['rows']} complete rows")
    print(
        "baseline overlap : "
        f"2017={overlap['SCC-2017-05']['out_of_fold_candidate_rows']} rows, "
        f"2021={overlap['SCC-2021-05']['out_of_fold_candidate_rows']} rows"
    )
    print("Reform-specific coefficient: NOT ESTIMABLE")
    print("Combined/national: exploratory; local: sensitivity only")
    print(f"written to {OUTPUT}")


if __name__ == "__main__":
    main()
