"""How many of the pending articles could actually become a feature.

    PYTHONPATH=src .venv/bin/python -m news_collection.measure_window_reach

Extraction is the expensive step and the pending corpus is 3,584 articles, so
the question worth answering before committing the budget is not "how many
articles are there" but "how many of them can reach a feature at all".

Two things have to be true for a pending article to affect the model, and
neither is about its content:

1. It needs a usable publication date. An article whose date could not be
   established cannot be placed in a window, so it cannot be aggregated into
   any feature however well it extracts. The date layer currently marks 5,026
   of 11,787 articles as having no date evidence, so this is not a rounding
   error.

2. Its date has to fall inside a window. The supervisor confirmed the existing
   six-window scheme on 2026-07-30. Those windows partition days 1-180, so a
   correctly dated pre-election article in the collection horizon should now
   reach exactly one principal window.

An older version of this diagnostic still used Prompt 2's three windows inside
30 days. Its output made days 31-180 look unusable even though the production
extraction and feature table already used them. This version imports the same
confirmed scheme as production so ``window_reach_assessment.json`` cannot
silently describe a different model.

Reported per election and per arm, because a headline percentage would hide
the case that matters most - the 2021 validation split, which currently has no
news at all and is the reason the extraction question is live.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from news_modelling.window_schemes import NEWS_ELECTION_DATES, ORIGINAL_EMAIL

REPO = Path(__file__).resolve().parents[2]
ELIGIBILITY = REPO / "news_collection/eligibility_assessment_v2.csv"
EFFECTIVE_DATES = REPO / "news_collection/effective_dates_v2.csv"
OUTPUT = REPO / "news_collection/window_reach_assessment.json"

# Articles that passed eligibility and have never been through extraction.
PENDING_STATUS = "pending_human_review"

# The date layer's verdict for a date solid enough to place an article in a
# window. Anything else - no evidence found, or still awaiting review - leaves
# the article unplaceable, which for this measurement is the same as unusable.
USABLE_DATE = "usable"


def load_pending() -> dict[str, dict]:
    """Pending articles keyed by id, carrying their election and arm."""

    with ELIGIBILITY.open(encoding="utf-8", newline="") as handle:
        return {
            row["article_id"]: {
                "election_id": row.get("election_id", ""),
                "arm": row.get("arm", ""),
            }
            for row in csv.DictReader(handle)
            if row.get("status") == PENDING_STATUS
        }


def load_dates() -> dict[str, dict]:
    """Effective dates keyed by article id, with the layer's status."""

    with EFFECTIVE_DATES.open(encoding="utf-8", newline="") as handle:
        return {
            row["article_id"]: {
                "effective_date": row.get("effective_date", ""),
                "date_status": row.get("date_status", ""),
            }
            for row in csv.DictReader(handle)
        }


def days_before_polling(published: str, election_id: str) -> int | None:
    """Complete days between publication and polling day.

    Positive means before polling. Zero means polling day itself and negative
    means after it - both are excluded from every window, the first because
    same-day coverage cannot be cleanly separated from early results reporting
    and the second because it is post-election material, which the brief rules
    out as leakage.
    """

    polling = NEWS_ELECTION_DATES.get(election_id)
    if polling is None or not published:
        return None
    try:
        return (polling - date.fromisoformat(published[:10])).days
    except ValueError:
        return None


def classify(days: int | None) -> str:
    """Which principal window a lag falls in, or why it falls in none.

    The six confirmed windows partition days 1 to 180. The two outside
    categories are kept apart rather than merged into
    "excluded": an article published after polling is a leakage exclusion and
    must stay excluded, whereas one published 181 days out is beyond the
    configured collection horizon.
    Collapsing them would hide a choice behind a filter.
    """

    if days is None:
        return "undated"
    if days <= 0:
        return "on_or_after_polling_day"

    for name, first, last in ORIGINAL_EMAIL.windows:
        if first <= days <= last:
            return name

    return "before_the_earliest_window"


