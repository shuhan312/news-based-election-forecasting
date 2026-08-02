"""The exploratory local re-run: the supervisor's local-vs-national answer.

    PYTHONPATH=src .venv/bin/python -m news_modelling.local_v3_rerun

Two months after the local arm was declared sensitivity-only, the v3
lineage made its frozen specification reportable: the pre-declared
local columns - ``local_party_article_share`` and
``local_net_portrayal_share``, exactly the pair the estimability audit
froze - both cleared the 10-value gate once the reviewer's opening
pass admitted 29 by-election articles. This module runs that frozen
specification against the 2026 outcomes, which is the last unanswered
half of the supervisor's arm comparison.

Reuse over reinvention - every number-producing step is frozen code:

- fitting: ``_fit_specification`` over the SAME 45 residual cells the
  v2 freeze used (``aggregate_v2_residuals`` on the Stage 1 out-of-
  fold rows); only the feature table changed, v2 -> v3exp;
- prediction: ``predict_specification`` on the outcome-stripped 2026
  holdout rows, then ``_assign_ranks`` for seat calls - the same
  contest normalisation and deterministic tie-break as the freeze;
- scoring: ``score_specification`` with the same contest bootstrap
  (2,000 resamples, protocol seed) the one-time unblinding ran, so
  every metric here is shape-identical and code-identical to the
  confirmatory tables it will sit beside.

Two honesty constraints, stated up front and in the output:

1. EXPLORATORY. The 2026 outcomes were unblinded long before any v3
   judgement existed; nothing here can join or revise the confirmatory
   verdict (v1 0/12, v2 5/12).
2. ONLY THE TRAINING SIDE GOT RICHER. The 29 new articles enrich the
   fitting cells' local features; the 2026 test-side local inputs are
   unchanged (the 203 tier-4 rows remain unjudged), so this asks "does
   a better-trained local model transfer?", not "does 2026 local
   coverage predict?".
"""

from __future__ import annotations

import json
from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    _assign_ranks,
    predict_specification,
    sanitise_holdout_rows,
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
from news_modelling.unblind_2026 import load_observed, score_specification

V3_FEATURES = Path("news_features/news_feature_table_v3exp.csv")
AUDIT = Path("news_features/production_estimability_v1/estimability_report.json")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")
OUT_DIR = Path("news_features/local_v3_rerun_v1")

WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

STATUS = ("EXPLORATORY local re-run on the v3 lineage. The 2026 outcomes "
          "were unblinded before any v3 judgement existed; nothing here "
          "joins the confirmatory verdict.")


def reference_deltas() -> dict:
    """The committed numbers this run is read against: the v2-fit local
    sensitivity deltas and the two confirmatory arms, per window."""

    record = json.loads(UNBLINDING.read_text(encoding="utf-8"))
    reference: dict[str, dict] = {w: {} for w in WINDOWS}
    for entry in record["files"]["v2"]:
        window = entry["period"]
        if window not in reference:
            continue
        delta = entry["metrics"]["all_supported_parties"][
            "news_vs_recalibrated_mae"]
        if entry["analysis"] == "local_sensitivity":
            reference[window]["local_v2_sensitivity"] = round(delta, 3)
        elif entry["family"] == "confirmatory":
            arm = entry["analysis"].replace("_exploratory", "")
            reference[window][f"{arm}_confirmatory"] = round(delta, 3)
    return reference


def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    columns = list(audit["frozen_feature_sets"]["local_sensitivity"]["columns"])
    # The gate crossing is this run's licence; assert it rather than
    # assume it, so a stale v3 table cannot silently serve.
    metadata = json.loads(Path(
        "news_features/news_feature_table_v3exp_metadata.json").read_text())
    verdicts = next(v for v in metadata.values()
                    if isinstance(v, dict) and "local_party_article_share" in v)
    for column in columns:
        if verdicts[column]["verdict"] != "usable":
            raise RuntimeError(f"{column} is not reportable in v3 "
                               f"({verdicts[column]['verdict']})")

    features = _read_csv(V3_FEATURES)
    feature_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    cells = aggregate_v2_residuals([dict(r) for r in bundle.out_of_fold])
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    observed = load_observed()

    results = []
    for window in WINDOWS:
        model, record = _fit_specification(
            cells, feature_index, period=window, feature_columns=columns)
        predictions, clipped = predict_specification(
            blinded, feature_index, model,
            period=window, feature_columns=columns)
        for row in predictions:
            row["included_in_reported_metrics"] = (
                "True" if row["party_key"] is not None else "False")
        _assign_ranks(predictions, "news_enhanced_prediction",
                      "analysis_number_of_seats")
        metrics = score_specification(predictions, observed,
                                      with_bootstrap=True)
        results.append({
            "window": window,
            "fit": {"training_rows": record["training_rows"],
                    "coefficients": record["standardised_coefficients"]},
            "clipped_rows": clipped,
            "metrics": metrics,
        })

    reference = reference_deltas()
    payload = {"status": STATUS,
               "specification_columns": columns,
               "fitting_cells": len(cells),
               "reference_deltas": reference,
               "windows": results}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "rerun_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    improved = sum(
        1 for r in results
        if r["metrics"]["all_supported_parties"]
        ["news_vs_recalibrated_mae"] > 0)
    lines = [
        "# The local arm, re-run on the v3 lineage", "",
        f"**{STATUS}**", "",
        f"Frozen specification ({' + '.join(columns)}), the same 45 "
        "fitting cells as the v2 freeze, frozen prediction and scoring "
        "code throughout; only the feature table is v3. Test-side 2026 "
        "local inputs are unchanged - this asks whether a better-trained "
        "local model transfers.", "",
        "| window | local v3 delta | 95% CI | local v2 (sens) | "
        "combined (conf) | national (conf) | seat acc |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for entry in results:
        window = entry["window"]
        overall = entry["metrics"]["all_supported_parties"]
        ci = entry["metrics"].get("bootstrap_news_vs_recalibrated", {})
        ref = reference[window]
        lines.append(
            f"| {window} | "
            f"{overall['news_vs_recalibrated_mae']:+.3f} | "
            f"[{ci.get('improvement_ci_lower', 0):+.3f}, "
            f"{ci.get('improvement_ci_upper', 0):+.3f}] | "
            f"{ref.get('local_v2_sensitivity', 0):+.3f} | "
            f"{ref.get('combined_confirmatory', 0):+.3f} | "
            f"{ref.get('national_confirmatory', 0):+.3f} | "
            f"{entry['metrics']['seat_accuracy_news']['accuracy']:.4f} |")
    lines += [
        "",
        f"Local v3 beats its recalibrated control in **{improved} of "
        f"{len(results)}** windows (v2-fit sensitivity: 3 of 6; the "
        "confirmatory arms: combined and national each 3 of 6 among "
        "these windows).", "",
    ]
    (OUT_DIR / "rerun_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
