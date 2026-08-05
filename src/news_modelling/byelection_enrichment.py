"""By-election enrichment: the quantity-quality trade-off.

    PYTHONPATH=src .venv/bin/python -m news_modelling.byelection_enrichment

Supervisor directive (2026-08-05): "The by-election result is worth writing
up on its own: enrichment that quadruples n while taking reliability from
0.938 to 0.225."

The Stage 1 model was trained on 2017 and 2021 Surrey County Council
elections (11 fitting cells, high reliability). Adding eight pre-holdout
by-elections expands the fit to 45 cells (34 of which are single-contest
by-election cells). This quadruples the sample but drops reliability from
0.938 to 0.225, because single-contest cells carry enormous sampling noise.

This module computes the reliability breakdown by subset, the detection
threshold under each subset, and documents the trade-off. The key finding:
more cells lower the critical value for significance (good), but also lower
the reliability (bad). In this dataset the two effects roughly cancel,
leaving the design underpowered but not incapable.

EXPLORATORY. Post-unblinding.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

from news_modelling.blinded_2026_predictions_v2 import (
    FIT_ELECTION_MAP,
    aggregate_v2_residuals,
)
from news_modelling.production_news_experiment import (
    _feature_index,
    _read_csv,
    party_key,
)
from news_modelling.stage1_bundle import load_stage1_bundle

FEATURES = Path("news_features/news_feature_table_v3party.csv")
BUNDLE = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")
OUT_DIR = Path("news_features/byelection_enrichment_v1")

WINDOW = "90_to_31_days"

STATUS = (
    "EXPLORATORY by-election enrichment analysis, post-unblinding. "
    "Documents the quantity-quality trade-off when adding single-contest "
    "by-election cells to the fitting set."
)


def _pooled_sigma2(oof_rows: list[dict]) -> float:
    """Weighted pooled within-cell variance of residuals."""
    by_cell: dict[tuple, list[float]] = defaultdict(list)
    for row in oof_rows:
        election = row.get("election_id")
        if election not in FIT_ELECTION_MAP:
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        by_cell[(election, key)].append(
            float(row["observed_vote_share"])
            - float(row["predicted_vote_share"])
        )
    total_ss = 0.0
    total_df = 0
    for resids in by_cell.values():
        n = len(resids)
        if n < 2:
            continue
        total_ss += float(np.var(resids, ddof=1)) * (n - 1)
        total_df += n - 1
    return total_ss / total_df


def _subset_stats(cells: list[dict], sigma2: float) -> dict:
    """Reliability and detection threshold for a subset of cells."""
    if not cells:
        return {"n_cells": 0}
    means = [c["mean_residual"] for c in cells]
    sizes = [c["candidate_rows"] for c in cells]
    n = len(cells)
    var_means = float(np.var(means, ddof=1))
    mean_sampling = float(np.mean([sigma2 / s for s in sizes]))
    tau2 = max(var_means - mean_sampling, 0.0)
    reliability = tau2 / var_means if var_means > 0 else 0.0
    # Two-sided critical r at alpha=0.05
    df = n - 2
    t_crit = float(stats.t.ppf(0.975, df)) if df > 0 else float("inf")
    r_crit = t_crit / np.sqrt(t_crit ** 2 + df) if df > 0 else 1.0
    # True r required to reach significance after attenuation
    attenuation = np.sqrt(reliability) if reliability > 0 else 0.0
    true_r_required = r_crit / attenuation if attenuation > 0 else float("inf")

    return {
        "n_cells": n,
        "mean_contests_per_cell": round(float(np.mean(sizes)), 1),
        "single_contest_cells": sum(1 for s in sizes if s == 1),
        "var_cell_means": round(var_means, 3),
        "mean_sampling_var": round(mean_sampling, 3),
        "tau2": round(tau2, 3),
        "reliability": round(reliability, 4),
        "r_critical": round(r_crit, 4),
        "attenuation_factor": round(attenuation, 4),
        "true_r_required": round(true_r_required, 4)
        if true_r_required != float("inf") else None,
    }


def main() -> None:
    bundle = load_stage1_bundle(BUNDLE)
    oof = [dict(r) for r in bundle.out_of_fold]
    cells = aggregate_v2_residuals(oof)
    features = _read_csv(FEATURES)
    feature_index = _feature_index(features)
    sigma2 = _pooled_sigma2(oof)

    # Split cells into subsets
    ge_cells = [c for c in cells if "by-election" not in c["election_id"]]
    be_cells = [c for c in cells if "by-election" in c["election_id"]]

    # Covered cells (carry news coverage at the headline window)
    def is_covered(cell):
        row = feature_index.get(
            (cell["news_election_id"], cell["party_key"], WINDOW))
        if row is None:
            return False
        count = str(row.get("party_article_count", "")).strip()
        return count not in ("", "0") and float(count) != 0

    covered = [c for c in cells if is_covered(c)]
    covered_ge = [c for c in ge_cells if is_covered(c)]
    covered_be = [c for c in be_cells if is_covered(c)]

    # By-election event count
    be_events = set(c["election_id"] for c in be_cells)

    subsets = {
        "all_45_cells": _subset_stats(cells, sigma2),
        "general_elections_only": _subset_stats(ge_cells, sigma2),
        "by_elections_only": _subset_stats(be_cells, sigma2),
        "covered_all": _subset_stats(covered, sigma2),
        "covered_general_elections": _subset_stats(covered_ge, sigma2),
        "covered_by_elections": _subset_stats(covered_be, sigma2),
    }

    payload = {
        "status": STATUS,
        "pooled_sigma2": round(sigma2, 3),
        "total_cells": len(cells),
        "general_election_cells": len(ge_cells),
        "by_election_cells": len(be_cells),
        "by_election_events": len(be_events),
        "by_election_event_ids": sorted(be_events),
        "subsets": subsets,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "byelection_enrichment.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    s = payload["subsets"]

    lines = [
        "# By-election enrichment: the quantity-quality trade-off",
        "",
        f"**{payload['status']}**",
        "",
        f"Pooled within-cell variance (sigma-squared): "
        f"{payload['pooled_sigma2']}",
        "",
        "## What the enrichment did",
        "",
        f"- General election cells (2017 + 2021): "
        f"**{payload['general_election_cells']}**",
        f"- By-election cells ({payload['by_election_events']} events): "
        f"**{payload['by_election_cells']}**",
        f"- Total: **{payload['total_cells']}**",
        "",
        "## Reliability and detection threshold by subset",
        "",
        "| subset | cells | mean n/cell | single-contest | reliability "
        "| r critical | true r required |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for label, stats in s.items():
        if stats["n_cells"] == 0:
            continue
        true_r = (f"{stats['true_r_required']:.4f}"
                  if stats["true_r_required"] is not None else ">1.0")
        lines.append(
            f"| {label} | {stats['n_cells']} | "
            f"{stats['mean_contests_per_cell']} | "
            f"{stats['single_contest_cells']} | "
            f"{stats['reliability']} | "
            f"{stats['r_critical']:.4f} | {true_r} |")

    ge = s["general_elections_only"]
    all_ = s["all_45_cells"]
    lines += [
        "",
        "## The trade-off",
        "",
        f"Adding {payload['by_election_cells']} by-election cells "
        f"({payload['by_election_events']} events) "
        f"quadrupled the sample from {ge['n_cells']} to "
        f"{all_['n_cells']} cells.",
        "",
        f"- Reliability dropped from **{ge['reliability']}** to "
        f"**{all_['reliability']}** — the single-contest cells carry "
        f"enormous sampling noise (within-cell variance "
        f"{payload['pooled_sigma2']:.0f} on n=1).",
        f"- The critical r fell from {ge['r_critical']:.4f} to "
        f"{all_['r_critical']:.4f} — more cells lower the significance "
        f"threshold.",
        "",
        "The net effect: the true-r-required moved from "
        f"**{ge['true_r_required']}** to **{all_['true_r_required']}**. "
        f"The two forces roughly cancel. The design is underpowered "
        f"but not incapable.",
        "",
        "## Lesson",
        "",
        "Sample enrichment that adds low-precision cells can quadruple n "
        "while dividing measurement quality by four. The critical value "
        "falls but so does the signal-to-noise ratio. In this dataset "
        "the enrichment neither helped nor hurt detectability, but it "
        "made the reliability figure misleading when quoted without the "
        "subset breakdown.",
        "",
    ]

    (OUT_DIR / "byelection_enrichment_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
