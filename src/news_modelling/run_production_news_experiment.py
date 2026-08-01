"""Run the frozen pre-2026 production news comparison.

Usage from the repository root:

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_production_news_experiment

The command reads Stage 1 out-of-fold predictions only.  It has no argument for
the 2026 holdout bundle, so model selection cannot accidentally inspect it.
"""

from pathlib import Path

from news_modelling.production_news_experiment import run_experiment, write_outputs


FEATURES = Path("news_features/news_feature_table_v1.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
OOF = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1/out_of_fold_predictions.csv")
OUTPUT = Path("news_features/production_news_experiment_v1")


def main() -> None:
    report, predictions = run_experiment(FEATURES, AUDIT, OOF)
    write_outputs(report, predictions, OUTPUT)

    print(f"fitting party rows : {report['training_party_rows']}")
    print(f"specifications     : {len(report['specification_results'])}")
    print("2026 holdout read  : no")
    print(f"written to         : {OUTPUT}")


if __name__ == "__main__":
    main()

