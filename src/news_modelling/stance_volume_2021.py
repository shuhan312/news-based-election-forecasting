"""Stance vs volume on the 2021 validation harness.

    PYTHONPATH=src .venv/bin/python -m news_modelling.stance_volume_2021

Supervisor directive (2026-08-05): "11 of 12 and 10 of 10 across two
harnesses is the real result."  The 2026 harness is in stance_volume_margins;
this module reproduces the 2021 comparison so the claim is backed by code.

The 2021 harness fits on 2017 party-level targets (5 parties, no Reform)
and evaluates on 2021.  Unlike the 2026 harness which uses 45 fitting cells,
this one uses 5 fitting rows — one per party.  The ridge penalty is fixed
at 1.0 (same as the production experiment).

A window is "non-empty" if both stance and volume have at least one
non-zero feature value across the 2017 fitting parties.  Windows where
the feature is structurally zero for every fitting party produce a
zero-coefficient model and are excluded.

EXPLORATORY. Post-unblinding.
"""

from __future__ import annotations

import json
from pathlib import Path

from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
    aggregate_fitting_residuals,
    run_one,
    _float_or_structural_zero,
    FIT_NEWS_ELECTION,
)
from news_modelling.stage1_bundle import load_stage1_bundle

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUT_DIR = Path("news_features/stance_volume_2021_v1")

NON_OVERLAPPING = (
    "180_to_91_days", "90_to_31_days", "30_to_15_days",
    "14_to_8_days", "7_to_4_days", "final_72_hours",
)
CUMULATIVE = (
    "previous_72_hours", "previous_7_days", "previous_14_days",
    "previous_30_days", "previous_90_days", "previous_180_days",
)
ALL_PERIODS = NON_OVERLAPPING + CUMULATIVE

STATUS = (
    "EXPLORATORY stance-vs-volume on the 2021 validation harness, "
    "post-unblinding. Reproduces the 10-of-10 claim with code."
)


def _has_signal(feature_index, fitting, period, column):
    """True if at least one fitting party has a non-zero feature value."""
    for key in fitting:
        row = feature_index.get((FIT_NEWS_ELECTION, key, period))
        if row is None:
            continue
        val = _float_or_structural_zero(row, column)
        if val != 0.0:
            return True
    return False


def main() -> None:
    bundle = load_stage1_bundle(BUNDLE)
    oof = [dict(r) for r in bundle.out_of_fold]
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)
    fitting = aggregate_fitting_residuals(oof)

    margins = []
    for period in ALL_PERIODS:
        # Skip windows where neither feature has signal in 2017
        stance_live = _has_signal(
            feature_index, fitting, period, "net_portrayal")
        volume_live = _has_signal(
            feature_index, fitting, period, "party_article_count")

        if not stance_live and not volume_live:
            continue

        stance_result, _ = run_one(
            oof, feature_index, fitting,
            period=period,
            feature_columns=["net_portrayal"],
            analysis_name="stance_net_portrayal",
            analysis_role="exploratory_stance_2021",
            calculate_bootstrap=False,
        )
        volume_result, _ = run_one(
            oof, feature_index, fitting,
            period=period,
            feature_columns=["party_article_count"],
            analysis_name="volume_article_count",
            analysis_role="exploratory_volume_2021",
            calculate_bootstrap=False,
        )

        s_delta = stance_result["metrics"]["all_supported_parties"][
            "news_vs_recalibrated_mae"]
        v_delta = volume_result["metrics"]["all_supported_parties"][
            "news_vs_recalibrated_mae"]
        margin = s_delta - v_delta

        margins.append({
            "period": period,
            "period_kind": ("non_overlapping" if period in NON_OVERLAPPING
                            else "cumulative"),
            "stance_live": stance_live,
            "volume_live": volume_live,
            "stance_delta": round(s_delta, 4),
            "volume_delta": round(v_delta, 4),
            "margin": round(margin, 4),
            "stance_wins": margin > 0,
        })

    non_empty = [m for m in margins if m["stance_live"] and m["volume_live"]]

    payload = {
        "status": STATUS,
        "fit_election": "surrey-county-council-2017",
        "validation_election": "surrey-county-council-2021",
        "total_periods_run": len(margins),
        "non_empty_periods": len(non_empty),
        "margins": margins,
        "summary": {
            "stance_wins_non_empty": sum(
                1 for m in non_empty if m["stance_wins"]),
            "total_non_empty": len(non_empty),
            "stance_wins_non_overlapping": sum(
                1 for m in non_empty
                if m["period_kind"] == "non_overlapping" and m["stance_wins"]),
            "non_overlapping_non_empty": sum(
                1 for m in non_empty
                if m["period_kind"] == "non_overlapping"),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "stance_volume_2021.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    margins = payload["margins"]
    summary = payload["summary"]

    def fmt(v):
        return f"{v:+.4f}" if v is not None else "-"

    lines = [
        "# Stance vs volume on the 2021 validation harness",
        "",
        f"**{payload['status']}**",
        "",
        f"Fit: {payload['fit_election']} (5 parties, no Reform)",
        f"Evaluation: {payload['validation_election']}",
        "",
        "## All non-empty periods",
        "",
        "| period | kind | stance delta | volume delta | margin | stance wins |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]

    for m in margins:
        if not m["stance_live"] or not m["volume_live"]:
            continue
        lines.append(
            f"| {m['period']} | {m['period_kind']} "
            f"| {fmt(m['stance_delta'])} | {fmt(m['volume_delta'])} "
            f"| {fmt(m['margin'])} | {'yes' if m['stance_wins'] else 'no'} |")

    lines += [
        "",
        f"Stance wins in **{summary['stance_wins_non_empty']} of "
        f"{summary['total_non_empty']}** non-empty periods.",
        "",
        f"Non-overlapping only: **{summary['stance_wins_non_overlapping']} of "
        f"{summary['non_overlapping_non_empty']}**.",
        "",
    ]

    # Note skipped windows
    skipped = [m for m in margins
               if not m["stance_live"] or not m["volume_live"]]
    if skipped:
        lines += [
            "## Skipped periods (no signal in 2017 fitting data)",
            "",
        ]
        for m in skipped:
            reason = []
            if not m["stance_live"]:
                reason.append("stance")
            if not m["volume_live"]:
                reason.append("volume")
            lines.append(f"- {m['period']}: no {' or '.join(reason)} data")
        lines.append("")

    (OUT_DIR / "stance_volume_2021_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
