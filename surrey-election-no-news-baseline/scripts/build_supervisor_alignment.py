"""Emit the three Stage 1 artefacts the supervisor's prompt asks for,
from outputs that already exist. Nothing is refitted.

    outputs/supervisor_alignment/leakage_audit.csv
    outputs/supervisor_alignment/split_manifest.csv          (both splits)
    outputs/supervisor_alignment/reform_metrics.json         (both splits)
    outputs/supervisor_alignment/reform_row_census.json

Usage:
    python3 -m scripts.build_supervisor_alignment
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from no_news_baseline import electoral_fundamentals_schema as schema
from no_news_baseline.supervisor_alignment import (SPLITS, assign_fold,
                                                   build_leakage_audit,
                                                   reform_metrics,
                                                   reform_row_census)

FEATURES = Path("outputs/electoral_fundamentals/"
                "electoral_fundamentals_features.csv")
DICTIONARY = Path("outputs/electoral_fundamentals/"
                  "electoral_feature_dictionary.csv")
PREDICTIONS = Path("outputs/persistence_benchmark/"
                   "previous_result_persistence_predictions.json")
OUT = Path("outputs/supervisor_alignment")


def _date(row) -> date:
    return date.fromisoformat(row["election_date"][:10])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    features = list(csv.DictReader(FEATURES.open()))
    dictionary = list(csv.DictReader(DICTIONARY.open()))
    preds = json.loads(PREDICTIONS.read_text())["rows"]

    # ---- 1. leakage audit -------------------------------------------
    audit = build_leakage_audit(
        schema.PREDICTOR_COLUMNS, schema.EVALUATION_COLUMNS,
        schema.FORBIDDEN_CURRENT_OUTCOME_COLUMNS,
        schema.ROW_KEY_COLUMNS, dictionary, schema.LEAKAGE_RULES)
    with (OUT / "leakage_audit.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(audit[0]))
        w.writeheader()
        w.writerows(audit)

    # ---- 2. split manifest, one block per split ---------------------
    elections = {}
    for r in features:
        elections.setdefault(r["election_id"],
                             {"election_id": r["election_id"],
                              "election_date": r["election_date"][:10],
                              "election_type": r["election_type"],
                              "rows": 0})
        elections[r["election_id"]]["rows"] += 1

    manifest = []
    for split in SPLITS:
        for e in sorted(elections.values(),
                        key=lambda x: x["election_date"]):
            manifest.append({
                "split_id": split.split_id,
                "split_description": split.description,
                **e,
                "fold": assign_fold(
                    date.fromisoformat(e["election_date"]), split),
            })
    with (OUT / "split_manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0]))
        w.writeheader()
        w.writerows(manifest)

    # ---- 3. Reform census + metrics under both splits ---------------
    census = reform_row_census(features, _date)
    (OUT / "reform_row_census.json").write_text(
        json.dumps(census, indent=1) + "\n")

    edate = {r["election_id"]: _date(r) for r in features}
    scored = [{"standard_party_name": p["standard_party_name"],
               "election_id": p["election_id"],
               "predicted": p["predicted_party_vote_share"],
               "actual": p["actual_party_vote_share"]}
              for p in preds
              if p["predicted_party_vote_share"] is not None
              and p["actual_party_vote_share"] is not None]

    metrics = {"benchmark": "previous_result_persistence_v1",
               "note": "Existing baseline predictions re-scored by "
                       "party and by fold. No model was refitted.",
               "overall": reform_metrics(scored), "by_split": {}}
    for split in SPLITS:
        folds = {}
        for f in ("train", "validation", "test"):
            rows = [s for s in scored
                    if s["election_id"] in edate
                    and assign_fold(edate[s["election_id"]], split) == f]
            folds[f] = reform_metrics(rows)
        metrics["by_split"][split.split_id] = {
            "description": split.description,
            "rationale": split.rationale, "folds": folds}
    (OUT / "reform_metrics.json").write_text(
        json.dumps(metrics, indent=1) + "\n")

    # ---- report ------------------------------------------------------
    print(f"leakage_audit.csv     {len(audit)} rows")
    print(f"split_manifest.csv    {len(manifest)} rows "
          f"({len(elections)} elections x {len(SPLITS)} splits)")
    print("\nReform / UKIP rows per fold:")
    for sid, folds in census["by_split"].items():
        print(f"  {sid}")
        for f, c in folds.items():
            print(f"    {f:<11} Reform {c['Reform UK']:>3}   "
                  f"UKIP {c['UK Independence Party']:>3}")
    print("\nPersistence baseline, Reform vs all parties:")
    for sid, blk in metrics["by_split"].items():
        print(f"  {sid} - {blk['description']}")
        for f, m in blk["folds"].items():
            print(f"    {f:<11} Reform n={m['reform_rows_scored']:>3} "
                  f"MAE={m['reform_mae_pp']}   "
                  f"all n={m['all_party_rows_scored']:>4} "
                  f"MAE={m['all_party_mae_pp']}")


if __name__ == "__main__":
    main()
