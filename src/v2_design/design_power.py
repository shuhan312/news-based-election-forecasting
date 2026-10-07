"""How many independent units does V2 need to resolve the content effect?

V2's single primary estimand is

    delta_content = MAE(M2) - MAE(M3)

    M0  intercept only (the recalibrated control)
    M1  + six party indicators
    M2  + coverage volume        (party_article_share)
    M3  + coverage tone          (net_portrayal_share)

i.e. what news *content* adds once party identity and media visibility are
already in the model. Positive is better for content.

The V1 MDE annex (`minimal_detectable_effect_v1`) cannot answer this. Its
intervals resample the 81 holdout contests with the fitted model held fixed,
so they see test-set noise only. They do not see (a) training noise from
fitting on 45 cells, or (b) the dominant term for a party-level news effect:
which election you happened to test on. Every candidate of one party in one
election receives the same news adjustment, so a single holdout election
contributes a handful of independent content signals, not 81.

This module measures that variance directly by running V2's evaluation design
on V1's own fitting data: leave one election out, refit M0-M3 on the rest,
score the held-out election's candidates. The spread of delta_content across
held-out elections and election-party cells is what V2's sample size has to
beat. It reads only committed Stage 1 out-of-fold rows (2013-2025 fitting
elections, all pre-2026) and the frozen feature table; it never reads 2026
outcomes and no new county's data.

Simplifications, stated rather than hidden:
- predictions are not clipped/renormalised per contest (V1's scorer does
  this); the comparison is between arms sharing the same omission;
- leave-one-out ignores chronology (an early election may be scored by a
  model fitted on later ones). That is acceptable for a variance estimate,
  which assumes elections are exchangeable; it is not acceptable for V2's
  confirmatory evaluation, which will forward-chain;
- tone enters as the raw level, the frozen column, not the within-party
  centred variant, so no estimate is borrowed from the held-out election.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from news_modelling.blinded_2026_predictions_v2 import (
    FIT_ELECTION_MAP,
    aggregate_v2_residuals,
)
from news_modelling.identity_placebos import (
    BUNDLE,
    DUMMY_COLUMNS,
    FEATURES,
    build_derived_index,
)
from news_modelling.news_estimator import RidgeModel
from news_modelling.placebo_specifications import WINDOWS
from news_modelling.production_news_experiment import (
    FIXED_RIDGE_PENALTY,
    _float_or_structural_zero,
    _read_csv,
    party_key,
)
from news_modelling.stage1_bundle import load_stage1_bundle

OUT_DIR = Path("v2_design/power_v1")
HEADLINE_WINDOW = "90_to_31_days"

ARMS = {
    "M0_intercept": [],
    "M1_party": DUMMY_COLUMNS,
    "M2_party_volume": DUMMY_COLUMNS + ["party_article_share"],
    "M3_party_volume_tone": DUMMY_COLUMNS
    + ["party_article_share", "net_portrayal_share"],
    # A second content operationalisation: the LLM frame with the strongest
    # raw association in V1. Reported so the projection is not tied to tone.
    "M3b_party_volume_incumbent": DUMMY_COLUMNS
    + ["party_article_share", "party_frame_incumbent_judgement_share"],
}
PRIMARY = ("M2_party_volume", "M3_party_volume_tone")

Z_ALPHA = 1.959964  # two-sided 5%
Z_BETA = 0.841621   # 80% power
TARGET_EFFECTS = (0.05, 0.10, 0.20, 0.30)  # share points of MAE
BOOTSTRAP_RESAMPLES = 4000
SEED = 20261007


def _design(rows, index, columns, window):
    return np.array([
        [_float_or_structural_zero(index[(r["news_election_id"], r["party_key"],
                                          window)], c) for c in columns]
        for r in rows], dtype=float).reshape(len(rows), len(columns))


def _fit_predict(train_cells, test_keys, index, columns, window):
    """Adjustment per held-out (news_election_id, party) key."""
    target = np.array([c["mean_residual"] for c in train_cells])
    if not columns:
        return {k: float(target.mean()) for k in test_keys}
    model = RidgeModel(FIXED_RIDGE_PENALTY).fit(
        _design(train_cells, index, columns, window), target)
    test_rows = [{"news_election_id": e, "party_key": p} for e, p in test_keys]
    adjustments = model.predict(_design(test_rows, index, columns, window))
    return {k: float(a) for k, a in zip(test_keys, adjustments)}


def leave_one_election_out(cells, candidates, index, window):
    """Candidate-level absolute errors for every arm, every held-out election."""
    elections = sorted({c["election_id"] for c in cells})
    scored = []
    for held_out in elections:
        train = [c for c in cells if c["election_id"] != held_out]
        test = [r for r in candidates if r["election_id"] == held_out]
        news_id = FIT_ELECTION_MAP[held_out]
        keys = sorted({(news_id, r["party_key"]) for r in test})
        adjustments = {arm: _fit_predict(train, keys, index, cols, window)
                       for arm, cols in ARMS.items()}
        for r in test:
            key = (news_id, r["party_key"])
            row = {"election_id": held_out, "party_key": r["party_key"]}
            for arm in ARMS:
                pred = r["predicted"] + adjustments[arm][key]
                row[arm] = abs(r["observed"] - pred)
            scored.append(row)
    return scored


def _cell_deltas(scored, a, b):
    """delta = MAE(a) - MAE(b) per election-party cell, with its size."""
    groups = defaultdict(list)
    for r in scored:
        groups[(r["election_id"], r["party_key"])].append(r[a] - r[b])
    return [{"election_id": e, "party_key": p, "n": len(v),
             "delta": float(np.mean(v))} for (e, p), v in sorted(groups.items())]


def _cluster_bootstrap(scored, a, b, rng):
    """Election-cluster bootstrap of the candidate-weighted delta."""
    by_election = defaultdict(list)
    for r in scored:
        by_election[r["election_id"]].append(r[a] - r[b])
    sums = np.array([np.sum(v) for v in by_election.values()])
    counts = np.array([len(v) for v in by_election.values()])
    k = len(sums)
    draws = np.empty(BOOTSTRAP_RESAMPLES)
    for i in range(BOOTSTRAP_RESAMPLES):
        pick = rng.integers(0, k, size=k)
        draws[i] = sums[pick].sum() / counts[pick].sum()
    return draws


def _icc(cells):
    """One-way ANOVA ICC of cell deltas within elections (floored at 0)."""
    groups = defaultdict(list)
    for c in cells:
        groups[c["election_id"]].append(c["delta"])
    values = np.array([c["delta"] for c in cells])
    k, n = len(groups), len(values)
    grand = values.mean()
    ssb = sum(len(v) * (np.mean(v) - grand) ** 2 for v in groups.values())
    ssw = sum(((np.array(v) - np.mean(v)) ** 2).sum() for v in groups.values())
    msb, msw = ssb / (k - 1), ssw / (n - k)
    m0 = (n - sum(len(v) ** 2 for v in groups.values()) / n) / (k - 1)
    sigma_b = max((msb - msw) / m0, 0.0)
    return sigma_b / (sigma_b + msw) if sigma_b + msw > 0 else 0.0


def project(sigma_cell, icc, cells_per_election, label):
    """Independent cells / elections needed for MDE80 = target."""
    deff = 1 + (cells_per_election - 1) * icc
    rows = []
    for target in TARGET_EFFECTS:
        n_cells = ((Z_ALPHA + Z_BETA) * sigma_cell / target) ** 2 * deff
        rows.append({"basis": label, "target_mde80": target,
                     "cells_needed": int(np.ceil(n_cells)),
                     "elections_needed": int(np.ceil(n_cells / cells_per_election)),
                     "design_effect": round(deff, 3)})
    return rows


def project_from_cluster_se(se, effective_clusters):
    """Second basis: scale the election-cluster SE by 1/sqrt(elections).

    Candidate weighting lets the two whole-council elections dominate, so the
    observed SE belongs to ~effective_clusters elections, not to all ten.
    """
    return [{"basis": "election-cluster SE", "target_mde80": target,
             "elections_needed": int(np.ceil(
                 effective_clusters * ((Z_ALPHA + Z_BETA) * se / target) ** 2))}
            for target in TARGET_EFFECTS]


def analyse_window(cells, candidates, index, window, rng):
    scored = leave_one_election_out(cells, candidates, index, window)
    arm_mae = {arm: float(np.mean([r[arm] for r in scored])) for arm in ARMS}
    ladder = {}
    for a, b in [("M0_intercept", "M1_party"), ("M1_party", "M2_party_volume"),
                 PRIMARY, ("M2_party_volume", "M3b_party_volume_incumbent")]:
        draws = _cluster_bootstrap(scored, a, b, rng)
        ladder[f"{b}_vs_{a}"] = {
            "delta": arm_mae[a] - arm_mae[b],
            "cluster_ci95": [float(np.percentile(draws, 2.5)),
                             float(np.percentile(draws, 97.5))],
            "cluster_se": float(draws.std(ddof=1)),
        }

    cells_primary = _cell_deltas(scored, *PRIMARY)
    full = [c for c in cells_primary if c["n"] >= 20]  # whole-council elections
    per_election = defaultdict(list)
    for c in cells_primary:
        per_election[c["election_id"]].append(c)
    m = float(np.mean([len(v) for e, v in per_election.items()
                       if any(c["n"] >= 20 for c in v)]))
    icc = _icc(cells_primary)
    sizes = np.array([sum(c["n"] for c in v) for v in per_election.values()])
    effective_clusters = float(sizes.sum() ** 2 / (sizes ** 2).sum())
    primary_se = ladder[f"{PRIMARY[1]}_vs_{PRIMARY[0]}"]["cluster_se"]
    sigma_all = float(np.std([c["delta"] for c in cells_primary], ddof=1))
    sigma_full = float(np.std([c["delta"] for c in full], ddof=1))
    return {
        "window": window,
        "held_out_elections": len(per_election),
        "candidates_scored": len(scored),
        "arm_mae_loeo": arm_mae,
        "ladder": ladder,
        "primary_cells": cells_primary,
        "sigma_cell_all": sigma_all,
        "sigma_cell_whole_council": sigma_full,
        "whole_council_cells": len(full),
        "icc_within_election": icc,
        "cells_per_whole_council_election": m,
        "effective_election_clusters": effective_clusters,
        "projection": project(sigma_full, icc, m, "whole-council cells")
        + project(sigma_all, icc, m, "all cells incl. by-elections")
        + project_from_cluster_se(primary_se, effective_clusters),
    }


def main() -> None:
    features = _read_csv(FEATURES)
    bundle = load_stage1_bundle(BUNDLE)
    oof = [dict(r) for r in bundle.out_of_fold]
    cells = aggregate_v2_residuals(oof)
    index, _ = build_derived_index(features, cells)
    cell_keys = {(c["election_id"], c["party_key"]) for c in cells}
    candidates = []
    for r in oof:
        key = party_key(r.get("standard_party_name"))
        if (r.get("election_id"), key) in cell_keys:
            candidates.append({"election_id": r["election_id"], "party_key": key,
                               "observed": float(r["observed_vote_share"]),
                               "predicted": float(r["predicted_vote_share"])})

    rng = np.random.default_rng(SEED)
    windows = [analyse_window(cells, candidates, index, w, rng) for w in WINDOWS]
    payload = {
        "status": "EXPLORATORY V2 design input. Pre-2026 fitting data only; "
                  "no 2026 outcome and no new-county data is read.",
        "estimand": "delta_content = MAE(M2_party_volume) - "
                    "MAE(M3_party_volume_tone); positive favours content",
        "fitting_cells": len(cells),
        "headline_window": HEADLINE_WINDOW,
        "power": {"alpha_two_sided": 0.05, "power": 0.80,
                  "z_sum": Z_ALPHA + Z_BETA},
        "windows": windows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "design_power_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
