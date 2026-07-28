"""Evaluation for the candidate-level model, to the brief's metric list.

The brief asks for candidate vote-share MAE and RMSE, Reform UK versions of
both, rank correlation, Reform UK predicted-rank accuracy, winner accuracy,
top-N seat-allocation accuracy, party seat-total absolute error, and results
broken down by election, by principal election versus by-election, by party
and for Reform UK specifically. All of those are here.

Brier score, log loss and calibration are deliberately absent: they need a
predicted probability of election, which the share model does not produce.
They arrive with the probability model rather than being faked from a rank.

Two rules the module exists to enforce
--------------------------------------
**Contest-level uncertainty.** The brief: "Bootstrap uncertainty at the
contest level rather than treating every candidate row as statistically
independent." Candidates in one contest are not independent - their shares
sum to 100, so one candidate's error is mechanically another's. Resampling
rows would therefore report an interval several times too narrow. Every
interval here resamples whole contests.

**No pooled headline across contest structures.** A single-member contest
averages 4.6 candidates and 22.65 per cent per candidate; a two-member ward
averages 10.4 and 9.75. An MAE of 4.9 on the second is worse in relative
terms than 8.3 on the first, so a pooled figure would flatter the multi-member
holdout. ``evaluate`` always returns the structure breakdown alongside the
pooled number, and every share metric carries the mean observed share it
should be read against.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from math import sqrt

import numpy as np


# Fixed so an interval is reproducible from the bundle alone. The brief
# requires a random seed to be recorded in architecture.json; this is the
# evaluation half of that.
BOOTSTRAP_SEED = 20260728
BOOTSTRAP_RESAMPLES = 2000


def _scored(records: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Rows with both a prediction and an observed outcome."""

    return [
        row
        for row in records
        if row.get("predicted_vote_share") is not None
        and row.get("observed_vote_share") is not None
    ]


# --------------------------------------------------------------------------
# Share error
# --------------------------------------------------------------------------


