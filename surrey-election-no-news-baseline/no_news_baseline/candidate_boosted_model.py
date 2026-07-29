"""Architecture B: gradient-boosted trees over the same candidate design.

The brief asks for "CatBoost, LightGBM or XGBoost" as the flexible comparator
against the interpretable and group-aware architectures, and sets the bar for
keeping it: "We only keep more complex models if they genuinely improve
performance on unseen elections."

LightGBM is used because it installs without a compiler on this environment
and its scikit-learn-style API keeps the fold code identical in shape to the
other two architectures. The dependency is declared in requirements.txt; if it
is unavailable the module raises a clear message rather than silently skipping
the architecture, because a missing comparator that fails quietly would let
the architecture comparison report two models as though three had been tried.

What is deliberately kept identical to Architectures A and C
------------------------------------------------------------
Same rows, same encoder, same target scale, same contest normalisation, same
seat allocation. A comparison between architectures is only a statement about
the architecture if nothing else changed, and four things changing at once is
how a tree model comes to look better for reasons that have nothing to do with
trees.

The one thing that differs is standardisation: it is switched off, because a
tree splits on order and gains nothing from centring or scaling, while leaving
it on would make the reported split thresholds unreadable.

Why the trees are kept small
----------------------------
The training folds hold roughly 1,100 rows against 107 encoded columns, and a
gradient-boosted model with default settings will fit that perfectly and
generalise badly. The declared configuration is deliberately conservative -
shallow trees, few leaves, a low learning rate with many rounds, and a minimum
leaf size that stops a leaf being carved out for a single rare party. These
are fixed in code before any fold is scored, and the number of boosting rounds
is the only quantity chosen from data, by early stopping inside each fold's
own inner validation split.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from no_news_baseline.candidate_cohort import (
    allocate_contest,
    contest_key,
    group_by_contest,
    normalise_within_contest,
)
from no_news_baseline.candidate_features import CandidateFeatureEncoder, target_vector
from no_news_baseline.candidate_share_model import (
    MIN_INNER_VALIDATION_ROWS,
    TARGET_SCALE,
    to_relative_share,
    to_vote_share,
)
from no_news_baseline.election_dates import parse_election_date


MODEL_ID = "lightgbm_candidate_share_v1"

# Pre-declared and fixed before any outer fold is scored. Conservative for a
# ~1,100-row training fold: shallow trees, a low learning rate, and a leaf
# minimum that prevents a leaf existing for one rare party's handful of rows.
BOOSTING_PARAMS: dict[str, object] = {
    "objective": "regression",
    "metric": "l1",
    "learning_rate": 0.03,
    "num_leaves": 15,
    "max_depth": 4,
    "min_child_samples": 25,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbose": -1,
    # Fixed so a rebuild reproduces the same trees; the brief requires the
    # seed to be recorded in architecture.json.
    "seed": 20260728,
    "deterministic": True,
    "force_row_wise": True,
}
MAX_BOOSTING_ROUNDS = 2000
EARLY_STOPPING_ROUNDS = 50
# Used only where a fold offers no usable inner validation split, in which
# case the round count is declared rather than chosen.
DEFAULT_BOOSTING_ROUNDS = 300


def boosting_params(seed: int | None = None) -> dict[str, object]:
    """A fresh copy of the parameters, with the seed optionally replaced.

    A copy every time because LightGBM mutates the dictionary it is handed;
    sharing one would let a fold silently change the parameters of the fold
    after it. The seed is the only value the configuration may override -
    the rest were declared before any outer fold was scored, and letting a
    run tune them from the command line would turn a fixed specification into
    a search.
    """

    params = dict(BOOSTING_PARAMS)
    if seed is not None:
        params["seed"] = int(seed)
    return params


def safe_feature_names(column_names: Sequence[str]) -> tuple[tuple[str, ...], dict[str, str]]:
    """Rename columns for LightGBM, keeping a map back to the real names.

    LightGBM rejects feature names containing characters it cannot put in
    JSON, and Surrey's registered party names are full of them: commas in
    "The Peace Party - Non-violence, Justice, Environment", an apostrophe in
    "Nork and Tattenhams Residents' Associations", quotation marks in
    'Christian Party "Proclaiming Christ's Lordship"'.

    The rename is applied only at the LightGBM boundary. Feature importance is
    translated back through the returned map before it is reported, so no
    output ever shows a mangled party name - which matters here, because the
    published party label is itself evidence in this project.
    """

    used: set[str] = set()
    safe: list[str] = []
    mapping: dict[str, str] = {}
    for position, name in enumerate(column_names):
        cleaned = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in name
        )
        # Collisions are possible once punctuation collapses to underscores,
        # so the column index guarantees uniqueness without hiding it.
        if cleaned in used or not cleaned:
            cleaned = f"{cleaned}_{position}"
        used.add(cleaned)
        safe.append(cleaned)
        mapping[cleaned] = name
    return tuple(safe), mapping


def _require_lightgbm():
    """Import LightGBM, or fail with an actionable message.

    Raising rather than returning None matters: a comparator that disappears
    quietly would let the architecture comparison report two architectures
    while claiming three were tried.
    """

    try:
        import lightgbm
    except ImportError as error:  # pragma: no cover - environment-dependent
        raise ImportError(
            "Architecture B needs LightGBM. Install it with "
            "`pip install lightgbm` (declared in requirements.txt). The "
            "architecture comparison must not silently drop a comparator."
        ) from error
    return lightgbm


@dataclass(frozen=True)
class BoostingChoice:
    """How many rounds were used, and whether the data chose that."""

    num_boost_round: int
    method: str
    inner_validation_dates: tuple[str, ...]
    inner_validation_rows: int
    best_score: float | None = None
    params: dict[str, object] = field(default_factory=lambda: dict(BOOSTING_PARAMS))


def select_boosting_rounds(
    train_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    *,
    seed: int | None = None,
    min_inner_rows: int = MIN_INNER_VALIDATION_ROWS,
) -> BoostingChoice:
    """Early-stop on the most recent qualifying polling day inside training.

    The same inner-validation discipline as the other architectures, and for
    the same reason: a round count chosen against the outer test fold would be
    leakage through a hyperparameter. Only one inner day is used rather than
    an average, because early stopping needs a single monotone validation
    curve to stop against.
    """

    lightgbm = _require_lightgbm()

    by_day: dict[str, list[Mapping[str, object]]] = {}
    for row in train_rows:
        day = parse_election_date(str(row["election_date"])).date().isoformat()
        by_day.setdefault(day, []).append(row)

    days = sorted(by_day)
    qualifying = [
        day
        for position, day in enumerate(days)
        if position > 0 and len(by_day[day]) >= min_inner_rows
    ]
    if not qualifying:
        return BoostingChoice(
            num_boost_round=DEFAULT_BOOSTING_ROUNDS,
            method="documented_default_no_inner_validation_day_large_enough",
            inner_validation_dates=(),
            inner_validation_rows=0,
        )

    inner_test_day = qualifying[-1]
    inner_train = [
        row
        for row in train_rows
        if parse_election_date(str(row["election_date"])).date().isoformat() < inner_test_day
    ]
    inner_test = by_day[inner_test_day]

    encoder = CandidateFeatureEncoder(standardise=False).fit(inner_train)
    x_train = encoder.transform(inner_train)
    x_test = encoder.transform(inner_test)
    y_train = to_relative_share(
        target_vector(inner_train, targets),
        [int(row["candidate_count_in_contest"]) for row in inner_train],
    )
    y_test = to_relative_share(
        target_vector(inner_test, targets),
        [int(row["candidate_count_in_contest"]) for row in inner_test],
    )

    safe_names, _ = safe_feature_names(x_train.column_names)
    booster = lightgbm.train(
        boosting_params(seed),
        lightgbm.Dataset(x_train.matrix, label=y_train,
                         feature_name=list(safe_names)),
        num_boost_round=MAX_BOOSTING_ROUNDS,
        valid_sets=[lightgbm.Dataset(x_test.matrix, label=y_test)],
        callbacks=[lightgbm.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)],
    )
    return BoostingChoice(
        # best_iteration is 0 when the first round already validated worst;
        # fall back to the declared default rather than training zero trees.
        num_boost_round=int(booster.best_iteration) or DEFAULT_BOOSTING_ROUNDS,
        method="inner_early_stopping_on_last_training_polling_day",
        inner_validation_dates=(inner_test_day,),
        inner_validation_rows=len(inner_test),
        best_score=float(booster.best_score["valid_0"]["l1"])
        if booster.best_score else None,
    )


@dataclass(frozen=True)
class BoostedFoldResult:
    split_id: str
    split_role: str
    train_rows: int
    test_rows: int
    train_reform_rows: int
    test_reform_rows: int
    boosting: BoostingChoice
    feature_importance: tuple[tuple[str, float], ...]
    predictions: tuple[dict[str, object], ...]


def fit_and_predict_boosted_fold(
    *,
    split_id: str,
    split_role: str,
    train_rows: Sequence[Mapping[str, object]],
    test_rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    num_boost_round: int | None = None,
    seed: int | None = None,
) -> BoostedFoldResult:
    """Fit Architecture B on one fold, in the same order as A and C."""

    lightgbm = _require_lightgbm()
    if not train_rows:
        raise ValueError(f"Split {split_id!r} has no training rows.")
    if not test_rows:
        raise ValueError(f"Split {split_id!r} has no test rows.")

    choice = (
        select_boosting_rounds(train_rows, targets, seed=seed)
        if num_boost_round is None
        else BoostingChoice(
            num_boost_round=int(num_boost_round),
            method="caller_supplied",
            inner_validation_dates=(),
            inner_validation_rows=0,
        )
    )

    # Standardisation off: trees split on order, and unscaled columns keep the
    # reported split thresholds readable.
    encoder = CandidateFeatureEncoder(standardise=False).fit(train_rows)
    x_train = encoder.transform(train_rows)
    x_test = encoder.transform(test_rows)
    train_counts = [int(row["candidate_count_in_contest"]) for row in train_rows]
    test_counts = [int(row["candidate_count_in_contest"]) for row in test_rows]
    y_train = to_relative_share(target_vector(train_rows, targets), train_counts)

    safe_names, safe_to_real = safe_feature_names(x_train.column_names)
    booster = lightgbm.train(
        boosting_params(seed),
        lightgbm.Dataset(x_train.matrix, label=y_train,
                         feature_name=list(safe_names)),
        num_boost_round=choice.num_boost_round,
    )
    predicted_relative = np.asarray(booster.predict(x_test.matrix), dtype=float)
    predicted_share_raw = to_vote_share(predicted_relative, test_counts)

    # --- identical contest handling to Architectures A and C --------------
    raw_by_id = {
        str(row["candidate_contest_id"]): float(value)
        for row, value in zip(test_rows, predicted_share_raw)
    }
    relative_by_id = {
        str(row["candidate_contest_id"]): float(value)
        for row, value in zip(test_rows, predicted_relative)
    }
    normalised_by_id: dict[str, float | None] = {}
    normalisation_status: dict[str, str] = {}
    allocation_by_id: dict[str, object] = {}

    for contest_rows in group_by_contest(test_rows).values():
        payload = [
            {"candidate_contest_id": str(row["candidate_contest_id"]),
             "predicted_candidate_vote_share": raw_by_id[str(row["candidate_contest_id"])]}
            for row in contest_rows
        ]
        for item in normalise_within_contest(payload):
            normalised_by_id[item.candidate_contest_id] = item.normalised_prediction
            normalisation_status[item.candidate_contest_id] = item.normalisation_status
        seats = contest_rows[0].get("analysis_number_of_seats")
        for item in allocate_contest(
            [{"candidate_contest_id": str(row["candidate_contest_id"]),
              "predicted_candidate_vote_share": normalised_by_id[str(row["candidate_contest_id"])]}
             for row in contest_rows],
            seats=None if seats is None else int(seats),
        ):
            allocation_by_id[item.candidate_contest_id] = item

    records: list[dict[str, object]] = []
    for row in test_rows:
        row_id = str(row["candidate_contest_id"])
        target = targets[row_id]
        observed = target.get("target_candidate_vote_share")
        observed_value = None if observed is None else float(observed)
        normalised = normalised_by_id.get(row_id)
        allocation = allocation_by_id[row_id]
        election_id, division_id = contest_key(row)
        error = (
            None if normalised is None or observed_value is None
            else normalised - observed_value
        )
        records.append(
            {
                "split_id": split_id, "split_role": split_role, "model_id": MODEL_ID,
                "candidate_contest_id": row_id, "election_id": election_id,
                "election_date": row["election_date"], "division_id": division_id,
                "contest_structure": row["contest_structure"],
                "standard_party_name": row["standard_party_name"],
                "is_reform_uk": bool(row.get("is_reform_uk")),
                "is_ukip": bool(row.get("is_ukip")),
                "candidate_count_in_contest": row["candidate_count_in_contest"],
                "analysis_number_of_seats": row["analysis_number_of_seats"],
                "predicted_relative_share": relative_by_id[row_id],
                "predicted_vote_share_unnormalised": raw_by_id[row_id],
                "predicted_vote_share": normalised,
                "normalisation_status": normalisation_status[row_id],
                "predicted_rank": allocation.predicted_rank,
                "predicted_rank_tied": allocation.predicted_rank_tied,
                "predicted_elected": allocation.predicted_elected,
                "allocation_status": allocation.allocation_status,
                "observed_vote_share": observed_value,
                "observed_rank": target.get("target_candidate_rank"),
                "observed_elected": target.get("target_candidate_elected") == "Yes",
                "error": error,
                "absolute_error": None if error is None else abs(error),
                "squared_error": None if error is None else error * error,
            }
        )

    # Gain importance rather than split count: how much each feature actually
    # improved the objective, not how often it happened to be chosen.
    gains = booster.feature_importance(importance_type="gain")
    # Translated back to the published column names, so no report ever shows
    # a party under a mangled label.
    importance = sorted(
        ((safe_to_real[name], float(gain))
         for name, gain in zip(booster.feature_name(), gains)),
        key=lambda item: -item[1],
    )

    return BoostedFoldResult(
        split_id=split_id, split_role=split_role,
        train_rows=len(train_rows), test_rows=len(test_rows),
        train_reform_rows=sum(1 for row in train_rows if row.get("is_reform_uk")),
        test_reform_rows=sum(1 for row in test_rows if row.get("is_reform_uk")),
        boosting=choice,
        feature_importance=tuple(importance[:25]),
        predictions=tuple(records),
    )


TARGET_TRANSFORMATION = TARGET_SCALE
