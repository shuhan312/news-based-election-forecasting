"""Emit the split manifest and leakage audit for the candidate-level model.

Steps 2 and 3 of the supervisor's ordering, and two of the sixteen files the
Stage 1 brief requires in the model bundle:

    outputs/candidate_split_leakage/split_manifest.csv
    outputs/candidate_split_leakage/leakage_audit.csv
    outputs/candidate_split_leakage/split_summary.json

Nothing is fitted here. The point of running the split and the audit before
any model exists is that the model then has no opportunity to influence
either: the folds and the permitted-predictor list are fixed artefacts the
model must accept, not choices made after seeing how well something scored.

Usage (from the IRP repository root):

    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
      surrey-election-no-news-baseline/scripts/build_candidate_split_and_leakage.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from no_news_baseline.candidate_cohort import (
    assert_one_to_one_candidate_release,
    is_within_candidate_cohort,
)
from no_news_baseline.candidate_leakage_audit import (
    build_leakage_audit,
    permitted_predictors,
)
from no_news_baseline.candidate_splits import (
    all_splits,
    assert_contest_integrity,
    assert_holdout_untouched,
    build_split_manifest,
    split_summary,
)


CONTRACT = Path("surrey-election-extractor/outputs/no_news_candidate_contests")
FEATURES = CONTRACT / "no_news_candidate_contest_features.json"
TARGETS = CONTRACT / "no_news_candidate_contest_targets.json"
OUT = Path("surrey-election-no-news-baseline/outputs/candidate_split_leakage")


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty file: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    features = json.loads(FEATURES.read_text())["rows"]
    targets = json.loads(TARGETS.read_text())["rows"]
    assert_one_to_one_candidate_release(features, targets)

    feature_columns = sorted(set().union(*(set(row) for row in features)))
    target_columns = sorted(set().union(*(set(row) for row in targets)))

    splits = all_splits(features)
    manifest = build_split_manifest(features, splits)

    # Both guarantees are checked against the produced manifest rather than
    # against the split definitions, so an assignment bug cannot pass merely
    # because the definitions read correctly.
    assert_contest_integrity(manifest)
    assert_holdout_untouched(manifest)

    audit = build_leakage_audit(feature_columns, target_columns)
    summaries = split_summary(features, splits)
    predictors = permitted_predictors(feature_columns)

    OUT.mkdir(parents=True, exist_ok=True)
    _write_csv(OUT / "split_manifest.csv", manifest)
    _write_csv(OUT / "leakage_audit.csv", audit)
    (OUT / "split_summary.json").write_text(
        json.dumps(
            {
                "permitted_predictors": list(predictors),
                "permitted_predictor_count": len(predictors),
                "published_feature_columns": len(feature_columns),
                "cohort_rows": sum(1 for row in features if is_within_candidate_cohort(row)),
                "splits": list(summaries),
            },
            indent=2,
        )
        + "\n"
    )

    # --- console summary -------------------------------------------------
    verdicts: dict[str, int] = {}
    for row in audit:
        verdicts[str(row["verdict"])] = verdicts.get(str(row["verdict"]), 0) + 1

    print(f"published feature columns: {len(feature_columns)}")
    print(f"permitted predictors:      {len(predictors)}")
    print(f"leakage audit rows:        {len(audit)}  {verdicts}")
    print(f"splits:                    {len(splits)}")
    print(f"split manifest rows:       {len(manifest)}")
    print()

    header = (f"{'split':46s} {'role':18s} {'train':>6s} {'test':>6s} "
              f"{'trRef':>6s} {'teRef':>6s}")
    print(header)
    print("-" * len(header))
    for row in summaries:
        print(
            f"{str(row['split_id'])[:46]:46s} "
            f"{str(row['split_role'])[:18]:18s} "
            f"{row['train_rows']:6d} "
            f"{row['test_rows']:6d} "
            f"{row['train_reform_uk_rows']:6d} "
            f"{row['test_reform_uk_rows']:6d}"
            + ("" if row["reform_estimable"] else "   <- no Reform in training")
        )
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
