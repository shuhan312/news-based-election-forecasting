"""Stages 1-3 for the Haslemere case-study probe (exploratory).

    python3 -m src.news_collection.run_haslemere_probe_stages

The one by-election with contest-targeted news that the enrichment run
could not use: Haslemere, polling day 7 July 2026. Its 379 collected
records were excluded from training enrichment because the polling day
falls after 7 May 2026 - ``run_byelection_stages`` refuses such
elections at the registry level, and that guard is correct and stays.

This probe is a different animal, and the difference is why registering
Haslemere here is legitimate where it was forbidden there:

- The enrichment run FITTED models on by-election residuals; holdout-
  period news entering that fit would have been leakage into training.
  This probe fits nothing. The frozen v2 specifications predict one
  contest they have never seen, and the one-time 2026 unblinding has
  already happened, so no confirmatory surface remains to contaminate.
- The leakage rule that does bind - no article after its own polling
  day - is enforced the same way as everywhere else: the election's
  window is (polling day - 180 days, polling day), and the frozen
  eligibility rules (E2/E3 in ``assess_one``) reject anything outside
  it. Collection itself was already windowed 2026-01-08 to 2026-07-07.
- Nothing written here can reach training: outputs live in their own
  ``news_collection/haslemere_probe/`` directory, and the canonical v2
  release, the feature table and both frozen prediction files are
  hash-anchored and untouched.

Why this contest is worth a probe at all: the unblinding's Reform
addendum showed party-grain news cannot locate WHICH wards break
through. Haslemere is a single-ward election, so party grain IS ward
grain here - the one setting where the broadcast limitation vanishes.
And the baseline's failure is Reform-shaped in the opposite direction
to May: before-May training over-predicts Reform at 17.5 against 8.6
observed (+8.9), retraining through May worsens it to 23.2 (+14.6).
The probe asks whether the pre-polling news carried the ward-level
signal - Reform weak here, Liberal Democrats strong - that election
history got wrong from both directions.

Judgement code is byte-identical to the principal and enrichment runs:
``build_effective_dates``, ``run_eligibility`` and the review-row
builder are imported unmodified; this module only registers the
election, selects its records, tags its sheet and writes to probe paths.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .build_manual_review_sample import build_review_row, write_csv
from .resolve_publication_dates import ELECTIONS
from .run_byelection_stages import (
    RECORDS,
    _write,
    build_effective_dates,
    load_byelection_records,
    run_eligibility,
)

HASLEMERE = "surrey-county-council-by-election-haslemere-2026-07-07"
POLLING_DAY = date(2026, 7, 7)

OUT_DIR = Path("news_collection/haslemere_probe")
OUT_DATES = OUT_DIR / "effective_dates.csv"
OUT_ELIGIBILITY = OUT_DIR / "eligibility_assessment.csv"
OUT_SHEET = OUT_DIR / "review_sheet.csv"


def register_haslemere_window() -> None:
    """Register the probe election in the shared in-process registry.

    Same additive, process-local mechanism the enrichment wrappers used;
    the frozen rules look elections up here and need nothing else. The
    180-day window convention is the same one every other election got.
    """

    ELECTIONS[HASLEMERE] = (POLLING_DAY - timedelta(days=180), POLLING_DAY)


def load_haslemere_records() -> list[dict]:
    """The 379 records collected for this contest, and only those.

    Selection is by the record's own ``discovered_for_election`` stamp -
    the same field ``load_byelection_records`` keys on - so the probe
    cannot absorb principal or enrichment articles by accident.
    """

    import json

    records = []
    for path in sorted(RECORDS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("discovered_for_election") == HASLEMERE:
            records.append(record)
    return records


def build_probe_sheet(eligibility_rows: list[dict],
                      date_rows: list[dict]) -> list[dict]:
    """Stage 3 with probe provenance in the stratum tag.

    Identical row shape to every other review sheet (``build_review_row``
    is the frozen builder, ``review_round`` must be ``full_corpus`` for
    the frozen batch runner) - only the tag differs, so these rows can
    never be mistaken for enrichment rows in any downstream audit.
    """

    eff_date_by_id = {
        row["article_id"]: row["effective_date"]
        for row in date_rows if row["date_status"] == "usable"
    }
    sheet = []
    for row in sorted(
            (r for r in eligibility_rows
             if r["status"] == "pending_human_review"),
            key=lambda r: r["article_id"]):
        tags = ["haslemere_probe"]
        if row["needs_reform_disambiguation"] == "yes":
            tags.append("reform")
        tags.append(f"{row['election_id']}:{row['arm']}")
        sheet.append(build_review_row(
            row, stratum_tags="|".join(tags), review_round="full_corpus",
            eff_date_by_id=eff_date_by_id,
        ))
    return sheet


def main() -> None:
    register_haslemere_window()
    records = load_haslemere_records()
    if not records:
        raise RuntimeError("no Haslemere records under data/raw/news/records")
    # Belt and braces: were an enrichment id ever stamped Haslemere, the
    # loader above would have selected it into training runs too - this
    # asserts the two record populations are disjoint.
    enrichment_ids = {r["article_id"] for r in load_byelection_records()}
    overlap = enrichment_ids & {r["article_id"] for r in records}
    if overlap:
        raise RuntimeError(f"records in both populations: {sorted(overlap)[:5]}")

    date_rows = build_effective_dates(records)
    _write(OUT_DATES, date_rows)
    usable = sum(1 for row in date_rows if row["date_status"] == "usable")

    eligibility_rows = run_eligibility(records, date_rows)
    _write(OUT_ELIGIBILITY, eligibility_rows)

    sheet = build_probe_sheet(eligibility_rows, date_rows)
    write_csv(OUT_SHEET, sheet)

    status_counts = Counter(
        f"{row['status']}:{row['exclusion_code']}" if row["exclusion_code"]
        else row["status"]
        for row in eligibility_rows
    )
    pool_by_arm = Counter(
        row["arm"] for row in eligibility_rows
        if row["status"] == "pending_human_review"
    )
    print(f"haslemere records       : {len(records)} "
          f"({usable} with usable dates) -> {OUT_ELIGIBILITY}")
    for key, count in sorted(status_counts.items()):
        print(f"  {key}: {count}")
    print(f"review sheet rows       : {len(sheet)} -> {OUT_SHEET}")
    print(f"  pool by arm           : {dict(pool_by_arm)}")
    print(f"  reform-flagged in pool: "
          f"{sum(1 for r in sheet if r['needs_reform_disambiguation'] == 'yes')}")


if __name__ == "__main__":
    main()
