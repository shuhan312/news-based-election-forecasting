"""Run the frozen leave-one-party-out news robustness audit.

Usage:

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_production_news_lopo

No 2026 path is accepted by this command.
"""

from pathlib import Path

from news_modelling.production_news_lopo import run_lopo, write_outputs


FEATURES = Path("news_features/news_feature_table_v1.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
OOF = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1/out_of_fold_predictions.csv")
PRIMARY = Path("news_features/production_news_experiment_v1/experiment_results.json")
OUTPUT = Path("news_features/production_news_lopo_v1")


def main() -> None:
    report = run_lopo(FEATURES, AUDIT, OOF, PRIMARY)
    write_outputs(report, OUTPUT)
    print(f"omissions              : {len(report['omitted_parties'])}")
    print(f"comparisons             : {report['total_comparisons']}")
    print(f"created improvements    : {report['overall_improvements_after_omission']}")
    print(f"verdict                 : {report['robustness_verdict']}")
    print("2026 holdout read       : no")
    print(f"written to              : {OUTPUT}")


if __name__ == "__main__":
    main()
