"""Collect 2026 East Surrey and West Surrey Council candidate results.

The two 2026 councils are separate validation datasets.  This script keeps
their ward results in separate CSV files and does not try to map the new wards
onto historic Surrey County Council divisions.

Usage:
    python3 src/fetch_2026_surrey_results.py --councils east,west
    python3 src/fetch_2026_surrey_results.py --councils east --limit 2
"""

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Reuse the page cache, anti-block-page check, and candidate-table parser used
# for the historic official Surrey County Council result pages.
from fetch_official_scc_results import (
    CouncilBlockPersists,
    RunBudgetReached,
    USER_AGENT,
    fetch,
    is_block_page,
    parse_division,
)


COUNCILS = {
    "east": {
        "election_id": "EAST-2026-05",
        "name": "2026 East Surrey Council election",
        "date": "2026-05-07",
        "authority": "East Surrey Council",
        # This is the supervisor's own East Surrey URL from the project
        # brief, not a mycouncil.surreycc.gov.uk page: it is a plain,
        # unblocked "Future Surrey" landing page (verified 2026-07-22,
        # HTTP 200, no Incapsula challenge) that links out to the usual
        # mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=..&EID=2037
        # ward pages ward_links() already knows how to parse. The
        # previous value here (mgElectionElectionAreaResults.aspx?EID=49)
        # was a guessed URL on the wrong host/path pattern and never
        # resolved to a real index page - that is why every prior run
        # reported "no usable index page yet" rather than an Incapsula
        # block on the index step itself.
        "index_url": "https://www10.surreycc.gov.uk/electionmap/eastSurrey/",
        "output": Path("data/elections/2026_east_surrey_results.csv"),
        "expected_wards": 36,
        "expected_seats": 72,
        "expected_candidates": 379,
        "expected_electorate": 406177,
        "expected_ballot_papers": 199485,
    },
    "west": {
        "election_id": "WEST-2026-05",
        "name": "2026 West Surrey Council election",
        "date": "2026-05-07",
        "authority": "West Surrey Council",
        # Same fix as East Surrey above; casing (WestSurrey, capital W)
        # matches the supervisor's brief exactly and was verified live.
        "index_url": "https://www10.surreycc.gov.uk/electionmap/WestSurrey/",
        "output": Path("data/elections/2026_west_surrey_results.csv"),
        "expected_wards": 45,
        "expected_seats": 90,
        "expected_candidates": 452,
        "expected_electorate": 488899,
        "expected_ballot_papers": 225203,
    },
}

OUTPUT_COLUMNS = [
    "Candidate Result ID", "Election Name", "Election Date", "Authority",
    "Ward Name", "Seats Available", "Candidate Name As Published",
    "Party Name As Published", "Standardised Party Name", "Votes Received",
    "Vote Share", "Final Position", "Elected", "Electorate",
    "Ballot Papers Issued", "Turnout", "Rejected Ballots", "Source URL", "Notes",
]

CACHE_ROOT = Path("data/raw/surrey_2026")


def ward_links(index_html, index_url):
    """Return each unique official ward-result link from the results index."""
    soup = BeautifulSoup(index_html, "html.parser")
    links = []
    seen_ids = set()
    for link in soup.find_all("a", href=True):
        href = urljoin(index_url, link["href"])
        if "mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx" not in href:
            continue
        area_id = parse_qs(urlparse(href).query).get("ID", [""])[0]
        if not area_id or area_id in seen_ids:
            continue
        ward_name = " ".join(link.get_text(" ", strip=True).split())
        if not ward_name:
            continue
        seen_ids.add(area_id)
        links.append((ward_name, href))
    if not links:
        raise ValueError("No official ward-result links were found on the 2026 results index.")
    return links


def to_tab_row(source_row):
    """Keep only the fields used by the separate East/West workbook tabs."""
    return {
        "Candidate Result ID": source_row["Candidate Result ID"],
        "Election Name": source_row["Election Name"],
        "Election Date": source_row["Election Date"],
        "Authority": source_row["Authority"],
        "Ward Name": source_row["Division/Ward Name"],
        "Seats Available": source_row["Seats Available"],
        "Candidate Name As Published": source_row["Candidate Name As Published"],
        "Party Name As Published": source_row["Party Name As Published"],
        "Standardised Party Name": source_row["Standardised Party Name"],
        "Votes Received": source_row["Votes Received"],
        "Vote Share": source_row["Vote Share"],
        "Final Position": source_row["Final Position"],
        "Elected": source_row["Elected"],
        "Electorate": source_row["Electorate"],
        "Ballot Papers Issued": source_row["Ballot Papers Issued"],
        "Turnout": source_row["Turnout"],
        "Rejected Ballots": source_row["Rejected Ballots"],
        "Source URL": source_row["Source URL"],
        "Notes": source_row["Notes"],
    }


