"""Freeze the v2 (enrichment) blinded 2026 predictions.

    PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions_v2

Second and final pre-registered model version. Reads the hash-verified
Stage 1 bundle, news feature table v2 and the frozen estimability report;
writes the v2 blinded prediction file beside the untouched v1 freeze.
The v1 sha256 manifest is a required input so the v2 protocol can bind
itself to the exact v1 files it will be unblinded alongside.
"""

from pathlib import Path

import json

from news_modelling.blinded_2026_predictions import write_outputs
from news_modelling.blinded_2026_predictions_v2 import (
    build_v2_blinded_predictions,
)
from news_modelling.production_news_experiment import _read_csv
from news_modelling.stage1_bundle import load_stage1_bundle

FEATURES = Path("news_features/news_feature_table_v2.csv")
FEATURES_META = Path("news_features/news_feature_table_v2_metadata.json")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
V1_MANIFEST = Path("news_features/blinded_2026_predictions_v1/sha256_manifest.json")
OUTPUT = Path("news_features/blinded_2026_predictions_v2")


def main() -> None:
    bundle = load_stage1_bundle(BUNDLE)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    features = _read_csv(FEATURES)
    meta = json.loads(FEATURES_META.read_text(encoding="utf-8"))
    v1_manifest = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))

    protocol, predictions = build_v2_blinded_predictions(
        oof_rows=[dict(row) for row in bundle.out_of_fold],
        holdout_rows=[dict(row) for row in bundle.holdout],
        features=features,
        audit=audit,
        v1_manifest=v1_manifest,
        release_id=meta["canonical_corpus_release_id"],
    )
    manifest = write_outputs(
        protocol, predictions, OUTPUT,
        input_paths={
            "news_feature_table_v2.csv": FEATURES,
            "estimability_report.json": AUDIT,
            "out_of_fold_predictions.csv": BUNDLE / "out_of_fold_predictions.csv",
            "holdout_predictions.csv": BUNDLE / "holdout_predictions.csv",
            "canonical_corpus_release_v2.json":
                Path("news_collection/canonical_corpus_release_v2.json"),
            "v1_sha256_manifest.json": V1_MANIFEST,
        },
    )

    print(f"fitting rows           : {protocol['fitting_rows']} "
          f"across {len(protocol['fitting_elections'])} elections")
    print(f"reform fitting cells   : {len(protocol['reform_fitting_cells'])}")
    print(f"blinded candidate rows : {protocol['blinded_candidate_rows']}")
    print(f"specifications frozen  : {len(protocol['specifications'])}")
    print(f"prediction rows        : {manifest['prediction_rows']}")
    print(f"predictions sha256     : {manifest['blinded_predictions.csv']}")
    print(f"protocol sha256        : {manifest['frozen_protocol.json']}")
    print(f"written to             : {OUTPUT}")
    print("2026 outcomes read     : no")


if __name__ == "__main__":
    main()