def share_metrics(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """MAE, RMSE and the scale they must be read against.

    ``mean_observed_share`` and ``relative_mae`` are not decoration. Absolute
    error is not comparable between contest structures, and reporting MAE
    without the mean it sits on invites exactly the misreading this project
    is most exposed to: that the two-member 2026 holdout is predicted better
    than 2021 because its MAE is half the size.
    """

    rows = _scored(records)
    if not rows:
        return {"rows": 0, "mae": None, "rmse": None,
                "mean_observed_share": None, "relative_mae": None}

    errors = np.array([float(row["predicted_vote_share"]) - float(row["observed_vote_share"])
                       for row in rows])
    observed = np.array([float(row["observed_vote_share"]) for row in rows])
    mae = float(np.mean(np.abs(errors)))
    mean_observed = float(np.mean(observed))

    return {
        "rows": len(rows),
        "mae": mae,
        "rmse": float(sqrt(np.mean(errors**2))),
        "median_absolute_error": float(np.median(np.abs(errors))),
        "mean_error": float(np.mean(errors)),
        "mean_observed_share": mean_observed,
        "relative_mae": (mae / mean_observed) if mean_observed else None,
    }


def equal_split_reference(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """The parameter-free floor: every candidate predicted an equal split.

    Included in every report because an MAE alone cannot say whether a model
    learned anything. On the relative-share scale a maximally-shrunk ridge
    converges to exactly this, so the gap between the two is the model's
    entire contribution.
    """

    rows = _scored(records)
    if not rows:
        return {"rows": 0, "mae": None, "improvement_over_equal_split": None}

    predicted = np.array([100.0 / float(row["candidate_count_in_contest"]) for row in rows])
    observed = np.array([float(row["observed_vote_share"]) for row in rows])
    reference_mae = float(np.mean(np.abs(predicted - observed)))
    model_mae = float(share_metrics(rows)["mae"])

    return {
        "rows": len(rows),
        "mae": reference_mae,
        "model_mae": model_mae,
        # Positive means the model beats an equal split; negative means it
        # does not, which is a result to report, not a bug to hide.
        "improvement_over_equal_split": (
            (reference_mae - model_mae) / reference_mae if reference_mae else None
        ),
    }


# --------------------------------------------------------------------------
# Rank and seats
# --------------------------------------------------------------------------


def _contests(rows: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], list]:
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for row in rows:
        grouped[(str(row["election_id"]), str(row["division_id"]))].append(row)
    return dict(grouped)


def _spearman(predicted: Sequence[float], observed: Sequence[float]) -> float | None:
    """Rank correlation within one contest.

    Written out rather than imported so the package's declared dependencies
    stay at numpy. Ties receive average ranks, which is the standard
    definition and matters here because published shares are rounded to whole
    percentages and ties are common.
    """

    if len(predicted) < 2:
        return None
    ranks_p = _average_ranks(predicted)
    ranks_o = _average_ranks(observed)
    centred_p = ranks_p - ranks_p.mean()
    centred_o = ranks_o - ranks_o.mean()
    denominator = sqrt(float(np.sum(centred_p**2) * np.sum(centred_o**2)))
    if denominator == 0.0:
        # Every value tied on one side: correlation is undefined, not zero.
        return None
    return float(np.sum(centred_p * centred_o) / denominator)


def _average_ranks(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    order = array.argsort()
    ranks = np.empty(len(array), dtype=float)
    ranks[order] = np.arange(1, len(array) + 1, dtype=float)
    # Average the ranks of tied values.
    for value in np.unique(array):
        mask = array == value
        if mask.sum() > 1:
            ranks[mask] = ranks[mask].mean()
    return ranks


def rank_metrics(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Mean within-contest rank correlation, and exact-rank agreement."""

    rows = [row for row in _scored(records) if row.get("observed_rank") is not None]
    if not rows:
        return {"contests": 0, "mean_rank_correlation": None, "exact_rank_accuracy": None}

    correlations: list[float] = []
    for contest_rows in _contests(rows).values():
        value = _spearman(
            [float(row["predicted_vote_share"]) for row in contest_rows],
            [float(row["observed_vote_share"]) for row in contest_rows],
        )
        if value is not None:
            correlations.append(value)

    exact = [
        int(row["predicted_rank"]) == int(row["observed_rank"])
        for row in rows
        if row.get("predicted_rank") is not None
    ]
    return {
        "contests": len(correlations),
        "mean_rank_correlation": float(np.mean(correlations)) if correlations else None,
        "exact_rank_accuracy": float(np.mean(exact)) if exact else None,
        "rank_rows": len(exact),
    }


def seat_metrics(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Winner accuracy, seat-set accuracy and party seat-total error.

    Three different questions that a single "accuracy" would blur:

    * ``winner_accuracy`` - was the top-ranked prediction actually elected?
    * ``seat_set_accuracy`` - did the predicted elected set match exactly?
      In a two-member ward these differ, and the brief asks for both a winner
      and a top-N seat measure.
    * ``party_seat_total_absolute_error`` - summed over parties within an
      election, the quantity a seat forecast is usually judged on.
    """

    rows = _scored(records)
    if not rows:
        return {"contests": 0, "winner_accuracy": None, "seat_set_accuracy": None}

    winner_hits: list[bool] = []
    set_hits: list[bool] = []
    for contest_rows in _contests(rows).values():
        predicted_top = min(
            (row for row in contest_rows if row.get("predicted_rank") is not None),
            key=lambda row: int(row["predicted_rank"]),
            default=None,
        )
        if predicted_top is not None:
            winner_hits.append(bool(predicted_top.get("observed_elected")))
        predicted_set = {
            str(row["candidate_contest_id"]) for row in contest_rows if row.get("predicted_elected")
        }
        observed_set = {
            str(row["candidate_contest_id"]) for row in contest_rows if row.get("observed_elected")
        }
        if observed_set:
            set_hits.append(predicted_set == observed_set)

    # Party seat totals, per election, then summed as an absolute error.
    by_election: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )
    for row in rows:
        entry = by_election[str(row["election_id"])][str(row["standard_party_name"])]
        entry[0] += int(bool(row.get("predicted_elected")))
        entry[1] += int(bool(row.get("observed_elected")))
    seat_errors = {
        election_id: sum(abs(predicted - observed) for predicted, observed in parties.values())
        for election_id, parties in by_election.items()
    }

    return {
        "contests": len(set_hits),
        "winner_accuracy": float(np.mean(winner_hits)) if winner_hits else None,
        "seat_set_accuracy": float(np.mean(set_hits)) if set_hits else None,
        "elected_row_accuracy": float(
            np.mean([bool(row.get("predicted_elected")) == bool(row.get("observed_elected"))
                     for row in rows])
        ),
        "party_seat_total_absolute_error_by_election": dict(sorted(seat_errors.items())),
        "party_seat_total_absolute_error": int(sum(seat_errors.values())),
    }


# --------------------------------------------------------------------------
# Contest-level bootstrap
# --------------------------------------------------------------------------


def bootstrap_contest_interval(
    records: Iterable[Mapping[str, object]],
    statistic: Callable[[Sequence[Mapping[str, object]]], float | None],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    percentiles: tuple[float, float] = (2.5, 97.5),
) -> dict[str, object]:
    """Resample whole contests, not rows, and return a percentile interval.

    Candidates within a contest are not independent: their shares sum to 100,
    so one candidate's over-prediction forces another's under-prediction.
    Resampling rows would treat those as separate pieces of evidence and
    report an interval far narrower than the data supports. Resampling
    contests keeps each contest's internal structure intact and counts it
    once, which is what the brief asks for.
    """

    rows = _scored(records)
    contests = list(_contests(rows).values())
    if len(contests) < 2:
        return {"contests": len(contests), "point_estimate": statistic(rows) if rows else None,
                "lower": None, "upper": None, "resamples": 0}

    rng = np.random.default_rng(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        drawn = rng.integers(0, len(contests), size=len(contests))
        sample = [row for index in drawn for row in contests[index]]
        value = statistic(sample)
        if value is not None:
            estimates.append(float(value))

    if not estimates:
        return {"contests": len(contests), "point_estimate": None,
                "lower": None, "upper": None, "resamples": 0}

    return {
        "contests": len(contests),
        "point_estimate": statistic(rows),
        "lower": float(np.percentile(estimates, percentiles[0])),
        "upper": float(np.percentile(estimates, percentiles[1])),
        "resamples": len(estimates),
        "seed": seed,
    }


def _mae(rows: Sequence[Mapping[str, object]]) -> float | None:
    value = share_metrics(rows)["mae"]
    return None if value is None else float(value)


# --------------------------------------------------------------------------
# Assembled reports
# --------------------------------------------------------------------------


def evaluate(
    records: Iterable[Mapping[str, object]],
    *,
    with_bootstrap: bool = True,
) -> dict[str, object]:
    """The full metric set, pooled and broken down as the brief requires."""

    rows = list(records)
    report: dict[str, object] = {
        "overall": {
            **share_metrics(rows),
            **rank_metrics(rows),
            **seat_metrics(rows),
            "equal_split_reference": equal_split_reference(rows),
        },
    }
    if with_bootstrap:
        report["overall"]["mae_contest_bootstrap_95"] = bootstrap_contest_interval(
            rows, _mae
        )

    # A pooled headline is never published alone: single-member and
    # multi-member contests are on different scales.
    report["by_contest_structure"] = {
        structure: {
            **share_metrics(group),
            **seat_metrics(group),
            "equal_split_reference": equal_split_reference(group),
        }
        for structure, group in _group(rows, "contest_structure").items()
    }
    report["by_election"] = {
        election_id: {
            **share_metrics(group),
            **rank_metrics(group),
            **seat_metrics(group),
            "equal_split_reference": equal_split_reference(group),
        }
        for election_id, group in _group(rows, "election_id").items()
    }
    # The brief asks for principal versus by-election separately, and this
    # split is where the model's weakness shows.
    report["by_election_type"] = {
        label: {**share_metrics(group), **seat_metrics(group),
                "equal_split_reference": equal_split_reference(group)}
        for label, group in _group_by(
            rows,
            lambda row: "by_election"
            if "by-election" in str(row["election_id"])
            else "principal_election",
        ).items()
    }
    report["by_party"] = {
        party: share_metrics(group)
        for party, group in _group(rows, "standard_party_name").items()
    }
    return report


def reform_report(
    records: Iterable[Mapping[str, object]],
    *,
    with_bootstrap: bool = True,
    small_sample_threshold: int = 30,
) -> dict[str, object]:
    """Reform UK results, reported separately as the brief requires.

    UKIP is reported beside Reform UK and never summed into it. The brief
    also requires a warning where a Reform estimate rests on a very small
    sample, so ``small_sample_warning`` is data rather than a sentence
    somebody has to remember to write.
    """

    rows = list(records)
    reform = [row for row in rows if row.get("is_reform_uk")]
    ukip = [row for row in rows if row.get("is_ukip")]

    report: dict[str, object] = {
        "reform_uk": {
            **share_metrics(reform),
            **rank_metrics(reform),
            **seat_metrics(reform),
            "equal_split_reference": equal_split_reference(reform),
            "by_election": {
                election_id: share_metrics(group)
                for election_id, group in _group(reform, "election_id").items()
            },
        },
        # Present for contrast only. A UKIP observation is never evidence
        # about Reform UK.
        "ukip_separately": share_metrics(ukip),
        "small_sample_warning": len(_scored(reform)) < small_sample_threshold,
        "small_sample_threshold": small_sample_threshold,
    }
    if with_bootstrap:
        report["reform_uk"]["mae_contest_bootstrap_95"] = bootstrap_contest_interval(
            reform, _mae
        )
    return report


def _group(
    rows: Sequence[Mapping[str, object]], field: str
) -> dict[str, list[Mapping[str, object]]]:
    return _group_by(rows, lambda row: str(row[field]))


def _group_by(
    rows: Sequence[Mapping[str, object]],
    key: Callable[[Mapping[str, object]], str],
) -> dict[str, list[Mapping[str, object]]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return dict(sorted(grouped.items()))
