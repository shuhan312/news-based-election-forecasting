"""The 1,060 local articles that cleared every mechanical rule and were
never adjudicated - exported as a fillable review sheet.

## What this fixes

The supervisor's brief names five sub-questions beyond the central one.
Three of them depend entirely on the local arm:

    "Whether local Surrey news or national political news has greater
     predictive value"
    "Whether the combination of national and local news produces the
     strongest forecast"
    "Whether national Reform UK momentum identifies its general growth,
     while local coverage identifies the Surrey wards where that support
     is most likely to convert into votes or seats"

The local arm currently has **120 included articles** - 11 from 2013, 59
from 2017, 33 from 2021, 17 for the whole of 2026. Against 1,332
national. No modelling choice recovers three sub-questions from 70
training-period articles.

Measured, the local funnel is:

    2,666 local queries -> 36,466 raw results
    9,299 unique articles reached mechanical eligibility
      5,042 excluded E1  date could not be resolved      <- technical
      2,832 excluded E2  outside the 180-day window      <- legitimate
         21 excluded E3 / 8 E5-known / 1 E9 / 1 E10
      1,394 passed to the human judgement pass
          334 adjudicated -> 120 included
        1,060 NEVER ADJUDICATED                          <- this module

The 1,060 are not "excluded". They cleared E1 (date resolved), E2
(inside the window), E3, E5-known-irrelevant, E7, E9 and E10. What they
are missing is the judgement pass the rules document reserves for a
human: E4 leakage, E5 local/national relevance, E6 Reform
disambiguation, E8 editorial type.

## Why the ordering in this sheet is not cosmetic

The 334 already adjudicated are NOT a representative sample of the
1,394. They are dominated by `guardian_api` - a national newspaper whose
articles appear in the local arm and mostly fail a *local* relevance
test. Measured E5 include rate among the adjudicated, per source:

    guardian_api        248 adjudicated,  47 included =  19.0%
    surreylive           55 adjudicated,  48 included =  87.3%
    bbc_surrey           19 adjudicated,  15 included =  78.9%
    guildford_dragon     10 adjudicated,  10 included = 100.0%
    surrey_comet          2 adjudicated,   0 included =   n=2, no basis

The un-adjudicated 1,060 are dominated by the opposite mix -
`bbc_surrey` 386, `google_dated_search` 277, `surrey_comet` 193,
`guardian_api` only 106. So a flat include rate taken over the
adjudicated set (120/334 = 36%) *understates* what the remaining work
would yield, because it averages in Guardian's 19%.

Rows are therefore emitted highest-expected-yield first, so that a
reviewer who fills in the first 400 rows and stops has captured most of
the available articles rather than a random 38% of them. Priority is
(measured source rate) x (training-period scarcity): 2013 and 2017 local
articles are the scarcest and the only ones that can carry a training
coefficient at all, so they are lifted within each source band.

## What this module refuses to do

**It does not fill in a single decision.** E5-local is the one rule
whose automated classifier failed validation, which is exactly why all
334 existing local E5 decisions carry `e5_source == "human"` and none
carry `llm_v2`. A pre-filled guess here would launder a failed
classifier into the corpus. Every judgement column is emitted blank.

It also does not touch `full_corpus_review.csv`. That file holds 334
completed rows and is the input to `assemble_corpus_decisions.py`;
appending to it is a separate, deliberate step taken once rows are
filled, not a side effect of generating a queue.

## Partial completion is safe - verified, not assumed

`assemble_corpus_decisions.py` handles a local article with a blank
`e5_decision` by appending `awaiting_human_e5` to its blockers and
writing `overall_decision = ""`. A blank is never read as an exclude, so
filling 200 rows and stopping loses nothing.

The same code path means something a reviewer needs to know before
starting: E4, E6 and E8 for a local article come from `llm_v2`, and none
of the 1,060 has an `llm_v2` row. Until that run happens every one of
them stays blocked on `awaiting_llm_retry` **even with E5 filled**. So
the cheapest order is usually LLM first, then human E5 only on what the
LLM cleared - `--llm-cleared-only` does exactly that, and without the
flag the sheet contains everything so neither order is wasted work.

Usage:
    # everything, highest-yield first
    python3 -m src.news_collection.build_e5_local_queue

    # only articles the llm_v2 pass has already cleared on E4/E6/E8
    python3 -m src.news_collection.build_e5_local_queue --llm-cleared-only
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.news_collection.build_manual_review_sample import (  # noqa: E402
    READING_AID_FIELDS,
    build_review_row,
)
from src.news_collection.manual_review_schema import REVIEW_FIELDS  # noqa: E402

ELIGIBILITY = Path("news_collection/eligibility_assessment_v2.csv")
DECISIONS = Path("news_collection/corpus_eligibility_decisions.csv")
EFFECTIVE_DATES = Path("news_collection/effective_dates_v2.csv")
# The original 2,370-row corpus pass and the later 1,060-row local extension
# are separate API batches with separate audit trails. They are one logical
# source for this filter, so read both without concatenating files on disk.
LLM_OUTPUTS = (
    Path("news_collection/manual_review_llm_v2_corpus.csv"),
    Path("news_collection/manual_review_llm_v2_local_extension.csv"),
)

# The queue carries ~1,500-character article excerpts, so it is local-only
# under the project's copyright tiering (code and compact results in Git,
# article text on disk and OneDrive). The companion summary carries counts
# and rates only and is safe to commit.
OUT_QUEUE = Path("news_collection/e5_local_review_queue_round2.csv")
OUT_SUMMARY = Path("news_collection/e5_local_review_queue_round2_summary.json")

# The training period, from the supervisor's chronological split. A local
# article in 2013 or 2017 is worth more than one in 2021 or 2026 for a
# specific reason: it is the only kind that can contribute to estimating a
# coefficient. 2021 is validation and 2026 is the protected holdout.
TRAINING_ELECTIONS = {"SCC-2013-05", "SCC-2017-05"}

# Below this many adjudicated articles a source's include rate is not an
# estimate of anything. surrey_comet has 2 adjudicated and both were
# excluded; treating that as 0% would bury 193 articles from a genuine
# Surrey local paper at the bottom of the queue on the strength of two
# observations. Such sources get the pooled non-Guardian rate instead,
# and the summary records that the substitution happened.
MIN_ADJUDICATED_FOR_RATE = 8

# Sources that are national publications appearing in the local arm. Their
# low local-relevance rate is a property of what they are, not a sampling
# artefact, so they are never given the pooled local rate.
NATIONAL_PUBLISHERS_IN_LOCAL_ARM = {"guardian_api"}


def load_eligibility() -> list[dict]:
    """Local-arm rows that the mechanical pass left for a human."""
    with ELIGIBILITY.open(newline="") as handle:
        return [r for r in csv.DictReader(handle)
                if r["arm"] == "local"
                and r["status"] == "pending_human_review"]


def adjudicated_ids() -> set[str]:
    """Article ids that already have a row in the decisions table.

    Membership in the decisions table is the definition of "adjudicated"
    used everywhere else in this pipeline, so it is used here too rather
    than inferring completion from a filled cell in a review sheet.
    """
    with DECISIONS.open(newline="") as handle:
        return {r["article_id"] for r in csv.DictReader(handle)}


def measured_e5_rates() -> tuple[dict[str, float], dict, float]:
    """Per-source E5 include rate among the local articles already judged.

    Returns the usable rates, the raw counts behind them (so the summary
    can show the denominator next to every rate), and the pooled rate over
    non-national-publisher sources, used as the fallback for any source
    with too few observations to estimate.
    """
    elig = {}
    with ELIGIBILITY.open(newline="") as handle:
        for r in csv.DictReader(handle):
            elig[r["article_id"]] = r["source_id"]

    counts: dict[str, Counter] = defaultdict(Counter)
    with DECISIONS.open(newline="") as handle:
        for r in csv.DictReader(handle):
            if r["arm"] != "local":
                continue
            counts[elig.get(r["article_id"], "unknown")][r["e5_decision"]] += 1

    raw = {src: {"adjudicated": sum(c.values()), "included": c.get("include", 0)}
           for src, c in counts.items()}

    # The pooled fallback deliberately excludes national publishers: mixing
    # Guardian's 19% into the rate handed to surrey_comet would import the
    # very bias this ordering exists to avoid.
    pooled_adj = sum(v["adjudicated"] for s, v in raw.items()
                     if s not in NATIONAL_PUBLISHERS_IN_LOCAL_ARM)
    pooled_inc = sum(v["included"] for s, v in raw.items()
                     if s not in NATIONAL_PUBLISHERS_IN_LOCAL_ARM)
    pooled = pooled_inc / pooled_adj if pooled_adj else 0.0

    rates = {src: v["included"] / v["adjudicated"]
             for src, v in raw.items()
             if v["adjudicated"] >= MIN_ADJUDICATED_FOR_RATE}
    return rates, raw, pooled


def priority(row: dict, rates: dict[str, float], pooled: float) -> tuple:
    """Sort key: highest expected yield first, deterministic ties.

    Two factors, in this order:

    1. The source's measured E5 include rate. A `surreylive` article is
       4.6 times more likely to survive than a `guardian_api` one, so an
       hour spent on surreylive returns 4.6 times as many articles.
    2. Whether the article falls in the training period. A 2013 or 2017
       article is the only kind that can support a coefficient, so within
       a source band those come first.

    Article id breaks remaining ties so two runs produce byte-identical
    files - the same determinism rule the rest of this pipeline follows.
    """
    src = row["source_id"]
    rate = rates.get(src, pooled if src not in NATIONAL_PUBLISHERS_IN_LOCAL_ARM
                     else 0.0)
    in_training = row["election_id"] in TRAINING_ELECTIONS
    return (-rate, not in_training, row["article_id"])


def stratum_tag(row: dict, rates: dict[str, float], pooled: float) -> str:
    """The `sample_stratum` value, recording why a row sits where it does.

    Written into the sheet rather than kept in this script so that a row
    carries its own provenance: a reviewer looking at row 900 can see it
    was placed there by a measured 19% source rate, and an auditor can
    reproduce the ordering from the file alone.
    """
    src = row["source_id"]
    if src in rates:
        basis = f"rate={rates[src]:.3f}:measured"
    elif src in NATIONAL_PUBLISHERS_IN_LOCAL_ARM:
        basis = "rate=0.000:national-publisher-in-local-arm"
    else:
        basis = f"rate={pooled:.3f}:pooled-local-fallback"
    role = "training" if row["election_id"] in TRAINING_ELECTIONS else "later"
    return f"{row['election_id']}:local:{src}:{basis}:{role}"


def llm_cleared_ids() -> set[str] | None:
    """Ids the llm_v2 pass cleared on every rule it owns for local articles.

    E4, E6 and E8 come from llm_v2 for a local article; E5 does not. An
    article the LLM excluded on E4 or E8 can never be included whatever a
    human decides about E5, so reading it is wasted effort. Returns None
    when the LLM output file is absent, which the caller reports rather
    than treating as "nothing cleared".
    """
    available = [path for path in LLM_OUTPUTS if path.exists()]
    if not available:
        return None
    cleared = set()
    seen: set[str] = set()
    for path in available:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for r in csv.DictReader(handle):
                article_id = r["article_id"]
                if article_id in seen:
                    raise RuntimeError(
                        f"{article_id} appears in more than one LLM corpus "
                        "output; extension and original batches must be "
                        "disjoint.")
                seen.add(article_id)
                if r.get("status") != "ok":
                    continue
                # not_applicable is a pass, not a gap: E6 is not_applicable by
                # construction for anything never Reform-flagged. E5 is absent
                # from this test on purpose because local E5 is human-owned.
                if all((r.get(f"{rule}_decision") or "") in (
                        "include", "not_applicable")
                       for rule in ("e4", "e6", "e8")):
                    cleared.add(article_id)
    return cleared


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm-cleared-only", action="store_true",
        help="emit only articles llm_v2 has already cleared on E4/E6/E8, "
             "so no article is read by hand that cannot be included anyway")
    args = parser.parse_args()

    done = adjudicated_ids()
    pending = load_eligibility()
    todo = [r for r in pending if r["article_id"] not in done]

    print(f"local arm, mechanically clear: {len(pending)}")
    print(f"  already adjudicated: {len(pending) - len(todo)}")
    print(f"  never adjudicated:   {len(todo)}   <- this queue")

    cleared = llm_cleared_ids()
    llm_note: str
    if args.llm_cleared_only:
        if cleared is None:
            print("\nNo LLM corpus output exists - nothing to filter on. "
                  "Run the llm_v2 pass first, or drop the flag.")
            return
        before = len(todo)
        todo = [r for r in todo if r["article_id"] in cleared]
        llm_note = (f"filtered to llm_v2-cleared: {before} -> {len(todo)}")
        print(f"\n{llm_note}")
        if not todo:
            print("  no article in this queue has an llm_v2 row yet - the "
                  "LLM pass has not covered them. Drop the flag to export "
                  "all of them, or run the LLM pass first.")
            return
    else:
        have_llm = (len([r for r in todo if r["article_id"] in cleared])
                    if cleared is not None else 0)
        llm_note = (f"unfiltered; {have_llm} of {len(todo)} already have an "
                    f"llm_v2 clearance on E4/E6/E8")
        print(f"\n{llm_note}")
        if have_llm == 0:
            print("  none of them has E4/E6/E8 yet, so every row will stay "
                  "at awaiting_llm_retry until the llm_v2 pass is run - "
                  "filling E5 is still useful, it just does not resolve an "
                  "article on its own.")

    rates, raw, pooled = measured_e5_rates()
    print("\nmeasured E5 include rate among the already-adjudicated:")
    for src in sorted(raw, key=lambda s: -raw[s]["adjudicated"]):
        v = raw[src]
        usable = "used" if src in rates else (
            "national-publisher" if src in NATIONAL_PUBLISHERS_IN_LOCAL_ARM
            else f"too few (<{MIN_ADJUDICATED_FOR_RATE}), pooled instead")
        print(f"  {src:22s} {v['adjudicated']:4d} judged  "
              f"{v['included']:4d} included  "
              f"{100*v['included']/v['adjudicated']:5.1f}%   {usable}")
    print(f"  pooled non-national local rate: {100*pooled:.1f}%")

    todo.sort(key=lambda r: priority(r, rates, pooled))

    eff: dict[str, str] = {}
    with EFFECTIVE_DATES.open(newline="") as handle:
        for r in csv.DictReader(handle):
            eff[r["article_id"]] = r["effective_date"]

    # build_review_row and reading_aid_fields are imported rather than
    # reimplemented: they already produce this exact 39-column schema for
    # round 1, and a second implementation would be free to drift from it.
    rows = [build_review_row(r, stratum_tags=stratum_tag(r, rates, pooled),
                             review_round="e5_local_round2",
                             eff_date_by_id=eff)
            for r in todo]

    fields = REVIEW_FIELDS + READING_AID_FIELDS
    with OUT_QUEUE.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    # Expected yield, computed only where a rate is measured. The sources
    # with no basis are reported as a separate unknown block rather than
    # folded in behind a guessed rate, so the projection cannot be read as
    # more certain than it is.
    per_source = Counter(r["source_id"] for r in todo)
    measured_articles = measured_expected = 0
    unknown_articles = 0
    breakdown = []
    for src, n in per_source.most_common():
        if src in rates:
            measured_articles += n
            measured_expected += n * rates[src]
            breakdown.append({"source_id": src, "articles": n,
                              "rate": round(rates[src], 4),
                              "rate_basis": "measured",
                              "expected_included": round(n * rates[src], 1)})
        elif src in NATIONAL_PUBLISHERS_IN_LOCAL_ARM:
            measured_articles += n
            measured_expected += n * 0.0
            breakdown.append({"source_id": src, "articles": n, "rate": 0.0,
                              "rate_basis": "national-publisher-in-local-arm",
                              "expected_included": 0.0})
        else:
            unknown_articles += n
            breakdown.append({"source_id": src, "articles": n, "rate": None,
                              "rate_basis": "no measured basis",
                              "expected_included": None})

    no_text = sum(1 for r in rows
                  if r["article_text_excerpt"].startswith("(no text stored"))

    print(f"\nqueue composition ({len(rows)} rows):")
    for b in breakdown:
        exp = ("      ?" if b["expected_included"] is None
               else f"{b['expected_included']:7.1f}")
        print(f"  {b['source_id']:22s} {b['articles']:4d} articles  "
              f"expect {exp}   ({b['rate_basis']})")
    print(f"\n  rows with a measured rate: {measured_articles}  "
          f"-> expect ~{measured_expected:.0f} additional local articles")
    print(f"  rows with no measured rate: {unknown_articles}  "
          f"-> no defensible estimate, not projected")
    print(f"  local arm today: 120 included  ->  at least "
          f"~{120 + measured_expected:.0f} if this queue is completed")
    print(f"  rows whose article has no stored text: {no_text} "
          "(judge from headline and extract, or mark insufficient_evidence)")

    OUT_SUMMARY.write_text(json.dumps({
        "queue_rows": len(rows),
        "local_mechanically_clear": len(pending),
        "local_already_adjudicated": len(pending) - len(todo)
                                     if not args.llm_cleared_only else None,
        "local_included_today": 120,
        "llm_filter": llm_note,
        "min_adjudicated_for_rate": MIN_ADJUDICATED_FOR_RATE,
        "measured_rates_raw": raw,
        "pooled_non_national_local_rate": round(pooled, 4),
        "per_source": breakdown,
        "expected_additional_included_measured_only":
            round(measured_expected, 1),
        "articles_with_no_measured_rate": unknown_articles,
        "rows_without_stored_text": no_text,
        "ordering": ("descending measured source E5 include rate, then "
                     "training-period articles first within a source, then "
                     "article_id"),
        "note": ("Every judgement column is blank by construction. E5-local "
                 "has no validated automated classifier - all 334 existing "
                 "local E5 decisions are e5_source=human - so no decision "
                 "is pre-filled here. E4/E6/E8 for a local article come "
                 "from llm_v2 and none of these articles has an llm_v2 row "
                 "yet, so each stays at awaiting_llm_retry until that pass "
                 "runs, with or without E5."),
    }, indent=2))

    print(f"\n-> {OUT_QUEUE}  (article excerpts: local only, gitignored)")
    print(f"-> {OUT_SUMMARY}  (counts and rates only, safe to commit)")


if __name__ == "__main__":
    main()
