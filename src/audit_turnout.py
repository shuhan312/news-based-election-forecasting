"""Create a turnout audit from the cached Wikipedia election tables.

The output has one row per scheduled-election result table.
Run with: python3 src/audit_turnout.py
"""

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import pandas as pd
from bs4 import BeautifulSoup


RESULTS_PATH = Path("data/elections/results_2017_2024.csv")
CACHE_DIR = Path("data/raw/wikipedia")
OUT_PATH = Path("data/elections/turnout_audit.csv")

# Allow a small difference caused by rounding the reported percentage.
RATE_TOLERANCE_PP = 0.2

SEAT_SUFFIX = re.compile(
    r"\s*\((top\s+)?\d+\s*(seats?|candidates?)[^)]*\)",
    re.IGNORECASE,
)
REFERENCE = re.compile(r"\[.*?\]")
NUMBER = re.compile(r"^[+\-−]?([0-9][0-9,]*(?:\.[0-9]+)?)%?$")


def clean(text):
    """Clean text read from a Wikipedia table cell."""
    return re.sub(r"\s+", " ", REFERENCE.sub("", text)).strip()


def parse_number(text):
    """Read a number from a table cell, or return None for blank cells."""
    match = NUMBER.fullmatch(str(text).strip())
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def display_number(value):
    """Write whole numbers without a decimal point in the CSV."""
    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


def cached_page_path(source_url):
    """Find the cached HTML file for a Wikipedia result page."""
    page_name = unquote(urlparse(source_url).path.rsplit("/", 1)[-1])
    return CACHE_DIR / f"{page_name}.html"


def normalise_ward(ward):
    """Remove a seat-count suffix, as aggregate_results.py does."""
    return SEAT_SUFFIX.sub("", str(ward)).strip()


def source_rows(table):
    """Return the Turnout and Registered electors rows from one table."""
    turnout_cells = []
    registered_voter_cells = []

    for row in table.find_all("tr"):
        cells = [clean(cell.get_text(" "))
                 for cell in row.find_all(["th", "td"])]
        label_index = next((i for i, value in enumerate(cells) if value), None)
        if label_index is None:
            continue

        label = cells[label_index].casefold()
        if label.startswith("turnout"):
            turnout_cells = cells[label_index:]
        elif (label.startswith("registered electors") or
              label.startswith("electorate")):
            registered_voter_cells = cells[label_index:]

    return turnout_cells, registered_voter_cells


def turnout_values(turnout_cells, registered_voter_cells):
    """Read people, percentage and registered voters from the source rows."""
    turnout_values_after_label = turnout_cells[1:]
    # In the usual Wikipedia layout these are the Votes and % columns.
    people_who_voted = (parse_number(turnout_values_after_label[0])
                         if len(turnout_values_after_label) >= 1 else None)
    turnout_percent = (parse_number(turnout_values_after_label[1])
                       if len(turnout_values_after_label) >= 2 else None)

    registered_voters = None
    for cell in registered_voter_cells[1:]:
        value = parse_number(cell)
        if value is not None:
            registered_voters = value
            break

    # Ignore a value outside the possible percentage range.
    if turnout_percent is not None and not 0 <= turnout_percent <= 100:
        turnout_percent = None

    calculated_turnout_percent = None
    if people_who_voted is not None and registered_voters not in (None, 0):
        calculated_turnout_percent = people_who_voted / registered_voters * 100

    turnout_percent_difference = None
    if turnout_percent is not None and calculated_turnout_percent is not None:
        turnout_percent_difference = abs(
            turnout_percent - calculated_turnout_percent)

    return (people_who_voted, turnout_percent, registered_voters,
            calculated_turnout_percent, turnout_percent_difference)


def layout_name(people_who_voted, turnout_percent):
    """Describe the turnout values available in the source table."""
    if people_who_voted is not None and turnout_percent is not None:
        return "people_and_percent"
    if people_who_voted is not None:
        return "people_only"
    if turnout_percent is not None:
        return "percent_only"
    return "missing"


def audit_status(people_who_voted, turnout_percent, calculated_percent,
                 percent_difference,
                 duplicate_ward_key):
    """Set a simple status and any reasons that need checking."""
    flags = []
    if duplicate_ward_key:
        flags.append("duplicate_scheduled_ward_key")
    if people_who_voted is None and turnout_percent is None:
        flags.append("missing_turnout")
    elif people_who_voted is not None and turnout_percent is None:
        flags.append("turnout_percent_unavailable")
    elif people_who_voted is None and turnout_percent is not None:
        flags.append("people_who_voted_unavailable")
    if (percent_difference is not None and
            percent_difference > RATE_TOLERANCE_PP):
        flags.append("reported_and_calculated_percent_disagree")

    requires_review = (
        duplicate_ward_key or
        (percent_difference is not None and
         percent_difference > RATE_TOLERANCE_PP)
    )

    if requires_review:
        status = "review_required"
    elif turnout_percent is not None:
        status = "reported_percent_available"
    elif calculated_percent is not None:
        status = "calculated_percent_available"
    elif people_who_voted is not None:
        status = "people_only"
    else:
        status = "missing"

    turnout_is_reliable = status in {
        "reported_percent_available", "calculated_percent_available"
    }
    return status, turnout_is_reliable, ";".join(flags)


