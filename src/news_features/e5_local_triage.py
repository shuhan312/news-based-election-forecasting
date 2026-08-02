"""Leverage triage for the E5-local backlog (plans judging; judges nothing).

    python3 -m src.news_features.e5_local_triage

The local arm never became reportable because the human E5 pass - the
only valid E5 after the classifier failed both validations - was never
budgeted: 1,060 principal-extension rows, 426 by-election local rows
and a 90-row second-review queue sit unjudged. Clearing all 1,576 rows
costs the reviewer days. This module computes where judging actually
pays, so the reviewer can clear the smallest set that changes what the
report can say.

The arithmetic it reproduces (frozen builder, verbatim semantics)
------------------------------------------------------------------
A column becomes REPORTABLE when, in at least one period, its distinct
values across TRAINING rows reach 10 (``MIN_CELLS_TO_REPORT``; the
verdict takes the maximum across periods). Training rows are the
``split_role == "train"`` elections: 2013, 2017 and the eight
pre-holdout by-elections. 2021 is validation and 2026 is test - rows
there are INVISIBLE to the gate. The frozen fits, meanwhile, pool a
DIFFERENT set (2017 + 2021 + the eight by-elections). Those two lists
disagreeing is what makes rows unequal, and the whole point of this
triage:

  class gate+fit  (2017 + eight by-elections) - counts for the gate
                  AND enriches an exploratory local refit;
  class fit-only  (2021)                      - invisible to the gate,
                  inside the pooled fit;
  class gate-only (2013)                      - counts for the gate,
                  inside no fit ever;
  class test-side (2026)                      - prediction inputs only;
  class second-review (the 90-row queue)      - E4/E8 still unresolved,
                  so E5 there may be moot; judged last.

For each window this module recomputes the six local columns' current
distinct training values from the committed v2 table (same rule: non-
empty values, within one period), then asks the only question that
matters for the gate: WHICH train elections contribute nothing to that
window today but have pending rows that could - an upper bound, since
admission decisions are the reviewer's and value collisions can occur.
Everything else is inventory.

Outputs (news_features/e5_local_triage_v1/): a JSON with the full
arithmetic, a findings file with the tier recommendation, and
``e5_local_triage_queue.csv`` - every pending row, tier-tagged and
sorted, in the exact review-sheet shape the reviewer already knows.
Nothing is admitted, dated or decided here.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(10_000_000)

TABLE = Path("news_features/news_feature_table_v2.csv")
ROUND2 = Path("news_collection/e5_local_review_queue_round2.csv")
BYELECTION_SHEET = Path("news_collection/byelection_review.csv")
SECOND_REVIEW = Path("news_collection/byelection_second_review_queue.csv")
OUT_DIR = Path("news_features/e5_local_triage_v1")

MIN_CELLS_TO_REPORT = 10  # the frozen builder's bar, restated locally

LOCAL_COLUMNS = ("local_article_count", "local_share",
                 "local_party_article_count", "local_party_article_share",
                 "local_unfavourable_count", "local_favourable_count")

WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

# The two election lists whose disagreement defines the classes.
GATE_TRAIN = {"SCC-2013-05", "SCC-2017-05"}   # by-elections added below
FIT_ELECTIONS = {"SCC-2017-05", "SCC-2021-05"}  # by-elections added below


def window_of(day_index: int) -> str | None:
    """The confirmed window a day-index falls in (builder convention)."""

    for window, (low, high) in {
        "final_72_hours": (1, 3), "7_to_4_days": (4, 7),
        "14_to_8_days": (8, 14), "30_to_15_days": (15, 30),
        "90_to_31_days": (31, 90), "180_to_91_days": (91, 180),
    }.items():
        if low <= day_index <= high:
            return window
    return None


def leverage_class(election: str) -> str:
    if election in GATE_TRAIN:
        return "gate+fit" if election != "SCC-2013-05" else "gate-only"
    if election in FIT_ELECTIONS:
        return "fit-only"
    if election == "ESWS-2026-05":
        return "test-side"
    return "gate+fit"  # the eight by-elections: train role AND in the fit


def load_table() -> list[dict]:
    with TABLE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def gate_state(rows: list[dict]) -> dict:
    """Per (column, period): current distinct training values, and which
    train elections currently contribute zero local articles there.

    ALL twelve periods are covered - the six confirmed windows and the
    six cumulative snapshots - because the frozen verdict takes the
    maximum across every period, and the closest-to-bar period turns
    out to be the ``previous_180_days`` snapshot, which the first
    version of this triage (windows only) would have missed entirely.
    Distinct-count semantics are the builder's own: values of training
    rows, empty strings excluded, counted within one period. The zero-
    contribution list reads ``local_article_count`` because that column
    is election-level - if it is 0 for an election's rows in a period,
    every local column is flat there and any admission changes it.
    """

    train = [r for r in rows if r["split_role"] == "train"]
    periods = sorted({r["period"] for r in train})
    state: dict[str, dict] = {}
    for period in periods:
        in_period = [r for r in train if r["period"] == period]
        distinct = {
            column: len({r[column] for r in in_period if r[column] != ""})
            for column in LOCAL_COLUMNS
        }
        zero_elections = sorted({
            r["election_id"] for r in in_period
            if (r["local_article_count"] or "0") in ("0", "")
        })
        state[period] = {"distinct": distinct,
                         "train_elections_with_zero_local": zero_elections}
    return state


def load_pending() -> list[dict]:
    """Every unjudged row from the three queues, tagged with its origin.

    Round-2 rows and by-election local rows are pending when e5_decision
    is blank; the second-review queue is pending wholesale (its rows
    still lack a final E4/E8, so E5 leverage there is conditional).
    """

    pending = []
    with ROUND2.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not (row.get("e5_decision") or "").strip():
                row["triage_source"] = "round2_principal_queue"
                pending.append(row)
    with BYELECTION_SHEET.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("arm") == "local"
                    and not (row.get("e5_decision") or "").strip()):
                row["triage_source"] = "byelection_sheet"
                pending.append(row)
    with SECOND_REVIEW.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row["triage_source"] = "second_review_queue"
            pending.append(row)
    return pending


def assign_tiers(pending: list[dict], state: dict) -> tuple[list[dict], dict]:
    """Tier every pending row by what judging it can buy.

    Tier 1: gate+fit rows from elections at ZERO local coverage in the
            cheapest period - the only rows whose admission can flip a
            whole election from flat to contributing, the mechanism
            that adds distinct values. Sorted smallest election pile
            first, so the opening move is the fewest rows with the
            most independent chances to cross.
    Tier 2: remaining gate+fit rows (fit richness, gate depth).
    Tier 3: fit-only rows (2021).
    Tier 4: test-side rows (2026).
    Tier 5: gate-only rows (2013) - largest pile, least downstream use.
    Tier 6: the second-review queue (E4/E8 first, E5 conditional).
    """

    # The cheapest crossing across ALL periods. Gap = how many new
    # distinct values the party-level local column still needs there.
    gap = {p: MIN_CELLS_TO_REPORT
           - s["distinct"]["local_party_article_count"]
           for p, s in state.items()}
    open_gaps = {p: g for p, g in gap.items() if g > 0}
    cheapest = min(open_gaps, key=open_gaps.get) if open_gaps else None
    zero_elections = (set(state[cheapest]
                          ["train_elections_with_zero_local"])
                      if cheapest else set())

    # Pile sizes count TIER-1 rows only: a second-review row from the
    # same election is not judgeable yet (E4/E8 unresolved) and must not
    # inflate the opening-move arithmetic - the first version counted
    # one such guildford-south-east row and reported 39 where the
    # judgeable opening move is 38.
    pile: Counter = Counter(
        row["election_id"] for row in pending
        if row.get("election_id") in zero_elections
        and row["triage_source"] != "second_review_queue")
    counts: Counter = Counter()
    for row in pending:
        if row["triage_source"] == "second_review_queue":
            tier = 6
        else:
            election = row["election_id"]
            klass = leverage_class(election)
            day_raw = row.get("day_index_from_polling_day") or ""
            window = window_of(int(day_raw)) if day_raw.isdigit() else None
            if klass == "gate+fit":
                tier = 1 if election in zero_elections else 2
            elif klass == "fit-only":
                tier = 3
            elif klass == "test-side":
                tier = 4
            else:
                tier = 5
            row["triage_window"] = window or "snapshot_only"
        row["triage_tier"] = str(tier)
        counts[tier] += 1
    # Tier first; inside tier 1, smallest election pile first.
    pending.sort(key=lambda r: (r["triage_tier"],
                                pile.get(r.get("election_id", ""), 0),
                                r.get("election_id", ""),
                                r.get("triage_window", "")))
    return pending, {
        "tier_counts": dict(sorted(counts.items())),
        "cheapest_period": cheapest,
        "gap_at_cheapest": open_gaps.get(cheapest),
        "gap_to_bar_by_period": gap,
        "zero_local_election_piles": dict(pile.most_common()),
    }


def main() -> None:
    rows = load_table()
    state = gate_state(rows)
    pending = load_pending()
    pending, plan = assign_tiers(pending, state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": ("PLANNING artefact. Nothing here admits, dates or "
                   "judges any article; tiers rank where the human E5 "
                   "pass buys the most."),
        "pending_rows": len(pending),
        "by_source": dict(Counter(r["triage_source"] for r in pending)),
        "gate_state_by_window": state,
        "plan": plan,
    }
    (OUT_DIR / "triage.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # The tier-tagged queue the reviewer actually works from: identical
    # review-sheet columns plus the three triage_* tags at the end.
    fieldnames = list(pending[0].keys())
    for row in pending:  # unify key sets across the three sources
        for key in fieldnames:
            row.setdefault(key, "")
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with (OUT_DIR / "e5_local_triage_queue.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(pending)

    lines = [
        "# E5-local triage: where judging pays", "",
        f"**{payload['status']}**", "",
        f"Pending rows: {len(pending)} "
        f"({payload['by_source']}).", "",
        "## Gate state per period (distinct training values; bar = 10)", "",
        "| period | " + " | ".join(c.replace("local_", "")
                                   for c in LOCAL_COLUMNS)
        + " | train elections at zero local |",
        "| --- |" + " ---: |" * len(LOCAL_COLUMNS) + " --- |",
    ]
    period_order = list(WINDOWS) + sorted(p for p in state
                                          if p not in WINDOWS)
    for period in period_order:
        s = state[period]
        lines.append(
            f"| {period} | "
            + " | ".join(str(s["distinct"][c]) for c in LOCAL_COLUMNS)
            + f" | {len(s['train_elections_with_zero_local'])} |")
    piles = plan["zero_local_election_piles"]
    opening = sorted(piles.items(), key=lambda kv: kv[1])[:4]
    lines += [
        "",
        f"Cheapest crossing: **{plan['cheapest_period']}**, gap "
        f"**{plan['gap_at_cheapest']}** new distinct value(s) needed. "
        "Every zero-local train election whose rows get any admission "
        "flips from flat to contributing there. Opening move - the "
        "four smallest piles: "
        + ", ".join(f"{e.split('by-election-')[-1].rsplit('-', 3)[0]} "
                    f"({n} rows)" for e, n in opening)
        + f" = **{sum(n for _e, n in opening)} rows** for four "
        "independent chances to cross.", "",
        "## Tiers", "",
        "| tier | rows | what judging them buys |", "| --- | ---: | --- |",
        f"| 1 | {plan['tier_counts'].get(1, 0)} | gate-flip candidates: "
        "by-election rows from zero-local elections, smallest pile "
        "first |",
        f"| 2 | {plan['tier_counts'].get(2, 0)} | 2017 rows: fit richness "
        "and gate depth |",
        f"| 3 | {plan['tier_counts'].get(3, 0)} | fit cells only (2021; "
        "invisible to the gate) |",
        f"| 4 | {plan['tier_counts'].get(4, 0)} | 2026 test-side feature "
        "richness |",
        f"| 5 | {plan['tier_counts'].get(5, 0)} | gate depth only (2013; "
        "in no fit) |",
        f"| 6 | {plan['tier_counts'].get(6, 0)} | second-review queue "
        "(E4/E8 unresolved first) |",
        "",
        "Judge tiers in order and stop when the budget runs out; the "
        "queue file is sorted accordingly. Admission decisions remain "
        "entirely the reviewer's; distinct-value gains are upper bounds "
        "until extraction places admitted articles.", "",
    ]
    (OUT_DIR / "triage_findings.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
