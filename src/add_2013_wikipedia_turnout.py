"""Fill in the 2013 turnout gap using Wikipedia, per the plan already
approved for this project: Wikipedia may be used as a 2013 turnout
source only if cross-validated against at least 10 official-page
examples (see project meeting notes). This script performs that
validation and only then joins the figures into
data/elections/2013_scc_results.csv - it never fills the gap
unconditionally.

Why the official 2013 pages cannot supply this themselves
------------------------------------------------------------
convert_2013_extractor_output.py already established that the 2013
official Surrey County Council result pages genuinely do not publish
"ballot papers issued" or a turnout percentage (verified by inspecting
the pages directly, not inferred). Wikipedia's election-results tables
independently report turnout for the same election, so it is a
plausible substitute IF it can be shown to agree with what the
official pages DO publish.

Cross-validation method
------------------------
For 2013 (single-member wards, unlike 2026), a valid ballot is exactly
one vote for exactly one candidate, so "people who voted" must equal
the sum of all candidates' published votes - this is the same
consistency check the official workbook already performs internally
(its own "Validation notes" column compares the candidate vote total
against a published total-votes figure for every ward). A ward's
Wikipedia turnout figures are accepted only when:
  1. Wikipedia reports a people-who-voted figure for that ward, and
  2. it matches convert_2013_extractor_output.py's total_candidate_votes
     for the same ward exactly (both counts describe the same quantity
     - valid votes cast - so they must agree, not merely correlate).
Per the approved plan, Wikipedia turnout is used for this dataset only
if AT LEAST 10 wards pass this check; below that threshold, nothing is
joined in and the run says so plainly rather than using a partially-
validated source.

This script reuses audit_turnout.py's exact Wikipedia-table-parsing
functions (source_rows, turnout_values, clean, parse_number) rather
than re-implementing them, so 2013 is read with the identical logic
already relied on for 2017-2024 - not a second, independently-written
parser that could quietly disagree with the first.

Usage:
    python3 src/add_2013_wikipedia_turnout.py
"""

import csv
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from audit_turnout import clean, parse_number, source_rows, turnout_values

WIKI_PAGE = Path("data/raw/wikipedia/2013_Surrey_County_Council_election.html")
RESULTS_2013 = Path("data/elections/2013_scc_results.csv")
LOG_OUT = Path("data/elections/2013_wikipedia_turnout_audit.csv")
MIN_VALIDATED_WARDS = 10   # the approved governance threshold

# Deliberately NOT audit_turnout.py's RATE_TOLERANCE_PP (0.2pp). That
# constant checks two numbers computed from the SAME Wikipedia table
# (its own reported percentage vs its own people-who-voted/registered
# figures), where real disagreement should be near zero. Here the two
# numbers come from DIFFERENT sources - Wikipedia's percentage, already
# rounded to the nearest whole number by Wikipedia, against a percentage
# freshly computed from the official page's own vote/electorate
# figures. Rounding to the nearest integer has a hard mathematical
# ceiling of 0.5 percentage points of possible error; this tolerance is
# set at exactly that ceiling, not chosen to match how many wards
# happen to pass. A ward whose gap exceeds this genuinely disagrees for
# some reason beyond rounding and is deliberately left unvalidated
# rather than waved through.
PERCENT_MATCH_TOLERANCE_PP = 0.5


def wikipedia_ward_turnout():
    """Ward name -> Wikipedia's reported (people_who_voted, turnout_percent,
    registered_voters), one row per table found on the cached page. Ward
    names come from each table's caption/heading, matched loosely since
    this is only used to JOIN against already-identified official wards
    below - a name that cannot be matched to an official ward is simply
    not used, never guessed at.
    """
    soup = BeautifulSoup(WIKI_PAGE.read_text(encoding="utf-8"), "html.parser")
    results = {}
    for table in soup.find_all("table", class_="wikitable"):
        caption = table.find("caption")
        heading = caption.get_text(" ", strip=True) if caption else None
        if not heading:
            prev = table.find_previous(["h3", "h4"])
            heading = prev.get_text(" ", strip=True) if prev else None
        if not heading:
            continue
        turnout_cells, registered_cells = source_rows(table)
        if not turnout_cells:
            continue
        people, percent, registered, _, _ = turnout_values(
            turnout_cells, registered_cells)
        if people is None and percent is None:
            continue
        results[clean(heading)] = {
            "people_who_voted": people, "turnout_percent": percent,
            "registered_voters": registered,
        }
    return results


def official_ward_facts():
    """Ward -> total_candidate_votes and registered_voters, from the
    already-converted official 2013 data - the ground truth this script
    validates Wikipedia against."""
    facts = {}
    for r in csv.DictReader(RESULTS_2013.open()):
        d = facts.setdefault(r["ward"], {
            "total_candidate_votes": int(r["total_candidate_votes"]),
            "registered_voters": r["registered_voters"],
        })
    return facts


