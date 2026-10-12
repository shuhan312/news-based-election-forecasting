"""Direction 1, stage 4: is H2 (news on Reform's cold start) testable?

    PYTHONPATH=.:src python -m forecast.power_h2 run

A free power check before any money is spent on news. News is measured per
council, so councils are the independent units. The script

  1. counts K, the councils with a scheduled whole-council election on
     1 May 2025, from Democracy Club election metadata (ballot ids only, no
     results);
  2. takes the no-news reference M0 (Leave-scaled uniform swing) and its
     errors on Reform cold-start rows in the 2019->2023 validation round;
  3. simulates a council-level "news" signal of known correlation rho with
     M0's council errors, corrects M0 with it (leave-one-council-out), and
     tests the gain on K resampled councils;
  4. reports power for each rho and the minimum detectable effect (MDE80).

Criteria: v2_design/direction1_power/criteria.md.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import requests

from forecast import models as M

OUT_DIR = Path("v2_design/direction1_power")
EE_API = "https://elections.democracyclub.org.uk/api/elections/"
RHOS = [round(x, 1) for x in np.arange(0.1, 0.91, 0.1)]
N_SIMS, N_BOOT = 400, 300
SEED = 20261012
MDE_GATE = 1.0                         # pp, from the design


# --- 1. K: the size of the 2025 test, from metadata only -------------------------------

def count_test_councils() -> tuple[int, list[str]]:
    """Councils with >= 10 scheduled (non-by-election) ballots on 1 May 2025.

    Only election ids and their child ballot ids are read. Ballot ids carry
    no votes, so no 2025 result enters this check.
    """
    listing = requests.get(EE_API, params={
        "poll_open_date": "2025-05-01", "election_type": "local",
        "identifier_type": "organisation", "limit": 200}, timeout=120).json()
    councils = []
    for e in listing["results"]:
        if (e.get("organisation") or {}).get("territory_code") != "ENG":
            continue
        detail = requests.get(EE_API + e["election_id"] + "/",
                              timeout=120).json()
        scheduled = [c for c in detail.get("children", [])
                     if ".by." not in c]
        if len(scheduled) >= 10:
            councils.append(e["organisation"]["slug"])
    return len(councils), sorted(councils)


# --- 2. M0's errors on Reform cold starts, by council ------------------------------------

def reform_cold_errors() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """y, M0 prediction and council for every Reform cold-start validation row."""
    rows = M.load_units()
    train = [r for r in rows if r["round"] in M.TRAIN_ROUNDS]
    valid = [r for r in rows if r["round"] == M.VALID_ROUND]
    prior = M.cold_start_prior(train)
    prior["_gamma"] = M.fit_leave_gamma(train)      # training rounds only
    pred = M.uniform_swing_leave(valid, prior)      # H2's M0 (amendment A2)
    idx = [i for i, r in enumerate(valid)
           if r["party"] == "REF" and r["cold_start"]]
    y = np.array([valid[i]["share"] for i in idx])
    return y, pred[idx], [valid[i]["council"] for i in idx]


# --- 3. one simulated news signal -------------------------------------------------------

def simulate_once(y, m0, councils, rho, K, rng) -> tuple[float, bool]:
    """Gain of M2 = M0 + beta * s_c over M0 on K resampled councils, and
    whether its 95% council-bootstrap CI excludes zero."""
    by = defaultdict(list)
    for i, c in enumerate(councils):
        by[c].append(i)
    names = sorted(by)
    # Council mean error r_c, standardised, and a signal with corr ~ rho.
    r = np.array([np.mean(y[by[c]] - m0[by[c]]) for c in names])
    z = (r - r.mean()) / (r.std() or 1.0)
    s = rho * z + np.sqrt(1 - rho ** 2) * rng.normal(size=len(names))
    s_row = np.empty(len(y))
    for k, c in enumerate(names):
        s_row[by[c]] = s[k]
    # beta for council c is fitted on every OTHER council's rows, so a
    # council's own error never helps correct it.
    m2 = m0.copy()
    resid = y - m0
    for k, c in enumerate(names):
        other = np.ones(len(y), bool)
        other[by[c]] = False
        x = s_row[other]
        beta = (x @ resid[other]) / (x @ x) if x @ x > 0 else 0.0
        m2[by[c]] = np.clip(m0[by[c]] + beta * s[k], 0, None)
    gain_c = np.array([np.abs(resid[by[c]]).sum()
                       - np.abs(y[by[c]] - m2[by[c]]).sum() for c in names])
    n_c = np.array([len(by[c]) for c in names])
    # A 2025-sized test: K councils drawn with replacement.
    pick = rng.integers(0, len(names), K)
    gain = gain_c[pick].sum() / n_c[pick].sum()
    boots = []
    for _ in range(N_BOOT):
        b = pick[rng.integers(0, K, K)]
        boots.append(gain_c[b].sum() / n_c[b].sum())
    return float(gain), bool(np.percentile(boots, 2.5) > 0)


def power_curve(y, m0, councils, K, rng) -> list[dict]:
    out = []
    for rho in RHOS:
        sims = [simulate_once(y, m0, councils, rho, K, rng)
                for _ in range(N_SIMS)]
        out.append({"rho": rho,
                    "mean_gain_pp": round(float(np.mean([g for g, _ in sims])), 4),
                    "power": round(float(np.mean([d for _, d in sims])), 3)})
    return out


def mde80(curve: list[dict]) -> dict | None:
    """The weakest signal with power >= 0.80, and the gain it delivers."""
    for point in curve:
        if point["power"] >= 0.80:
            return point
    return None


# --- the run --------------------------------------------------------------------------

def stage_run() -> None:
    from forecast.polls import load_polls, poll_average
    rng = np.random.default_rng(SEED)
    K, test_councils = count_test_councils()
    y, m0, councils = reform_cold_errors()

    primary = power_curve(y, m0, councils, K, rng)
    # Sensitivity: Reform's errors scaled up to its 2025 polling level.
    polls = load_polls()
    scale = (poll_average(polls, "2025-05-01", "REF")
             / poll_average(polls, "2023-05-04", "REF"))
    scaled = power_curve(y * scale, m0 * scale, councils, K, rng)

    p, s = mde80(primary), mde80(scaled)
    passes = p is not None and p["mean_gain_pp"] <= MDE_GATE
    payload = {
        "criteria": "v2_design/direction1_power/criteria.md",
        "K_test_councils": K, "test_councils": test_councils,
        "validation_reform_cold_rows": int(len(y)),
        "validation_councils": len(set(councils)),
        "m0_validation_mae": round(float(np.abs(y - m0).mean()), 4),
        "primary_curve": primary, "primary_mde80": p,
        "scaled_by": round(scale, 3), "scaled_curve": scaled,
        "scaled_mde80": s,
        "gate_pp": MDE_GATE,
        "verdict": "run H2" if passes else "do not run H2 (underpowered)",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "power_h2_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items()
                      if k not in ("test_councils",)}, indent=2))


if __name__ == "__main__":
    {"run": stage_run}[sys.argv[1]]()
