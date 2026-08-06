"""Stance vs volume: margins, not sign counts.

    PYTHONPATH=src .venv/bin/python -m news_modelling.stance_volume_margins

Supervisor directive (2026-08-05): "11 of 12 and 10 of 10 across two harnesses
is the real result. I'd want the margins rather than the sign counts (overlapping
windows, so not 12 independent trials), and a check that stance isn't partly
volume-weighted underneath."

## What this module replaces

Section 5 of ``PARTY_IDENTITY_AND_DESIGN_POWER.md`` reported a sign count:
stance beat volume in 11 of 12 periods on 2026, 10 of 10 live on 2021. The
sign count is easy to read but overstates confidence, because the six cumulative
windows overlap: ``previous_180_days`` contains ``previous_90_days`` which
contains ``previous_30_days`` and so on. They are not 12 independent trials
and cannot be read as a binomial count.

This module reports the actual margin (delta_stance - delta_volume) for every
period, with bootstrap intervals on each delta, so the reader can judge both
the sign and the size. The six non-overlapping windows are the independent set;
the six cumulative windows are a sensitivity check.

## The volume-weighting check

``net_portrayal`` = favourable - unfavourable articles. If a party that receives
more articles also receives more negative articles in proportion, then
net_portrayal correlates with article count: stance is volume with a sign.
The check computes the Pearson correlation between the two at the fitting-cell
level, per window. A high absolute correlation would mean the stance arm is
partly a volume proxy.

EXPLORATORY. The 2026 holdout is unsealed; nothing here promotes a result.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from news_modelling.blinded_2026_predictions import (
    predict_specification,
    sanitise_holdout_rows,
)
from news_modelling.blinded_2026_predictions_v2 import (
    _fit_specification,
    aggregate_v2_residuals,
)
from news_modelling.placebo_specifications import committed_deltas, run_arm
from news_modelling.production_news_experiment import _feature_index, _read_csv
from news_modelling.stage1_bundle import load_stage1_bundle
from news_modelling.unblind_2026 import load_observed

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUT_DIR = Path("news_features/stance_volume_margins_v1")

FROZEN = ["party_article_share", "net_portrayal_share"]

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
    "EXPLORATORY stance-vs-volume margin table, post-unblinding. "
    "Replaces the sign count in section 5 with per-period margins."
)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r from two equal-length lists. None if n < 3."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return cov / (sx * sy)


def volume_weighting_check(
    feature_index: dict,
    cells: list[dict],
) -> dict[str, dict]:
    """Correlation between net_portrayal and party_article_count per window.

    Computed over the fitting cells that carry coverage (article count > 0).
    A high |r| means stance is partly a volume proxy at that window.
    """

    fitting_keys = {(cell["news_election_id"], cell["party_key"])
                    for cell in cells}
    report = {}
    for window in ALL_PERIODS:
        counts, tones = [], []
        for election, party in sorted(fitting_keys):
            row = feature_index.get((election, party, window))
            if row is None:
                continue
            count_str = str(row.get("party_article_count", "")).strip()
            tone_str = str(row.get("net_portrayal", "")).strip()
            if count_str in ("", "0") or tone_str == "":
                continue
            count_val = float(count_str)
            if count_val == 0:
                continue
            counts.append(count_val)
            tones.append(float(tone_str))
        r = _pearson(counts, tones)
        report[window] = {
            "covered_cells": len(counts),
            "r_tone_vs_count": round(r, 4) if r is not None else None,
            "r_squared": round(r ** 2, 4) if r is not None else None,
        }
    return report


def main() -> None:
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)
    bundle = load_stage1_bundle(BUNDLE)
    cells = aggregate_v2_residuals([dict(r) for r in bundle.out_of_fold])
    blinded = sanitise_holdout_rows([dict(r) for r in bundle.holdout])
    observed = load_observed()

    # --- reproduction gate on the frozen specification --------------------
    frozen = [run_arm(FROZEN, cells, feature_index, blinded, observed, w)
              for w in NON_OVERLAPPING]
    reference = committed_deltas()
    mismatches = [
        (r["window"], round(r["delta_vs_recalibrated"], 3), reference[r["window"]])
        for r in frozen
        if abs(round(r["delta_vs_recalibrated"], 3)
               - reference[r["window"]]) > 1e-9
    ]
    if mismatches:
        raise RuntimeError(
            "the frozen specification did not reproduce its committed "
            f"deltas: {mismatches}")

    # --- run stance and volume across all 12 periods ----------------------
    stance_results = {}
    volume_results = {}
    for window in ALL_PERIODS:
        stance_results[window] = run_arm(
            ["net_portrayal"], cells, feature_index, blinded, observed, window)
        volume_results[window] = run_arm(
            ["party_article_count"], cells, feature_index, blinded, observed, window)

    # --- margins ----------------------------------------------------------
    margins = []
    for window in ALL_PERIODS:
        s = stance_results[window]
        v = volume_results[window]
        margin = s["delta_vs_recalibrated"] - v["delta_vs_recalibrated"]
        margins.append({
            "window": window,
            "window_kind": "non_overlapping" if window in NON_OVERLAPPING
                           else "cumulative",
            "stance_delta": s["delta_vs_recalibrated"],
            "stance_ci_lower": s.get("ci_lower"),
            "stance_ci_upper": s.get("ci_upper"),
            "volume_delta": v["delta_vs_recalibrated"],
            "volume_ci_lower": v.get("ci_lower"),
            "volume_ci_upper": v.get("ci_upper"),
            "margin": margin,
            "stance_wins": margin > 0,
        })

    # --- volume-weighting check -------------------------------------------
    weighting = volume_weighting_check(feature_index, cells)

    payload = {
        "status": STATUS,
        "feature_table": str(FEATURES),
        "fitting_cells": len(cells),
        "reproduction_check_passed": len(mismatches) == 0,
        "margins": margins,
        "volume_weighting_check": weighting,
        "summary": {
            "stance_wins_non_overlapping": sum(
                1 for m in margins
                if m["window_kind"] == "non_overlapping" and m["stance_wins"]),
            "stance_wins_cumulative": sum(
                1 for m in margins
                if m["window_kind"] == "cumulative" and m["stance_wins"]),
            "stance_wins_total": sum(1 for m in margins if m["stance_wins"]),
            "total_periods": len(margins),
            "mean_margin_non_overlapping": sum(
                m["margin"] for m in margins
                if m["window_kind"] == "non_overlapping") / len(NON_OVERLAPPING),
            "mean_margin_all": sum(m["margin"] for m in margins) / len(margins),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "stance_volume_margins.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    margins = payload["margins"]
    weighting = payload["volume_weighting_check"]
    summary = payload["summary"]

    def fmt(v):
        return f"{v:+.4f}" if v is not None else "-"

    lines = [
        "# Stance vs volume: margins",
        "",
        f"**{payload['status']}**",
        "",
        "Each row runs one single-feature arm through the frozen harness. "
        "Stance = `net_portrayal` (favourable minus unfavourable articles). "
        "Volume = `party_article_count` (how many articles mention a party). "
        "Delta is the change in election-wide MAE against the recalibrated "
        "control; positive is better. Margin = stance delta minus volume "
        f"delta. All arms share the {payload['fitting_cells']} frozen fitting "
        "cells.",
        "",
        "## Non-overlapping windows (the independent set)",
        "",
        "| window | stance delta | 95% CI | volume delta | 95% CI | margin |",
        "| --- | ---: | --- | ---: | --- | ---: |",
    ]
    for m in margins:
        if m["window_kind"] != "non_overlapping":
            continue
        lines.append(
            f"| {m['window']} | {fmt(m['stance_delta'])} | "
            f"[{fmt(m['stance_ci_lower'])}, {fmt(m['stance_ci_upper'])}] | "
            f"{fmt(m['volume_delta'])} | "
            f"[{fmt(m['volume_ci_lower'])}, {fmt(m['volume_ci_upper'])}] | "
            f"{fmt(m['margin'])} |")

    lines += [
        "",
        f"Stance wins in **{summary['stance_wins_non_overlapping']} of "
        f"{len(NON_OVERLAPPING)}** non-overlapping windows. "
        f"Mean margin: **{summary['mean_margin_non_overlapping']:+.4f}**.",
        "",
        "## Cumulative windows (sensitivity, not independent)",
        "",
        "| window | stance delta | volume delta | margin |",
        "| --- | ---: | ---: | ---: |",
    ]
    for m in margins:
        if m["window_kind"] != "cumulative":
            continue
        lines.append(
            f"| {m['window']} | {fmt(m['stance_delta'])} | "
            f"{fmt(m['volume_delta'])} | {fmt(m['margin'])} |")

    lines += [
        "",
        f"Stance wins in **{summary['stance_wins_cumulative']} of "
        f"{len(CUMULATIVE)}** cumulative windows.",
        "",
        f"Overall: stance wins **{summary['stance_wins_total']} of "
        f"{summary['total_periods']}** periods. "
        f"Mean margin across all: **{summary['mean_margin_all']:+.4f}**.",
        "",
        "## Is stance volume-weighted underneath?",
        "",
        "Pearson r between `net_portrayal` (stance) and `party_article_count` "
        "(volume) across covered fitting cells, per window. A high |r| would "
        "mean stance is largely a volume proxy with a sign.",
        "",
        "| window | covered cells | r | r-squared |",
        "| --- | ---: | ---: | ---: |",
    ]
    for window in ALL_PERIODS:
        w = weighting[window]
        r = w["r_tone_vs_count"]
        rsq = w["r_squared"]
        r_str = f"{r:+.4f}" if r is not None else "-"
        rsq_str = f"{rsq:.4f}" if rsq is not None else "-"
        lines.append(
            f"| {window} | {w['covered_cells']} | {r_str} | {rsq_str} |")

    r_headline = weighting.get("90_to_31_days", {}).get("r_tone_vs_count")
    if r_headline is not None:
        lines += [
            "",
            f"At the headline window (90-31 days), r = **{r_headline:+.4f}** "
            f"(r-squared = {r_headline**2:.4f}). "
            + ("This is a weak correlation: stance carries substantial "
               "information that volume alone does not."
               if abs(r_headline) < 0.5 else
               "This is a moderate-to-strong correlation: stance is partly "
               "a volume proxy, though the margins above show it still adds "
               "predictive value."
               if abs(r_headline) < 0.7 else
               "This is a strong correlation: much of what stance captures "
               "is volume with a sign. The margins above should be read with "
               "that caveat."),
        ]

    lines.append("")
    (OUT_DIR / "stance_volume_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
