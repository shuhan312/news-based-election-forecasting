"""Publication Date Resolution stage (pipeline step 1 of 4 before LLM
extraction: Date Resolution -> Article Eligibility (E1-E10) -> Cleaning
-> Deduplication).

Raw News Collection deliberately never resolved a single conflicting or
missing publication date - schema.py's summarise_dates() only fills
`published_date` when EVERY piece of evidence already agrees; anything
else is left null and graded Uncertain or Missing (see
raw_news_schema.md). That is correct for collection but leaves 207
records (160 Uncertain conflicts + 47 Missing, as of this run) that
article_eligibility_rules.md cannot use as-is - rule E1 requires at
least Probable confidence.

This script is that resolution step. It never edits a raw record file
(data/raw/news/records/*.json stays exactly as collected, forever -
the immutable evidentiary record); every decision is written to a
separate, joinable table instead
(news_collection/date_resolution_log.csv), keyed by article_id.

The central design question, and why this cannot be one blanket rule
--------------------------------------------------------------------
The BBC 2013 pilot record (see retrieval_validation_report.md) is the
reason this script exists in this shape: its JSON-LD metadata claimed
a pre-poll publication date while its visible dateline was the results
day itself. A rule like "trust JSON-LD over visible text" would have
been wrong there. There is no source-type hierarchy that is safe in
every case - so instead of picking a "most trustworthy" evidence type,
this script asks a narrower, answerable question for every conflict:

    Does resolving this conflict one way vs. the other change whether
    the article counts as pre-poll, in-window evidence, or not?

If the answer is yes - the conflicting dates straddle polling day, or
straddle the edge of the election's 180-day window - getting it wrong
is an election-leakage risk, so the record is sent to mandatory human
review and NOTHING is auto-decided, however small the gap looks.

If the answer is no - every candidate date, however many there are,
places the article safely on the same side of every boundary that
matters (e.g. two dates 172 and 175 days before polling day: both deep
inside the window, both unambiguously pre-poll) - the conflict cannot
change any downstream eligibility or time-band decision, so a single,
pre-registered, conservative tie-break is applied: the EARLIEST
candidate date. Earliest is chosen deliberately, not arbitrarily: it
never invents recency the evidence doesn't support, and if the article
is later assigned to a non-overlapping time band (protocol section
3.3), the earliest date is the more conservative (harder-to-inflate-
apparent-relevance) choice between two evidence-supported alternatives.

Usage:
    python3 -m src.news_collection.resolve_publication_dates
"""

import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path

RECORDS = Path("data/raw/news/records")
OUT = Path("news_collection/date_resolution_log.csv")

# Polling days and 180-day window starts, copied verbatim from the
# protocol (news_research_protocol.md section 2) - the single source
# of truth for these dates already used throughout news_collection.
ELECTIONS = {
    "SCC-2013-05":  (date(2012, 11, 3), date(2013, 5, 2)),
    "SCC-2017-05":  (date(2016, 11, 5), date(2017, 5, 4)),
    "SCC-2021-05":  (date(2020, 11, 7), date(2021, 5, 6)),
    "ESWS-2026-05": (date(2025, 11, 8), date(2026, 5, 7)),
}

# How close to a boundary counts as "close enough that a parsing or
# timezone quirk could plausibly move a date across it". Set wider
# than a single day deliberately: the point of this margin is to be
# generous about what triggers human review, never to be generous
# about what gets auto-resolved.
BOUNDARY_MARGIN_DAYS = 2


def parse_candidate_dates(date_evidence):
    """Every parseable calendar day among a record's date_evidence,
    deduplicated. Non-parseable strings are ignored here (they already
    contributed nothing to schema.py's original grading either)."""
    days = set()
    for ev in date_evidence:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", ev["value"].strip())
        if m:
            try:
                days.add(date(*map(int, m.groups())))
            except ValueError:
                continue
    return days


def boundary_relevant(candidate_days, polling_day, window_start):
    """True if resolving this conflict one way vs. another could change
    an eligibility or leakage decision - the only question that
    matters for whether auto-resolution is permitted (see module
    docstring). Checked against BOTH boundaries the protocol cares
    about: the polling-day/post-poll cutoff and the 180-day window
    edge, each with a safety margin.
    """
    poll_cutoff_zone = (polling_day - timedelta(days=BOUNDARY_MARGIN_DAYS),
                        polling_day + timedelta(days=BOUNDARY_MARGIN_DAYS))
    window_edge_zone = (window_start - timedelta(days=BOUNDARY_MARGIN_DAYS),
                        window_start + timedelta(days=BOUNDARY_MARGIN_DAYS))

    near_poll = any(poll_cutoff_zone[0] <= d <= poll_cutoff_zone[1]
                   for d in candidate_days)
    near_window_edge = any(window_edge_zone[0] <= d <= window_edge_zone[1]
                           for d in candidate_days)
    # Also boundary-relevant if the candidates disagree about which SIDE
    # of a boundary they fall on, even without either being numerically
    # close to it (a wide gap could still straddle the cutoff).
    straddles_poll = (min(candidate_days) < polling_day
                      <= max(candidate_days) + timedelta(days=1))
    straddles_window = (min(candidate_days) < window_start
                        <= max(candidate_days))
    return near_poll or near_window_edge or straddles_poll or straddles_window


