"""Council-level Leave share in the 2016 EU referendum.

Reform UK, the Brexit Party before it and UKIP before that draw on the same
voters, and their geography follows the referendum Leave vote closely. A
council's Leave share is therefore the strongest pre-election clue to where
a party with no local history of its own is likely to be strong. That is the
cold-start problem. It is public, pre-dates every election used here, and
involves no news.

The Electoral Commission published results by 2016 district ("counting
area"). Each council is resolved to the 2016 areas it covers, and its Leave
share is total Leave votes over total valid votes:

  1. councils reorganised after 2016: a manual list of the districts they
     replaced (REORGANISED);
  2. counties: their non-metropolitan districts, from Wikipedia's "List of
     English districts" (revision id recorded), via EC_ALIASES for
     districts renamed or merged since 2016;
  3. districts, unitaries and boroughs: the EC area whose name matches;
  4. renamed or merged districts: EC_ALIASES.

An earlier version used MapIt, but its free tier rate-limited the run
(HTTP 429) and the refusals were cached as "not found". This version needs
no rate-limited service.

Usage:
  PYTHONPATH=.:src python -m forecast.geography build
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup

EC_URL = ("https://www.electoralcommission.org.uk/sites/default/files/"
          "2019-07/EU-referendum-result-data.csv")
WIKI_DISTRICTS = "https://en.wikipedia.org/wiki/List_of_English_districts"
HEADERS = {"User-Agent": "v2-election-research/1.0 (shuhanliu44@gmail.com)"}
DATA_DIR = Path("v2_design/direction1_data")
EC_CSV = DATA_DIR / "eu_referendum_2016.csv"          # public, committed
LEAVE_CSV = DATA_DIR / "council_leave.csv"            # the derived feature
SOURCE_JSON = DATA_DIR / "council_leave_source.json"

# Councils created, merged or abolished after the 2016 referendum, listed by
# the 2016 districts (EC counting areas) they cover.
REORGANISED = {
    "buckinghamshire": ["Aylesbury Vale", "Chiltern", "South Bucks",
                        "Wycombe"],
    "northamptonshire": ["Corby", "Daventry", "East Northamptonshire",
                         "Kettering", "Northampton",
                         "South Northamptonshire", "Wellingborough"],
    "north-northamptonshire": ["Corby", "East Northamptonshire", "Kettering",
                               "Wellingborough"],
    "west-northamptonshire": ["Daventry", "Northampton",
                              "South Northamptonshire"],
    "dorset": ["East Dorset", "North Dorset", "Purbeck", "West Dorset",
               "Weymouth and Portland"],
    "bournemouth-christchurch-and-poole": ["Bournemouth", "Christchurch",
                                           "Poole"],
    "somerset": ["Mendip", "Sedgemoor", "South Somerset", "Taunton Deane",
                 "West Somerset"],
    "north-yorkshire": ["Craven", "Hambleton", "Harrogate", "Richmondshire",
                        "Ryedale", "Scarborough", "Selby"],
    "cumbria": ["Allerdale", "Barrow-in-Furness", "Carlisle", "Copeland",
                "Eden", "South Lakeland"],
    "cumberland": ["Allerdale", "Carlisle", "Copeland"],
    "westmorland-and-furness": ["Barrow-in-Furness", "Eden",
                                "South Lakeland"],
}

# Districts renamed or merged since 2016 (current name -> 2016 EC areas).
EC_ALIASES = {
    "Folkestone and Hythe": ["Shepway"],
    "East Suffolk": ["Suffolk Coastal", "Waveney"],
    "West Suffolk": ["Forest Heath", "St Edmundsbury"],
    "Somerset West and Taunton": ["Taunton Deane", "West Somerset"],
}


# Council slugs whose Democracy Club spelling differs from the EC area name.
SLUG_TO_EC = {
    "city-of-lincoln": ["Lincoln"],
    "folkestone-hythe": ["Shepway"],              # renamed in 2018
    "herefordshire": ["Herefordshire, County of"],
}


def slugify(name: str) -> str:
    """'King's Lynn and West Norfolk' -> 'kings-lynn-and-west-norfolk',
    matching Democracy Club's council slugs."""
    name = name.lower().replace("&", "and").replace("'", "").replace("’", "")
    name = re.sub(r",\s*city of$", "", name)       # "Bristol, City of"
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def load_ec() -> dict[str, dict]:
    """EC results keyed by 2016 area name; downloaded once, then committed."""
    if not EC_CSV.exists():
        r = requests.get(EC_URL, timeout=120)
        r.raise_for_status()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EC_CSV.write_bytes(r.content)
    with EC_CSV.open(encoding="utf-8") as handle:
        return {row["Area"]: row for row in csv.DictReader(handle)}


