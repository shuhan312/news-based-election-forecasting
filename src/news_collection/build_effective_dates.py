"""Merge every stage of date resolution into one lookup table:
article_id -> the single date the Article Eligibility Assessment stage
(E1-E10) should use, or an honest explanation of why there isn't one.

Three upstream stages each know part of the picture and none of them
alone is enough for E1 ("at least Probable confidence date"):
  * raw collection (schema.py) - Confirmed/Probable records already
    have a usable published_date; everything else was left null on
    purpose (raw_news_schema.md)
  * resolve_publication_dates.py - auto-resolves the conflicts that
    cannot affect an eligibility decision either way, and routes
    everything that could to date_resolution_log.csv's
    needs_human_review / unresolvable_missing_evidence buckets
  * manual_review_decisions.csv - human-reviewed outcomes for specific
    boundary-relevant conflicts or evidence-recovery cases (the BBC
    2013 pilot, the two retrieval-time-contamination cases, the
    Addlestone by-election, and the three PDF-recovery cases)

Nothing here invents a date. A record with no resolution from any of
the three sources above gets date_status=no_date_evidence and an empty
effective_date - eligibility rule E1 must exclude it, not guess.

This also carries forward (not applies) the two relevance-flag files
built the same day (guardian_geographic_relevance_flags.csv,
serpapi_domain_relevance_flags.csv) as an informational column, since
a record can have a perfectly good date and still be flagged as
off-topic - that is a relevance judgement E1-E10 makes, not this stage.

Usage:
    python3 -m src.news_collection.build_effective_dates
"""

import csv
import json
from pathlib import Path

RECORDS = Path("data/raw/news/records")
RESOLUTION_LOG = Path("news_collection/date_resolution_log.csv")
MANUAL_DECISIONS = Path("news_collection/manual_review_decisions.csv")
GUARDIAN_FLAGS = Path("news_collection/guardian_geographic_relevance_flags.csv")
SERPAPI_FLAGS = Path("news_collection/serpapi_domain_relevance_flags.csv")
OUT = Path("news_collection/effective_dates.csv")

AUTO_USABLE = {"auto_resolved_conservative_earliest", "resolved_single_value"}


def load_csv(path):
    return list(csv.DictReader(path.open())) if path.exists() else []


def main():
    resolution_by_id = {r["article_id"]: r for r in load_csv(RESOLUTION_LOG)}
    manual_by_id = {r["article_id"]: r for r in load_csv(MANUAL_DECISIONS)
                    if r.get("article_id")}
    irrelevant_ids = ({r["article_id"] for r in load_csv(GUARDIAN_FLAGS)} |
                      {r["article_id"] for r in load_csv(SERPAPI_FLAGS)})

    rows = []
    status_counts = {}
    for path in sorted(RECORDS.glob("*.json")):
        rec = json.loads(path.read_text())
        aid = rec["article_id"]
        eid = rec["discovered_for_election"]
        confidence = rec["dates"]["date_confidence"]
        flagged = "yes" if aid in irrelevant_ids else ""

        if confidence in ("Confirmed", "Probable"):
            row = {"article_id": aid, "election_id": eid,
                  "effective_date": rec["dates"]["published_date"],
                  "date_status": "usable", "date_source": "raw_collection",
                  "known_irrelevant_flag": flagged, "notes": ""}
        elif aid in manual_by_id:
            m = manual_by_id[aid]
            row = {"article_id": aid, "election_id": eid,
                  "effective_date": m["decided_date"],
                  "date_status": "usable", "date_source": "manual_review",
                  "known_irrelevant_flag": flagged,
                  "notes": f"decided_by={m['decided_by']}"}
        elif aid in resolution_by_id and \
                resolution_by_id[aid]["resolution_status"] in AUTO_USABLE:
            r = resolution_by_id[aid]
            row = {"article_id": aid, "election_id": eid,
                  "effective_date": r["resolved_date"],
                  "date_status": "usable",
                  "date_source": "auto_resolution_stage",
                  "known_irrelevant_flag": flagged,
                  "notes": r["rule_applied"]}
        elif aid in resolution_by_id and \
                resolution_by_id[aid]["resolution_status"] == \
                "needs_human_review":
            row = {"article_id": aid, "election_id": eid,
                  "effective_date": "",
                  "date_status": "pending_human_review",
                  "date_source": "", "known_irrelevant_flag": flagged,
                  "notes": "Boundary-relevant conflict, no reviewed "
                           "decision yet - see date_resolution_log.csv."}
        else:
            # Either genuinely no evidence (unresolvable_missing_evidence,
            # no manual decision), or a Confirmed/Probable-adjacent state
            # that never reached resolve_publication_dates.py at all -
            # both are honestly "no usable date" for this record.
            row = {"article_id": aid, "election_id": eid,
                  "effective_date": "", "date_status": "no_date_evidence",
                  "date_source": "", "known_irrelevant_flag": flagged,
                  "notes": ""}

        status_counts[row["date_status"]] = (
            status_counts.get(row["date_status"], 0) + 1)
        rows.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} records -> {OUT}")
    for status, n in sorted(status_counts.items()):
        print(f"  {status}: {n}")
    flagged_and_usable = sum(1 for r in rows if r["date_status"] == "usable"
                             and r["known_irrelevant_flag"] == "yes")
    print(f"\n  of which 'usable' but already flagged non-UK/off-topic: "
          f"{flagged_and_usable} (date is fine; E1-E10 still excludes "
          f"these on relevance grounds)")


if __name__ == "__main__":
    main()