def cache_name_for(url):
    """Use the official area ID so cache files cannot drift when link order changes."""
    area_id = parse_qs(urlparse(url).query).get("ID", [""])[0]
    if not area_id or not area_id.isdigit():
        raise ValueError(f"Ward result URL has no numeric ID: {url}")
    return f"ward_{area_id}.html"


def collect_council(session, key, budget, limit=None):
    """Parse cached wards and fetch only missing pages, stopping on a block."""
    council = COUNCILS[key]
    election = {
        "election_id": council["election_id"],
        "name": council["name"],
        "date": council["date"],
    }
    cache_dir = CACHE_ROOT / key
    index_html = fetch(session, council["index_url"], cache_dir / "result_index.html", budget)
    wards = ward_links(index_html, council["index_url"])
    if limit is not None:
        wards = wards[:limit]

    rows = []
    stop_reason = None
    completed_wards = []
    missing_wards = []
    parse_failures = []
    network_stopped = False
    for number, (ward_name, ward_url) in enumerate(wards, start=1):
        cache_path = cache_dir / cache_name_for(ward_url)
        ward_html = None
        if cache_path.exists():
            candidate_html = cache_path.read_text(encoding="utf-8")
            if not is_block_page(candidate_html):
                ward_html = candidate_html

        if ward_html is None and not network_stopped:
            try:
                ward_html = fetch(session, ward_url, cache_path, budget)
            except (RunBudgetReached, CouncilBlockPersists, requests.RequestException, ValueError) as exc:
                stop_reason = exc
                network_stopped = True

        if ward_html is None:
            missing_wards.append(ward_name)
            continue

        try:
            source_rows = parse_division(election, ward_name, ward_url, ward_html)
        except ValueError as exc:
            parse_failures.append(f"{ward_name}: {exc}")
            continue
        for source_row in source_rows:
            source_row["Authority"] = council["authority"]
            rows.append(to_tab_row(source_row))
        completed_wards.append(ward_name)
        print(f"{council['authority']}: {number}/{len(wards)} {ward_name}", flush=True)
    return rows, wards, completed_wards, missing_wards, parse_failures, stop_reason