def assess() -> dict:
    """Measure reach for every pending article."""

    pending = load_pending()
    dates = load_dates()

    # Totals, plus the same counts split by election and by arm. Built in one
    # pass so the breakdowns cannot disagree with the total.
    overall: Counter[str] = Counter()
    by_election: dict[str, Counter[str]] = defaultdict(Counter)
    by_arm: dict[str, Counter[str]] = defaultdict(Counter)
    lags_by_election: dict[str, list[int]] = defaultdict(list)

    for article_id, article in pending.items():
        election_id = article["election_id"]
        arm = article["arm"] or "unknown"
        record = dates.get(article_id, {})

        if record.get("date_status") != USABLE_DATE:
            # Distinguish "the date layer looked and found nothing" from "this
            # article was never seen by the date layer at all"; the second is a
            # pipeline gap rather than a property of the article.
            bucket = ("undated_no_evidence" if article_id in dates
                      else "undated_not_assessed")
        else:
            lag = days_before_polling(record.get("effective_date", ""),
                                      election_id)
            bucket = classify(lag)
            if lag is not None and lag > 0:
                lags_by_election[election_id].append(lag)

        overall[bucket] += 1
        by_election[election_id][bucket] += 1
        by_arm[arm][bucket] += 1

    window_names = {name for name, _first, _last in ORIGINAL_EMAIL.windows}

    def reachable(counts: Counter[str]) -> int:
        """Articles landing in a principal window - the ones that can matter."""

        return sum(count for bucket, count in counts.items()
                   if bucket in window_names)

    def summarise(counts: Counter[str]) -> dict:
        total = sum(counts.values())
        reach = reachable(counts)
        return {
            "pending": total,
            "reaches_a_window": reach,
            "share_reaching_a_window": round(reach / total, 4) if total else 0.0,
            "buckets": dict(counts.most_common()),
        }

    # Cumulative snapshots are nested rather than disjoint - everything in the
    # final day is also in the 7-day snapshot and the 30-day one - so they are
    # counted from the lags directly rather than summed from the buckets.
    cumulative = {}
    all_lags = [lag for lags in lags_by_election.values() for lag in lags]
    for name, depth in ORIGINAL_EMAIL.cumulative:
        cumulative[name] = sum(1 for lag in all_lags if 1 <= lag <= depth)

    return {
        "window_scheme": ORIGINAL_EMAIL.key,
        "pending_articles": len(pending),
        "overall": summarise(overall),
        "cumulative_snapshots": cumulative,
        "by_election": {election: summarise(counts)
                        for election, counts in sorted(by_election.items())},
        "by_arm": {arm: summarise(counts)
                   for arm, counts in sorted(by_arm.items())},
        "window_definitions": {
            name: [first, last]
            for name, first, last in ORIGINAL_EMAIL.windows
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure how many pending articles can reach a feature.")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()

    report = assess()

    if arguments.json:
        print(json.dumps(report, indent=2))
    else:
        overall = report["overall"]
        print(f"Pending articles: {report['pending_articles']:,}")
        print(f"Reaching a principal window: {overall['reaches_a_window']:,} "
              f"({overall['share_reaching_a_window']:.1%})\n")

        print("Where the pending articles sit:")
        for bucket, count in overall["buckets"].items():
            print(f"  {bucket:30s} {count:6,}")

        print("\nBy election:")
        for election, entry in report["by_election"].items():
            print(f"  {election:16s} {entry['reaches_a_window']:5,} of "
                  f"{entry['pending']:5,} "
                  f"({entry['share_reaching_a_window']:.1%})")

        print("\nBy arm:")
        for arm, entry in report["by_arm"].items():
            print(f"  {arm:16s} {entry['reaches_a_window']:5,} of "
                  f"{entry['pending']:5,} "
                  f"({entry['share_reaching_a_window']:.1%})")

        print("\nCumulative snapshots (nested, not additive):")
        for name, count in report["cumulative_snapshots"].items():
            print(f"  {name:36s} {count:5,}")

    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWritten to {OUTPUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
