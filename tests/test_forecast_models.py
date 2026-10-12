"""Tests for direction 1's models (forecast.models).

Hand-made contests check the baselines and renormalisation; synthetic data
checks that the ridge and the council intercepts recover what they should.
Integration tests on the built units (skipped if not built locally) check
that no 2025 row is used and that validation is reproducible.
"""

from pathlib import Path

import numpy as np
import pytest

from forecast import models as M


def unit(ballot, party, share_prev, share=0.0, cold=0, poll_prev=None,
         poll_curr=None, council="c", rnd="2017-2021"):
    change = (poll_curr - poll_prev
              if poll_prev is not None and poll_curr is not None else None)
    return {"round": rnd, "council": council, "subtype": "NMD",
            "ballot_id": ballot, "ward_id": ballot, "party": party,
            "share_prev": share_prev, "boundary_fallback": 0,
            "match_type": "id", "cold_start": cold, "incumbent_standing": 0,
            "n_candidates": 3, "n_party_candidates": 1, "winner_count": 1,
            "controls_council_prev": 0, "council_whole_prev": 1,
            "poll_prev": poll_prev, "poll_curr": poll_curr,
            "poll_change": change, "share": share,
            "leave_pct": M.ENGLAND_LEAVE, "leave_missing": 0,
            "insurgent_council_prev": 0.0}


CONTEST = [unit("b1", "CON", 60, poll_prev=40, poll_curr=30),
           unit("b1", "LAB", 40, poll_prev=30, poll_curr=40),
           unit("b1", "REF", 0, cold=1, poll_curr=10)]


def test_renormalise_clips_and_sums_to_100_per_contest():
    rows = CONTEST + [unit("b2", "CON", 0), unit("b2", "LAB", 0)]
    out = M.renormalise(rows, np.array([-5.0, 50.0, 50.0, 0.0, 0.0]))
    assert out[:3].sum() == pytest.approx(100) and out[0] == 0
    assert list(out[3:]) == [50.0, 50.0]          # all-zero contest: equal


def test_baselines_on_a_hand_computed_contest():
    # Raw: CON 60/50/45, LAB 40/50/53.3, REF (cold start) 10 in each.
    p = M.persistence(CONTEST, {})
    assert p == pytest.approx(100 * np.array([60, 40, 10]) / 110)
    u = M.uniform_swing(CONTEST, {})
    assert u == pytest.approx(100 * np.array([50, 50, 10]) / 110)
    s = M.proportional_swing(CONTEST, {})
    raw = np.array([45, 40 * 40 / 30, 10])
    assert s == pytest.approx(100 * raw / raw.sum())


def test_cold_start_without_a_poll_uses_the_training_prior():
    rows = [unit("b", "CON", 50, poll_prev=40, poll_curr=40),
            unit("b", "OTH", 0, cold=1)]
    assert M.persistence(rows, {"OTH": 25.0})[1] == pytest.approx(
        100 * 25 / 75)


def test_ridge_recovers_a_linear_signal():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 3))
    y = 2 * X[:, 0] - X[:, 1] + 5 + rng.normal(scale=0.01, size=500)
    pred = M.Ridge(alpha=0.01).fit(X, y).predict(X)
    assert np.abs(pred - y).mean() < 0.05


def test_council_intercepts_are_shrunk_and_unseen_councils_get_none():
    X = np.zeros((6, 1))
    y = np.array([3, 3, 3, -3, -3, -3], dtype=float)
    groups = ["a", "a", "a", "b", "b", "b"]
    m = M.RidgeCouncil(alpha=1.0, k=3).fit_with_groups(X, y, groups)
    # Mean residual 3, n = 3, k = 3: shrunk to half.
    assert m.u["a"] == pytest.approx(1.5)
    assert m.predict_groups(np.zeros((1, 1)), ["new"])[0] == pytest.approx(0)