def main():
    raw = pd.read_csv(RESULTS_PATH)
    required = {
        "year", "council", "ward", "event_type", "source_url",
        "source_table_index", "source_caption", "source_heading",
        "people_who_voted", "registered_voters", "turnout_percent",
        "turnout_data_source", "turnout_is_reliable", "votes",
        "seats_contested",
    }
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(
            "Election results are missing required audit columns: " +
            ", ".join(sorted(missing)))

    # Match the scheduled-election rows used by the modelling pipeline.
    scheduled = raw.loc[raw["event_type"].eq("scheduled")].copy()
    table_keys = ["source_url", "source_table_index"]
    source_tables = scheduled.drop_duplicates(table_keys)

    # Flag ward names that would merge more than one source table.
    scheduled["normalised_ward"] = scheduled["ward"].map(normalise_ward)
    ward_keys = ["year", "council", "normalised_ward"]
    table_counts = (scheduled.drop_duplicates(ward_keys + table_keys)
                    .groupby(ward_keys).size())

    page_tables = {}
    audit_rows = []

    for _, source in source_tables.iterrows():
        page_path = cached_page_path(source["source_url"])
        if not page_path.exists():
            raise FileNotFoundError(
                f"Cached source page is missing: {page_path}")

        # Read each cached Wikipedia page once, even if it has many wards.
        if page_path not in page_tables:
            soup = BeautifulSoup(page_path.read_text(), "html.parser")
            page_tables[page_path] = soup.find_all(
                "table", class_="wikitable")

        table_index = int(source["source_table_index"])
        tables = page_tables[page_path]
        if table_index >= len(tables):
            raise IndexError(
                f"Table {table_index} is missing from {page_path}")

        turnout_cells, registered_voter_cells = source_rows(tables[table_index])
        (source_people_who_voted, source_turnout_percent,
         source_registered_voters, calculated_turnout_percent,
         turnout_percent_difference) = turnout_values(
             turnout_cells, registered_voter_cells)

        # Candidate votes are recorded for comparison only; they are never
        # used to calculate turnout because multi-seat voters can cast more
        # than one vote.
        candidate_rows = scheduled.loc[
            scheduled["source_url"].eq(source["source_url"]) &
            scheduled["source_table_index"].eq(
                source["source_table_index"])]
        candidate_vote_sum = int(candidate_rows["votes"].sum())

        ward_key = (
            int(source["year"]), source["council"],
            normalise_ward(source["ward"]),
        )
        duplicate_ward_key = bool(table_counts.loc[ward_key] > 1)
        status, source_turnout_is_reliable, flags = audit_status(
            source_people_who_voted, source_turnout_percent,
            calculated_turnout_percent, turnout_percent_difference,
            duplicate_ward_key)

        parsed_people_who_voted = source["people_who_voted"]
        parsed_matches_source = None
        if pd.notna(parsed_people_who_voted) or source_people_who_voted is not None:
            parsed_matches_source = (
                pd.notna(parsed_people_who_voted) and
                source_people_who_voted is not None and
                float(parsed_people_who_voted) == float(source_people_who_voted))

        seats = candidate_rows["seats_contested"].dropna()
        seats_contested = int(seats.iloc[0]) if not seats.empty else None

        audit_rows.append({
            "year": int(source["year"]),
            "council": source["council"],
            "ward": source["ward"],
            "event_type": source["event_type"],
            "source_url": source["source_url"],
            "source_table_index": table_index,
            "source_caption": source["source_caption"],
            "source_heading": source["source_heading"],
            "parsed_people_who_voted": parsed_people_who_voted,
            "source_turnout_row": " | ".join(turnout_cells),
            "turnout_layout": layout_name(source_people_who_voted,
                                             source_turnout_percent),
            "source_people_who_voted": display_number(source_people_who_voted),
            "source_registered_voters": display_number(source_registered_voters),
            "source_turnout_percent": display_number(source_turnout_percent),
            "calculated_turnout_percent": (
                round(calculated_turnout_percent, 2)
                if calculated_turnout_percent is not None else None),
            "turnout_percent_difference": (
                round(turnout_percent_difference, 2)
                if turnout_percent_difference is not None else None),
            "turnout_data_source": (
                "wikipedia_reported_turnout_percent"
                if source_turnout_percent is not None else
                "calculated_from_people_and_registered_voters"
                if calculated_turnout_percent is not None else
                "wikipedia_people_who_voted_only"
                if source_people_who_voted is not None else "missing"),
            "turnout_is_reliable": source_turnout_is_reliable,
            "parsed_people_who_voted_matches_source": parsed_matches_source,
            "candidate_vote_sum": candidate_vote_sum,
            "seats_contested": seats_contested,
            "candidate_votes_exceed_people_who_voted": (
                candidate_vote_sum > source_people_who_voted
                if source_people_who_voted is not None else None),
            "duplicate_scheduled_ward_key": duplicate_ward_key,
            "audit_status": status,
            "audit_flags": flags,
        })

    audit = pd.DataFrame(audit_rows).sort_values([
        "year", "council", "ward", "source_table_index"
    ])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUT_PATH, index=False)

    print(f"{len(audit)} scheduled source tables -> {OUT_PATH}")
    print("\nTurnout layouts:")
    print(audit["turnout_layout"].value_counts().to_string())
    print("\nAudit status:")
    print(audit["audit_status"].value_counts().to_string())
    print("\nReadable registered-voter values:")
    print(audit["source_registered_voters"].notna().sum())
    print("\nCouncil/year reported-percent coverage:")
    coverage = audit.groupby(["year", "council"]).agg(
        tables=("ward", "size"),
        percent_available=("source_turnout_percent",
                           lambda values: values.notna().sum()),
        review_required=("audit_status",
                         lambda values: values.eq("review_required").sum()),
    )
    coverage["percent_coverage"] = (
        coverage["percent_available"] / coverage["tables"] * 100
    ).round(1)
    print(coverage.to_string())


if __name__ == "__main__":
    main()
