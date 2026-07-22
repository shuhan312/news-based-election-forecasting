"""Convert the validated 2026 SerpAPI-extractor workbooks into
data/elections/2026_east_surrey_results.csv and 2026_west_surrey_results.csv,
in the same column shape as the completed historical baseline table
(data/elections/results_2017_2024.csv), so 2026 slots into the existing,
already-validated feature pipeline without a bespoke schema.

Why this script exists rather than a fresh scrape
--------------------------------------------------
An earlier attempt (src/fetch_2026_surrey_results.py) tried to scrape
mycouncil.surreycc.gov.uk directly and was blocked by the site's
Incapsula anti-bot protection even after the project's existing
retry/backoff logic. The supervisor's own brief for this project
(Supervisor Requirement/Extraction Tool Prompt.txt) anticipated exactly
this and specifies an indexed-search-based extractor instead of direct
scraping. That tool already exists (surrey-election-extractor/) and has
already been run to completion for both 2026 councils:
    outputs/2026_east_full_extraction/surrey_county_council_2026.xlsx
    outputs/2026_west_full_extraction/surrey_county_council_2026.xlsx
with 0 failed extraction attempts and 0 failed validation checks for
both. This script only READS those two workbooks and reshapes them; it
does not re-run any extraction or touch the extractor's own code.

Two data-quality points a naive conversion would get wrong
------------------------------------------------------------
1. The extractor's own summary .md files report "0 incomplete wards",
   but every ward's Index row is actually marked "Incomplete" - the one
   missing field is a literal `election_name` label string, not any
   candidate or vote figure (verified by inspecting the Index and a
   sample ward sheet directly). This script does not trust the summary
   claim; it re-derives ward-level completeness from the Index sheet
   itself and records the discrepancy in the conversion log.
2. The 2026 election introduced two-member wards (the supervisor's
   brief: "the 2026 elections used new two-member wards"), so a voter
   can cast up to two candidate votes. The workbook's "Total votes"
   figure is the SUM of all candidates' votes, not the number of
   people who voted - using it as `people_who_voted` would silently
   inflate 2026 turnout relative to the single-member 2013-2021
   elections. `Ballot papers issued` is the correct people-who-voted
   analogue (confirmed: Ballot papers issued / Electorate reproduces
   the workbook's own published Turnout figure for a sample ward).
   This script uses Ballot papers issued for that column and keeps the
   candidate-vote sum in a separate, clearly-named column.

Party standardisation
----------------------
Party names are matched against the already-completed
data/elections/party_name_standardisation.csv lookup where possible.
2026 introduces parties/alliances with no historic precedent (Reform
UK contested seats for the first time; several bespoke independent
alliances appear, e.g. "Ashtead Independent, working with Ashtead
Residents"). Unmatched party strings are NOT guessed at: the raw
string is kept as party_canonical fallback and the row is flagged in
the conversion log, so a human can extend the standardisation table
deliberately later (this is exactly the project's own "Party History
and New Entrants" workflow) rather than have this script invent one.

Usage:
    python3 src/convert_2026_extractor_output.py
"""

import csv
import json
from pathlib import Path

import openpyxl

WORKBOOKS = {
    "east": Path("surrey-election-extractor/outputs/2026_east_full_extraction/"
                 "surrey_county_council_2026.xlsx"),
    "west": Path("surrey-election-extractor/outputs/2026_west_full_extraction/"
                 "surrey_county_council_2026.xlsx"),
}
AUTHORITY = {"east": "East Surrey Council", "west": "West Surrey Council"}
ELECTION_ID = {"east": "EAST-2026-05", "west": "WEST-2026-05"}
ELECTION_NAME = {"east": "2026 East Surrey Council election",
                 "west": "2026 West Surrey Council election"}
POLLING_DATE = "2026-05-07"

OUT = {
    "east": Path("data/elections/2026_east_surrey_results.csv"),
    "west": Path("data/elections/2026_west_surrey_results.csv"),
}
LOG_OUT = Path("data/elections/2026_conversion_log.csv")

PARTY_LOOKUP_PATH = Path("data/elections/party_name_standardisation.csv")

# Column order matches results_2017_2024.csv (the completed historical
# baseline table) exactly, plus two 2026-specific columns appended at
# the end (never inserted in the middle, so any code reading the first
# N historic columns positionally is unaffected).
OUTPUT_COLUMNS = [
    "year", "council", "ward", "party_raw", "party_canonical", "candidate",
    "votes", "candidate_vote_share", "candidate_rank", "candidate_elected",
    "seats_contested", "people_who_voted", "registered_voters",
    "turnout_percent", "turnout_data_source", "turnout_is_reliable",
    "event_type", "polling_date", "source_url", "source_table_index",
    "source_caption", "source_heading", "source_section",
    # 2026-specific, appended (not present for 2013-2021 rows):
    "total_candidate_votes",  # sum of all candidates' votes in the ward;
                              # NOT the same as people_who_voted under a
                              # two-member ward (see module docstring)
    "ward_index_status",      # this ward's Index-sheet completeness
                              # status, preserved for audit even though
                              # it does not affect any figure used here
]


