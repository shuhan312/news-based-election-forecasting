"""Run stages 1-3 (dates, eligibility, review sheet) for by-elections.

    python3 -m src.news_collection.run_byelection_stages

Scenario A of the costed walk-through: both arms, all eight pre-holdout
by-elections. This module deliberately writes NEW files
(``byelection_*``) and never touches a principal-election artifact, but
the judgement logic is imported from the frozen principal modules —
``assess_one`` for the mechanical rules and ``build_review_row`` for the
sheet — so a by-election article is judged by byte-identical code, only
against its own election's 180-day window.

The two by-elections held on or after 7 May 2026 (Warlingham, Haslemere)
are excluded here at the registry level: their news falls inside the
sealed holdout period and can never become training data, so their
records are not assessed at all rather than assessed and filtered later.

Stage 1 is simpler than the principal version on purpose. The principal
corpus needed a three-source date-resolution merge because early
collection left many dates null and conflicting; the by-election records
were collected by the current pipeline, which stamps a
Confirmed/Probable ``published_date`` on 87% of them and records no
conflicting evidence. So the honest rule is the same one the principal
merge ends at: a Confirmed-or-Probable stored date is usable, anything
else is ``no_date_evidence`` and falls to rule E1. Nothing is guessed;
recovering the 414 no-date records (Wayback/PDF work) is a separately
costed job this run does not attempt.
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from .assess_eligibility import assess_one, reform_query_article_ids
from .build_manual_review_sample import (
    READING_AID_FIELDS,
    build_review_row,
    write_csv,
)
from .resolve_publication_dates import ELECTIONS

RECORDS = Path("data/raw/news/records")
OUT_DATES = Path("news_collection/byelection_effective_dates_v1.csv")
OUT_ELIGIBILITY = Path("news_collection/byelection_eligibility_assessment_v1.csv")
OUT_SHEET = Path("news_collection/byelection_review.csv")

# Polling day on or after this date sits inside the sealed 2026 holdout
# period; those by-elections are not registered and never assessed.
HOLDOUT_DATE = date(2026, 5, 7)

# The eight pre-holdout by-elections with collected news. Windows follow
# the principal convention exactly: (polling_day - 180 days, polling_day),
# with E2/E3 in assess_one enforcing the boundary behaviour.
BYELECTION_POLLING_DAYS = {
    "surrey-county-council-by-election-weybridge-2015-05-07": date(2015, 5, 7),
    "surrey-county-council-by-election-warlingham-2019-01-31": date(2019, 1, 31),
    "surrey-county-council-by-election-nork-tattenhams-2025-05-01": date(2025, 5, 1),
    "surrey-county-council-by-election-addlestone-2025-08-21": date(2025, 8, 21),
    "surrey-county-council-by-election-hinchley-wood-claygate-oxshott-2025-08-21":
        date(2025, 8, 21),
    "surrey-county-council-by-election-camberley-west-2025-10-16": date(2025, 10, 16),
    "surrey-county-council-by-election-caterham-valley-2025-10-16": date(2025, 10, 16),
    "surrey-county-council-by-election-guildford-south-east-2025-10-16":
        date(2025, 10, 16),
}

USABLE_CONFIDENCE = {"Confirmed", "Probable"}


def register_byelection_windows() -> None:
    """Add the eight windows to the shared ELECTIONS registry in-process.

    ``assess_one`` and ``build_review_row`` both look elections up in
    that dict, so one in-memory update makes the frozen code work on
    by-elections without editing it. The update is additive and only
    lives for this process; principal artifacts are not re-run here.
    """

    for election_id, polling_day in BYELECTION_POLLING_DAYS.items():
        if polling_day >= HOLDOUT_DATE:
            raise RuntimeError(
                f"{election_id} is inside the holdout period and must not "
                "be registered for training enrichment."
            )
        ELECTIONS[election_id] = (polling_day - timedelta(days=180), polling_day)


def load_byelection_records() -> list[dict]:
    records = []
    for path in sorted(RECORDS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("discovered_for_election") in BYELECTION_POLLING_DAYS:
            records.append(record)
    return records


def build_effective_dates(records: list[dict]) -> list[dict]:
    """Stage 1: one row per record, usable only on stored confidence."""

    rows = []
    for record in records:
        dates = record.get("dates", {})
        usable = (
            dates.get("date_confidence") in USABLE_CONFIDENCE
            and dates.get("published_date")
        )
        rows.append({
            "article_id": record["article_id"],
            "election_id": record["discovered_for_election"],
            "effective_date": dates.get("published_date") or "",
            "date_status": "usable" if usable else "no_date_evidence",
            "date_source": "raw_record_confidence" if usable else "",
            # The Guardian/SerpAPI relevance audits were principal-only
            # sweeps; no by-election record was flagged by them.
            "known_irrelevant_flag": "no",
            "notes": "" if usable else (
                f"date_confidence={dates.get('date_confidence')!r}; rule E1 "
                "excludes this record rather than guessing a date"
            ),
        })
    return rows


def run_eligibility(records: list[dict], date_rows: list[dict]) -> list[dict]:
    """Stage 2: the frozen mechanical rules over every by-election record."""

    dates_by_id = {row["article_id"]: row for row in date_rows}
    reform_ids = reform_query_article_ids()
    rows = []
    for record in records:
        article_id = record["article_id"]
        status, code, note = assess_one(record, dates_by_id.get(article_id))
        flagged = article_id in reform_ids
        if flagged and status == "pending_human_review":
            note += (" This record also matched a Reform-related query - "
                     "E6 manual disambiguation is mandatory before "
                     "inclusion (protocol requirement, not optional).")
        rows.append({
            "article_id": article_id,
            "election_id": record["discovered_for_election"],
            "source_id": record["source_id"],
            "arm": record["arm"],
            "status": status,
            "exclusion_code": code,
            "needs_reform_disambiguation": "yes" if flagged else "",
            "note": note,
        })
    return rows


def build_sheet(eligibility_rows: list[dict], date_rows: list[dict]) -> list[dict]:
    """Stage 3: one review row per pending record, in the frozen shape.

    ``review_round`` is set to ``full_corpus`` because the frozen batch
    runner accepts exactly that value; provenance is carried by the
    separate by-election sheet file, not by the round label.
    """

    eff_date_by_id = {
        row["article_id"]: row["effective_date"]
        for row in date_rows if row["date_status"] == "usable"
    }
    pool = sorted(
        (row for row in eligibility_rows
         if row["status"] == "pending_human_review"),
        key=lambda row: row["article_id"],
    )
    sheet = []
    for row in pool:
        tags = ["byelection"]
        if row["needs_reform_disambiguation"] == "yes":
            tags.append("reform")
        tags.append(f"{row['election_id']}:{row['arm']}")
        sheet.append(build_review_row(
            row, stratum_tags="|".join(tags), review_round="full_corpus",
            eff_date_by_id=eff_date_by_id,
        ))
    return sheet


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    register_byelection_windows()
    records = load_byelection_records()
    if not records:
        raise RuntimeError("no by-election records found under data/raw/news")

    date_rows = build_effective_dates(records)
    _write(OUT_DATES, date_rows)
    usable = sum(1 for row in date_rows if row["date_status"] == "usable")

    eligibility_rows = run_eligibility(records, date_rows)
    _write(OUT_ELIGIBILITY, eligibility_rows)

    sheet = build_sheet(eligibility_rows, date_rows)
    write_csv(OUT_SHEET, sheet)

    from collections import Counter
    status_counts = Counter(
        f"{row['status']}:{row['exclusion_code']}" if row["exclusion_code"]
        else row["status"]
        for row in eligibility_rows
    )
    pool_by_arm = Counter(
        row["arm"] for row in eligibility_rows
        if row["status"] == "pending_human_review"
    )
    print(f"records assessed        : {len(records)} "
          f"({usable} with usable dates) -> {OUT_ELIGIBILITY}")
    for key, count in sorted(status_counts.items()):
        print(f"  {key}: {count}")
    print(f"review sheet rows       : {len(sheet)} -> {OUT_SHEET}")
    print(f"  pool by arm           : {dict(pool_by_arm)}")
    print(f"  reform-flagged in pool: "
          f"{sum(1 for row in sheet if row['needs_reform_disambiguation'] == 'yes')}")


if __name__ == "__main__":
    main()