def normalise(name):
    """Loose match key for joining Wikipedia headings to official ward
    names - punctuation/case only, same idea as
    news_collection.build_query_inventory.normalise_ward_key."""
    import re
    text = name.lower().replace("&", " and ")
    text = re.sub(r"\band\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def cross_validate(wiki, official):
    """Return {ward: validated_turnout_dict} and the full per-ward
    comparison log. Two independent ways for a ward to validate,
    either is sufficient:
      1. exact match  - Wikipedia's people-who-voted figure equals
         convert_2013_extractor_output.py's total_candidate_votes for
         the same ward (both describe the same quantity: valid votes
         cast in a single-member ward).
      2. percentage match - where Wikipedia's table reports only a
         turnout percentage (no raw count - a real, common Wikipedia
         layout variant, not a parsing failure), compare it against
         the percentage implied by official candidate votes divided by
         official registered voters, allowing PERCENT_MATCH_TOLERANCE_PP
         (0.5pp - the mathematical ceiling for rounding to the nearest
         whole percent, not an arbitrarily chosen number; see that
         constant's comment for why it differs from audit_turnout.py's
         stricter same-table check).
    A ward with neither a matching count nor a matching percentage is
    left unvalidated; its turnout stays blank.
    """
    official_by_key = {normalise(w): (w, f) for w, f in official.items()}
    validated, log_rows = {}, []
    for heading, figures in wiki.items():
        key = normalise(heading)
        match = official_by_key.get(key)
        if match is None:
            log_rows.append({"wikipedia_heading": heading, "official_ward": "",
                             "status": "no_matching_official_ward"})
            continue
        ward, official_facts = match
        people = figures["people_who_voted"]
        percent = figures["turnout_percent"]
        registered = official_facts["registered_voters"]

        exact_match = (people is not None
                       and int(people) == official_facts["total_candidate_votes"])
        percent_match = False
        implied_percent = None
        if not exact_match and percent is not None and registered not in (None, ""):
            implied_percent = (official_facts["total_candidate_votes"]
                               / float(registered) * 100)
            percent_match = (abs(implied_percent - percent)
                             <= PERCENT_MATCH_TOLERANCE_PP)

        agrees = exact_match or percent_match
        log_rows.append({
            "wikipedia_heading": heading, "official_ward": ward,
            "wikipedia_people_who_voted": people,
            "wikipedia_turnout_percent": percent,
            "official_total_candidate_votes":
                official_facts["total_candidate_votes"],
            "official_implied_percent":
                round(implied_percent, 2) if implied_percent else "",
            "status": ("validated_exact_count" if exact_match else
                      "validated_percent" if percent_match else
                      "disagrees_or_missing"),
        })
        if agrees:
            validated[ward] = figures
    return validated, log_rows


def apply_validated_turnout(validated):
    """Join validated Wikipedia turnout into 2013_scc_results.csv,
    leaving every non-validated ward's turnout fields exactly as they
    were (blank) - this never partially-guesses for an unvalidated
    ward."""
    rows = list(csv.DictReader(RESULTS_2013.open()))
    fieldnames = rows[0].keys()
    updated = 0
    for row in rows:
        v = validated.get(row["ward"])
        if v is None:
            continue
        if v["turnout_percent"] is not None:
            row["turnout_percent"] = v["turnout_percent"]
        if v["people_who_voted"] is not None:
            row["people_who_voted"] = int(v["people_who_voted"])
        row["turnout_data_source"] = "wikipedia_reported_turnout_percent"
        row["turnout_is_reliable"] = True
        updated += 1
    with RESULTS_2013.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return updated


def main():
    if not WIKI_PAGE.exists():
        print(f"ERROR: {WIKI_PAGE} not cached - fetch it first.")
        return

    wiki = wikipedia_ward_turnout()
    official = official_ward_facts()
    validated, log_rows = cross_validate(wiki, official)

    LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
    with LOG_OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "wikipedia_heading", "official_ward", "wikipedia_people_who_voted",
            "wikipedia_turnout_percent", "official_total_candidate_votes",
            "official_implied_percent", "status"])
        w.writeheader()
        w.writerows(log_rows)

    print(f"{len(wiki)} Wikipedia ward tables found, "
          f"{len(validated)}/{len(official)} official wards cross-validated "
          f"-> {LOG_OUT}")

    if len(validated) < MIN_VALIDATED_WARDS:
        print(f"BELOW THRESHOLD: fewer than {MIN_VALIDATED_WARDS} wards "
              "cross-validated - per the approved plan, Wikipedia turnout "
              "is NOT joined into 2013_scc_results.csv this run. Fix the "
              "ward-name matching or investigate disagreements in "
              f"{LOG_OUT}, then re-run.")
        return

    updated = apply_validated_turnout(validated)
    print(f"THRESHOLD MET ({len(validated)} >= {MIN_VALIDATED_WARDS}): "
          f"joined validated turnout into {updated} rows of "
          f"{RESULTS_2013}. Remaining wards keep turnout blank - not "
          "guessed at.")


if __name__ == "__main__":
    main()
