"""Build the party and candidate name standardisation tables (task 4).

Every party label and candidate name is kept exactly as published, with the
standardised form in a separate column, so each row can be audited back to
its source.  Labels are standardised only where variants clearly refer to
the same organisation; uncertain cases keep the published label and carry a
note instead of a guess.  Reform UK and UKIP remain separate parties.

Inputs (already in the repository):
    data/elections/results_2017_2024.csv                 Wikipedia-derived results
    data/elections/official_scc_candidate_results_test.csv  official 2013 test extract

Outputs (column order matches the workbook tabs, so the workbook builder
can load them directly):
    data/elections/party_name_standardisation.csv       -> Political Parties tab
    data/elections/candidate_name_standardisation.csv   -> Candidates tab

Usage:
    python3 src/build_name_standardisation.py
"""

import csv
import re
from pathlib import Path

from fetch_official_scc_results import stable_id

WIKIPEDIA_RESULTS = Path("data/elections/results_2017_2024.csv")
OFFICIAL_TEST = Path("data/elections/official_scc_candidate_results_test.csv")
PARTY_OUTPUT = Path("data/elections/party_name_standardisation.csv")
CANDIDATE_OUTPUT = Path("data/elections/candidate_name_standardisation.csv")

PARTY_COLUMNS = [
    "Party ID", "Party Name As Published", "Standardised Party Name",
    "Party Category", "Established/Emerging/Local/Independent",
    "First Appearance Election ID", "Source URL", "Notes",
]

CANDIDATE_COLUMNS = [
    "Candidate ID", "Candidate Name As Published", "Standardised Candidate Name",
    "Known Variants", "First Election ID", "Latest Election ID", "Previously Stood",
    "Incumbent Candidate", "Current/Last Known Party", "Source URL", "Notes",
]

# Elections in the supervisor's project scope, in chronological order.
ELECTION_ORDER = ["SCC-2013-05", "SCC-2017-05", "SCC-2021-05", "SCC-BYELECTIONS"]

