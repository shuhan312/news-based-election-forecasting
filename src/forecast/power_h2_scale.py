"""Direction 1, stage 4, amendment A3: council-level error at a large share.

    PYTHONPATH=.:src python -m forecast.power_h2_scale run

Why this exists. Amendment A2 estimated the between-council variance of
M0's Reform errors (tau^2) on the 2019->2023 validation round and found
zero. Reform then averaged 6.8% where it stood. A party on a few per cent
everywhere cannot differ much between councils, so tau^2 = 0 says little
about 2025, when Reform polled about 30%. A2's "2025 scale" sensitivity
multiplied the errors by the poll ratio (x4.49), but 4.49 x 0 is still 0,
so it could not catch this.

The check that A2's findings called impossible without 2025 data is in fact
possible on training data: decompose M0's errors for every party large
enough to resemble Reform in 2025. Uses 2017-2023 only; each round is
predicted with the cold-start prior and Leave gamma fitted on the other two
rounds. No 2025 result is read.

The power simulation of A2 is then rerun with tau and sigma set to the
median over party-rounds whose mean share is at least LARGE_SHARE.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from forecast import models as M
from forecast.power_h2 import MDE_GATE, OUT_DIR
from forecast.power_h2_structural import (SEED, council_sizes_2025, mde80,
                                          power_curve, variance_components)

PARTIES = ["CON", "LAB", "LD", "GRN", "REF"]
LARGE_SHARE = 13.0      # pp: the smallest major-party mean share observed


def decompositions() -> list[dict]:
    """tau, sigma and ICC of M0's errors for each party and round."""
    rows = M.load_units()
    out = []
    for rd in sorted({r["round"] for r in rows}):
        train = [r for r in rows if r["round"] != rd]
        test = [r for r in rows if r["round"] == rd]
        prior = M.cold_start_prior(train)
        prior["_gamma"] = M.fit_leave_gamma(train)
        pred = M.uniform_swing_leave(test, prior)          # H2's M0
        for party in PARTIES:
            idx = [i for i, r in enumerate(test) if r["party"] == party]
            if len(idx) < 200:
                continue
            y = np.array([test[i]["share"] for i in idx])
            vc = variance_components(y - pred[idx],
                                     [test[i]["council"] for i in idx])
            out.append({"round": rd, "party": party, "rows": len(idx),
                        "councils": vc["councils"],
                        "mean_share": round(float(y.mean()), 1),
                        "tau": round(vc["tau2"] ** 0.5, 2),
                        "sigma": round(vc["sigma2"] ** 0.5, 2),
                        "icc": round(vc["icc"], 3)})
    return out


def stage_run() -> None:
    table = decompositions()
    large = [d for d in table if d["mean_share"] >= LARGE_SHARE]
    tau = float(np.median([d["tau"] for d in large]))
    sigma = float(np.median([d["sigma"] for d in large]))
    sizes = list(council_sizes_2025().values())
    curve = power_curve(tau, sigma, sizes, np.random.default_rng(SEED))
    # Sensitivity: the smallest council-level error among large parties.
    low = min(large, key=lambda d: d["tau"])
    curve_low = power_curve(low["tau"], low["sigma"], sizes,
                            np.random.default_rng(SEED))
    p = mde80(curve)
    payload = {
        "amendment": "A3 (council-level error at a large share)",
        "decompositions": table,
        "large_share_min_pp": LARGE_SHARE,
        "tau_used": tau, "sigma_used": sigma, "K": len(sizes),
        "curve": curve, "mde80": p,
        "sensitivity_lowest_tau": {"tau": low["tau"], "sigma": low["sigma"],
                                   "curve": curve_low,
                                   "mde80": mde80(curve_low)},
        "gate_pp": MDE_GATE,
        "verdict": ("run H2" if p is not None and p["mean_gain_pp"] <= MDE_GATE
                    else "do not run H2 (underpowered)"),
    }
    (OUT_DIR / "power_h2_results_A3.json").write_text(
        json.dumps(payload, indent=2, default=float) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items()
                      if k != "decompositions"}, indent=2, default=float))


if __name__ == "__main__":
    {"run": stage_run}[sys.argv[1]]()
