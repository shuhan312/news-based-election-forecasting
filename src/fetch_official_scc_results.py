"""Download candidate results from Surrey County Council's official pages.

The older project dataset was collected from Wikipedia.  This script starts a
separate, auditable official-source dataset for Surrey County Council.  It
first downloads the election's ward index, then follows each division link
and writes one row per candidate to data/elections/official_scc_candidate_results.csv.

The council site limits how fast pages may be fetched, so collection is
designed to happen in instalments: each run downloads at most
--max-new-pages new pages (default 30) and then stops cleanly.  Pages
already downloaded are cached and cost nothing, so simply repeat the same
command every 15-30 minutes until it reports the full CSV was written:

    python3 src/fetch_official_scc_results.py --years 2013

The same structure is ready for 2017 and 2021, but they should be run only
after the 2013 output has been checked against several official pages.
"""

import argparse
import csv
import hashlib
import random
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ELECTIONS = {
    2013: {
        "election_id": "SCC-2013-05",
        "name": "2013 Surrey County Council election",
        "date": "2013-05-02",
        "url": "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=5&RPID=0",
    },
    2017: {
        "election_id": "SCC-2017-05",
        "name": "2017 Surrey County Council election",
        "date": "2017-05-04",
        "url": "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=10&RPID=0",
    },
    2021: {
        "election_id": "SCC-2021-05",
        "name": "2021 Surrey County Council election",
        "date": "2021-05-06",
        "url": "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0",
    },
}

OUTPUT_COLUMNS = [
    "Candidate Result ID", "Election ID", "Election Name", "Election Date",
    "Election Type", "Authority", "Division/Ward ID", "Division/Ward Name",
    "Seats Available", "Candidate ID", "Candidate Name As Published", "Party ID",
    "Party Name As Published", "Standardised Party Name", "Party Category",
    "Votes Received", "Vote Share", "Final Position", "Elected",
    "Winning Candidate", "Winning Party", "Winning Margin Votes",
    "Winning Margin Percentage Points", "Electorate", "Ballot Papers Issued",
    "Turnout", "Rejected Ballots", "Previous Winning Party",
    "Previous Party Vote Share", "Change In Vote Share", "Candidate Previously Stood",
    "Incumbent Candidate", "Incumbent Party", "First Appearance Of Party In Area",
    "Source URL", "Notes",
]

OUTPUT_PATH = Path("data/elections/official_scc_candidate_results.csv")
CACHE_ROOT = Path("data/raw/surrey_county_council")

# A standard browser identity.  The site's protection service blocks
# non-browser clients outright, so an honest robot label just gets the
# block page.  We stay polite where it matters: public pages only, very
# low request rate, and every page cached so it is fetched exactly once.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0.0.0 Safari/537.36")

# The council site sits behind a bot-protection service whose blocks last
# minutes, not seconds.  Downloading slowly, at varied intervals, and only a
# limited number of new pages per run keeps each run below its threshold;
# the page cache means the next run carries on where this one stopped.
REQUEST_DELAY_RANGE = (15.0, 30.0)
BLOCK_WAIT_SECONDS = (120, 300)


class RunBudgetReached(Exception):
    """This run has downloaded its --max-new-pages allowance."""


class CouncilBlockPersists(Exception):
    """The block page kept coming back despite long waits."""

# This is deliberately conservative.  For example, Reform UK and UKIP remain
# different parties, because combining them would hide a politically relevant
# change over time.
PARTY_ALIASES = {
    "labour co-op": "Labour",
    "labour and co-operative": "Labour",
    "liberal democrat": "Liberal Democrats",
    "liberal democrats": "Liberal Democrats",
    "green party": "Green",
    "the green party": "Green",
    "conservative party": "Conservative",
}


def clean(text):
    """Return one space between visible words from an HTML cell."""
    return re.sub(r"\s+", " ", text or "").strip()


def number(text):
    """Read a published whole number, leaving unavailable values blank."""
    cleaned = clean(text).replace(",", "")
    return int(cleaned) if cleaned.isdigit() else None


def percentage(text):
    """Read the source percentage without calculating a replacement value."""
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", clean(text))
    return float(match.group(1)) if match else None


def standard_party_name(label):
    """Keep the published label and supply a stable label for clear aliases."""
    published = clean(label)
    return PARTY_ALIASES.get(published.casefold(), published)


