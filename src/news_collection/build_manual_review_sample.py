"""Build the reproducible stratified pilot sample for the Article
Eligibility Manual Review stage (E4/E5-relevance/E6/E8), plus a
held-out blind-recheck subset for measuring reviewer agreement before
the full corpus is reviewed.

Why a deliberately DISPROPORTIONATE stratified sample
------------------------------------------------------
The 2,666-record pending_human_review pool (assess_eligibility.py's
output) is heavily skewed: 95% Guardian API / national arm, and the
rare-but-important categories this pilot must cover are tiny in the
raw pool - checked directly against eligibility_assessment.csv on
2026-07-23:

    local arm             476 / 2666  (17.9%)
    Reform-flagged         165 / 2666  ( 6.2%, all from 2021/2026 -
                                          the query design never tags
                                          "Reform" for 2013/2017, since
                                          the party didn't exist yet)
    serpapi route            9 / 2666  ( 0.3%)
    site_search route         1 / 2666  ( 0.04%)
    missing/partial text     17 / 2666  ( 0.6%)

A proportional random sample of ~175 records would draw roughly 0-1
records from several of these categories - useless for checking
whether a reviewer applies the rules consistently on exactly the
content types (thin extracts, non-Guardian routes, Reform hits) where
disagreement is most likely. This script instead takes a near-census
of every rare category, a deliberately oversampled Reform quota, and a
stratified-by-(election x arm) background draw for the common case -
and reports the ACHIEVED composition rather than assuming the targets
below were all met (some cells simply don't have enough records).

Reproducibility
----------------
Every random choice uses a single seeded random.Random instance, and
every collection this script draws from is sorted by article_id before
any sampling - Python's set/dict iteration order is not itself
guaranteed stable across runs, so relying on it would make "the same
sample" not actually reproducible. Re-running this script against an
unchanged corpus produces byte-identical output.

Usage:
    python3 -m src.news_collection.build_manual_review_sample
"""

import csv
import json
import random
from pathlib import Path

from .manual_review_schema import REVIEW_FIELDS

ELIGIBILITY = Path("news_collection/eligibility_assessment.csv")
RECORDS = Path("data/raw/news/records")
SAMPLE_OUT = Path("news_collection/manual_review_sample.csv")
KAPPA_OUT = Path("news_collection/manual_review_kappa_subset.csv")

SEED = 20260723   # date this protocol was designed - fixed, never changed
RNG_SAMPLE = "sample_selection"
RNG_KAPPA = "kappa_subset_selection"

# Targets, not guarantees - the code takes min(target, available) per
# cell and reports the shortfall if any target could not be met.
REFORM_TARGET = 25          # ~15% of the sample, vs. 6.2% true share
LOCAL_PER_ELECTION_TARGET = 18   # x4 elections = up to 72 local-arm rows
NATIONAL_PER_ELECTION_TARGET = 12  # x4 elections = up to 48 national-arm rows
KAPPA_SUBSET_FRACTION = 0.20        # min(this fraction, KAPPA_MIN) below
KAPPA_MIN = 30


def load_pool():
    rows = [r for r in csv.DictReader(ELIGIBILITY.open())
           if r["status"] == "pending_human_review"]
    rows.sort(key=lambda r: r["article_id"])   # deterministic order
    return rows


def text_completeness(rec):
    wc = rec["content"].get("word_count") or 0
    has_full = rec["content"].get("has_full_text")
    if not has_full or wc == 0:
        return "missing"
    if wc < 100:
        return "partial"
    return "full"


def annotate(rows):
    """Attach the stratification tags each row needs (route, text
    completeness) by reading the raw record once per row."""
    for r in rows:
        rec = json.loads((RECORDS / f"{r['article_id']}.json").read_text())
        r["_route"] = rec["retrieval"]["adapter"]
        r["_text_completeness"] = text_completeness(rec)
    return rows


def select_sample(pool):
    """The disproportionate stratified draw described in the module
    docstring. Returns (selected_rows, composition_report)."""
    rng = random.Random(f"{SEED}:{RNG_SAMPLE}")
    remaining = {r["article_id"]: r for r in pool}
    selected = {}

    def take(candidates, cap=None):
        """Move up to `cap` (or all) candidates, sorted then shuffled
        deterministically, from remaining into selected."""
        candidates = sorted(candidates, key=lambda r: r["article_id"])
        rng.shuffle(candidates)
        chosen = candidates if cap is None else candidates[:cap]
        for r in chosen:
            selected[r["article_id"]] = r
            remaining.pop(r["article_id"], None)
        return chosen

    # 1. Near-census of the rare categories: thin/missing text, and the
    # two smallest collection routes. No cap - these pools are already
    # tiny (17 and 10 respectively as of the 2026-07-23 check above).
    take([r for r in remaining.values()
         if r["_text_completeness"] in ("missing", "partial")])
    take([r for r in remaining.values() if r["_route"] in
         ("serpapi", "site_search")])

    # 2. Reform oversample - deliberately far above its 6.2% true share
    # (see module docstring), since E6 disambiguation is a named,
    # mandatory-review rule and the pilot must contain enough Reform
    # cases to say anything about reviewer consistency on it.
    take([r for r in remaining.values()
         if r["needs_reform_disambiguation"] == "yes"], cap=REFORM_TARGET)

    # 3. Local arm, stratified per election - oversampled relative to
    # its 17.9% true share so all four elections' local coverage can be
    # compared, which the wider research design needs (local vs.
    # national vs. combined news models).
    for election_id in sorted({r["election_id"] for r in pool}):
        take([r for r in remaining.values()
             if r["election_id"] == election_id and r["arm"] == "local"],
             cap=LOCAL_PER_ELECTION_TARGET)

    # 4. National arm, stratified per election - the background/common
    # case, capped well below its true 82% share so it doesn't crowd
    # out everything above.
    for election_id in sorted({r["election_id"] for r in pool}):
        take([r for r in remaining.values()
             if r["election_id"] == election_id and r["arm"] == "national"],
             cap=NATIONAL_PER_ELECTION_TARGET)

    return list(selected.values())


