"""Extract ward-level election results from the Wikipedia pages in the calendar.

For every 2017-2024 election in data/elections/election_calendar.csv this
script downloads the Wikipedia article (cached in data/raw/wikipedia/, so
pages are only fetched once) and pulls out each ward's results table:
one row per candidate with party, votes and vote share.  Turnout information
is kept in separate fields when the page provides it.

Everything is combined into one long table:
  data/elections/results_2017_2024.csv
  columns: year, council, ward, party_raw, party_canonical, candidate, votes,
           candidate_vote_share, candidate_rank, candidate_elected,
           seats_contested, people_who_voted, registered_voters,
           turnout_percent, turnout_data_source, turnout_is_reliable,
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

If a scheduled-election page repeats a ward caption but one duplicate table
has a different local ward heading, the heading is used as the ward name for
that duplicate.  The original caption remains in the source metadata.

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
    r"majority|turnout|registered electors|electorate|rejected|swing|gain|hold|total",
    re.IGNORECASE)

# Wikipedia usually rounds the displayed turnout percentage.
TURNOUT_RATE_TOLERANCE_PP = 0.2

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

# Ward captions commonly say either "(3 seats)" or "(top 3 candidates
# elected)".  This is the number of seats being contested in that table, not
# the total number of councillors on the council.
SEATS_CONTESTED = re.compile(
    r"\b(?:top\s+)?(?P<count>\d+)\s+(?:seats?|candidates?)"
    r"(?:\s+elected)?\b", re.IGNORECASE)

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

    # Prefer the local caption/heading.  A missing value means that the
    # Wikipedia table did not explicitly state the number of contested seats;
    # do not guess that it was a single-seat contest.
    seats_contested = None
    for label in (caption, heading):
        seat_match = SEATS_CONTESTED.search(label)
        if seat_match:
            seats_contested = int(seat_match.group("count"))
            break

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
        "seats_contested": seats_contested,
    }


def ward_name(metadata):
    """Ward = table caption, falling back to its nearest local heading."""
    return metadata["source_caption"] or metadata["source_heading"]


def ward_label_key(label):
    """Normalise a caption or heading before comparing ward names."""
    value = str(label).casefold().replace("&", " and ")
    value = POLLING_DATE.sub("", value)
    value = BY_ELECTION.sub("", value)
    value = re.sub(
        r"\s*\((top\s+)?\d+\s*(seats?|candidates?)[^)]*\)", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def correct_duplicate_scheduled_captions(df):
    """Use a specific ward heading when a scheduled caption was copied twice."""
    table_keys = ["source_url", "source_table_index"]
    table_columns = table_keys + [
        "event_type", "source_caption", "source_heading"
    ]
    tables = df[table_columns].drop_duplicates(table_keys)
    scheduled = tables.loc[tables["event_type"].eq("scheduled")]
    corrected_tables = 0

    for (_, caption), group in scheduled.groupby(["source_url", "source_caption"]):
        if not caption or len(group) < 2:
            continue

        caption_key = ward_label_key(caption)
        heading_keys = group["source_heading"].map(ward_label_key)
        has_matching_heading = heading_keys.eq(caption_key).any()
        if not has_matching_heading:
            continue

        # A generic heading such as "Election result" is not a ward name.
        for _, table in group.loc[
            heading_keys.ne(caption_key) &
            ~heading_keys.isin(["", "electionresult"])
        ].iterrows():
            mask = (df["source_url"].eq(table["source_url"]) &
                    df["source_table_index"].eq(table["source_table_index"]))
            df.loc[mask, "ward"] = table["source_heading"]
            corrected_tables += 1

    return corrected_tables


def to_number(text, cast=int):
    value = str(text).replace(",", "").replace("%", "").strip()
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def turnout_info(people_who_voted, registered_voters, turnout_percent):
    """Return the turnout fields for one source table."""
    if turnout_percent is not None and not 0 <= turnout_percent <= 100:
        turnout_percent = None

    calculated_percent = None
    if people_who_voted is not None and registered_voters not in (None, 0):
        calculated_percent = people_who_voted / registered_voters * 100

    if turnout_percent is not None:
        reliable = True
        source = "wikipedia_reported_turnout_percent"
        if (calculated_percent is not None and
                abs(turnout_percent - calculated_percent) > TURNOUT_RATE_TOLERANCE_PP):
            reliable = False
            source = "wikipedia_reported_turnout_percent_needs_review"
    elif calculated_percent is not None:
        turnout_percent = round(calculated_percent, 2)
        reliable = True
        source = "calculated_from_people_and_registered_voters"
    elif people_who_voted is not None:
        reliable = False
        source = "wikipedia_people_who_voted_only"
    elif registered_voters is not None:
        reliable = False
        source = "wikipedia_registered_voters_only"
    else:
        reliable = False
        source = "missing"

    return {
        "people_who_voted": people_who_voted,
        "registered_voters": registered_voters,
        "turnout_percent": turnout_percent,
        "turnout_data_source": source,
        "turnout_is_reliable": reliable,
    }


def parse_table(table):
    """Parse one election result table and its turnout information."""
    header = " ".join(th.get_text() for th in table.find_all("th"))
    # a ward results table always lists Party, Candidate and Votes;
    # summary tables (seats won etc.) lack a Candidate column
    if not ("Party" in header and "Candidate" in header and "Votes" in header):
        return [], None

    rows = []
    people_who_voted = None
    registered_voters = None
    turnout_percent = None

    for tr in table.find_all("tr"):
        # candidate names are sometimes <th> (plainrowheaders variant),
        # so read every cell in order and work from the text pattern
        texts = [clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
        if not texts:
            continue

        label_index = next((i for i, value in enumerate(texts) if value), None)
        if label_index is None:
            continue
        label = texts[label_index]

        if NON_CANDIDATE.search(label[:30]):
            values_after_label = texts[label_index + 1:]
            if label.casefold().startswith("turnout"):
                # The source layout is normally Turnout | people | percent.
                people_who_voted = (
                    to_number(values_after_label[0])
                    if len(values_after_label) >= 1 else None)
                turnout_percent = (
                    to_number(values_after_label[1], float)
                    if len(values_after_label) >= 2 else None)
            elif (label.casefold().startswith("registered electors") or
                  label.casefold().startswith("electorate")):
                for value in values_after_label:
                    registered_voters = to_number(value)
                    if registered_voters is not None:
                        break
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
                     "votes": votes, "candidate_vote_share": share})
    return rows, turnout_info(people_who_voted, registered_voters,
                              turnout_percent)


def mark_candidate_outcomes(rows, seats_contested):
    """Add candidate rank and elected status when a table states its seats.

    Candidate rows are checked by vote total rather than assumed to be in the
    correct order.  A tie spanning the final available seat is left unknown:
    a source table without a stated tie-break must not be used to invent a
    winner.
    """
    for row in rows:
        row["candidate_rank"] = 1 + sum(
            other["votes"] > row["votes"] for other in rows)
        row["candidate_elected"] = None

    if seats_contested is None or len(rows) < seats_contested:
        return

    sorted_votes = sorted((row["votes"] for row in rows), reverse=True)
    cutoff = sorted_votes[seats_contested - 1]
    tied_at_cutoff = (len(rows) > seats_contested and
                       sum(row["votes"] == cutoff for row in rows) > 1 and
                       sum(row["votes"] > cutoff for row in rows) < seats_contested)

    for row in rows:
        if tied_at_cutoff and row["votes"] == cutoff:
            # The source does not tell us which tied candidate won the final
            # seat, so preserve the uncertainty instead of choosing one.
            continue
        row["candidate_elected"] = row["votes"] >= cutoff


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
            rows, table_turnout = parse_table(table)
            if not rows:
                continue
            metadata = table_metadata(table)
            ward = ward_name(metadata)
            if "election result" in ward.lower():  # page-level summary, not a ward
                continue
            mark_candidate_outcomes(rows, metadata["seats_contested"])
            for r in rows:
                r.update({"year": e["year"], "council": e["council"],
                          "ward": ward, **table_turnout,
                          "source_url": e["url"],
                          "source_table_index": table_index,
                          **metadata})
            all_rows.extend(rows)
            n_tables += 1
            n_rows += len(rows)
        print(f"{e['year']} {e['council']}: {n_tables} ward tables, {n_rows} candidate rows")

    df = pd.DataFrame(all_rows)
    corrected_tables = correct_duplicate_scheduled_captions(df)
    if corrected_tables:
        print(f"corrected ward name from heading in {corrected_tables} source table(s)")

    df = df[[
        "year", "council", "ward", "party_raw", "party_canonical", "candidate", "votes",
        "candidate_vote_share", "candidate_rank", "candidate_elected",
        "seats_contested", "people_who_voted", "registered_voters",
        "turnout_percent", "turnout_data_source", "turnout_is_reliable",
        "event_type", "polling_date",
        "source_url", "source_table_index", "source_caption",
        "source_heading", "source_section",
    ]]
    df.to_csv(OUT_PATH, index=False)
    print(f"\n{len(df)} candidate rows -> {OUT_PATH}")
    print("\nCandidate rows by event type:")
    print(df["event_type"].value_counts().to_string())
    print("\nCandidate rows with an explicit seat count:")
    print(df["seats_contested"].notna().sum())
    print("Candidate rows identified as elected:")
    print(df["candidate_elected"].eq(True).sum())
    print("Candidate rows with a reliable turnout percentage:")
    print(df["turnout_is_reliable"].sum())
    print("\nRows per year:")
    print(df["year"].value_counts().sort_index().to_string())
    print("\nTop parties by row count:")
    print(df["party_canonical"].value_counts().head(8).to_string())


if __name__ == "__main__":
    main()
