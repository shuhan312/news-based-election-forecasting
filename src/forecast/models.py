"""Direction 1, stage 3: classical baselines, ML models, temporal validation.

    PYTHONPATH=.:src python -m forecast.models validate

Training rounds 2017->2021 and 2018->2022; validation round 2019->2023.
2025 is never touched here. The run writes:

  v2_design/direction1_models/validation_results.json   every candidate
  v2_design/direction1_models/selected_config.json      the H1 freeze

Every prediction is a vote share per ward x party. Within each ward contest,
shares are clipped at zero and renormalised to 100, so every model is scored
on the same footing as a real forecast.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

UNITS_CSV = Path("data/forecast/units_train.csv")
OUT_DIR = Path("v2_design/direction1_models")
TRAIN_ROUNDS = ("2017-2021", "2018-2022")
VALID_ROUND = "2019-2023"
SEED = 20261012

PARTIES = ("CON", "LAB", "LD", "GRN", "REF", "UKIP", "OTH")
SUBTYPES = ("CTY", "UA", "MD", "NMD", "LBO")
MATCH_TYPES = ("id", "label", "fallback")


# --- data ------------------------------------------------------------------------------

def _num(value: str) -> float | None:
    return None if value in ("", None) else float(value)


def load_units(path: Path = UNITS_CSV) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for r in rows:
        for k in ("share", "share_prev", "poll_prev", "poll_curr",
                  "poll_change"):
            r[k] = _num(r[k])
        for k in ("boundary_fallback", "cold_start", "incumbent_standing",
                  "n_candidates", "n_party_candidates", "winner_count",
                  "controls_council_prev", "council_whole_prev"):
            r[k] = int(r[k])
    return rows


def renormalise(rows: list[dict], raw: np.ndarray) -> np.ndarray:
    """Clip at zero, then scale each contest's shares to sum to 100.

    A contest whose raw predictions are all zero falls back to equal shares
    rather than dividing by zero.
    """
    # Cast to float first: an all-integer input would otherwise make
    # `out` an integer array and silently truncate every share.
    raw = np.clip(np.asarray(raw, dtype=float), 0, None)
    out = np.empty_like(raw)
    by_contest = defaultdict(list)
    for i, r in enumerate(rows):
        by_contest[r["ballot_id"]].append(i)
    for idx in by_contest.values():
        total = raw[idx].sum()
        out[idx] = 100 * raw[idx] / total if total > 0 else 100 / len(idx)
    return out


# --- classical baselines --------------------------------------------------------------

def cold_start_prior(train: list[dict]) -> dict[str, float]:
    """Mean share of each party when standing somewhere for the first time,
    from the training rounds only. Used when no national poll exists for a
    party (OTH; UKIP after 2020)."""
    acc = defaultdict(list)
    for r in train:
        if r["cold_start"]:
            acc[r["party"]].append(r["share"])
    return {p: float(np.mean(v)) for p, v in acc.items()}


def _cold_start_value(r: dict, prior: dict) -> float:
    """Naive cold-start rule: the party's national poll share now, else its
    training-round cold-start mean."""
    if r["poll_curr"] is not None:
        return r["poll_curr"]
    return prior.get(r["party"], 0.0)


def persistence(rows, prior) -> np.ndarray:
    """Last share carries over; cold starts take the naive rule."""
    raw = np.array([_cold_start_value(r, prior) if r["cold_start"]
                    else r["share_prev"] for r in rows])
    return renormalise(rows, raw)


def uniform_swing(rows, prior) -> np.ndarray:
    """Last share plus the party's national poll change (in points)."""
    raw = np.array([
        _cold_start_value(r, prior) if r["cold_start"]
        else r["share_prev"] + (r["poll_change"] or 0.0) for r in rows])
    return renormalise(rows, raw)


def proportional_swing(rows, prior) -> np.ndarray:
    """Last share scaled by the party's national poll ratio, so a party
    loses more where it was strong."""
    def one(r):
        if r["cold_start"]:
            return _cold_start_value(r, prior)
        if r["poll_prev"] and r["poll_curr"] is not None and r["poll_prev"] > 0:
            return r["share_prev"] * r["poll_curr"] / r["poll_prev"]
        return r["share_prev"]
    return renormalise(rows, np.array([one(r) for r in rows]))


BASELINES = {"persistence": persistence, "uniform_swing": uniform_swing,
             "proportional_swing": proportional_swing}


# --- features for the ML models --------------------------------------------------------

FEATURES = (
    ["uns_pred", "share_prev", "poll_prev", "poll_curr", "poll_change",
     "poll_missing", "cold_start", "incumbent_standing", "n_candidates",
     "n_party_candidates", "winner_count", "controls_council_prev",
     "council_whole_prev", "boundary_fallback"]
    + [f"party_{p}" for p in PARTIES]
    + [f"subtype_{s}" for s in SUBTYPES]
    + [f"match_{m}" for m in MATCH_TYPES]
)


