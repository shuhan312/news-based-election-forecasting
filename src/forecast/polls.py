"""National voting-intention polls, as a time-varying party signal.

Scrapes Wikipedia's UK opinion-polling tables, records each poll's fieldwork
end date and party shares, and derives the feature the models use: each
party's mean share over the 14 days before a polling day. Only polls whose
fieldwork ended before polling day are used, so no poll can contain
information from the vote itself.

Provenance: each page's Wikipedia revision id is stored with the polls, so
the exact source can be re-read later even if the page changes.

Usage:
  PYTHONPATH=.:src python -m forecast.polls fetch
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path("v2_design/direction1_data")    # small and public: committed
POLLS_CSV = OUT_DIR / "polls.csv"
SOURCES_JSON = OUT_DIR / "poll_sources.json"
HEADERS = {"User-Agent": "v2-election-research/1.0 (shuhanliu44@gmail.com)"}

# Each page covers the polls between two general elections.
PAGES = [
    "Opinion_polling_for_the_2017_United_Kingdom_general_election",
    "Opinion_polling_for_the_2019_United_Kingdom_general_election",
    "Opinion_polling_for_the_2024_United_Kingdom_general_election",
    "Opinion_polling_for_the_next_United_Kingdom_general_election",
]

# Column header -> party code. The Brexit Party renamed itself Reform UK in
# January 2021, so its column continues as REF.
COLUMN_PARTY = {
    "con": "CON", "lab": "LAB", "ld": "LD", "lib dem": "LD",
    "grn": "GRN", "green": "GRN", "ref": "REF", "reform": "REF",
    "brexit": "REF", "bxp": "REF", "brx": "REF", "ukip": "UKIP",
}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
     "nov", "dec"], start=1)}
WINDOW_DAYS = 14


# --- parsing -----------------------------------------------------------------------

def expand_table(table) -> list[list[str]]:
    """Table cells as a full grid, with rowspan/colspan cells repeated.

    Wikipedia merges cells (for example one "Area" cell spanning several
    polls). Read naively, the rows below a merged cell are one column short
    and every number shifts left. Repeating merged cells into every row and
    column they cover keeps each value under its own header.
    """
    grid: list[list[str]] = []
    carry: dict[tuple[int, int], str] = {}        # (row, col) -> text
    for r, tr in enumerate(table.find_all("tr")):
        row, col = [], 0
        cells = tr.find_all(["td", "th"])
        i = 0
        while i < len(cells) or (r, col) in carry:
            if (r, col) in carry:                 # filled by a rowspan above
                row.append(carry.pop((r, col)))
                col += 1
                continue
            cell = cells[i]
            i += 1
            text = cell.get_text(" ", strip=True)
            span_c = int(cell.get("colspan", 1) or 1)
            span_r = int(cell.get("rowspan", 1) or 1)
            for dc in range(span_c):
                row.append(text)
                for dr in range(1, span_r):
                    carry[(r + dr, col + dc)] = text
            col += span_c
        grid.append(row)
    return grid


def end_date(text: str, year: int) -> date | None:
    """Fieldwork end date from strings like '28– 30 Dec', '29 Apr – 1 May',
    '4 Jul 2024'. The last day-month pair is the end date."""
    pairs = re.findall(r"(\d{1,2})\s*([A-Za-z]{3})[a-z]*\.?(?:\s+(\d{4}))?",
                       text)
    if not pairs:
        return None
    day, mon, yr = pairs[-1]
    month = MONTHS.get(mon.lower())
    if not month:
        return None
    try:
        return date(int(yr) if yr else year, month, int(day))
    except ValueError:
        return None


def share(text: str) -> float | None:
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%?", text)
    return float(m.group(1)) if m else None


def parse_page(html: str) -> list[dict]:
    """Every GB/UK poll on one page (Scotland- and Wales-only polls dropped)."""
    soup = BeautifulSoup(html, "html.parser")
    polls = []
    for table in soup.select("table.wikitable"):
        heading = table.find_previous(["h2", "h3", "h4"])
        year_match = re.search(r"\b(20\d\d)\b",
                               heading.get_text(" ") if heading else "")
        if not year_match:
            continue                       # not a year-section poll table
        year = int(year_match.group(1))
        grid = expand_table(table)
        header = [h.lower() for h in grid[0]]
        # The pollster column is headed "Pollster", "Pollster/client(s)" or,
        # on the 2015-17 page, "Polling organisation/client".
        if not header or "poll" not in " ".join(header[:3]):
            continue
        cols = {i: COLUMN_PARTY[h] for i, h in enumerate(header)
                if h in COLUMN_PARTY}
        area_col = next((i for i, h in enumerate(header) if h == "area"), None)
        pollster_col = next(i for i, h in enumerate(header)
                            if "poll" in h and "date" not in h)
        for row in grid[1:]:
            if len(row) < len(header):
                continue
            pollster = row[pollster_col]
            # Actual election results sit in these tables too; skip them.
            if "election" in pollster.lower():
                continue
            if area_col is not None and row[area_col] not in ("GB", "UK"):
                continue
            ended = end_date(row[0], year)
            if ended is None:
                continue
            values = {p: share(row[i]) for i, p in cols.items()}
            if values.get("CON") is None or values.get("LAB") is None:
                continue                   # not a voting-intention row
            polls.append({"end_date": ended.isoformat(), "pollster": pollster,
                          **{p: values.get(p) for p in
                             ("CON", "LAB", "LD", "GRN", "REF", "UKIP")}})
    return polls


# --- fetch and features -----------------------------------------------------------

def stage_fetch() -> None:
    all_polls, sources = [], {}
    for page in PAGES:
        r = requests.get(f"https://en.wikipedia.org/wiki/{page}",
                         headers=HEADERS, timeout=120)
        r.raise_for_status()
        rev = re.search(r'"wgRevisionId":(\d+)', r.text)
        sources[page] = {"revision_id": int(rev.group(1)) if rev else None}
        polls = parse_page(r.text)
        sources[page]["polls"] = len(polls)
        all_polls += polls
        print(page, len(polls), flush=True)
    # The same poll can appear on two adjacent pages; keep it once.
    seen, unique = set(), []
    for p in sorted(all_polls, key=lambda p: (p["end_date"], p["pollster"])):
        key = (p["end_date"], p["pollster"], p["CON"], p["LAB"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with POLLS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(unique[0]))
        writer.writeheader()
        writer.writerows(unique)
    SOURCES_JSON.write_text(json.dumps(sources, indent=2) + "\n")
    print(f"-> {POLLS_CSV}: {len(unique)} polls")


def load_polls(path: Path = POLLS_CSV) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def poll_average(polls: list[dict], polling_day: str, party: str,
                 days: int = WINDOW_DAYS) -> float | None:
    """Mean share for `party` over polls ending in the `days` days BEFORE
    polling day. The polling day itself is excluded."""
    day = date.fromisoformat(polling_day)
    start = day - timedelta(days=days)
    values = [float(p[party]) for p in polls
              if p.get(party) not in (None, "")
              and start <= date.fromisoformat(p["end_date"]) < day]
    return sum(values) / len(values) if values else None


if __name__ == "__main__":
    {"fetch": stage_fetch}[sys.argv[1]]()