# One entry per published label observed in the project data:
# published label -> (standardised name, category, note).
# The standardised name changes the published wording only where variants
# clearly refer to the same organisation or a well-documented alias exists.
PARTY_STANDARD = {
    # Established national parties.
    "Conservative": ("Conservative", "Established", ""),
    "Labour": ("Labour", "Established", ""),
    "Labour Co-op": ("Labour", "Established",
                     "Labour and Co-operative candidates grouped under Labour."),
    "Liberal Democrats": ("Liberal Democrats", "Established", ""),
    "Green": ("Green", "Established", ""),
    "Liberal": ("Liberal", "Established",
                "Continuing Liberal Party; must not be merged with Liberal Democrats."),
    "SDP": ("SDP", "Established", "Continuing Social Democratic Party."),
    "Official Monster Raving Loony Party": ("Official Monster Raving Loony Party",
                                            "Established", "Registered since 1983."),
    "Monster Raving Loony": ("Official Monster Raving Loony Party", "Established",
                             "Short form of the registered party name."),
    "Peace": ("Peace", "Established", "The Peace Party, registered 1996; Guildford-based."),
    "Socialist (GB)": ("Socialist Party of Great Britain", "Established", ""),

    # Emerging parties. Reform UK and UKIP remain separate; their relationship
    # belongs in the Party History and New Entrants tab, not in this mapping.
    "UKIP": ("UK Independence Party", "Emerging",
             "Treated as the emerging party of the 2013-2017 cycle in this study; "
             "kept separate from Reform UK."),
    "UK Independence Party": ("UK Independence Party", "Emerging",
                              "Kept separate from Reform UK."),
    "Reform": ("Reform UK", "Emerging",
               "Verified for SCC 2021 contests. A 2019 instance in the wider dataset "
               "predates the Reform UK name and needs manual checking. Never merged "
               "with UKIP."),
    "Heritage": ("Heritage", "Emerging", "Heritage Party, registered 2020."),
    "TUSC": ("Trade Unionist and Socialist Coalition", "Emerging", ""),
    "Workers Party": ("Workers Party", "Emerging",
                      "Registered affiliation not confirmed from the published label."),
    "Democrats and Veterans": ("Democrats and Veterans", "Emerging", ""),
    "Christian": ("Christian", "Emerging",
                  "Published description only; national affiliation not confirmed."),
    "Pirate": ("Pirate", "Emerging",
               "Published description only; national affiliation not confirmed."),

    # Local parties: residents' associations and community groups. Variants
    # are merged only within the same organisation.
    "Residents Association": ("Residents Association", "Local",
                              "Generic published label; the organisation differs by ward."),
    "Residents": ("Residents", "Local",
                  "Generic published label; the organisation differs by ward."),
    "R4GV": ("Residents for Guildford and Villages", "Local", "R4GV expanded."),
    "GGG": ("Guildford Greenbelt Group", "Local", "GGG expanded."),
    "OLRG": ("Oxted and Limpsfield Residents' Group", "Local", "OLRG expanded."),
    "Oxted & Limpsfield Residents' Group": ("Oxted and Limpsfield Residents' Group",
                                            "Local", ""),
    "RIRG": ("Runnymede Independent Residents' Group", "Local", "RIRG expanded."),
    "Runnymede Independent Residents' Group": ("Runnymede Independent Residents' Group",
                                               "Local", ""),
    "Runnymeade Independent Residents Group": ("Runnymede Independent Residents' Group",
                                               "Local", "'Runnymeade' spelling as published."),
    "Farnham Residents": ("Farnham Residents", "Local", ""),
    "Ashtead Independent": ("Ashtead Independent", "Local", ""),
    "Ashtead Ind.": ("Ashtead Independent", "Local", ""),
    "Ashstead Ind.": ("Ashtead Independent", "Local", "'Ashstead' spelling as published."),
    "Molesey Residents' Association": ("Molesey Residents' Association", "Local", ""),
    "The Molesey Residents Association": ("Molesey Residents' Association", "Local", ""),
    "Nork RA": ("Nork Residents' Association", "Local", "RA expanded."),
    "Tattenhams RA": ("Tattenhams Residents' Association", "Local", "RA expanded."),
    "Tattenham RA": ("Tattenhams Residents' Association", "Local",
                     "'Tattenham' spelling as published."),
    "Nork and Tattenhams Residents' Associations": (
        "Nork and Tattenhams Residents' Associations", "Local",
        "Joint label; kept distinct from the separate Nork and Tattenhams associations."),
    "Nork and Tattenhams Residents` Associations": (
        "Nork and Tattenhams Residents' Associations", "Local",
        "Backtick in the published label."),
    "Hersham Village Society": ("Hersham Village Society", "Local", ""),
    "The Walton Society": ("The Walton Society", "Local", ""),
    "Weybridge & St. George's Independents": ("Weybridge & St. George's Independents",
                                              "Local", ""),
    "Esher Residents' Association": ("Esher Residents' Association", "Local", ""),
    "Hinchley Wood Residents' Association": ("Hinchley Wood Residents' Association",
                                             "Local", ""),
    "Hinchley Wood / Weston Green Residents' Associations": (
        "Hinchley Wood / Weston Green Residents' Associations", "Local",
        "Joint label; kept distinct from the single-area associations."),
    "Thames Ditton & Weston Green Residents' Association": (
        "Thames Ditton and Weston Green Residents' Association", "Local", ""),
    "Thames Ditton / Weston Green Residents' Association": (
        "Thames Ditton and Weston Green Residents' Association", "Local", ""),
    "Dittons and Weston Green Residents": (
        "Dittons and Weston Green Residents", "Local",
        "Possibly the same organisation as Thames Ditton and Weston Green "
        "Residents' Association; confirm before merging."),
    "Burstow, Horne & Outwood Residents": ("Burstow, Horne & Outwood Residents",
                                           "Local", ""),
    "Godstone Residents": ("Godstone Residents", "Local", ""),
    "Lingfield & Crowhurst Residents": ("Lingfield & Crowhurst Residents", "Local", ""),
    "Dormansland & Felbridge Residents": ("Dormansland & Felbridge Residents", "Local", ""),
    "Caterham Residents": ("Caterham Residents", "Local", ""),
    "Whyteleafe Residents": ("Whyteleafe Residents", "Local", ""),
    "Bletchingley & Nutfield Residents": ("Bletchingley & Nutfield Residents", "Local", ""),
    "Residents Associations of Epsom and Ewell": (
        "Residents Associations of Epsom and Ewell", "Local", ""),

    # Candidates standing without a party.
    "Independent": ("Independent", "Independent", ""),
    "No Description": ("No Description", "Independent",
                       "Nominated without a party description; not formally 'Independent'."),
}


def standardise_candidate(published):
    """Deterministic form only: strip source markers, tidy spacing, and turn
    the official 'Surname, Forenames' order into 'Forenames Surname'."""
    name = re.sub(r"[*†‡]+\s*$", "", published).strip()
    name = re.sub(r"\s+", " ", name)
    if ", " in name:
        surname, forenames = name.split(", ", 1)
        name = f"{forenames} {surname}"
    return name


def election_id_for(row):
    """Map a Wikipedia dataset row to the project's election register."""
    if row["event_type"] == "by_election":
        return "SCC-BYELECTIONS"
    return {"2017": "SCC-2017-05", "2021": "SCC-2021-05"}[row["year"]]


