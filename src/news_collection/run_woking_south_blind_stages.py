"""Stages 1-3 for the Woking South blind test (frozen rules, new paths).

    python3 -m src.news_collection.run_woking_south_blind_stages

Third reuse of the by-election stage pattern (enrichment, then the
Haslemere probe, now this): the date rule, the mechanical eligibility
rules and the review-row builder are imported byte-identical; this
module only registers the one election, selects its records and writes
to the blind test's own directory. Nothing here can touch a principal,
enrichment or probe artefact.

Blind-test specifics, in the frozen protocol's words
(news_features/woking_south_blind_v1/protocol.json):

- the election window is polling day minus 180 days, the standard
  convention (2025-01-11 to 2025-07-10) - matching the collection
  window just executed;
- the funnel reads news records only; no stage in this file or its
  successors reads any outcome column for this contest - the observed
  results stay sealed until the named unseal script runs against a
  committed predictions file;
- the stop-loss (abort and record if the assembled corpus ends under
  15 usable articles) is evaluated at assembly, not here: stages 1-3
  are free and their counts inform, never decide.

Registering a training-era election here is legitimate for the same
reason the probe's registration was: nothing is trained on anything
this funnel produces - the frozen specifications will predict one
contest, after the one-time unblinding already happened, under a
protocol committed before collection began.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .build_manual_review_sample import build_review_row, write_csv
from .resolve_publication_dates import ELECTIONS
from .run_byelection_stages import (
    RECORDS,
    _write,
    build_effective_dates,
    run_eligibility,
)

WOKING_SOUTH = "surrey-county-council-by-election-woking-south-2025-07-10"
POLLING_DAY = date(2025, 7, 10)

OUT_DIR = Path("news_collection/woking_south_blind")
OUT_DATES = OUT_DIR / "effective_dates.csv"
OUT_ELIGIBILITY = OUT_DIR / "eligibility_assessment.csv"
OUT_SHEET = OUT_DIR / "review_sheet.csv"


def register_window() -> None:
    """The one in-process registration the frozen rules need."""

    ELECTIONS[WOKING_SOUTH] = (POLLING_DAY - timedelta(days=180), POLLING_DAY)


def load_records() -> list[dict]:
    """Every record the collection stamped for this contest, and only
    those - selection by the record's own discovery stamp, as always."""

    records = []
    for path in sorted(RECORDS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("discovered_for_election") == WOKING_SOUTH:
            records.append(record)
    return records


def build_sheet(eligibility_rows: list[dict],
                date_rows: list[dict]) -> list[dict]:
    """Stage 3 with blind-test provenance in the stratum tag."""

    eff_date_by_id = {
        row["article_id"]: row["effective_date"]
        for row in date_rows if row["date_status"] == "usable"
    }
    sheet = []
    for row in sorted(
            (r for r in eligibility_rows
             if r["status"] == "pending_human_review"),
            key=lambda r: r["article_id"]):
        tags = ["woking_south_blind"]
        if row["needs_reform_disambiguation"] == "yes":
            tags.append("reform")
        tags.append(f"{row['election_id']}:{row['arm']}")
        sheet.append(build_review_row(
            row, stratum_tags="|".join(tags), review_round="full_corpus",
            eff_date_by_id=eff_date_by_id,
        ))
    return sheet


def main() -> None:
    register_window()
    records = load_records()
    if not records:
        raise RuntimeError("no Woking South records under data/raw/news")

    date_rows = build_effective_dates(records)
    _write(OUT_DATES, date_rows)
    usable = sum(1 for row in date_rows if row["date_status"] == "usable")

    eligibility_rows = run_eligibility(records, date_rows)
    _write(OUT_ELIGIBILITY, eligibility_rows)

    sheet = build_sheet(eligibility_rows, date_rows)
    write_csv(OUT_SHEET, sheet)

    status_counts = Counter(
        f"{row['status']}:{row['exclusion_code']}" if row["exclusion_code"]
        else row["status"]
        for row in eligibility_rows)
    pool_by_arm = Counter(
        row["arm"] for row in eligibility_rows
        if row["status"] == "pending_human_review")
    print(f"records assessed        : {len(records)} "
          f"({usable} with usable dates) -> {OUT_ELIGIBILITY}")
    for key, count in sorted(status_counts.items()):
        print(f"  {key}: {count}")
    print(f"review sheet rows       : {len(sheet)} -> {OUT_SHEET}")
    print(f"  pool by arm           : {dict(pool_by_arm)}")
    print(f"  reform-flagged in pool: "
          f"{sum(1 for r in sheet if r['needs_reform_disambiguation'] == 'yes')}")


if __name__ == "__main__":
    main()
