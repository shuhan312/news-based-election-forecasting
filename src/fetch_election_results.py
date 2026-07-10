"""Extract ward-level election results from the Wikipedia pages in the calendar.

For every 2017-2024 election in data/elections/election_calendar.csv this
script downloads the Wikipedia article (cached in data/raw/wikipedia/, so
pages are only fetched once) and pulls out each ward's results table:
one row per candidate with party, votes and vote share, plus the ward
turnout where the page provides it.

Everything is combined into one long table:
  data/elections/results_2017_2024.csv
  columns: year, council, ward, party_raw, party_canonical, candidate, votes,
           vote_share, turnout,
           event_type, polling_date, source metadata

The Wikipedia pages are living pages: a page for a scheduled election can
also later acquire tables for by-elections.  We therefore preserve the table
caption and nearby headings, and explicitly label each table as a scheduled
election or a by-election.  Downstream aggregation can then exclude
by-elections without trying to infer their type from the ward name.

Wikipedia result tables are hand-edited and vary between pages, so the
parser is defensive: it reports per page how many tables and candidate
rows it recognised, and unrecognised rows are skipped, not guessed.
Spot-check the output against official council result pages before use.

Usage:  python src/fetch_election_results.py
        (needs: pip install beautifulsoup4)
"""

import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

CALENDAR = Path("data/elections/election_calendar.csv")
CACHE_DIR = Path("data/raw/wikipedia")
OUT_PATH = Path("data/elections/results_2017_2024.csv")

# Rows in an election box that are bookkeeping, not candidates.
NON_CANDIDATE = re.compile(
    r"majority|turnout|registered electors|rejected|swing|gain|hold|total",
    re.IGNORECASE)

# Dates in Wikipedia captions/headings use a written month, e.g. "4 July
# 2024".  A source-page year is not enough because pages can contain later
# by-elections, so retain the actual polling date when the page states one.
POLLING_DATE = re.compile(
    r"\b(?P<day>[0-3]?\d)\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(?P<year>\d{4})\b",
    re.IGNORECASE)
BY_ELECTION = re.compile(r"\bby[-\s]?elections?\b", re.IGNORECASE)
# A scheduled all-out election can contain a note such as "2 seats due to a
# by-election".  That describes why an extra seat is vacant; it does not turn
# the whole table into a by-election.
DUE_TO_BY_ELECTION = re.compile(
    r"\bdue\s+to\s+(?:an?\s+)?by[-\s]?election\b", re.IGNORECASE)

# Keep the original Wikipedia label in party_raw and use this conservative
# mapping only for unambiguous spelling or naming variants.  Local resident
# groups remain distinct unless their alias is exact, because their local
# identity can be politically meaningful in a Surrey ward.
PARTY_ALIASES = {
    "reform": "Reform UK",
    "reform uk": "Reform UK",
    "labour co-op": "Labour",
    "labour and co-operative": "Labour",
    "labour and co-op": "Labour",
    "liberal democrat": "Liberal Democrats",
    "liberal democrats": "Liberal Democrats",
    "lib dem": "Liberal Democrats",
    "lib dems": "Liberal Democrats",
    "green party": "Green",
    "the green party": "Green",
    "conservative party": "Conservative",
    "residents associations": "Residents Association",
    "residents' association": "Residents Association",
    "residents' associations": "Residents Association",
}


def canonical_party(label):
    """Return a stable party label while retaining the raw label separately."""
    value = re.sub(r"\s+", " ", str(label)).strip()
    return PARTY_ALIASES.get(value.casefold(), value)


def download(url, cache_file):
    """Fetch a page once; afterwards serve it from the local cache."""
    if cache_file.exists():
        return cache_file.read_text()
    resp = requests.get(url, timeout=30,
                        headers={"User-Agent": "IRP election results collector"})
    resp.raise_for_status()
    cache_file.write_text(resp.text)
    time.sleep(1)
    return resp.text


def clean(text):
    """Strip footnote markers like [1] and surrounding whitespace."""
    return re.sub(r"\[.*?\]", "", text).strip()


def heading_before(table, names):
    """Return the nearest preceding heading of one of the requested levels."""
    heading = table.find_previous(names)
    return clean(heading.get_text(" ")) if heading else ""