def design_matrix(rows: list[dict], uns: np.ndarray) -> np.ndarray:
    """One fixed column order for every model. Missing polls are set to 0
    with an indicator, so the model can tell "no poll" from "0%"."""
    X = np.zeros((len(rows), len(FEATURES)))
    col = {f: i for i, f in enumerate(FEATURES)}
    for i, r in enumerate(rows):
        X[i, col["uns_pred"]] = uns[i]
        X[i, col["share_prev"]] = r["share_prev"] or 0.0
        missing = r["poll_curr"] is None
        X[i, col["poll_missing"]] = int(missing)
        for k in ("poll_prev", "poll_curr", "poll_change"):
            X[i, col[k]] = r[k] or 0.0
        for k in ("cold_start", "incumbent_standing", "n_candidates",
                  "n_party_candidates", "winner_count",
                  "controls_council_prev", "council_whole_prev",
                  "boundary_fallback"):
            X[i, col[k]] = r[k]
        X[i, col[f"party_{r['party']}"]] = 1
        if f"subtype_{r['subtype']}" in col:
            X[i, col[f"subtype_{r['subtype']}"]] = 1
        X[i, col[f"match_{r['match_type']}"]] = 1
    return X


# --- ML models: each learns a correction to uniform swing -------------------------------

class Ridge:
    """Closed-form ridge on standardised features; intercept not penalised.
    (scikit-learn is not a project dependency, and this is ten lines.)"""

    def __init__(self, alpha: float):
        self.alpha = alpha

    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0)
        self.sd[self.sd == 0] = 1.0                # constant columns: inert
        Z = (X - self.mu) / self.sd
        self.b0 = y.mean()
        A = Z.T @ Z + self.alpha * np.eye(Z.shape[1])
        self.w = np.linalg.solve(A, Z.T @ (y - self.b0))
        return self

    def predict(self, X):
        return self.b0 + ((X - self.mu) / self.sd) @ self.w


class RidgeCouncil(Ridge):
    """Ridge plus shrunken council intercepts (an empirical-Bayes random
    intercept). Each council's intercept is its mean training residual,
    shrunk towards zero by k pseudo-observations: n / (n + k) of the mean.
    Councils not seen in training get no intercept."""

    def __init__(self, alpha: float, k: float):
        super().__init__(alpha)
        self.k = k

    def fit_with_groups(self, X, y, groups):
        self.fit(X, y)
        res = y - self.predict(X)
        acc = defaultdict(list)
        for g, e in zip(groups, res):
            acc[g].append(e)
        self.u = {g: float(np.sum(v) / (len(v) + self.k))
                  for g, v in acc.items()}
        return self

    def predict_groups(self, X, groups):
        return self.predict(X) + np.array([self.u.get(g, 0.0) for g in groups])


def fit_predict(spec: dict, train, valid, prior) -> np.ndarray:
    """Fit one ML specification on `train` and predict `valid` shares."""
    uns_tr, uns_va = uniform_swing(train, prior), uniform_swing(valid, prior)
    X_tr, X_va = design_matrix(train, uns_tr), design_matrix(valid, uns_va)
    y_tr = np.array([r["share"] for r in train]) - uns_tr   # residual target
    kind = spec["model"]
    if kind == "ridge":
        corr = Ridge(spec["alpha"]).fit(X_tr, y_tr).predict(X_va)
    elif kind == "ridge_council":
        m = RidgeCouncil(spec["alpha"], spec["k"]).fit_with_groups(
            X_tr, y_tr, [r["council"] for r in train])
        corr = m.predict_groups(X_va, [r["council"] for r in valid])
    elif kind == "lightgbm":
        # LightGBM's native API: its scikit-learn wrapper would need
        # scikit-learn, which is not a project dependency.
        import lightgbm as lgb
        params = {"objective": "regression", "learning_rate": 0.05,
                  "num_leaves": spec["num_leaves"], "min_data_in_leaf": 50,
                  "bagging_fraction": 0.8, "bagging_freq": 1,
                  "feature_fraction": 0.8, "seed": SEED,
                  "deterministic": True, "num_threads": 1, "verbose": -1}
        booster = lgb.train(params, lgb.Dataset(X_tr, y_tr),
                            num_boost_round=spec["n_estimators"])
        corr = booster.predict(X_va)
    else:
        raise ValueError(kind)
    return renormalise(valid, uns_va + corr)


ML_GRID = (
    [{"model": "ridge", "alpha": a} for a in (1, 10, 100, 1000)]
    + [{"model": "ridge_council", "alpha": a, "k": k}
       for a in (10, 100) for k in (10, 50, 200)]
    # 1000 and 2000 rounds added after the first run picked 500, the edge
    # of the original grid. Still validation-only model selection.
    + [{"model": "lightgbm", "num_leaves": nl, "n_estimators": ne}
       for nl in (7, 15, 31) for ne in (200, 500, 1000, 2000)]
)