def load_party_lookup():
    """As-published party string -> standardised name, from the
    completed historical standardisation table. Read-only: this script
    never writes back to that file."""
    lookup = {}
    for row in csv.DictReader(PARTY_LOOKUP_PATH.open()):
        lookup[row["Party Name As Published"]] = row["Standardised Party Name"]
    return lookup


def parse_ward_sheet(ws):
    """Pull the Index metadata block, Table 1 (candidates) and Table 2
    (voting summary) out of one ward worksheet by locating their header
    rows rather than fixed row numbers, since blank spacer rows differ
    slightly between sheets."""
    rows = list(ws.iter_rows(values_only=True))

    status = None
    for r in rows:
        if r and r[0] == "Extraction status":
            status = r[1]
            break

    candidates, summary = [], {}
    section = None
    for r in rows:
        first = r[0] if r else None
        if first == "Candidate" and r[1] == "Party":
            section = "candidates"
            continue
        if first == "Detail" and r[1] == "Number":
            section = "summary"
            continue
        if first in (None, "") and all(v is None for v in r):
            # A blank spacer row always ends whichever table we were in
            # (candidates or summary); the next real row is either a
            # new table's header or a plain title we should ignore.
            section = None
            continue
        if section == "candidates" and first:
            candidates.append({
                "candidate": first, "party": r[1], "votes": r[2],
                "vote_share": r[3], "outcome": r[4],
            })
        elif section == "summary" and first:
            summary[first] = r[1]

    return status, candidates, summary


def convert_council(key, party_lookup, log_rows):
    wb = openpyxl.load_workbook(WORKBOOKS[key], data_only=True)
    idx = wb["Index"]
    # Index columns: Ward or Division, Worksheet, Election, Election Date,
    # Source URL, Status, Missing Fields, Validation Notes, Search Attempts
    index_rows = [
        {"ward": r[0], "worksheet": r[1], "source_url": r[4]}
        for r in idx.iter_rows(min_row=2, values_only=True) if r[0]
    ]

    out_rows = []
    for entry in index_rows:
        ws = wb[entry["worksheet"]]
        status, candidates, summary = parse_ward_sheet(ws)
        if not candidates:
            log_rows.append({
                "council": key, "ward": entry["ward"], "issue": "no_candidates_parsed",
                "detail": f"worksheet={entry['worksheet']}",
            })
            continue

        # Deterministic rank from published votes (ties broken by name,
        # so re-running this script always produces the same order) -
        # this ranks published figures, it does not invent any.
        ranked = sorted(candidates, key=lambda c: (-int(c["votes"]), c["candidate"]))
        rank_of = {id(c): i + 1 for i, c in enumerate(ranked)}
        total_candidate_votes = sum(int(c["votes"]) for c in candidates)

        seats = summary.get("Seats")
        ballot_papers_issued = summary.get("Ballot papers issued")
        electorate = summary.get("Electorate")
        turnout = summary.get("Turnout")

        for c in candidates:
            raw_party = c["party"]
            canonical = party_lookup.get(raw_party)
            if canonical is None:
                canonical = raw_party      # fallback: never invented,
                log_rows.append({          # just the raw string, flagged
                    "council": key, "ward": entry["ward"],
                    "issue": "party_not_in_standardisation_table",
                    "detail": raw_party,
                })
            out_rows.append({
                "year": "2026", "council": AUTHORITY[key],
                "ward": entry["ward"], "party_raw": raw_party,
                "party_canonical": canonical, "candidate": c["candidate"],
                "votes": c["votes"], "candidate_vote_share": c["vote_share"],
                "candidate_rank": rank_of[id(c)],
                "candidate_elected": c["outcome"] == "Elected",
                "seats_contested": seats,
                # People-who-voted analogue: ballot papers issued, NOT
                # the candidate-vote sum (see module docstring point 2).
                "people_who_voted": ballot_papers_issued,
                "registered_voters": electorate,
                "turnout_percent": turnout,
                "turnout_data_source": "official_result_page_via_serpapi_extractor",
                "turnout_is_reliable": True,
                "event_type": "scheduled", "polling_date": POLLING_DATE,
                "source_url": entry["source_url"],
                "source_table_index": "", "source_caption": "",
                "source_heading": "", "source_section": "",
                "total_candidate_votes": total_candidate_votes,
                "ward_index_status": status,
            })

        if status != "Complete":
            log_rows.append({
                "council": key, "ward": entry["ward"],
                "issue": "index_status_not_complete",
                "detail": f"status={status} (candidate/summary fields "
                          "present and used regardless; see docstring)",
            })

    OUT[key].parent.mkdir(parents=True, exist_ok=True)
    with OUT[key].open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(out_rows)
    print(f"{key}: {len(out_rows)} candidate rows -> {OUT[key]}")


def main():
    party_lookup = load_party_lookup()
    log_rows = []
    for key in ("east", "west"):
        convert_council(key, party_lookup, log_rows)

    LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
    with LOG_OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["council", "ward", "issue", "detail"])
        w.writeheader()
        w.writerows(log_rows)

    by_issue = {}
    for r in log_rows:
        by_issue[r["issue"]] = by_issue.get(r["issue"], 0) + 1
    print(f"\n{len(log_rows)} conversion notes -> {LOG_OUT}")
    print("by issue type:", by_issue)


if __name__ == "__main__":
    main()