def composition_report(rows):
    from collections import Counter
    return {
        "total": len(rows),
        "by_election": dict(Counter(r["election_id"] for r in rows)),
        "by_arm": dict(Counter(r["arm"] for r in rows)),
        "by_route": dict(Counter(r["_route"] for r in rows)),
        "by_text_completeness": dict(
            Counter(r["_text_completeness"] for r in rows)),
        "reform_flagged": sum(1 for r in rows
                              if r["needs_reform_disambiguation"] == "yes"),
    }


def build_review_row(r, *, stratum_tags, review_round):
    """One blank review row - every deterministic/carried-over field
    filled in, every judgement field left explicitly empty. Never
    guesses a decision; a reviewer fills those in by hand."""
    row = {field: "" for field in REVIEW_FIELDS}
    row.update({
        "article_id": r["article_id"], "election_id": r["election_id"],
        "source_id": r["source_id"], "arm": r["arm"],
        "sample_stratum": stratum_tags,
        "review_round": review_round,
        "deterministic_status": r["status"],
        "deterministic_note": r["note"],
        "needs_reform_disambiguation": r["needs_reform_disambiguation"],
    })
    # E6 is not_applicable by construction for anything not Reform-flagged
    # - fill this in now so the schema's closed vocabulary is satisfied
    # from the start rather than left as an empty string a validator
    # would reject.
    if r["needs_reform_disambiguation"] != "yes":
        row["e6_decision"] = "not_applicable"
        row["e6_reason_code"] = "E6-NOT-REFORM-FLAGGED"
    return row


def select_kappa_subset(sample_rows):
    rng = random.Random(f"{SEED}:{RNG_KAPPA}")
    ordered = sorted(sample_rows, key=lambda r: r["article_id"])
    rng.shuffle(ordered)
    n = max(KAPPA_MIN, round(len(ordered) * KAPPA_SUBSET_FRACTION))
    n = min(n, len(ordered))
    return ordered[:n]


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        w.writerows(rows)


def main():
    pool = annotate(load_pool())
    sample = select_sample(pool)

    stratum_of = {}
    for r in sample:
        tags = []
        if r["_text_completeness"] in ("missing", "partial"):
            tags.append(f"text:{r['_text_completeness']}")
        if r["_route"] in ("serpapi", "site_search"):
            tags.append(f"route:{r['_route']}")
        if r["needs_reform_disambiguation"] == "yes":
            tags.append("reform")
        tags.append(f"{r['election_id']}:{r['arm']}")
        stratum_of[r["article_id"]] = "|".join(tags)

    sample_review_rows = [
        build_review_row(r, stratum_tags=stratum_of[r["article_id"]],
                         review_round="initial")
        for r in sorted(sample, key=lambda r: r["article_id"])]
    write_csv(SAMPLE_OUT, sample_review_rows)

    kappa_rows = select_kappa_subset(sample)
    kappa_review_rows = [
        build_review_row(r, stratum_tags=stratum_of[r["article_id"]],
                         review_round="kappa_blind_recheck")
        for r in sorted(kappa_rows, key=lambda r: r["article_id"])]
    write_csv(KAPPA_OUT, kappa_review_rows)

    report = composition_report(sample)
    print(f"Pool: {len(pool)} pending_human_review records")
    print(f"Sample: {report['total']} records -> {SAMPLE_OUT}")
    print(f"  by election: {report['by_election']}")
    print(f"  by arm: {report['by_arm']}")
    print(f"  by route: {report['by_route']}")
    print(f"  by text completeness: {report['by_text_completeness']}")
    print(f"  Reform-flagged: {report['reform_flagged']}")
    print(f"\nBlind kappa-recheck subset: {len(kappa_review_rows)} records "
         f"-> {KAPPA_OUT}")
    print("(same articles as a subset of the main sample, blank decision "
         "fields again - fill in independently, without looking at the "
         "'initial' round's answers, then run compute_review_agreement.py)")


if __name__ == "__main__":
    main()