# --- scoring ---------------------------------------------------------------------------

def mae(rows, pred, mask=None) -> float:
    y = np.array([r["share"] for r in rows])
    m = np.ones(len(rows), bool) if mask is None else mask
    return float(np.abs(pred[m] - y[m]).mean())


def score(rows, pred) -> dict:
    cold = np.array([bool(r["cold_start"]) for r in rows])
    out = {"mae": round(mae(rows, pred), 4),
           "mae_cold_start": round(mae(rows, pred, cold), 4),
           "mae_warm": round(mae(rows, pred, ~cold), 4)}
    ref_cold = np.array([r["party"] == "REF" and bool(r["cold_start"])
                         for r in rows])
    if ref_cold.any():
        out["mae_REF_cold"] = round(mae(rows, pred, ref_cold), 4)
    for p in PARTIES:
        m = np.array([r["party"] == p for r in rows])
        if m.any():
            out[f"mae_{p}"] = round(mae(rows, pred, m), 4)
    return out


def council_bootstrap_diff(rows, pred_a, pred_b, n=2000) -> list[float]:
    """95% CI for MAE(a) - MAE(b), resampling councils (contests in a
    council share shocks, so councils are the independent units)."""
    y = np.array([r["share"] for r in rows])
    ea, eb = np.abs(pred_a - y), np.abs(pred_b - y)
    by = defaultdict(list)
    for i, r in enumerate(rows):
        by[r["council"]].append(i)
    groups = list(by.values())
    sa = np.array([ea[g].sum() for g in groups])
    sb = np.array([eb[g].sum() for g in groups])
    cnt = np.array([len(g) for g in groups])
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(n):
        k = rng.integers(0, len(groups), len(groups))
        draws.append((sa[k].sum() - sb[k].sum()) / cnt[k].sum())
    return [round(float(np.percentile(draws, q)), 4) for q in (2.5, 97.5)]


# --- the validation run ----------------------------------------------------------------

def _label(spec: dict) -> str:
    return spec["model"] + "".join(f"_{k}{v}" for k, v in spec.items()
                                   if k != "model")


def stage_validate() -> None:
    rows = load_units()
    train = [r for r in rows if r["round"] in TRAIN_ROUNDS]
    valid = [r for r in rows if r["round"] == VALID_ROUND]
    prior = cold_start_prior(train)

    results, preds = {}, {}
    for name, fn in BASELINES.items():
        preds[name] = fn(valid, prior)
        results[name] = {"family": "baseline", **score(valid, preds[name])}
    for spec in ML_GRID:
        name = _label(spec)
        preds[name] = fit_predict(spec, train, valid, prior)
        results[name] = {"family": "ml", "spec": spec,
                         **score(valid, preds[name])}
        print(name, results[name]["mae"], flush=True)

    best_base = min((n for n in results if results[n]["family"] == "baseline"),
                    key=lambda n: results[n]["mae"])
    best_ml = min((n for n in results if results[n]["family"] == "ml"),
                  key=lambda n: results[n]["mae"])
    diff_ci = council_bootstrap_diff(valid, preds[best_base], preds[best_ml])
    # H2's no-news reference (design amendment A1): the strongest no-news
    # model on Reform cold-start rows, whichever family it comes from, so
    # news must beat the best opponent rather than correct a weak one.
    h2_m0 = min(results, key=lambda n: results[n]["mae_REF_cold"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "validation_results.json").write_text(json.dumps({
        "train_rounds": TRAIN_ROUNDS, "valid_round": VALID_ROUND,
        "n_train": len(train), "n_valid": len(valid),
        "results": results}, indent=2) + "\n")
    (OUT_DIR / "selected_config.json").write_text(json.dumps({
        "status": "H1 freeze: chosen on 2019-2023 validation only; refit on "
                  "all three training rounds before the single 2025 test.",
        "best_baseline": best_base,
        "best_ml": {"name": best_ml, "spec": results[best_ml]["spec"]},
        "validation_mae": {best_base: results[best_base]["mae"],
                           best_ml: results[best_ml]["mae"]},
        "validation_gain_pp": round(results[best_base]["mae"]
                                    - results[best_ml]["mae"], 4),
        "validation_gain_ci95_council_bootstrap": diff_ci,
        "h2_m0": {"name": h2_m0,
                  "spec": results[h2_m0].get("spec"),
                  "validation_mae_REF_cold": results[h2_m0]["mae_REF_cold"],
                  "selected_ml_mae_REF_cold": results[best_ml]["mae_REF_cold"]},
        "features": FEATURES, "seed": SEED}, indent=2) + "\n")
    print(f"best baseline {best_base} {results[best_base]['mae']}; "
          f"best ML {best_ml} {results[best_ml]['mae']}; gain CI {diff_ci}")


if __name__ == "__main__":
    {"validate": stage_validate}[sys.argv[1]]()