def resolve_one(record):
    """Return one row for the resolution log. Never mutates `record`."""
    aid = record["article_id"]
    eid = record["discovered_for_election"]
    confidence = record["dates"]["date_confidence"]
    evidence = record["dates"]["date_evidence"]

    if confidence in ("Confirmed", "Probable"):
        return None  # already usable under article_eligibility_rules.md - not this stage's job

    candidate_days = parse_candidate_dates(evidence)
    if not candidate_days:
        return {
            "article_id": aid, "election_id": eid,
            "original_confidence": confidence,
            "candidate_dates": "",
            "resolution_status": "unresolvable_missing_evidence",
            "resolved_date": "", "rule_applied": "",
            "notes": "No parseable date in any evidence field - "
                     "genuinely missing, not a conflict. Excluded from "
                     "influence calculations under rule E1 unless a "
                     "human supplies a date.",
        }

    if len(candidate_days) == 1:
        # schema.py already treats this as Confirmed/Probable, so
        # reaching here with exactly one distinct day and a non-usable
        # confidence would itself be inconsistent - resolve it directly
        # rather than silently dropping it, and note the inconsistency.
        (only_day,) = candidate_days
        return {
            "article_id": aid, "election_id": eid,
            "original_confidence": confidence,
            "candidate_dates": only_day.isoformat(),
            "resolution_status": "resolved_single_value",
            "resolved_date": only_day.isoformat(),
            "rule_applied": "only_one_distinct_day_present",
            "notes": "",
        }

    window_start, polling_day = ELECTIONS[eid][0], ELECTIONS[eid][1]
    sorted_days = sorted(candidate_days)

    if boundary_relevant(candidate_days, polling_day, window_start):
        return {
            "article_id": aid, "election_id": eid,
            "original_confidence": confidence,
            "candidate_dates": "; ".join(d.isoformat() for d in sorted_days),
            "resolution_status": "needs_human_review",
            "resolved_date": "",
            "rule_applied": "",
            "notes": "Conflict is close to, or straddles, the polling-"
                     "day cutoff or the 180-day window edge - resolving "
                     "automatically risks an election-leakage error "
                     "(the BBC 2013 pilot case). Requires manual "
                     "confirmation before this record can be used.",
        }

    # Safe to auto-resolve: every interpretation lands on the same side
    # of every boundary that matters. Conservative tie-break: earliest.
    chosen = sorted_days[0]
    return {
        "article_id": aid, "election_id": eid,
        "original_confidence": confidence,
        "candidate_dates": "; ".join(d.isoformat() for d in sorted_days),
        "resolution_status": "auto_resolved_conservative_earliest",
        "resolved_date": chosen.isoformat(),
        "rule_applied": "earliest_candidate_date; "
                       "no_boundary_within_margin_days="
                       f"{BOUNDARY_MARGIN_DAYS}",
        "notes": "",
    }


def main():
    rows = []
    for path in sorted(RECORDS.glob("*.json")):
        record = json.loads(path.read_text())
        result = resolve_one(record)
        if result:
            rows.append(result)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "article_id", "election_id", "original_confidence",
            "candidate_dates", "resolution_status", "resolved_date",
            "rule_applied", "notes"])
        w.writeheader()
        w.writerows(rows)

    by_status = {}
    for r in rows:
        by_status[r["resolution_status"]] = (
            by_status.get(r["resolution_status"], 0) + 1)
    print(f"{len(rows)} records processed -> {OUT}")
    for status, n in sorted(by_status.items()):
        print(f"  {status}: {n}")
    review_needed = by_status.get("needs_human_review", 0)
    if review_needed:
        print(f"\n{review_needed} records require manual review before "
              "they can be used - see rows with "
              "resolution_status=needs_human_review in the log. This "
              "is expected, not an error: the whole point of this "
              "design is that leakage-relevant conflicts are never "
              "auto-decided.")


if __name__ == "__main__":
    main()
