"""Does the news layer know which ward it is looking at?

    PYTHONPATH=src .venv/bin/python -m news_features.ward_resolution_diagnostic

## Why this exists

The identity placebo settled that the frozen news specification loses to six
party indicator switches that read no articles at all: on the 2026 holdout the
switches score +0.8342 against the news layer's +0.2404, and adding the news
features on top of the switches buys +0.0162 - a fifteenth of what the design
can resolve.

That result has exactly one honest reading. A party indicator is constant for
a party across every contest it stands in, so anything it can explain is a
per-party constant. The news layer lost because *its features are also very
close to per-party constants*: 64.3 per cent of the variance in
``net_portrayal_share`` at 90-31 days separates parties rather than elections,
and 86.3 per cent at 180-91 days.

So there is precisely one way for news to beat a party name, and it is not a
better model. The feature has to vary along an axis the indicator cannot
represent. There are two such axes and only one of them is worth anything:

1. **Between wards inside one election.** A party indicator gives Reform the
   same value in Woking South and in Caterham Valley. If news can say those
   two contests differed, no indicator can ever match it.
2. Between elections for one party - currently 14 to 36 per cent of the
   variance, which is thin.

This module measures axis 1, and it measures it on the feature table that has
the grain to show it: ``ward_party_election_features.parquet``, 6,323 rows of
one party per contest, rather than the 45 election-by-party cells the frozen
model was fitted on.

## What it reports, and why the number is credible

For every (arm, window) it takes each live news column, groups the rows by
(election, party), keeps the groups that carry any coverage at all, and asks
whether the column takes more than one value across the electoral areas in
that group. The share of covered groups that vary is the **ward resolution
rate**.

The arm split is the whole point. The hypothesis under test is that national
coverage cannot name a Surrey division and local coverage can, so the local
arm's rate should be the one that moves when the E5 backlog is judged. The
article attribution summary already puts a ceiling on it: of 1,632 corpus
articles, 1,538 (94.2 per cent) can be placed only to an election, and of the
94 that reach a named area, 89 sit in the 188-article local arm and about 5 in
the 1,444-article national arm.

## Why it is safe to run at any time

**It reads no outcome.** The ``target__`` and ``baseline__`` column families
are excluded by name and the exclusion is asserted, not assumed, because the
point of this diagnostic is to be runnable before deciding whether to spend
reviewer time - and a gate that costs a look at the answers is not a gate.
That also keeps it clear of the standing constraint on the 2026 holdout: a
count of distinct feature values says nothing about who won.

Run it once now to record the baseline, then again after each batch of E5
judgements. The number to watch is ``local``'s ward resolution rate. If
judging local articles does not move it, local coverage does not name wards
either, and the last route to a news effect is closed - which is itself a
reportable finding, and a much better one than silence.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

FEATURES = Path(
    "news_features/ward_party_election_features_v1/"
    "ward_party_election_features.parquet")
# The coverage ledger. It records, cell by cell, whether a ward-tier search
# was in scope, was attempted, succeeded, or is still waiting - which is what
# turns "the rate is zero" into a statement about why.
COVERAGE = Path("news_features/missing_news_representation.parquet")
OUT_DIR = Path("news_features/ward_resolution_v1")

# Column families that describe an outcome or a prediction of one. Named here
# so the exclusion is a declared list rather than a regex that might quietly
# stop matching when a column is renamed.
OUTCOME_PREFIXES = ("target", "baseline")

# The identity columns this diagnostic groups by. `electoral_area_id` is the
# ward, and it is the axis whose variation a party indicator cannot express.
GROUP_KEYS = ("election_id", "standardised_party_name")
WARD_KEY = "electoral_area_id"

# The six pre-registered disjoint windows. The cumulative snapshots are
# excluded: they are supersets of these, so counting both would report the
# same article twice under two names and inflate every rate.
CONFIRMATORY_WINDOWS = (
    "180_to_91_days", "90_to_31_days", "30_to_15_days",
    "14_to_8_days", "7_to_4_days", "final_72_hours",
)


def load_features() -> pd.DataFrame:
    """Read the ward-grain table and prove it carries no outcome to this run."""

    frame = pd.read_parquet(FEATURES)
    leaked = [column for column in frame.columns
              if column.split("__")[0] in OUTCOME_PREFIXES]
    # The columns exist in the file - dropping them here is what makes the
    # rest of this module safe to run without unsealing anything.
    return frame.drop(columns=leaked)


def news_columns(frame: pd.DataFrame) -> dict[tuple[str, str], list[str]]:
    """Live news columns, keyed by (arm, window).

    A column that is zero or absent in every row carries no information and
    would count as "does not vary across wards" in every group, dragging every
    rate towards zero for a reason that has nothing to do with wards. Those
    are dropped before anything is counted.
    """

    candidates = [column for column in frame.columns if column.count("__") >= 2]
    live_mask = (frame[candidates].fillna(0) != 0).any(axis=0)

    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for column in candidates:
        if not live_mask[column]:
            continue
        arm, window = column.split("__")[0], column.split("__")[1]
        if window not in CONFIRMATORY_WINDOWS:
            continue
        by_key[(arm, window)].append(column)
    return dict(by_key)


def ward_resolution(frame: pd.DataFrame,
                    columns_by_key: dict) -> dict[str, dict]:
    """Share of covered (election, party) groups whose value varies by ward.

    "Covered" means the column is non-zero somewhere in the group. A group
    with no coverage cannot vary, and including it would measure how empty
    the corpus is - which is a real problem but a different one, already
    counted elsewhere.
    """

    report: dict[str, dict] = {}
    for (arm, window), columns in sorted(columns_by_key.items()):
        covered = varying = 0
        wards_seen = []
        for column in columns:
            subset = frame.loc[frame[column].fillna(0) != 0,
                               [*GROUP_KEYS, WARD_KEY, column]]
            if subset.empty:
                continue
            for _, group in subset.groupby(list(GROUP_KEYS)):
                covered += 1
                wards_seen.append(group[WARD_KEY].nunique())
                # More than one distinct value across the wards of one
                # election-party group is exactly the thing a party indicator
                # cannot reproduce. One value is a per-party constant wearing
                # a ward's name.
                if group[column].nunique() > 1:
                    varying += 1
        report[f"{arm}/{window}"] = {
            "live_columns": len(columns),
            "covered_group_column_pairs": covered,
            "varying_across_wards": varying,
            "ward_resolution_rate": round(varying / covered, 4) if covered else None,
            "median_wards_per_covered_group": (
                float(pd.Series(wards_seen).median()) if wards_seen else None),
        }
    return report


def by_arm(report: dict[str, dict]) -> dict[str, dict]:
    """Roll the per-window rows up to one line per arm.

    The arm is the level the hypothesis lives at: local coverage should be
    able to name a ward and national coverage should not. Per-window rows are
    kept as well, because a rate that only moves in the far windows would mean
    the near-campaign blind spot is untouched.
    """

    totals: dict[str, dict] = defaultdict(
        lambda: {"covered_group_column_pairs": 0, "varying_across_wards": 0})
    for key, record in report.items():
        arm = key.split("/")[0]
        totals[arm]["covered_group_column_pairs"] += record[
            "covered_group_column_pairs"]
        totals[arm]["varying_across_wards"] += record["varying_across_wards"]
    for arm, record in totals.items():
        covered = record["covered_group_column_pairs"]
        record["ward_resolution_rate"] = (
            round(record["varying_across_wards"] / covered, 4)
            if covered else None)
    return dict(totals)


def ward_tier_ceiling() -> dict:
    """Why the rate is what it is, and the most judging could ever change.

    A zero rate has two very different explanations and they lead to opposite
    decisions. Either the ward-tier articles exist and are waiting on the E5
    review - in which case reviewer time buys the axis - or they were never
    collected, in which case no amount of reviewing can produce them.

    This reads the coverage ledger and separates the ward-tier cells by
    status, then by the granularity the cell is actually keyed at. The second
    split is the one that matters: a cell recorded against ``ELECTION_WIDE``
    reaches every ward of its election equally, so filling it adds
    election-level news and leaves the between-ward axis exactly where it was.
    """

    ledger = pd.read_parquet(COVERAGE)
    ward_tier = ledger[ledger["scope_classification"] == "ward_specific_local"]

    def split(rows: pd.DataFrame) -> dict:
        wide = rows["geographic_target_id"].astype(str).str.endswith(
            "ELECTION_WIDE")
        return {
            "cells": int(len(rows)),
            "keyed_to_a_named_ward": int((~wide).sum()),
            "keyed_election_wide": int(wide.sum()),
            "distinct_targets": int(rows["geographic_target_id"].nunique()),
        }

    by_status = {
        str(status): split(group)
        for status, group in ward_tier.groupby("coverage_status")
    }

    # The decisive quantity: how many wards a single (election, party) group
    # can carry. Variation across wards is arithmetically impossible when the
    # answer is one, no matter how many articles arrive.
    unlockable = ward_tier[ward_tier["coverage_status"].isin(
        ["pending_external_stage", "observed_news"])]
    wards_per_group = unlockable.groupby(
        ["election_id", "focal_party_id"])["geographic_target_id"].nunique()

    return {
        "ward_tier_cells": int(len(ward_tier)),
        "by_coverage_status": by_status,
        "unlockable_cells": int(len(unlockable)),
        "unlockable_election_party_groups": int(len(wards_per_group)),
        "wards_per_unlockable_group": {
            str(k): int(v) for k, v in
            wards_per_group.value_counts().sort_index().items()},
        "max_wards_in_any_unlockable_group": (
            int(wards_per_group.max()) if len(wards_per_group) else 0),
    }


def main() -> None:
    frame = load_features()
    columns_by_key = news_columns(frame)
    per_window = ward_resolution(frame, columns_by_key)
    per_arm = by_arm(per_window)
    ceiling = ward_tier_ceiling()

    payload = {
        "status": ("DIAGNOSTIC. Reads feature columns only; the target and "
                   "baseline families are dropped before anything is counted, "
                   "so this can be run before deciding to spend reviewer "
                   "time and without touching any outcome."),
        "feature_table": str(FEATURES),
        "rows": int(len(frame)),
        "contests": int(frame["contest_id"].nunique()),
        "electoral_areas": int(frame[WARD_KEY].nunique()),
        "confirmatory_windows_only": list(CONFIRMATORY_WINDOWS),
        "by_arm": per_arm,
        "by_arm_and_window": per_window,
        "ward_tier_ceiling": ceiling,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ward_resolution_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_findings(payload)
    print(f"-> {OUT_DIR}")


def write_findings(payload: dict) -> None:
    lines = [
        "# Does the news layer know which ward it is looking at?",
        "",
        f"**{payload['status']}**",
        "",
        f"Grain: {payload['rows']} party-contest rows across "
        f"{payload['contests']} contests and {payload['electoral_areas']} "
        "electoral areas. The frozen model was fitted on 45 election-by-party "
        "cells, so this table can show a distinction that one cannot.",
        "",
        "## The number that decides whether news can ever beat a party name",
        "",
        "A party indicator gives a party the same value in every contest it "
        "stands in. So the only variation it can never reproduce is variation "
        "*between wards inside one election*. The rate below is the share of "
        "covered (election, party) groups whose feature takes more than one "
        "value across that election's wards.",
        "",
        "| arm | covered group-column pairs | varying across wards | ward resolution rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for arm, record in sorted(payload["by_arm"].items()):
        rate = record["ward_resolution_rate"]
        lines.append(
            f"| {arm} | {record['covered_group_column_pairs']} | "
            f"{record['varying_across_wards']} | "
            f"{'-' if rate is None else f'{rate * 100:.1f}%'} |")

    lines += [
        "",
        "## Per arm and window",
        "",
        "Cumulative snapshots are excluded; they are supersets of these six "
        "windows and would count the same article twice.",
        "",
        "| arm / window | live columns | covered | varying | rate | median wards per group |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, record in sorted(payload["by_arm_and_window"].items()):
        rate = record["ward_resolution_rate"]
        wards = record["median_wards_per_covered_group"]
        lines.append(
            f"| {key} | {record['live_columns']} | "
            f"{record['covered_group_column_pairs']} | "
            f"{record['varying_across_wards']} | "
            f"{'-' if rate is None else f'{rate * 100:.1f}%'} | "
            f"{'-' if wards is None else f'{wards:.0f}'} |")

    ceiling = payload["ward_tier_ceiling"]
    lines += [
        "",
        "## Why the rate is zero, and the most any review could change it",
        "",
        "A zero rate has two explanations that lead to opposite decisions. "
        "Either the ward-tier articles exist and are waiting on the human E5 "
        "review, in which case reviewer time buys the axis; or they were "
        "never collected, in which case no amount of reviewing can produce "
        "them. The coverage ledger separates the two.",
        "",
        f"Ward-tier cells: **{ceiling['ward_tier_cells']}**",
        "",
        "| coverage status | cells | keyed to a named ward | keyed election-wide |",
        "| --- | ---: | ---: | ---: |",
    ]
    for status, record in sorted(ceiling["by_coverage_status"].items()):
        lines.append(
            f"| {status} | {record['cells']} | "
            f"{record['keyed_to_a_named_ward']} | "
            f"{record['keyed_election_wide']} |")

    lines += [
        "",
        f"Cells that carry news or could still receive it: "
        f"**{ceiling['unlockable_cells']}**, spread over "
        f"{ceiling['unlockable_election_party_groups']} (election, party) "
        "groups.",
        "",
        f"**Wards per unlockable group: "
        f"{ceiling['wards_per_unlockable_group']}** - the maximum is "
        f"{ceiling['max_wards_in_any_unlockable_group']}.",
        "",
        "That last line is the one that decides it. Variation across wards "
        "inside an (election, party) group is arithmetically impossible when "
        "the group carries one ward, however many articles arrive. If every "
        "unlockable cell is keyed election-wide, judging them adds "
        "election-level news and leaves the between-ward axis exactly where "
        "it is now.",
        "",
        "Re-run this after any change to the corpus. The number to watch is "
        "``max_wards_in_any_unlockable_group``: until it exceeds one, the "
        "between-ward comparison cannot be run at all, and the news layer has "
        "no axis available to it that a party indicator does not already "
        "cover.",
        "",
    ]
    (OUT_DIR / "ward_resolution_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
