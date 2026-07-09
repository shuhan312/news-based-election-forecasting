"""Extract ward-level election results from the Wikipedia pages in the calendar.

For every 2017-2024 election in data/elections/election_calendar.csv this
script downloads the Wikipedia article (cached in data/raw/wikipedia/, so
pages are only fetched once) and pulls out each ward's results table:
one row per candidate with party, votes and vote share, plus the ward
turnout where the page provides it.

Everything is combined into one long table:
  data/elections/results_2017_2024.csv
  columns: year, council, ward, party, candidate, votes, vote_share, turnout

Wikipedia result tables are hand-edited and vary between pages, so the
parser is defensive: it reports per page how many tables and candidate
rows it recognised, and unrecognised rows are skipped, not guessed.
Spot-check the output against official council result pages before use.

Usage:  python src/fetch_election_results.py
        (needs: pip install beautifulsoup4)
"""

import re
import time
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


def ward_name(table):
    """Ward = the table's caption, else the nearest heading above it."""
    if table.caption:
        return re.sub(r"\s+", " ", clean(table.caption.get_text(" ")))
    for heading in table.find_all_previous(["h3", "h4", "h2"]):
        return clean(heading.get_text())
    return ""


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
        rows.append({"party": texts[1], "candidate": texts[2],
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
        for table in soup.find_all("table", class_="wikitable"):
            rows, turnout = parse_table(table)
            if not rows:
                continue
            ward = ward_name(table)
            if "election result" in ward.lower():  # page-level summary, not a ward
                continue
            for r in rows:
                r.update({"year": e["year"], "council": e["council"],
                          "ward": ward, "turnout": turnout})
            all_rows.extend(rows)
            n_tables += 1
            n_rows += len(rows)
        print(f"{e['year']} {e['council']}: {n_tables} ward tables, {n_rows} candidate rows")

    df = pd.DataFrame(all_rows)[["year", "council", "ward", "party",
                                 "candidate", "votes", "vote_share", "turnout"]]
    df.to_csv(OUT_PATH, index=False)
    print(f"\n{len(df)} candidate rows -> {OUT_PATH}")
    print("\nRows per year:")
    print(df["year"].value_counts().sort_index().to_string())
    print("\nTop parties by row count:")
    print(df["party"].value_counts().head(8).to_string())


if __name__ == "__main__":
    main()
