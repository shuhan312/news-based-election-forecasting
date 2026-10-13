"""Direction 1, stage 4, amendment A2: H2 power at 2025's data structure.

    PYTHONPATH=.:src python -m forecast.power_h2_structural run

Why this exists. The first power check (forecast.power_h2) resampled
validation councils directly. In the 2019->2023 validation round, Reform's
cold-start rows average fewer than 3 per council (401 rows in 149 councils),
so each council's mean error is mostly ward-level noise. In 2025, Reform
stood in almost every ward of 23 councils, about 60-80 rows per council,
where that noise largely averages out. Resampling 2023's thin cells
understates how visible a council-level news signal would be in 2025. This
flaw was found AFTER the first check returned "do not run H2", which is
recorded in amendment A2.

Method. Instead of resampling cells, estimate the two components of M0's
error from validation and simulate 2025's shape:

  tau^2    variance of council-level error (what council news could fix)
  sigma^2  variance of ward-level error within a council (what it cannot)

Then for each simulation: draw K = 23 councils with n_c wards each (n_c =
the council's scheduled 2025 ballots, from Democracy Club metadata; Reform
is assumed to stand in every one), errors u_c + e_ic, a news signal with
correlation rho to u_c, a leave-one-council-out correction, and a council
bootstrap of the gain. Power is the share of simulations whose CI excludes
zero. Decision rule and scale are unchanged from the criteria.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from forecast.power_h2 import (EE_API, EE_CACHE, MDE_GATE, OUT_DIR, RHOS,
                               _ee_get, reform_cold_errors)

N_SIMS, N_BOOT = 400, 300
SEED = 20261013


# --- variance components from validation ----------------------------------------

def variance_components(err: np.ndarray, councils: list[str]) -> dict:
    """One-way random-effects (ANOVA, unbalanced) estimates of the council
    variance tau^2 and the within-council variance sigma^2 of M0's errors.
    tau^2 is floored at zero, as is standard."""
    groups = defaultdict(list)
    for e, c in zip(err, councils):
        groups[c].append(e)
    k, n = len(groups), len(err)
    grand = float(np.mean(err))
    ssb = sum(len(v) * (np.mean(v) - grand) ** 2 for v in groups.values())
    ssw = sum(((np.array(v) - np.mean(v)) ** 2).sum() for v in groups.values())
    msb, msw = ssb / (k - 1), ssw / (n - k)
    n0 = (n - sum(len(v) ** 2 for v in groups.values()) / n) / (k - 1)
    tau2 = max((msb - msw) / n0, 0.0)
    return {"tau2": tau2, "sigma2": msw, "councils": k, "rows": n,
            "mean_error": grand,
            "icc": tau2 / (tau2 + msw) if tau2 + msw > 0 else 0.0}


# --- 2025 structure from metadata -------------------------------------------------

def council_sizes_2025() -> dict[str, int]:
    """Scheduled ballots per 2025 council that held its election (metadata
    only: ballot ids carry no results)."""
    listing = _ee_get(EE_API, cache=EE_CACHE / "listing.json")
    sizes = {}
    for e in listing["results"]:
        if (e.get("organisation") or {}).get("territory_code") != "ENG":
            continue
        detail = _ee_get(EE_API + e["election_id"] + "/",
                         cache=EE_CACHE / f"{e['election_id']}.json")
        if detail.get("cancelled"):
            continue
        scheduled = [c for c in detail.get("children", []) if ".by." not in c]
        if len(scheduled) >= 10:
            sizes[e["organisation"]["slug"]] = len(scheduled)
    return sizes


# --- one simulated 2025-shaped test -------------------------------------------------

def simulate_once(tau: float, sigma: float, sizes: list[int], rho: float,
                  rng) -> tuple[float, bool]:
    """Gain of M0 + beta*s_c over M0 on one simulated 2025-shaped dataset,
    and whether its 95% council-bootstrap CI excludes zero."""
    K = len(sizes)
    u = rng.normal(0, tau, K)                          # council-level error
    z = (u - u.mean()) / (u.std() or 1.0)
    s = rho * z + np.sqrt(1 - rho ** 2) * rng.normal(size=K)
    idx = np.repeat(np.arange(K), sizes)
    err = u[idx] + rng.normal(0, sigma, idx.size)      # M0 error per ward
    s_row = s[idx]
    gain_c, n_c = np.empty(K), np.array(sizes, float)
    for c in range(K):
        # beta from every other council only: no council corrects itself
        # with its own error.
        other = idx != c
        x, r = s_row[other], err[other]
        beta = (x @ r) / (x @ x) if x @ x > 0 else 0.0
        mine = idx == c
        gain_c[c] = (np.abs(err[mine]).sum()
                     - np.abs(err[mine] - beta * s[c]).sum())
    gain = gain_c.sum() / n_c.sum()
    boots = []
    for _ in range(N_BOOT):
        b = rng.integers(0, K, K)
        boots.append(gain_c[b].sum() / n_c[b].sum())
    return float(gain), bool(np.percentile(boots, 2.5) > 0)


def power_curve(tau, sigma, sizes, rng) -> list[dict]:
    out = []
    for rho in RHOS:
        sims = [simulate_once(tau, sigma, sizes, rho, rng)
                for _ in range(N_SIMS)]
        out.append({"rho": rho,
                    "mean_gain_pp": round(float(np.mean([g for g, _ in sims])), 4),
                    "power": round(float(np.mean([d for _, d in sims])), 3)})
    return out


def mde80(curve):
    return next((p for p in curve if p["power"] >= 0.80), None)


def stage_run() -> None:
    from forecast.polls import load_polls, poll_average
    rng = np.random.default_rng(SEED)
    y, m0, councils = reform_cold_errors()
    vc = variance_components(y - m0, councils)
    sizes_map = council_sizes_2025()
    sizes = list(sizes_map.values())
    tau, sigma = np.sqrt(vc["tau2"]), np.sqrt(vc["sigma2"])

    primary = power_curve(tau, sigma, sizes, rng)
    polls = load_polls()
    scale = (poll_average(polls, "2025-05-01", "REF")
             / poll_average(polls, "2023-05-04", "REF"))
    scaled = power_curve(tau * scale, sigma * scale, sizes, rng)
    # Sensitivity: Reform standing in only 70% of wards.
    thin = power_curve(tau, sigma, [max(1, int(0.7 * n)) for n in sizes], rng)

    p = mde80(primary)
    passes = p is not None and p["mean_gain_pp"] <= MDE_GATE
    payload = {
        "amendment": "A2 (structure-matched simulation)",
        "variance_components": {k: round(v, 4) if isinstance(v, float) else v
                                for k, v in vc.items()},
        "K": len(sizes), "wards_per_council": sizes_map,
        "primary_curve": primary, "primary_mde80": p,
        "scaled_by": round(scale, 3), "scaled_curve": scaled,
        "scaled_mde80": mde80(scaled),
        "coverage70_curve": thin, "coverage70_mde80": mde80(thin),
        "gate_pp": MDE_GATE,
        "verdict": "run H2" if passes else "do not run H2 (underpowered)",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "power_h2_results_A2.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items()
                      if k != "wards_per_council"}, indent=2))


if __name__ == "__main__":
    {"run": stage_run}[sys.argv[1]]()