def write_rows(rows, output_path):
    """Write one flat, reproducible CSV for one council only."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, output_path)


def write_json(payload, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, output_path)


def validate_complete(council, rows, ward_names, all_wards):
    """Return human-readable failures; an empty list means final-ready."""
    failures = []
    if len(all_wards) != council["expected_wards"]:
        failures.append(f"index has {len(all_wards)} wards, expected {council['expected_wards']}")
    if len(set(ward_names)) != council["expected_wards"]:
        failures.append(f"parsed {len(set(ward_names))} wards, expected {council['expected_wards']}")
    if len(rows) != council["expected_candidates"]:
        failures.append(f"parsed {len(rows)} candidates, expected {council['expected_candidates']}")
    elected = sum(row["Elected"] == "Yes" for row in rows)
    if elected != council["expected_seats"]:
        failures.append(f"parsed {elected} elected candidates, expected {council['expected_seats']}")
    malformed = sorted({
        row["Ward Name"] for row in rows
        if row["Seats Available"] != 2
    })
    if malformed:
        failures.append(f"non-two-seat ward data: {', '.join(malformed)}")
    elected_by_ward = Counter(
        row["Ward Name"] for row in rows if row["Elected"] == "Yes"
    )
    wrong_elected_count = sorted(
        ward for ward in set(ward_names) if elected_by_ward[ward] != 2
    )
    if wrong_elected_count:
        failures.append(f"wards without exactly two elected candidates: {', '.join(wrong_elected_count)}")
    result_ids = [row["Candidate Result ID"] for row in rows]
    if len(set(result_ids)) != len(result_ids):
        failures.append("duplicate Candidate Result ID values")
    missing_votes = sorted({row["Ward Name"] for row in rows if row["Votes Received"] == ""})
    if missing_votes:
        failures.append(f"candidate votes missing in: {', '.join(missing_votes)}")
    first_row_by_ward = {}
    for row in rows:
        first_row_by_ward.setdefault(row["Ward Name"], row)
    if len(first_row_by_ward) == council["expected_wards"]:
        if any(row["Electorate"] == "" for row in first_row_by_ward.values()):
            failures.append("one or more ward electorates are missing")
        else:
            electorate = sum(row["Electorate"] for row in first_row_by_ward.values())
            if electorate != council["expected_electorate"]:
                failures.append(
                    f"ward electorates sum to {electorate}, expected {council['expected_electorate']}"
                )
        if any(row["Ballot Papers Issued"] == "" for row in first_row_by_ward.values()):
            failures.append("one or more ward ballot-paper counts are missing")
        else:
            ballots = sum(row["Ballot Papers Issued"] for row in first_row_by_ward.values())
            if ballots != council["expected_ballot_papers"]:
                failures.append(
                    f"ward ballot papers sum to {ballots}, expected {council['expected_ballot_papers']}"
                )
    return failures


def progress_paths(final_path):
    return (
        final_path.with_name(final_path.stem + "_partial.csv"),
        final_path.with_name(final_path.stem + "_status.json"),
    )


def parse_councils(text):
    keys = [item.strip().casefold() for item in text.split(",") if item.strip()]
    invalid = sorted(set(keys) - set(COUNCILS))
    if invalid:
        raise ValueError(f"Unknown council(s): {invalid}. Choose east, west, or east,west.")
    return keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--councils", default="east,west", help="east, west, or east,west")
    parser.add_argument("--limit", type=int, help="Only collect this many wards; used for parser checks.")
    parser.add_argument("--max-new-pages", type=int, default=1,
                        help="Maximum new page downloads in one run. Cached pages do not count.")
    parser.add_argument("--offline", action="store_true",
                        help="Use cached pages only; make no network requests.")
    args = parser.parse_args()
    council_keys = parse_councils(args.councils)

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    })

    for key in council_keys:
        council = COUNCILS[key]
        # Each council gets its own allowance, so an incomplete East run does
        # not consume West's opportunity to make progress (and vice versa).
        budget = {"new_pages": 0 if args.offline else args.max_new_pages}
        try:
            rows, wards, completed_wards, missing_wards, parse_failures, stop_reason = collect_council(
                session, key, budget, limit=args.limit)
        except (RunBudgetReached, CouncilBlockPersists, requests.RequestException, ValueError) as exc:
            print(f"{council['authority']}: no usable index page yet ({exc}).")
            continue

        if args.limit is not None:
            output_path = COUNCILS[key]["output"]
            output_path = output_path.with_name(output_path.stem + "_test.csv")
            write_rows(rows, output_path)
            print(f"Wrote {len(rows)} rows to {output_path}")
            continue

        final_path = council["output"]
        partial_path, status_path = progress_paths(final_path)
        write_rows(rows, partial_path)
        failures = validate_complete(council, rows, completed_wards, wards)
        failures.extend(parse_failures)
        status = {
            "council": council["authority"],
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "index_url": council["index_url"],
            "wards_expected": council["expected_wards"],
            "wards_in_index": len(wards),
            "wards_completed": len(completed_wards),
            "candidates_expected": council["expected_candidates"],
            "candidates_parsed": len(rows),
            "complete": not failures and stop_reason is None,
            "validation_failures": failures,
            "missing_wards": missing_wards,
            "stop_reason": type(stop_reason).__name__ if stop_reason else None,
            "next_missing_ward": missing_wards[0] if missing_wards else None,
        }
        write_json(status, status_path)

        if status["complete"]:
            write_rows(rows, final_path)
            print(f"COMPLETE: wrote {len(rows)} validated rows to {final_path}")
        else:
            print(
                f"INCOMPLETE: {len(completed_wards)}/{len(wards)} wards and {len(rows)} candidates. "
                f"Progress: {partial_path}; status: {status_path}"
            )
            if stop_reason:
                print(f"Stopped safely: {type(stop_reason).__name__}. Resume later or use --offline to audit cache.")


if __name__ == "__main__":
    main()
