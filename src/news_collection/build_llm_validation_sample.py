"""Draw the fresh blind validation sample for the frozen v2 LLM
classifier (eligibility_manual_review_methodology.md §7's "new,
untouched human-coded validation sample").

Why a NEW sample is required at all
------------------------------------
The 168-article pilot sample was demoted to a development set the
moment its human labels were used to diagnose v1's failures and design
v2. Any agreement computed on it is in-sample and proves nothing.
This script therefore draws from the population the pilot never
touched: pending_human_review records whose article_id does NOT appear
in manual_review_sample.csv.

Order of operations (methodological, not technical)
----------------------------------------------------
1. This sample may be drawn and human-coded at any time - human
   judgements depend only on the codebook, which is unchanged.
2. v2 must be FROZEN (no prompt/schema/model edits) before its output
   on these articles is ever generated or compared.
3. The comparison itself, and which agreement statistic gates it,
   happens only after the supervisor approves the proposed amendment
   in eligibility_manual_review_methodology.md §8.
Coding the sample before step 3 is safe; editing v2 after seeing any
result on this sample is what would invalidate it.

Design choices, and why they are not tuned to help v2 pass
-----------------------------------------------------------
* Same stratification logic as the pilot (build_manual_review_sample),
  same codebook, same review sheet format - the only differences are
  the pool (untouched articles), the seed, and the quotas.
* Reform quota is raised to 40 (pilot: 25) because E6 is only
  computable on Reform-flagged articles and the pilot's 35 judged
  pairs gave agreement statistics with very wide uncertainty; 40 is
  ~31% of the 130 flagged articles remaining, the most that can be
  spent here while leaving a majority for the actual corpus review.
* Background quotas mirror the pilot (local oversampled vs. its true
  share, national capped) so validation difficulty is comparable to
  the development set - a validation sample easier than development
  would flatter v2; one drawn from a different mix would measure a
  different task.
* Seed is a new fixed constant (the date this sample was designed).
  It was chosen before any v2 output on these articles existed and is
  never changed - re-running this script reproduces the same sample
  byte-for-byte.

Usage:
    python3 -m src.news_collection.build_llm_validation_sample
"""

import csv
from pathlib import Path

from .build_manual_review_sample import (
    annotate,
    build_review_row,
    composition_report,
    load_effective_dates,
    load_pool,
    write_csv,
)

PILOT_SAMPLE = Path("news_collection/manual_review_sample.csv")
VALIDATION_OUT = Path("news_collection/llm_validation_sample.csv")

# Fixed on the day this validation design was written; independent of
# the pilot's seed so the two draws share no randomness.
SEED = 20260724
RNG_STREAM = "llm_validation_sample_selection"

REFORM_TARGET = 40                # vs. 25 in the pilot - see docstring
LOCAL_PER_ELECTION_TARGET = 12    # pilot used 18; slightly leaner here
NATIONAL_PER_ELECTION_TARGET = 10  # pilot used 12


def load_untouched_pool():
    """pending_human_review records minus every article the pilot ever
    showed a human. Membership is by article_id against the pilot
    sheet as it exists on disk - the authoritative record of what was
    seen - not against a re-derived sample, so a future re-run cannot
    quietly disagree with what actually happened."""
    seen = {r["article_id"] for r in csv.DictReader(PILOT_SAMPLE.open())}
    pool = [r for r in load_pool() if r["article_id"] not in seen]
    return pool, seen


def select_validation_sample(pool):
    """Same disproportionate stratified draw as the pilot's
    select_sample(), with this design's quotas. Re-implemented rather
    than parameterising the pilot function so the pilot script stays
    byte-identical to what produced the frozen 168-article sample."""
    import random
    rng = random.Random(f"{SEED}:{RNG_STREAM}")
    remaining = {r["article_id"]: r for r in pool}
    selected = {}

    def take(candidates, cap=None):
        candidates = sorted(candidates, key=lambda r: r["article_id"])
        rng.shuffle(candidates)
        chosen = candidates if cap is None else candidates[:cap]
        for r in chosen:
            selected[r["article_id"]] = r
            remaining.pop(r["article_id"], None)
        return chosen

    # 1. Reform first: E6's entire evidence base comes from this quota.
    take([r for r in remaining.values()
         if r["needs_reform_disambiguation"] == "yes"], cap=REFORM_TARGET)

    # 2. Local arm per election, then 3. national arm per election -
    # same ordering as the pilot so the strata compete for slots the
    # same way. (The pilot's rare-category near-census step is absent
    # here because the pilot already consumed those tiny pools.)
    for election_id in sorted({r["election_id"] for r in pool}):
        take([r for r in remaining.values()
             if r["election_id"] == election_id and r["arm"] == "local"],
             cap=LOCAL_PER_ELECTION_TARGET)
    for election_id in sorted({r["election_id"] for r in pool}):
        take([r for r in remaining.values()
             if r["election_id"] == election_id and r["arm"] == "national"],
             cap=NATIONAL_PER_ELECTION_TARGET)

    return list(selected.values())


def main():
    pool, seen = load_untouched_pool()
    print(f"Untouched pool: {len(pool)} records "
         f"({len(seen)} pilot articles excluded)")

    sample = select_validation_sample(annotate(pool))
    eff_date_by_id = load_effective_dates()

    stratum_of = {}
    for r in sample:
        tags = []
        if r["needs_reform_disambiguation"] == "yes":
            tags.append("reform")
        tags.append(f"{r['election_id']}:{r['arm']}")
        stratum_of[r["article_id"]] = "|".join(tags)

    rows = [
        build_review_row(r, stratum_tags=stratum_of[r["article_id"]],
                         review_round="llm_validation",
                         eff_date_by_id=eff_date_by_id)
        for r in sorted(sample, key=lambda r: r["article_id"])]
    write_csv(VALIDATION_OUT, rows)

    report = composition_report(sample)
    print(f"Validation sample: {report['total']} records -> {VALIDATION_OUT}")
    print(f"  by election: {report['by_election']}")
    print(f"  by arm: {report['by_arm']}")
    print(f"  Reform-flagged (E6-judgeable): {report['reform_flagged']}")
    print("\nNext: a human codes every row (decision fields are blank; "
         "reading aids are filled). Do NOT generate v2 output for these "
         "articles until v2 is frozen and the supervisor has approved "
         "the statistic amendment - see the module docstring.")


if __name__ == "__main__":
    main()
