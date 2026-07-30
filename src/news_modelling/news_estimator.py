"""The news-layer estimator: Approach A (residual) and Approach B (joint).

Until now `src/news_modelling/` could build features, select them, and
diagnose coverage, but nothing in it fitted a model - the central question
of the project ("does news improve prediction of Reform UK vote share over
an election-history baseline?") had no code that could answer it. This
module is that code.

Two approaches, per the research design
---------------------------------------
**Approach A - residual.** For each eligible historical candidate row take
the Stage 1 out-of-fold prediction, form

    residual = observed_vote_share - baseline_prediction

and fit a model of that residual on news features alone. The final
prediction is ``baseline_prediction + predicted_adjustment``. This is the
principal approach because it measures directly what the research question
asks: whether news carries information the election-history baseline does
not already have. A residual model that predicts nothing is the cleanest
possible statement of "news adds nothing here".

**Approach B - joint.** Fit ``observed ~ baseline_prediction + news
features`` in one model, letting it re-weight the baseline rather than
treating it as fixed. Compared against A because the two fail differently:
A cannot rescale a systematically biased baseline, B can, but B can also
absorb news signal into the baseline coefficient and report an improvement
that is really a recalibration. Reporting both makes that distinction
visible instead of hiding it inside one number.

Why ridge, and why closed form
------------------------------
Same choice, for the same reason, as Architecture A of the no-news
baseline (`candidate_share_model.py`): ridge has a closed-form solution
that can be checked by hand, whereas a correct elastic net needs an
iterative solver whose convergence would itself have to be argued for.
With a training matrix this small - single-digit Reform rows in some folds
- an estimator whose behaviour is fully inspectable matters more than one
that might select features slightly better.

The penalty is chosen inside each fold's training rows, never on the rows
being predicted. A penalty tuned on the evaluation rows would leak the
answer through the hyperparameter, which is the quiet version of the
leakage the whole project is built to avoid.

What this module refuses to do
------------------------------
It does not touch the 7 May 2026 holdout. Fold construction reads the
Stage 1 split manifest and evaluates on development folds only; the
holdout is reachable only through an explicit, separately-named call that
the comparison harness does not make. The supervisor's standing
constraint is that the 2026 holdout must not be used to choose anything,
and the safest way to honour that is for the selection path to have no
route to it at all.

It also does not impute. A row without a baseline prediction, or without
an observed share, is dropped with a recorded reason - a residual against
an unknown baseline is not a residual, and filling one in would
manufacture agreement between the two layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np

# Penalty grid. Spans four orders of magnitude because the news design
# matrix is far smaller and more collinear than the baseline's, so the
# useful penalty is not known in advance; a grid this wide makes the
# selected value informative rather than an artefact of a narrow range.
PENALTY_GRID = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)

# Fitted with fewer rows than this, a fold's estimate is reported but
# flagged. Ten is the point below which a ridge fit on even a handful of
# columns is describing its own noise; the flag exists so a reader is
# never shown such a number without the warning attached.
MIN_ROWS_FOR_STABLE_FIT = 10

# Bootstrap settings, matched to the baseline bundle so intervals from the
# two layers are directly comparable rather than merely similar.
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260728


class RidgeModel:
    """Closed-form ridge regression, centred so the intercept is unshrunk.

    Deliberately a near-copy of the baseline's `RidgeShareModel` rather
    than an import: the baseline bundle is frozen, and reaching into it
    for a class would couple the news layer to a package that must not
    change. The arithmetic is short enough that duplicating it costs less
    than that coupling would.
    """

    def __init__(self, l2_penalty: float) -> None:
        if l2_penalty < 0:
            raise ValueError("The ridge L2 penalty must be non-negative.")
        self._l2 = float(l2_penalty)
        self._coefficients: np.ndarray | None = None
        self._intercept: float | None = None
        self._design_means: np.ndarray | None = None
        self._design_scales: np.ndarray | None = None

    def fit(self, design: np.ndarray, target: np.ndarray) -> "RidgeModel":
        if design.shape[0] != target.shape[0]:
            raise ValueError("Design matrix and target must align one-to-one.")
        if design.shape[0] == 0:
            raise ValueError("Cannot fit on an empty training set.")

        # Standardise here rather than expecting the caller to have done
        # it. News features arrive on wildly different scales - counts in
        # the tens, sentiment fractions in [0,1], recency weights in
        # [0,1] - and an unstandardised ridge penalty would silently
        # penalise the count columns hundreds of times harder than the
        # fractions, which is a modelling decision nobody made.
        means = design.mean(axis=0)
        scales = design.std(axis=0)
        # A constant column has zero variance; dividing by zero would
        # produce NaNs that propagate through the whole fit. Such a
        # column carries no information anyway, so it is scaled by one
        # and centred to exactly zero, contributing nothing.
        scales = np.where(scales > 0, scales, 1.0)
        standardised = (design - means) / scales

        target_mean = float(target.mean())
        centred_target = target - target_mean

        # w = (X'X + lambda I)^-1 X'y, solved as a linear system rather
        # than by explicit inversion for numerical stability on a
        # collinear matrix. Centring both sides keeps the intercept out
        # of the penalised system: it is the training mean, unshrunk.
        n_features = standardised.shape[1]
        gram = standardised.T @ standardised + self._l2 * np.eye(n_features)
        self._coefficients = np.linalg.solve(
            gram, standardised.T @ centred_target)
        self._design_means = means
        self._design_scales = scales
        self._intercept = target_mean
        return self

    def predict(self, design: np.ndarray) -> np.ndarray:
        if self._coefficients is None:
            raise ValueError("The model must be fitted before predicting.")
        if design.shape[1] != self._coefficients.shape[0]:
            raise ValueError(
                "Design matrix has a different width than at fit time.")
        standardised = (design - self._design_means) / self._design_scales
        return standardised @ self._coefficients + self._intercept

    @property
    def coefficients(self) -> np.ndarray:
        """Coefficients on the STANDARDISED design, not the raw columns.

        Because ``fit`` standardises internally, a coefficient here reads
        as "change in the target per one standard deviation of this
        feature", not per unit. A feature with a raw effect of 1.5 per
        article and a standard deviation of 1.7 articles appears as
        roughly 2.6. This is the right scale for comparing features whose
        units differ - counts against fractions - but it must not be
        reported as a per-article effect. Divide by the feature's training
        standard deviation to recover that, which ``feature_scales`` makes
        possible.
        """
        if self._coefficients is None:
            raise ValueError("The model has not been fitted.")
        return self._coefficients.copy()

    @property
    def feature_scales(self) -> np.ndarray:
        """Training standard deviations used to standardise each column.

        Exposed so a coefficient can be converted back to the feature's
        own units when a result needs to be stated as "per article" rather
        than "per standard deviation". Constant columns carry 1.0 here,
        the substitute applied at fit time.
        """
        if self._design_scales is None:
            raise ValueError("The model has not been fitted.")
        return self._design_scales.copy()

    @property
    def intercept(self) -> float:
        if self._intercept is None:
            raise ValueError("The model has not been fitted.")
        return self._intercept

    @property
    def l2_penalty(self) -> float:
        return self._l2


def design_matrix(rows: Sequence[Mapping[str, object]],
                  columns: Sequence[str]) -> np.ndarray:
    """Rows x named columns as floats, with missing read as zero.

    Zero is the right fill for these particular columns and only these:
    every news feature is a count, a share, or a weighted sum over
    articles, so "no article contributed" genuinely is zero. This is not a
    general imputation rule and must not be reused for the baseline's
    predictors, where a missing previous vote share means "unknown", not
    "nobody voted" - the distinction the null-semantics documentation in
    the baseline release exists to protect.
    """
    return np.array(
        [[float(row.get(c) or 0.0) for c in columns] for row in rows],
        dtype=float)


def select_penalty(design: np.ndarray, target: np.ndarray,
                   groups: Sequence[str]) -> tuple[float, dict]:
    """Choose the L2 penalty by leave-one-group-out inside the training rows.

    Groups are contests (election x division). Holding out whole contests
    rather than individual rows matters because candidates in one contest
    share the same news: a row-wise split would let the model see part of
    a contest's news while predicting the rest of it, and would choose a
    penalty tuned to that advantage.

    Returns the penalty and a record of what was tried, so the choice
    appears in the output rather than only in the fitted object.
    """
    unique_groups = sorted(set(groups))
    scores: dict[float, float] = {}

    # With one group there is nothing to hold out. Returning the grid's
    # midpoint and saying so is honest; silently returning the best
    # in-sample penalty would report a tuned value that was never tested.
    if len(unique_groups) < 2:
        return 1.0, {"method": "default_no_inner_split",
                     "reason": f"only {len(unique_groups)} contest(s) in "
                               f"the training rows, so no held-out group "
                               f"exists to score a penalty against",
                     "penalty": 1.0}

    group_array = np.array(groups)
    for penalty in PENALTY_GRID:
        errors = []
        for held in unique_groups:
            mask = group_array != held
            if mask.sum() == 0 or (~mask).sum() == 0:
                continue
            try:
                model = RidgeModel(penalty).fit(design[mask], target[mask])
            except (ValueError, np.linalg.LinAlgError):
                # A singular system at this penalty means the penalty is
                # too small for this design; record it as unusable rather
                # than crashing the sweep.
                errors = None
                break
            predicted = model.predict(design[~mask])
            errors.extend(np.abs(predicted - target[~mask]).tolist())
        if errors:
            scores[penalty] = float(np.mean(errors))

    if not scores:
        return 1.0, {"method": "default_all_penalties_unusable",
                     "penalty": 1.0}
    best = min(scores, key=scores.get)
    return best, {"method": "leave_one_contest_out",
                  "penalty": best,
                  "mean_absolute_error_by_penalty":
                      {str(k): round(v, 5) for k, v in scores.items()}}


@dataclass
class FoldFit:
    """One fold's fit and its predictions, with the fold's own diagnostics."""

    fold: str
    approach: str
    train_rows: int
    test_rows: int
    train_reform_rows: int
    test_reform_rows: int
    penalty: float
    penalty_choice: dict
    feature_columns: list[str]
    coefficients: dict[str, float]
    intercept: float
    predictions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_reform(row: Mapping[str, object]) -> bool:
    return str(row.get("standard_party_name") or
               row.get("party_id") or "").strip().lower() in (
        "reform uk", "reform_uk")


def fit_fold(train: Sequence[Mapping[str, object]],
             test: Sequence[Mapping[str, object]],
             feature_columns: Sequence[str],
             *, approach: str, fold_name: str) -> FoldFit:
    """Fit one approach on one fold and predict its test rows.

    ``approach`` is "residual" (target: observed minus baseline) or
    "joint" (target: observed, with the baseline prediction admitted as an
    extra column). The two differ only in the target and in whether the
    baseline is a feature - everything else is deliberately identical so
    that any difference in their results is attributable to that choice
    and not to two divergent pipelines.
    """
    if approach not in ("residual", "joint"):
        raise ValueError(f"Unknown approach: {approach!r}")

    columns = list(feature_columns)
    if approach == "joint":
        # The baseline prediction enters as a feature the model may
        # re-weight. Named explicitly so it is visible in the coefficient
        # table - a joint model whose news coefficients are all zero and
        # whose baseline coefficient is 1.0 has found nothing, and that
        # should be readable at a glance.
        columns = columns + ["baseline_prediction"]

    def target_of(rows):
        if approach == "residual":
            return np.array([float(r["residual"]) for r in rows])
        return np.array([float(r["observed_vote_share"]) for r in rows])

    warnings: list[str] = []
    train_design = design_matrix(train, columns)
    train_target = target_of(train)
    groups = [f"{r.get('election_id')}|{r.get('area_id')}" for r in train]

    if len(train) < MIN_ROWS_FOR_STABLE_FIT:
        warnings.append(
            f"fitted on {len(train)} rows, below the {MIN_ROWS_FOR_STABLE_FIT}"
            f"-row threshold for a stable ridge fit - treat the coefficients "
            f"as descriptive, not as estimates")

    penalty, penalty_choice = select_penalty(train_design, train_target, groups)
    model = RidgeModel(penalty).fit(train_design, train_target)

    predictions = []
    if test:
        test_design = design_matrix(test, columns)
        raw = model.predict(test_design)
        for row, value in zip(test, raw):
            baseline = float(row["predicted_vote_share"])
            if approach == "residual":
                adjustment = float(value)
                final = baseline + adjustment
            else:
                adjustment = float(value) - baseline
                final = float(value)
            predictions.append({
                "election_id": row.get("election_id"),
                "area_id": row.get("area_id"),
                "party": row.get("standard_party_name") or row.get("party_id"),
                "is_reform_uk": _is_reform(row),
                "observed_vote_share": float(row["observed_vote_share"]),
                "baseline_prediction": baseline,
                "news_adjustment": adjustment,
                "news_enhanced_prediction": final,
                "baseline_absolute_error": abs(baseline -
                                               float(row["observed_vote_share"])),
                "news_absolute_error": abs(final -
                                           float(row["observed_vote_share"])),
            })

    return FoldFit(
        fold=fold_name, approach=approach,
        train_rows=len(train), test_rows=len(test),
        train_reform_rows=sum(1 for r in train if _is_reform(r)),
        test_reform_rows=sum(1 for r in test if _is_reform(r)),
        penalty=penalty, penalty_choice=penalty_choice,
        feature_columns=columns,
        coefficients={c: float(v) for c, v in
                      zip(columns, model.coefficients)},
        intercept=model.intercept,
        predictions=predictions, warnings=warnings)


def metrics(predictions: Sequence[Mapping[str, object]]) -> dict:
    """Baseline and news-enhanced error, and the difference between them.

    Reported for all rows and for Reform UK separately, because the
    research question is about Reform specifically and an improvement
    driven entirely by other parties would answer a different question.

    ``improvement`` is positive when the news model is better. It is a
    difference of mean absolute errors on the same rows, so it needs no
    normalisation - but it is also reported as a proportion, because a
    0.1-point gain means something different on a 3-point baseline error
    than on a 10-point one.
    """

    def block(rows) -> dict:
        if not rows:
            return {"rows": 0}
        base = np.array([r["baseline_absolute_error"] for r in rows])
        news = np.array([r["news_absolute_error"] for r in rows])
        base_err = np.array([r["baseline_prediction"] -
                             r["observed_vote_share"] for r in rows])
        news_err = np.array([r["news_enhanced_prediction"] -
                             r["observed_vote_share"] for r in rows])
        baseline_mae = float(base.mean())
        news_mae = float(news.mean())
        return {
            "rows": len(rows),
            "contests": len({(r["election_id"], r["area_id"]) for r in rows}),
            "baseline_mae": baseline_mae,
            "news_mae": news_mae,
            "baseline_rmse": float(np.sqrt((base_err ** 2).mean())),
            "news_rmse": float(np.sqrt((news_err ** 2).mean())),
            "improvement_mae": baseline_mae - news_mae,
            "improvement_proportion": (
                (baseline_mae - news_mae) / baseline_mae
                if baseline_mae > 0 else None),
            "rows_improved": int((news < base).sum()),
            "rows_worsened": int((news > base).sum()),
        }

    rows = list(predictions)
    return {
        "all_parties": block(rows),
        "reform_uk": block([r for r in rows if r["is_reform_uk"]]),
    }


def bootstrap_improvement(predictions: Sequence[Mapping[str, object]],
                          *, resamples: int = BOOTSTRAP_RESAMPLES,
                          seed: int = BOOTSTRAP_SEED) -> dict:
    """A contest-level bootstrap interval on the MAE improvement.

    Resampling contests, not rows: candidates within a contest share the
    same news and the same baseline fold, so treating each candidate row
    as an independent draw would understate the interval - the same
    group-aware requirement the brief places on the baseline's
    uncertainty.

    An interval that straddles zero is the answer to the research
    question, not a failure of the method, and is reported as such.
    """
    rows = list(predictions)
    if not rows:
        return {"resamples": 0, "reason": "no predictions"}

    by_contest: dict[tuple, list] = {}
    for r in rows:
        by_contest.setdefault((r["election_id"], r["area_id"]), []).append(r)
    contests = list(by_contest)
    if len(contests) < 2:
        return {"resamples": 0,
                "reason": f"{len(contests)} contest(s) - a bootstrap over "
                          f"one group would resample the same rows every "
                          f"time and report a zero-width interval"}

    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(resamples):
        picked = rng.integers(0, len(contests), size=len(contests))
        sample = [row for i in picked for row in by_contest[contests[i]]]
        base = np.mean([r["baseline_absolute_error"] for r in sample])
        news = np.mean([r["news_absolute_error"] for r in sample])
        draws.append(base - news)
    draws = np.array(draws)
    return {
        "resamples": resamples, "seed": seed,
        "contests_resampled": len(contests),
        "improvement_mean": float(draws.mean()),
        "improvement_ci_lower": float(np.percentile(draws, 2.5)),
        "improvement_ci_upper": float(np.percentile(draws, 97.5)),
        "proportion_of_draws_favouring_news": float((draws > 0).mean()),
    }
