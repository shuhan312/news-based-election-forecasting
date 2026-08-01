"""Freeze the blinded 2026 news-layer predictions.

Usage from the repository root:

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions

This is the single sanctioned opening of the Stage 1 holdout file by the
news layer.  The bundle is loaded through the validating read-only loader,
observed columns are stripped before any prediction is formed, and the
output directory refuses to be overwritten once written.  No comparison
with 2026 outcomes happens here or anywhere until the separate, single
unblinding step.
"""

from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    build_blinded_predictions,
    write_outputs,
)
from news_modelling.production_news_experiment import _read_csv
from news_modelling.stage1_bundle import load_stage1_bundle

import json

FEATURES = Path("news_features/news_feature_table_v1.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUTPUT = Path("news_features/blinded_2026_predictions_v1")


def main() -> None:
    # The validating loader checks the bundle against its own hash manifest,
    # so the freeze provably reads the same files the Stage 1 metrics
    # describe — not a quietly regenerated baseline.
    bundle = load_stage1_bundle(BUNDLE)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    features = _read_csv(FEATURES)

    protocol, predictions = build_blinded_predictions(
        oof_rows=[dict(row) for row in bundle.out_of_fold],
        holdout_rows=[dict(row) for row in bundle.holdout],
        features=features,
        audit=audit,
    )
    manifest = write_outputs(
        protocol, predictions, OUTPUT,
        input_paths={
            "news_feature_table_v1.csv": FEATURES,
            "estimability_report.json": AUDIT,
            "out_of_fold_predictions.csv": BUNDLE / "out_of_fold_predictions.csv",
            "holdout_predictions.csv": BUNDLE / "holdout_predictions.csv",
        },
    )

    # Deliberately counts and hashes only: predicted values stay in the
    # frozen files, and observed values were never loaded past the strip.
    print(f"blinded candidate rows : {protocol['blinded_candidate_rows']}")
    print(f"specifications frozen  : {len(protocol['specifications'])}")
    print(f"prediction rows        : {manifest['prediction_rows']}")
    print(f"predictions sha256     : {manifest['blinded_predictions.csv']}")
    print(f"protocol sha256        : {manifest['frozen_protocol.json']}")
    print(f"written to             : {OUTPUT}")
    print("2026 outcomes read     : no")


if __name__ == "__main__":
    main()