def table_metadata(table):
    """Extract auditable context and an explicit election type for one table.

    Some by-election tables have a plain ward-name caption, while the date is
    only in their h3 heading and the word "by-election" only in their h2
    section.  Looking at all three levels prevents those tables being merged
    with the scheduled ward result later on.  A phrase such as "seats due to
    a by-election" is deliberately not treated as a by-election table.
    """
    caption = (re.sub(r"\s+", " ", clean(table.caption.get_text(" ")))
               if table.caption else "")
    heading = heading_before(table, ["h3", "h4"])
    section = heading_before(table, ["h2"])
    source_text = " ".join(part for part in (caption, heading, section) if part)

    match = POLLING_DATE.search(source_text)
    polling_date = None
    if match:
        # Store ISO dates so later scripts can reliably compare them with
        # publication dates and scheduled election dates.
        polling_date = datetime.strptime(match.group(0).title(), "%d %B %Y").date().isoformat()

    # A dedicated "By-elections" section is authoritative.  Outside one,
    # accept only an explicit by-election label in the local caption/heading;
    # this avoids false positives from normal tables with an extra vacancy.
    local_text = " ".join(part for part in (caption, heading) if part)
    is_by_election = (
        bool(BY_ELECTION.search(section)) or
        (bool(BY_ELECTION.search(local_text)) and
         not bool(DUE_TO_BY_ELECTION.search(local_text)))
    )

    return {
        "source_caption": caption,
        "source_heading": heading,
        "source_section": section,
        "event_type": "by_election" if is_by_election else "scheduled",
        "polling_date": polling_date,
    }


def ward_name(metadata):
    """Ward = table caption, falling back to its nearest local heading."""
    return metadata["source_caption"] or metadata["source_heading"]


def to_number(text, cast=int):
    try:
        return cast(text.replace(",", "").strip())
    except ValueError:
        return None


def parse_table(table):
    """Parse one election box. Returns (candidate rows, turnout or None)."""
    header = " ".join(th.get_text() for th in table.find_all("th"))
    # a ward results table always lists Party, Candidate and Votes;
    # summary tables (seats won etc.) lack a Candidate column
    if not ("Party" in header and "Candidate" in header and "Votes" in header):
        return [], None

    rows, turnout = [], None
    for tr in table.find_all("tr"):
        # candidate names are sometimes <th> (plainrowheaders variant),
        # so read every cell in order and work from the text pattern
        texts = [clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
        if not texts:
            continue
        first_label = texts[0] or (texts[1] if len(texts) > 1 else "")

        if NON_CANDIDATE.search(first_label[:30]):
            if first_label.lower().startswith("turnout"):
                numbers = [to_number(t) for t in texts[1:]]
                turnout = next((n for n in numbers if n is not None), None)
            continue
        # candidate row pattern: empty colour-swatch cell, then
        # party, candidate, votes, share
        if len(texts) < 5 or texts[0] != "":
            continue
        votes = to_number(texts[3])
        share = to_number(texts[4], float)
        if not texts[1] or votes is None:
            continue
        # summary tables sneak past the header check; their "candidate"
        # cell is a count, a real candidate name has letters in it
        if not re.search(r"[A-Za-z]", texts[2]):
            continue
        rows.append({"party_raw": texts[1],
                     "party_canonical": canonical_party(texts[1]),
                     "candidate": texts[2],
                     "votes": votes, "vote_share": share})
    return rows, turnout


def main():
    calendar = pd.read_csv(CALENDAR)
    calendar = calendar[calendar["wikipedia_page"].notna()
                        & (calendar["year"] <= 2024)]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for _, e in calendar.iterrows():
        cache_file = CACHE_DIR / (e["wikipedia_page"].replace(" ", "_") + ".html")
        html = download(e["url"], cache_file)
        soup = BeautifulSoup(html, "html.parser")

        n_tables, n_rows = 0, 0
        for table_index, table in enumerate(soup.find_all("table", class_="wikitable")):
            rows, turnout = parse_table(table)
            if not rows:
                continue
            metadata = table_metadata(table)
            ward = ward_name(metadata)
            if "election result" in ward.lower():  # page-level summary, not a ward
                continue
            for r in rows:
                r.update({"year": e["year"], "council": e["council"],
                          "ward": ward, "turnout": turnout,
                          "source_url": e["url"],
                          "source_table_index": table_index,
                          **metadata})
            all_rows.extend(rows)
            n_tables += 1
            n_rows += len(rows)
        print(f"{e['year']} {e['council']}: {n_tables} ward tables, {n_rows} candidate rows")

    df = pd.DataFrame(all_rows)[[
        "year", "council", "ward", "party_raw", "party_canonical", "candidate", "votes",
        "vote_share", "turnout", "event_type", "polling_date",
        "source_url", "source_table_index", "source_caption",
        "source_heading", "source_section",
    ]]
    df.to_csv(OUT_PATH, index=False)
    print(f"\n{len(df)} candidate rows -> {OUT_PATH}")
    print("\nCandidate rows by event type:")
    print(df["event_type"].value_counts().to_string())
    print("\nRows per year:")
    print(df["year"].value_counts().sort_index().to_string())
    print("\nTop parties by row count:")
    print(df["party_canonical"].value_counts().head(8).to_string())


if __name__ == "__main__":
    main()