def load_scope_rows():
    """Candidate rows for project-scope elections only, from both sources."""
    rows = []
    with WIKIPEDIA_RESULTS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["council"] != "Surrey County Council":
                continue
            rows.append({
                "published": row["candidate"].strip(),
                "party_published": row["party_raw"].strip(),
                "election_id": election_id_for(row),
                "source_url": row["source_url"],
                "provenance": "Wikipedia-derived dataset; reconcile against official pages.",
            })
    with OFFICIAL_TEST.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "published": row["Candidate Name As Published"].strip(),
                "party_published": row["Party Name As Published"].strip(),
                "election_id": row["Election ID"],
                "source_url": row["Source URL"],
                "provenance": "Official SCC result page (2013 test extract).",
            })
    return rows


def observed_party_labels():
    """Every published party label in the project data, with counts and a source."""
    labels = {}
    with WIKIPEDIA_RESULTS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            label = row["party_raw"].strip()
            entry = labels.setdefault(label, {"count": 0, "source_url": row["source_url"]})
            entry["count"] += 1
    with OFFICIAL_TEST.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            label = row["Party Name As Published"].strip()
            entry = labels.setdefault(label, {"count": 0, "source_url": row["Source URL"]})
            entry["count"] += 1
    return labels


def build_party_table():
    labels = observed_party_labels()
    unmapped = sorted(set(labels) - set(PARTY_STANDARD))
    if unmapped:
        # A new label must get an explicit decision, never a silent guess.
        raise SystemExit(f"Unmapped party label(s); add them to PARTY_STANDARD: {unmapped}")

    rows = []
    for published, meta in labels.items():
        standardised, category, note = PARTY_STANDARD[published]
        notes = [note] if note else []
        notes.append(f"Observed in {meta['count']} candidate row(s) in the project data.")
        rows.append({
            "Party ID": stable_id("SCC-PARTY", standardised),
            "Party Name As Published": published,
            "Standardised Party Name": standardised,
            "Party Category": category,
            "Established/Emerging/Local/Independent": category,
            # Left blank: the official 2013-2021 extraction is not complete,
            # so a first appearance cannot be stated yet.
            "First Appearance Election ID": "",
            "Source URL": meta["source_url"],
            "Notes": " ".join(notes),
        })
    rows.sort(key=lambda r: (r["Standardised Party Name"], r["Party Name As Published"]))
    return rows


def build_candidate_table():
    by_published = {}
    for row in load_scope_rows():
        entry = by_published.setdefault(row["published"], {
            "standardised": standardise_candidate(row["published"]),
            "elections": set(), "parties": {}, "source_url": row["source_url"],
            "provenance": row["provenance"], "marked_incumbent": set(),
        })
        entry["elections"].add(row["election_id"])
        entry["parties"][row["election_id"]] = row["party_published"]
        if row["published"].rstrip().endswith("*"):
            entry["marked_incumbent"].add(row["election_id"])

    # Published forms that share one standardised name are each other's variants.
    variants = {}
    for published, entry in by_published.items():
        variants.setdefault(entry["standardised"], []).append(published)

    rows = []
    for published, entry in by_published.items():
        ordered = sorted(entry["elections"], key=ELECTION_ORDER.index)
        latest = ordered[-1]
        party_published = entry["parties"][latest]
        party_standardised = PARTY_STANDARD[party_published][0]
        siblings = [v for v in variants[entry["standardised"]] if v != published]
        notes = [entry["provenance"]]
        if entry["marked_incumbent"]:
            marked = ", ".join(sorted(entry["marked_incumbent"], key=ELECTION_ORDER.index))
            notes.append(f"Source marked this name with * (incumbent) in {marked}.")
        rows.append({
            "Candidate ID": stable_id("SCC-CAND", published),
            "Candidate Name As Published": published,
            "Standardised Candidate Name": entry["standardised"],
            "Known Variants": "; ".join(sorted(siblings)),
            "First Election ID": ordered[0],
            "Latest Election ID": latest,
            "Previously Stood": "Unknown",
            "Incumbent Candidate": "",
            "Current/Last Known Party": party_standardised,
            "Source URL": entry["source_url"],
            "Notes": " ".join(notes),
        })
    rows.sort(key=lambda r: (r["Standardised Candidate Name"], r["Candidate Name As Published"]))
    return rows


def write_csv(rows, columns, output_path):
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output_path}")


def main():
    write_csv(build_party_table(), PARTY_COLUMNS, PARTY_OUTPUT)
    write_csv(build_candidate_table(), CANDIDATE_COLUMNS, CANDIDATE_OUTPUT)


if __name__ == "__main__":
    main()
