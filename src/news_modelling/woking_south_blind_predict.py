"""Produce the Woking South BLIND predictions (no outcome is read).

    PYTHONPATH=src .venv/bin/python -m news_modelling.woking_south_blind_predict

The last step on the blind side of the wall. What it does, in the
frozen protocol's order:

1. VERIFIES THE PROTOCOL'S PINS. Every input the protocol hashed at
   freeze time (both fitting tables, the estimability audit, the
   out-of-fold baseline file, both result records) is re-hashed and
   compared; any mismatch aborts the run.
2. LOADS THE BASELINE ROWS BLIND. The contest's five candidate rows
   come from the Stage 1 out-of-fold file and are passed through
   ``strip_outcome_columns`` at load, inside this module, before
   anything else touches them - the sanitiser that guarantees the
   prediction path cannot see a result even by accident.
3. FITS AND PREDICTS WITH FROZEN CODE ONLY. For each arm x window:
   the arm's frozen two-column specification, fitted on the same 45
   residual cells as ever - combined and national on the v2 table,
   local on v3exp, exactly as the protocol's ARM_TABLE pins - then
   applied through ``predict_specification`` (contest normalisation
   included) and ``_assign_ranks`` (deterministic seat call).
4. MARKS, NEVER SELECTS. Every one of the 18 arm x window
   specifications is written; the protocol's derived combination is a
   ``combination_pick`` flag on its assigned row per window, so the
   unseal can score everything and highlight the pick without any
   number having been chosen after the fact.
5. FREEZES ITS OUTPUT. Refuses to overwrite an existing predictions
   file; writes a sha256 manifest beside it. The unseal script will
   demand these exact bytes exist in git history before it runs.

The summary printed at the end contains predictions only - shares and
seat calls this side of the wall are legitimate to see; results are
not, and none is loaded anywhere in this module.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    _assign_ranks,
    predict_specification,
    strip_outcome_columns,
)
from news_modelling.blinded_2026_predictions_v2 import (
    _fit_specification,
    aggregate_v2_residuals,
)
from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
)
from news_modelling.stage1_bundle import load_stage1_bundle
import news_modelling.blinded_2026_predictions as frozen_predict

PROTOCOL = Path("news_features/woking_south_blind_v1/protocol.json")
WOKING_FEATURES = Path(
    "news_features/woking_south_blind_v1/news_feature_table_wokingsouth.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUT_CSV = Path("news_features/woking_south_blind_v1/blind_predictions.csv")
OUT_MANIFEST = Path(
    "news_features/woking_south_blind_v1/blind_predictions_manifest.json")

ARM_COLUMNS_KEY = {"combined": "combined_exploratory",
                   "national": "national_exploratory",
                   "local": "local_sensitivity"}


def verify_pins(protocol: dict) -> None:
    """Re-hash every pinned input; a drifted file aborts the run."""

    for name, recorded in protocol["pinned_input_sha256"].items():
        path = Path({
            "unblinding_record":
                "news_features/unblinding_2026_v1/unblinding_results.json",
            "local_v3_rerun_record":
                "news_features/local_v3_rerun_v1/rerun_results.json",
            "feature_table_v2": "news_features/news_feature_table_v2.csv",
            "feature_table_v3exp":
                "news_features/news_feature_table_v3exp.csv",
            "estimability_audit":
                "news_features/production_estimability_v1/"
                "estimability_report.json",
            "baseline_out_of_fold":
                "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
                "out_of_fold_predictions.csv",
        }[name])
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != recorded:
            raise RuntimeError(f"pinned input {name} has drifted")


def load_contest_rows_blind(election: str) -> list[dict]:
    """The five candidate rows, outcome columns stripped AT LOAD."""

    with (BUNDLE / "out_of_fold_predictions.csv").open(
            newline="", encoding="utf-8") as handle:
        rows = [dict(r) for r in csv.DictReader(handle)
                if r["election_id"] == election]
    if len(rows) != 5:
        raise RuntimeError(f"expected 5 contest rows, got {len(rows)}")
    return strip_outcome_columns(rows)


def main() -> None:
    if OUT_CSV.exists():
        raise RuntimeError(f"{OUT_CSV} already exists - blind predictions "
                           "are written once; delete deliberately or stop")
    protocol = json.loads(PROTOCOL.read_text())
    verify_pins(protocol)
    election = protocol["election"]
    window_to_arm = protocol["window_to_arm"]

    audit = json.loads(Path(
        "news_features/production_estimability_v1/estimability_report.json"
    ).read_text())
    fit_tables = {
        "feature_table_v2": _feature_index(
            _read_csv("news_features/news_feature_table_v2.csv")),
        "feature_table_v3exp": _feature_index(
            _read_csv("news_features/news_feature_table_v3exp.csv")),
    }
    woking_index = _feature_index(_read_csv(WOKING_FEATURES))
    cells = aggregate_v2_residuals(
        [dict(r) for r in load_stage1_bundle(BUNDLE).out_of_fold])
    blinded = load_contest_rows_blind(election)

    out_rows = []
    saved = frozen_predict.HOLDOUT_NEWS_ELECTION
    try:
        frozen_predict.HOLDOUT_NEWS_ELECTION = election
        for arm, table_key in protocol["arm_fitting_tables"].items():
            columns = list(audit["frozen_feature_sets"][
                ARM_COLUMNS_KEY[arm]]["columns"])
            for window in window_to_arm:
                model, _rec = _fit_specification(
                    cells, fit_tables[table_key],
                    period=window, feature_columns=columns)
                predictions, clipped = predict_specification(
                    blinded, woking_index, model,
                    period=window, feature_columns=columns)
                _assign_ranks(predictions, "news_enhanced_prediction",
                              "analysis_number_of_seats")
                for row in predictions:
                    out_rows.append({
                        "arm": arm, "window": window,
                        "combination_pick": window_to_arm[window] == arm,
                        "candidate_contest_id": row["candidate_contest_id"],
                        "standard_party_name": row["standard_party_name"],
                        "party_key": row["party_key"] or "",
                        "baseline_prediction":
                            round(row["baseline_prediction"], 4),
                        "recalibrated_prediction":
                            round(row["recalibrated_prediction"], 4),
                        "news_enhanced_prediction":
                            round(row["news_enhanced_prediction"], 4),
                        "news_predicted_rank": row["news_predicted_rank"],
                        "news_predicted_elected":
                            row["news_predicted_elected"],
                        "clipped_rows_in_spec": clipped["news_enhanced"],
                    })
    finally:
        frozen_predict.HOLDOUT_NEWS_ELECTION = saved

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0].keys()),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)
    OUT_MANIFEST.write_text(json.dumps({
        "predictions_sha256":
            hashlib.sha256(OUT_CSV.read_bytes()).hexdigest(),
        "rows": len(out_rows),
        "protocol": protocol["protocol"],
        "woking_features_sha256":
            hashlib.sha256(WOKING_FEATURES.read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")

    print(f"{len(out_rows)} prediction rows -> {OUT_CSV}")
    print("\ncombination picks, predicted shares (BLIND side - no result "
          "has been read):")
    for row in out_rows:
        if row["combination_pick"] and row["window"] == "180_to_91_days":
            print(f"  180-91d [{row['arm']}] "
                  f"{row['standard_party_name']:20s} "
                  f"{row['news_enhanced_prediction']:6.2f} "
                  f"{'ELECTED' if row['news_predicted_elected'] else ''}")


if __name__ == "__main__":
    main()
