"""Recompute every number in the descriptive targets annex.

    PYTHONPATH=src .venv/bin/python -m news_modelling.descriptive_2026_targets

The annex (`unblinding_2026_v1/descriptive_targets_annex.md`) reports
per-party MAE, seat totals, fully-correct wards, Reform's rank and
top-two record and the deciding-margin error. Those figures were first
produced by an ad-hoc script during analysis; this module makes each of
them reproducible from the repository, per the course rule that all code
required to generate an output must be tracked. It reads the same
already-unblinded holdout file the one-time scorer read, changes no
model and writes nothing - it prints the accounting so any figure in
the annex can be re-derived with one command.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

HOLDOUT = Path(
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "holdout_predictions.csv"
)


def load_2026_rows() -> list[dict]:
    with HOLDOUT.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle)
                if row["election_id"].startswith("surrey-county-council-2026")]
    for row in rows:
        row["pred"] = float(row["predicted_vote_share"])
        row["obs"] = float(row["observed_vote_share"])
    return rows


def per_party_mae(rows: list[dict]) -> list[tuple[str, int, float]]:
    errors: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        errors[row["standard_party_name"]].append(abs(row["pred"] - row["obs"]))
    return sorted(
        ((party, len(v), sum(v) / len(v)) for party, v in errors.items()),
        key=lambda item: -item[1],
    )


def seat_totals(rows: list[dict]) -> list[tuple[str, int, int]]:
    predicted, actual = Counter(), Counter()
    for row in rows:
        if row["predicted_elected"] == "True":
            predicted[row["standard_party_name"]] += 1
        if row["observed_elected"] == "True":
            actual[row["standard_party_name"]] += 1
    return sorted(
        ((party, predicted[party], actual[party])
         for party in set(predicted) | set(actual)),
        key=lambda item: -item[2],
    )


def contests_fully_correct(rows: list[dict]) -> tuple[int, int]:
    contests: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        contests[(row["election_id"], row["division_id"])].append(row)
    correct = sum(
        1 for contest in contests.values()
        if {r["candidate_contest_id"] for r in contest
            if r["predicted_elected"] == "True"}
        == {r["candidate_contest_id"] for r in contest
            if r["observed_elected"] == "True"}
    )
    return correct, len(contests)


def reform_block(rows: list[dict]) -> dict:
    reform = [row for row in rows if row["is_reform_uk"] == "True"]
    return {
        "candidates": len(reform),
        "mean_predicted_share":
            round(sum(r["pred"] for r in reform) / len(reform), 1),
        "mean_observed_share":
            round(sum(r["obs"] for r in reform) / len(reform), 1),
        "rank_exactly_right":
            sum(1 for r in reform
                if r["predicted_rank"] == r["observed_rank"]),
        "predicted_top_two":
            sum(1 for r in reform if int(r["predicted_rank"]) <= 2),
        "observed_top_two":
            sum(1 for r in reform if int(r["observed_rank"]) <= 2),
    }


def deciding_margin_mae(rows: list[dict]) -> tuple[float, int]:
    """Error of the second-seat-versus-third-place gap, per two-seat ward."""

    contests: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        contests[(row["election_id"], row["division_id"])].append(row)
    errors = []
    for contest in contests.values():
        if len(contest) < 3:
            continue
        by_pred = sorted(contest, key=lambda r: -r["pred"])
        by_obs = sorted(contest, key=lambda r: -r["obs"])
        predicted_gap = by_pred[1]["pred"] - by_pred[2]["pred"]
        observed_gap = by_obs[1]["obs"] - by_obs[2]["obs"]
        errors.append(abs(predicted_gap - observed_gap))
    return sum(errors) / len(errors), len(errors)


def main() -> None:
    rows = load_2026_rows()

    print("Per-party baseline MAE:")
    for party, n, mae in per_party_mae(rows)[:7]:
        print(f"  {party:28s} n={n:3d} MAE={mae:.2f}")

    print("\nSeats predicted vs actual:")
    for party, predicted, actual in seat_totals(rows):
        if predicted + actual > 2:
            print(f"  {party:28s} pred={predicted:3d} actual={actual:3d}")

    correct, total = contests_fully_correct(rows)
    print(f"\nContests with BOTH seats exactly right: {correct}/{total}")

    reform = reform_block(rows)
    print(f"\nReform ({reform['candidates']} candidates): mean share "
          f"pred {reform['mean_predicted_share']}% vs actual "
          f"{reform['mean_observed_share']}%")
    print(f"  rank exactly right: {reform['rank_exactly_right']}/"
          f"{reform['candidates']} | predicted top-2 "
          f"{reform['predicted_top_two']} vs actual top-2 "
          f"{reform['observed_top_two']}")

    margin, contests = deciding_margin_mae(rows)
    print(f"\nWinning-margin (2nd vs 3rd) MAE: {margin:.2f} pts "
          f"over {contests} contests")


if __name__ == "__main__":
    main()