def county_districts() -> tuple[dict[str, list[str]], int | None]:
    """county slug -> its non-metropolitan districts (current names), from
    Wikipedia, plus the page revision id for provenance."""
    from forecast.polls import expand_table
    r = requests.get(WIKI_DISTRICTS, headers=HEADERS, timeout=120)
    r.raise_for_status()
    rev = re.search(r'"wgRevisionId":(\d+)', r.text)
    table = BeautifulSoup(r.text, "html.parser").select("table.wikitable")[0]
    grid = expand_table(table)
    header = grid[0]
    name_i, type_i = header.index("Name"), header.index("Type")
    county_i = header.index("Ceremonial County")
    out = defaultdict(list)
    for row in grid[1:]:
        # A blank type marks a non-metropolitan district: these, and only
        # these, sit under a county council.
        if len(row) > county_i and row[type_i].strip() == "":
            name = re.sub(r"\s*\[.*?\]", "", row[name_i]).strip()
            out[slugify(row[county_i])].append(name)
    return dict(out), int(rev.group(1)) if rev else None


def resolve(slug: str, subtype: str, ec_by_slug: dict,
            counties: dict) -> tuple[list[str], str]:
    """The 2016 EC areas a council covers, and the rule that found them."""
    if slug in REORGANISED:
        return REORGANISED[slug], "manual"
    if slug in SLUG_TO_EC:
        return SLUG_TO_EC[slug], "alias"
    if subtype == "CTY" and slug in counties:
        return [a for d in counties[slug]
                for a in EC_ALIASES.get(d, [ec_by_slug.get(slugify(d), d)])],\
            "county"
    if slug in ec_by_slug:
        return [ec_by_slug[slug]], "name"
    for current, old in EC_ALIASES.items():
        if slugify(current) == slug:
            return old, "alias"
    return [], "unresolved"


def council_list() -> list[dict]:
    """Every council in the training units, plus the 2025 test councils
    (names and types only; no results are read)."""
    from forecast.elections import UNITS_CSV
    seen = {}
    with UNITS_CSV.open() as handle:
        for r in csv.DictReader(handle):
            seen[r["council"]] = r["subtype"]
    test = requests.get(
        "https://elections.democracyclub.org.uk/api/elections/",
        params={"poll_open_date": "2025-05-01", "election_type": "local",
                "identifier_type": "organisation", "limit": 200},
        timeout=120).json()["results"]
    for e in test:
        org = e.get("organisation") or {}
        if org.get("territory_code") == "ENG":
            seen.setdefault(org["slug"], org["organisation_subtype"])
    return [{"slug": s, "subtype": t} for s, t in sorted(seen.items())]


def stage_build() -> None:
    ec = load_ec()
    ec_by_slug = {slugify(name): name for name in ec}
    counties, revision = county_districts()
    rows = []
    for c in council_list():
        areas, method = resolve(c["slug"], c["subtype"], ec_by_slug, counties)
        found = [ec[a] for a in areas if a in ec]
        missing = [a for a in areas if a not in ec]
        leave = sum(int(r["Leave"]) for r in found)
        valid = sum(int(r["Valid_Votes"]) for r in found)
        ok = bool(found) and not missing
        rows.append({
            "council": c["slug"], "subtype": c["subtype"],
            "method": method if ok else "unresolved",
            "areas": ";".join(areas), "missing_areas": ";".join(missing),
            "leave_pct": round(100 * leave / valid, 3) if ok else ""})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LEAVE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    SOURCE_JSON.write_text(json.dumps({
        "ec_url": EC_URL, "wikipedia": WIKI_DISTRICTS,
        "wikipedia_revision_id": revision}, indent=2) + "\n")
    unresolved = [(r["council"], r["missing_areas"]) for r in rows
                  if r["leave_pct"] == ""]
    print(f"-> {LEAVE_CSV}: {len(rows)} councils, {len(unresolved)} unresolved")
    for council, missing in unresolved:
        print("  unresolved:", council, missing)


def load_leave() -> dict[str, float]:
    with LEAVE_CSV.open(encoding="utf-8") as handle:
        return {r["council"]: float(r["leave_pct"])
                for r in csv.DictReader(handle) if r["leave_pct"]}


if __name__ == "__main__":
    {"build": stage_build}[sys.argv[1]]()