def test_bootstrap_ci_brackets_a_known_difference():
    rows = [unit(f"b{i}", "CON", 0, share=10, council=f"c{i % 20}")
            for i in range(200)]
    a = np.full(200, 12.0)                       # error 2
    b = np.full(200, 11.0)                       # error 1
    lo, hi = M.council_bootstrap_diff(rows, a, b, n=200)
    assert lo == pytest.approx(1.0) and hi == pytest.approx(1.0)


# --- stage 3b: Reform cold start ---------------------------------------------------------

def test_leave_gamma_is_recovered_from_synthetic_training_rows():
    rows = []
    for i, leave in enumerate(np.linspace(40, 70, 40)):
        r = unit(f"b{i}", "REF", 0, cold=1, poll_curr=10)
        r["leave_pct"] = leave
        r["share"] = 10 * (leave / M.ENGLAND_LEAVE) ** 2   # true gamma = 2
        rows.append(r)
    assert M.fit_leave_gamma(rows) == pytest.approx(2.0)


def test_leave_rule_reduces_to_uniform_swing_when_gamma_is_zero():
    rows = [dict(r, leave_pct=70.0) for r in CONTEST]
    assert M.uniform_swing_leave(rows, {"_gamma": 0.0}) == \
        pytest.approx(M.uniform_swing(rows, {}))


def test_leave_rule_raises_reform_where_leave_was_higher():
    high = [dict(r, leave_pct=65.0) for r in CONTEST]
    low = [dict(r, leave_pct=45.0) for r in CONTEST]
    prior = {"_gamma": 2.0}
    assert M.uniform_swing_leave(high, prior)[2] > \
        M.uniform_swing_leave(low, prior)[2]
    # Only the insurgent cold start moves; warm parties keep their ratio.
    h, l = M.uniform_swing_leave(high, prior), M.uniform_swing_leave(low, prior)
    assert h[0] / h[1] == pytest.approx(l[0] / l[1])


# --- integration on the built units ------------------------------------------------------

BUILT = Path("data/forecast/units_train.csv").exists()


@pytest.mark.skipif(not BUILT, reason="units not built locally")
def test_no_test_round_row_is_ever_loaded():
    rounds = {r["round"] for r in M.load_units()}
    assert rounds <= set(M.TRAIN_ROUNDS) | {M.VALID_ROUND}


@pytest.mark.skipif(not BUILT, reason="units not built locally")
def test_ml_fit_is_deterministic():
    rows = M.load_units()
    train = [r for r in rows if r["round"] == "2017-2021"][:3000]
    valid = [r for r in rows if r["round"] == M.VALID_ROUND][:1000]
    prior = M.cold_start_prior(train)
    spec = {"model": "lightgbm", "num_leaves": 7, "n_estimators": 50}
    a = M.fit_predict(spec, train, valid, prior)
    b = M.fit_predict(spec, train, valid, prior)
    assert np.array_equal(a, b)


# --- stage 4: H2 power simulation ---------------------------------------------------------

def test_power_simulation_gain_grows_with_signal_strength():
    from forecast import power_h2 as P
    rng = np.random.default_rng(0)
    councils = [f"c{i}" for i in range(30) for _ in range(20)]
    shift = {f"c{i}": rng.normal(scale=3) for i in range(30)}
    m0 = np.full(len(councils), 10.0)
    y = np.array([10 + shift[c] + rng.normal(scale=1) for c in councils])
    weak = np.mean([P.simulate_once(y, m0, councils, 0.1, 30, rng)[0]
                    for _ in range(30)])
    strong = np.mean([P.simulate_once(y, m0, councils, 0.9, 30, rng)[0]
                      for _ in range(30)])
    assert strong > weak and strong > 0.5


def test_mde80_picks_the_first_point_reaching_80_percent_power():
    from forecast import power_h2 as P
    curve = [{"rho": 0.1, "power": 0.2, "mean_gain_pp": 0.1},
             {"rho": 0.5, "power": 0.85, "mean_gain_pp": 0.7},
             {"rho": 0.9, "power": 1.0, "mean_gain_pp": 1.5}]
    assert P.mde80(curve)["rho"] == 0.5
    assert P.mde80(curve[:1]) is None