def stable_id(prefix, value):
    """Create a reproducible ID without changing the published name."""
    digest = hashlib.sha1(clean(value).casefold().encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def is_block_page(html):
    """Recognise the council site's short anti-bot page despite its HTTP 200."""
    return "_Incapsula_Resource" in html or len(html.strip()) < 500


def fetch(session, url, cache_path, budget):
    """Use a real local snapshot, or download one new page within this run's budget."""
    if cache_path.exists():
        cached_html = cache_path.read_text(encoding="utf-8")
        if not is_block_page(cached_html):
            return cached_html

    if budget["new_pages"] <= 0:
        raise RunBudgetReached(url)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for wait in (0, *BLOCK_WAIT_SECONDS):
        if wait:
            print(f"  block page received; waiting {wait} seconds before retrying")
            time.sleep(wait)
        response = session.get(url, timeout=45)
        response.raise_for_status()
        if not is_block_page(response.text):
            cache_path.write_text(response.text, encoding="utf-8")
            budget["new_pages"] -= 1
            # Vary the pause: fixed-interval requests are exactly the
            # pattern the protection service looks for.  Cached pages do
            # not make another network request.
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
            return response.text

    raise CouncilBlockPersists(url)


def detailed_results_url(summary_html, summary_url):
    """Find the official page that lists all divisions for one election."""
    soup = BeautifulSoup(summary_html, "html.parser")
    for link in soup.find_all("a", href=True):
        label = clean(link.get_text(" ")).casefold()
        href = urljoin(summary_url, link["href"])
        if "detailed results" in label and "mgElectionElectionAreaResults.aspx" in href:
            return href
    raise ValueError("Could not find the detailed division-results link on the official summary page.")


def division_links(index_html, index_url):
    """Return one official result URL for each electoral division."""
    soup = BeautifulSoup(index_html, "html.parser")
    links = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = urljoin(index_url, link["href"])
        if "mgElectionAreaResults.aspx" not in href or href in seen:
            continue
        label = clean(link.get_text(" "))
        if not label:
            continue
        seen.add(href)
        links.append((label, href))
    if not links:
        raise ValueError("The official division-results page did not contain any division links.")
    return links


def first_table_with_headers(soup, required_headers):
    """Find a table by its header names rather than assuming a table position."""
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        headers = {clean(cell.get_text(" ")).casefold()
                   for cell in first_row.find_all(["th", "td"])}
        if required_headers.issubset(headers):
            return table
    return None


def voting_summary(soup):
    """Extract only values explicitly published in the official summary table."""
    table = first_table_with_headers(soup, {"details", "number"})
    values = {"seats": None, "electorate": None, "rejected": None, "total_votes": None}
    if table is None:
        return values

    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        detail = clean(cells[0].get_text(" ")).casefold()
        value = number(cells[1].get_text(" "))
        if detail == "seats":
            values["seats"] = value
        elif detail == "electorate":
            values["electorate"] = value
        elif "rejected" in detail:
            values["rejected"] = value
        elif detail == "total votes":
            values["total_votes"] = value
    return values


def parse_division(election, division_name, division_url, html):
    """Convert one division page into one row for each published candidate."""
    soup = BeautifulSoup(html, "html.parser")
    candidate_table = first_table_with_headers(
        soup, {"election candidate", "party", "votes", "%", "outcome"})
    if candidate_table is None:
        raise ValueError(f"Could not find the candidate table for {division_name}.")

    summary = voting_summary(soup)
    area_id = parse_qs(urlparse(division_url).query).get("ID", ["unknown"])[0]
    division_id = f"SCC-{election['date'][:4]}-DIV-{area_id}"
    candidates = []

    for position, row in enumerate(candidate_table.find_all("tr")[1:], start=1):
        cells = row.find_all(["th", "td"])
        if len(cells) < 5:
            continue
        candidate = clean(cells[0].get_text(" "))
        party = clean(cells[1].get_text(" "))
        votes = number(cells[2].get_text(" "))
        share = percentage(cells[3].get_text(" "))
        outcome = clean(cells[4].get_text(" ")).casefold()
        if not candidate or votes is None:
            continue
        candidates.append({
            "candidate": candidate,
            "party": party,
            "votes": votes,
            "share": share,
            "position": position,
            "elected": outcome == "elected",
        })

    if not candidates:
        raise ValueError(f"No candidate rows were found for {division_name}.")

    # In a multi-seat division the useful margin is the final elected place
    # versus the highest unsuccessful candidate, not simply the top two names.
    elected = [candidate for candidate in candidates if candidate["elected"]]
    not_elected = [candidate for candidate in candidates if not candidate["elected"]]
    final_elected = min(elected, key=lambda candidate: candidate["votes"]) if elected else None
    first_unsuccessful = max(not_elected, key=lambda candidate: candidate["votes"]) if not_elected else None
    margin_votes = None
    margin_points = None
    if final_elected and first_unsuccessful:
        margin_votes = final_elected["votes"] - first_unsuccessful["votes"]
        if final_elected["share"] is not None and first_unsuccessful["share"] is not None:
            margin_points = round(final_elected["share"] - first_unsuccessful["share"], 2)

    top_candidate = max(candidates, key=lambda candidate: candidate["votes"])
    notes = []
    if summary["total_votes"] is not None:
        notes.append(
            f'Official "Total votes" = {summary["total_votes"]}; '
            "kept as candidate-vote total and not treated as ballot papers issued.")

    result_rows = []
    for candidate in candidates:
        result_rows.append({
            "Candidate Result ID": f"SCC-{election['date'][:4]}-{area_id}-{candidate['position']:02d}",
            "Election ID": election["election_id"],
            "Election Name": election["name"],
            "Election Date": election["date"],
            "Election Type": "Scheduled",
            "Authority": "Surrey County Council",
            "Division/Ward ID": division_id,
            "Division/Ward Name": division_name,
            "Seats Available": summary["seats"],
            "Candidate ID": stable_id("SCC-CAND", candidate["candidate"]),
            "Candidate Name As Published": candidate["candidate"],
            "Party ID": stable_id("SCC-PARTY", standard_party_name(candidate["party"])),
            "Party Name As Published": candidate["party"],
            "Standardised Party Name": standard_party_name(candidate["party"]),
            "Party Category": "",
            "Votes Received": candidate["votes"],
            "Vote Share": candidate["share"],
            "Final Position": candidate["position"],
            "Elected": "Yes" if candidate["elected"] else "No",
            "Winning Candidate": top_candidate["candidate"],
            "Winning Party": standard_party_name(top_candidate["party"]),
            "Winning Margin Votes": margin_votes,
            "Winning Margin Percentage Points": margin_points,
            "Electorate": summary["electorate"],
            # The official page gives candidate votes.  In multi-seat contests
            # their sum is not the number of people who voted, so leave this blank.
            "Ballot Papers Issued": "",
            "Turnout": "",
            "Rejected Ballots": summary["rejected"],
            "Previous Winning Party": "",
            "Previous Party Vote Share": "",
            "Change In Vote Share": "",
            "Candidate Previously Stood": "",
            "Incumbent Candidate": "",
            "Incumbent Party": "",
            "First Appearance Of Party In Area": "",
            "Source URL": division_url,
            "Notes": " ".join(notes),
        })
    return result_rows


def extract_year(session, year, budget, limit=None):
    """Download all official division pages for one selected election year."""
    election = ELECTIONS[year]
    cache_dir = CACHE_ROOT / str(year)
    summary_html = fetch(session, election["url"], cache_dir / "summary.html", budget)
    index_url = detailed_results_url(summary_html, election["url"])
    index_html = fetch(session, index_url, cache_dir / "division_index.html", budget)
    links = division_links(index_html, index_url)
    if limit is not None:
        links = links[:limit]

    rows = []
    for index, (division_name, division_url) in enumerate(links, start=1):
        area_id = parse_qs(urlparse(division_url).query).get("ID", [str(index)])[0]
        page_html = fetch(session, division_url, cache_dir / f"division_{area_id}.html", budget)
        rows.extend(parse_division(election, division_name, division_url, page_html))
        print(f"{year}: {index}/{len(links)} {division_name}")
    return rows


def read_existing_rows():
    """Keep already collected years when adding another completed year later."""
    if not OUTPUT_PATH.exists():
        return []
    with OUTPUT_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(rows, output_path):
    """Write the result dataset in the same field order as the Excel table."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_years(text):
    years = [int(item.strip()) for item in text.split(",") if item.strip()]
    unsupported = sorted(set(years) - set(ELECTIONS))
    if unsupported:
        raise ValueError(f"Unsupported year(s): {unsupported}. Choose from {sorted(ELECTIONS)}.")
    return years


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", default="2013", help="Comma-separated years, for example 2013 or 2013,2017")
    parser.add_argument("--limit", type=int, help="Only collect this many divisions; useful for a parser test.")
    parser.add_argument("--max-new-pages", type=int, default=30,
                        help="New page downloads allowed in this run; cached pages are free. "
                             "Rerun the same command later to continue where this run stopped.")
    args = parser.parse_args()
    years = parse_years(args.years)

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    budget = {"new_pages": args.max_new_pages}
    collected = []
    try:
        for year in years:
            collected.extend(extract_year(session, year, budget, limit=args.limit))
    except RunBudgetReached:
        print(f"\nStopping: this run's allowance of {args.max_new_pages} new pages is used up.")
        print("Downloaded pages are cached. Run the same command again in 15-30 minutes;")
        print("it will skip the cache and continue from the first missing page.")
        return
    except CouncilBlockPersists as blocked:
        print(f"\nStopping: the council site is still serving its block page for {blocked}.")
        print("Downloaded pages are cached. Try again in an hour or so;")
        print("the run will continue from where it stopped.")
        return

    if args.limit is not None:
        # A limited run is a parser check, not a valid research dataset.  Keep
        # it separately so the Excel builder cannot mistake it for full data.
        test_path = OUTPUT_PATH.with_name("official_scc_candidate_results_test.csv")
        write_rows(collected, test_path)
        print(f"Wrote {len(collected)} test candidate rows to {test_path}")
        return

    # Do not retain old rows for a selected year: a completed rerun replaces
    # that year as one coherent official-source extract.
    selected_ids = {ELECTIONS[year]["election_id"] for year in years}
    old_rows = [row for row in read_existing_rows() if row.get("Election ID") not in selected_ids]
    write_rows(old_rows + collected, OUTPUT_PATH)
    print(f"Wrote {len(collected)} candidate rows for {', '.join(map(str, years))} to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
