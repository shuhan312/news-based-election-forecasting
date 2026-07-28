"""Report the candidate-level cohort and its chronological fold assignment.

Purpose
-------
The party-share cohort contains no rows from 7 May 2026, so the supervisor's
primary holdout could not be scored.  The candidate-level release fixes that.
This script is the evidence: it reads the published contract and reports, per
election, how many rows are eligible, how they split by contest structure, how
many are Reform UK or UKIP, and which fold each election falls in under both
candidate splits.

It fits nothing and predicts nothing.  It exists so the cohort claim can be
checked from a file rather than taken on trust.

Usage (from the IRP repository root):

    PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
      surrey-election-no-news-baseline/scripts/build_candidate_cohort_report.py

Regenerate the input contract first if required:

    PYTHONPATH=surrey-election-extractor .venv/bin/python \
      surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from no_news_baseline.candidate_cohort import (
    assert_one_to_one_candidate_release,
    group_by_contest,
    is_within_candidate_cohort,
    reform_census,
    stratify_by_structure,
)
from no_news_baseline.supervisor_alignment import SPLITS, assign_fold


CONTRACT = Path(
    "surrey-election-extractor/outputs/no_news_candidate_contests"
)
FEATURES = CONTRACT / "no_news_candidate_contest_features.json"
TARGETS = CONTRACT / "no_news_candidate_contest_targets.json"
OUT = Path("surrey-election-no-news-baseline/outputs/candidate_cohort")

# The supervisor's primary holdout is a date, not an election name: every
# event polled on 7 May 2026 belongs to it, including the Warlingham
# by-election held the same day.  Keeping it as a date is what stops one
# same-day event being trained on while another is tested.
PRIMARY_HOLDOUT_DATE = date(2026, 5, 7)
SECONDARY_HOLDOUT_DATE = date(2026, 7, 7)


def _election_date(value: str) -> date:
    """Parse the release's published date format.

    The extractor publishes human-readable dates such as ``7 May 2026``; ISO
    is accepted too so the script keeps working if that ever changes.
    """

    for date_format in ("%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported election date: {value!r}")


def main() -> None:
    features = json.loads(FEATURES.read_text())["rows"]
    targets = json.loads(TARGETS.read_text())["rows"]
    assert_one_to_one_candidate_release(features, targets)

    cohort = [row for row in features if is_within_candidate_cohort(row)]

    # --- per-election summary --------------------------------------------
    per_election: dict[str, dict[str, object]] = {}
    for row in cohort:
        election_id = str(row["election_id"])
        entry = per_election.setdefault(
            election_id,
            {
                "election_id": election_id,
                "election_date": str(row["election_date"]),
                "election_type": row["election_type"],
                "contest_structure": str(row["contest_structure"]),
                "candidate_rows": 0,
                "contests": set(),
                "reform_uk_rows": 0,
                "ukip_rows": 0,
                "rows_with_approved_previous_share": 0,
            },
        )
        entry["candidate_rows"] += 1
        entry["contests"].add((str(row["election_id"]), str(row["division_id"])))
        if row.get("is_reform_uk"):
            entry["reform_uk_rows"] += 1
        if row.get("is_ukip"):
            entry["ukip_rows"] += 1
        if row.get("previous_party_vote_share") is not None:
            entry["rows_with_approved_previous_share"] += 1
        # A single election can mix structures; record that honestly rather
        # than letting the last row seen win.
        if entry["contest_structure"] != str(row["contest_structure"]):
            entry["contest_structure"] = "mixed"

    for entry in per_election.values():
        entry["contests"] = len(entry["contests"])
        election_day = _election_date(str(entry["election_date"]))
        entry["holdout_role"] = (
            "primary_holdout_7_may_2026"
            if election_day == PRIMARY_HOLDOUT_DATE
            else "secondary_holdout_7_july_2026"
            if election_day == SECONDARY_HOLDOUT_DATE
            else "development"
        )
        for split in SPLITS:
            entry[f"fold_{split.split_id}"] = assign_fold(election_day, split)

    ordered = sorted(
        per_election.values(),
        key=lambda entry: (_election_date(str(entry["election_date"])), entry["election_id"]),
    )

    # --- headline counts --------------------------------------------------
    strata = stratify_by_structure(features)
    holdout_rows = [
        entry for entry in ordered if entry["holdout_role"].startswith("primary")
    ]
    summary = {
        "candidate_rows_published": len(features),
        "candidate_rows_in_cohort": len(cohort),
        "contests_in_cohort": len(group_by_contest(cohort)),
        "single_member_rows": len(strata.get("single_member", [])),
        "multi_member_rows": len(strata.get("multi_member", [])),
        "primary_holdout_events": len(holdout_rows),
        "primary_holdout_rows": sum(
            int(entry["candidate_rows"]) for entry in holdout_rows
        ),
        "primary_holdout_reform_rows": sum(
            int(entry["reform_uk_rows"]) for entry in holdout_rows
        ),
        "reform_uk_rows_total": sum(
            int(entry["reform_uk_rows"]) for entry in ordered
        ),
        "reform_uk_rows_before_2026": sum(
            int(entry["reform_uk_rows"])
            for entry in ordered
            if _election_date(str(entry["election_date"])).year < 2026
        ),
        "ukip_rows_total": sum(int(entry["ukip_rows"]) for entry in ordered),
    }

    # --- Reform rows per fold --------------------------------------------
    # The brief requires "the number of Reform observations used in each
    # fold".  Reported for both candidate splits, because that count is
    # exactly what distinguishes them.
    reform_by_fold: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        folds: dict[str, int] = defaultdict(int)
        for entry in ordered:
            folds[str(entry[f"fold_{split.split_id}"])] += int(entry["reform_uk_rows"])
        reform_by_fold[split.split_id] = {
            "description": split.description,
            **{fold: folds[fold] for fold in ("train", "validation", "test")},
        }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "candidate_cohort_report.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "reform_rows_by_fold": reform_by_fold,
                "per_election": ordered,
                "reform_census": reform_census(features),
            },
            indent=2,
        )
        + "\n"
    )

    # --- console summary --------------------------------------------------
    print(f"cohort rows: {summary['candidate_rows_in_cohort']} / "
          f"{summary['candidate_rows_published']} published")
    print(f"contests: {summary['contests_in_cohort']}  "
          f"(single-member rows {summary['single_member_rows']}, "
          f"multi-member rows {summary['multi_member_rows']})")
    print(f"primary holdout 7 May 2026: {summary['primary_holdout_events']} events, "
          f"{summary['primary_holdout_rows']} rows, "
          f"{summary['primary_holdout_reform_rows']} Reform UK")
    print(f"Reform UK rows before 2026: {summary['reform_uk_rows_before_2026']}")
    print()
    for split_id, folds in reform_by_fold.items():
        print(f"Reform rows by fold [{split_id}] - {folds['description']}")
        print(f"    train {folds['train']} | validation {folds['validation']} "
              f"| test {folds['test']}")
    print()
    header = f"{'election':58s} {'rows':>5s} {'cont':>5s} {'RefUK':>6s} {'struct':>14s}"
    print(header)
    print("-" * len(header))
    for entry in ordered:
        print(
            f"{entry['election_id'][:58]:58s} "
            f"{entry['candidate_rows']:5d} "
            f"{entry['contests']:5d} "
            f"{entry['reform_uk_rows']:6d} "
            f"{entry['contest_structure']:>14s}"
        )
    print(f"\nwritten: {OUT / 'candidate_cohort_report.json'}")


if __name__ == "__main__":
    main()
