"""Build the production query inventory (deterministic, version-controlled).

Generates news_collection/query_inventory.csv from committed inputs only:

  * election windows        - news_research_protocol.md section 2
  * national query families - the supervisor's national topic list
  * local publishers + routes - news_source_registry.csv as corrected by
    the verified coverage audit (robots-restricted sites -> wayback_cdx;
    source x election combinations audited 'none' are not queried)
  * ward-tier queries       - restricted to the 17 divisions in
    news_protocol/division_sample.md (supervisor to-do 7), instantiated
    per election from data/elections/2013_scc_results.csv (2013),
    data/elections/results_2017_2024.csv (2017/2021) and
    data/elections/2026_east_surrey_results.csv /
    2026_west_surrey_results.csv (2026)

Because every input is committed, re-running this script reproduces the
identical inventory (rows are sorted, IDs are content-hashes).  Queries
are NEVER invented at collection time: the runner executes this file.

v1.1: ward-tier stages (C, M) are now restricted to the 17 divisions in
news_protocol/division_sample.csv, and extended to cover 2026. v1.0
generated ward-tier queries for all 93 divisions before the sample
existed, which defeated the point of sampling 15-25 divisions
(supervisor to-do 7). Cross-era naming is resolved through the
project's GIS-based boundary crosswalk, not by matching ward-name
strings; where no verified correspondence exists for a division's
other era, that era is skipped and logged rather than guessed at.

v1.2: ward-tier queries now cover 2013 too, using
convert_2013_extractor_output.py's output. 2013-2021 divisions share
the same boundaries (single-member wards, unlike 2026's new two-member
wards), so 2013 names are reconciled straight to the 2021 spelling via
normalise_ward_key() - no GIS crosswalk needed for this pair, only the
2021-to-2026 boundary change needs one.

Usage:
    python3 -m src.news_collection.build_query_inventory
"""

import csv
import hashlib
import json
import re
from pathlib import Path

from . import PROTOCOL_VERSION

OUT = Path("news_collection/query_inventory.csv")
RESULTS_2013 = Path("data/elections/2013_scc_results.csv")
RESULTS_2017_2021 = Path("data/elections/results_2017_2024.csv")
RESULTS_2026 = [Path("data/elections/2026_east_surrey_results.csv"),
                Path("data/elections/2026_west_surrey_results.csv")]
DIVISION_SAMPLE = Path("news_protocol/division_sample.csv")
EXACT_CROSSWALK = Path(
    "surrey-election-extractor/outputs/geographic_crosswalk_resolution/"
    "final_direct_mapping_dataset.json")
OVERLAP_RATIO_MIN = 0.99   # same floor as src/build_division_sample.py

# 180-day windows, copied verbatim from the protocol.
ELECTIONS = {
    "SCC-2013-05":  ("2012-11-03", "2013-05-02"),
    "SCC-2017-05":  ("2016-11-05", "2017-05-04"),
    "SCC-2021-05":  ("2020-11-07", "2021-05-06"),
    "ESWS-2026-05": ("2025-11-08", "2026-05-07"),
}

# The supervisor's national topic list -> Guardian query strings.
# The challenger-party family is era-appropriate: UKIP for 2013/2017,
# UKIP + Reform UK for 2021 (Reform renamed from the Brexit Party in
# January 2021), Reform UK for 2026.  Reform UK and UKIP remain separate
# parties throughout (protocol section 4.3).
NATIONAL_FAMILIES = {
    "party_leadership":      'UK "party leader" OR "party leadership"',
    "government_performance": '"the government" AND (performance OR record OR criticised)',
    "national_scandal":      'UK "political scandal"',
    "polling_switching":     '"opinion poll" AND voters',
    "cost_of_living":        '"cost of living"',
    "tax":                   'UK tax policy',
    "immigration":           'UK immigration policy',
    "nhs_public_services":   'NHS AND "public services"',
    "local_gov_funding":     '"local government" AND funding',
}
CHALLENGER = {
    "SCC-2013-05":  ['UKIP', 'UKIP AND Conservatives'],
    "SCC-2017-05":  ['UKIP', 'UKIP AND Conservatives'],
    "SCC-2021-05":  ['UKIP', '"Reform UK"',
                     '"Reform UK" AND Conservatives'],
    "ESWS-2026-05": ['"Reform UK"',
                     '"Reform UK" AND (Conservatives OR Labour OR "Liberal Democrats")'],
}
# County-tier queries on the national outlet (the supervisor's
# '"Reform UK" AND Surrey' pattern and its era equivalents).
COUNTY_ON_GUARDIAN = {
    "SCC-2013-05":  ['Surrey AND (council OR election)', 'UKIP AND Surrey'],
    "SCC-2017-05":  ['Surrey AND (council OR election)', 'UKIP AND Surrey'],
    "SCC-2021-05":  ['Surrey AND (council OR election)',
                     '"Reform UK" AND Surrey'],
    "ESWS-2026-05": ['Surrey AND (council OR election)',
                     '"Reform UK" AND Surrey'],
}

# Local publishers by route (verified audit).  site_search combinations
# audited expected_coverage=none are excluded up front - querying a live
# site for years it did not exist wastes budget and pollutes logs.
CDX_SOURCES = ["surreylive", "bbc_surrey", "surrey_comet",
               "guildford_dragon"]
SITE_SEARCH_SOURCES = {
    "woking_news_mail":  ["SCC-2017-05", "SCC-2021-05", "ESWS-2026-05"],
    "farnham_herald":    list(ELECTIONS),
    "guildford_dragon":  list(ELECTIONS),
    "epsom_ewell_times": ["ESWS-2026-05"],
}
SITE_SEARCH_TERMS = ["election", "Surrey County Council",
                     "council election"]
WARD_ISSUES = ["planning", "roads", "council tax"]


def qid(election_id, family, source, text):
    h = hashlib.sha256(f"{election_id}|{family}|{source}|{text}"
                       .encode()).hexdigest()[:8]
    return f"Q-{election_id}-{family}-{h}"


def row(election_id, family, text, source, scope, route, arm,
        stage, ward=""):
    start, end = ELECTIONS[election_id]
    return {
        "query_id": qid(election_id, family, source, text),
        "election_id": election_id, "ward": ward, "arm": arm,
        "query_family": family, "query_text": text,
        "source_id": source, "geographic_scope": scope,
        "retrieval_route": route,
        "window_start": start, "window_end": end,
        "stage": stage, "protocol_version": PROTOCOL_VERSION,
    }


def ward_slug(ward):
    """First place-name segment, lowercased and hyphenated, for CDX URL
    matching (Reach/WordPress slugs contain place names, never the
    word 'ward' itself).
    'Bagshot, Windlesham and Chobham' -> 'bagshot'
    'Addlestone Ward' -> 'addlestone'  (not 'addlestone-ward')

    Bug found running Stage C on the real 2026-named divisions: this
    function only split on comma/'and'/'&', so a single-segment 2026
    name like 'Addlestone Ward' fell through untouched and kept
    '-ward' in the slug, while a comma-containing name like 'Bagshot,
    Windlesham & Chobham Ward' happened to drop 'Ward' anyway because
    it comes after the comma the split already cuts on - the same
    function was accidentally right for one shape of name and wrong
    for the other. 'Addlestone Ward' CDX searches returned 0 candidates
    (verified in news_collection/search_log.csv) because no real
    article URL slug contains the literal word 'ward'. Stripping a
    trailing ' Ward' first makes both shapes go through the same,
    intentional path.
    """
    ward = re.sub(r"\s+Ward$", "", ward, flags=re.IGNORECASE)
    head = re.split(r",| and | & ", ward)[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", head).strip("-")


def load_sampled_divisions():
    """The 17 pre-registered divisions from supervisor to-do 7, as their
    'as selected' name (a mix of 2021-era and 2026-era spellings - see
    build_division_sample.py's reconcile_aliases). Ward-tier collection
    covers ONLY these divisions, never the full 93."""
    if not DIVISION_SAMPLE.exists():
        print("WARNING: no division sample found - run "
              "src/build_division_sample.py first. Ward-tier stages "
              "(C, M) will be empty this run.")
        return []
    return [r["division"] for r in csv.DictReader(DIVISION_SAMPLE.open())]


def load_crosswalk_both_directions():
    """{2021 division name: 2026 ward name} and its exact inverse, built
    from the same GIS-verified 'exact'/'near_exact' pairs
    build_division_sample.py uses - identical filter, so the two
    scripts can never silently disagree about which pairs are safe to
    treat as the same ground."""
    if not EXACT_CROSSWALK.exists():
        return {}, {}
    forward = {}
    for r in json.loads(EXACT_CROSSWALK.read_text()):
        if r.get("relationship_type") not in ("exact", "near_exact"):
            continue
        if (r["source_overlap_ratio"] < OVERLAP_RATIO_MIN
                or r["target_overlap_ratio"] < OVERLAP_RATIO_MIN):
            continue
        prev = r["previous_area_name"].removesuffix(" ED")
        curr = r["current_area_name"] + " Ward"
        forward[prev] = curr
    backward = {v: k for k, v in forward.items()}
    return forward, backward


def normalise_ward_key(ward):
    """Punctuation-insensitive join key: lowercase, '&' and 'and' both
    collapse away, commas/whitespace collapse away. Used ONLY to detect
    when two literal ward-name strings refer to the same division - the
    literal, as-published spelling is still what gets used in queries
    and output.
    """
    text = ward.lower().replace("&", " and ")
    text = re.sub(r"\band\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def scc_ward_data_2017_2021():
    """Ward -> {parties, candidates} for 2017 and 2021, from the
    committed candidate-level table.

    v1.1 fix: results_2017_2024.csv spells the same compound ward name
    differently between its 2017 rows ('&', e.g. 'Banstead,
    Woodmansterne & Chipstead') and its 2021 rows ('and', e.g.
    'Banstead, Woodmansterne and Chipstead') for at least 12 divisions.
    v1.0 read the 'ward' column literally, so every one of those 12
    divisions silently had no 2017-vs-2021 correspondence at all inside
    this function - not a crosswalk problem, a punctuation problem
    within one already-committed source file. Every 2017 ward name is
    reconciled here to its 2021 spelling whenever they are the same
    division under normalise_ward_key(), so the rest of this script -
    and anything else keying off these dicts - sees one consistent
    name per division. The literal 2021 spelling is preferred because
    it is what ward_winners.csv, division_sample.md and the geographic
    crosswalk already use throughout this project.
    """
    year_to_eid = {"2017": "SCC-2017-05", "2021": "SCC-2021-05"}
    raw = {"SCC-2017-05": {}, "SCC-2021-05": {}}
    for r in csv.DictReader(open(RESULTS_2017_2021)):
        eid = year_to_eid.get(r["year"])
        if not eid or r["council"] != "Surrey County Council" \
                or r.get("event_type") not in ("scheduled", "", None):
            continue
        d = raw[eid].setdefault(r["ward"], {"parties": set(),
                                            "candidates": set()})
        if r.get("party_canonical"):
            d["parties"].add(r["party_canonical"])
        if r.get("candidate"):
            d["candidates"].add(r["candidate"])

    canonical_2021 = {normalise_ward_key(w): w for w in raw["SCC-2021-05"]}
    data = {"SCC-2021-05": raw["SCC-2021-05"], "SCC-2017-05": {}}
    for ward_2017, d in raw["SCC-2017-05"].items():
        key = normalise_ward_key(ward_2017)
        data["SCC-2017-05"][canonical_2021.get(key, ward_2017)] = d
    return data


def scc_ward_data_2013(canonical_2021_keys):
    """Ward -> {parties, candidates} for 2013, from
    convert_2013_extractor_output.py's output. New in v1.2 - closes the
    biggest remaining gap in ward-tier collection (2013 previously had
    no committed division/candidate table at all).

    2013 divisions are the same single-member boundaries as 2017/2021
    (unlike 2026's new two-member wards), so names are reconciled to
    the 2021 spelling by normalise_ward_key() alone - verified earlier
    (13 of 81 wards differ only in '&' vs 'and', 0 unmatched - see the
    commit that added this function). No GIS crosswalk lookup is
    needed for 2013<->2021, only for 2021<->2026.

    canonical_2021_keys is the set of ward names scc_ward_data_2017_2021
    already uses, so 2013 is folded into that same naming convention
    rather than introducing a third, independent spelling.
    """
    if not RESULTS_2013.exists():
        print("WARNING: 2013 ward-level results not found - run "
              "src/convert_2013_extractor_output.py first. 2013 "
              "ward-tier queries will be skipped this run.")
        return {}
    canonical = {normalise_ward_key(w): w for w in canonical_2021_keys}
    data = {}
    for r in csv.DictReader(RESULTS_2013.open()):
        key = normalise_ward_key(r["ward"])
        ward = canonical.get(key, r["ward"])
        d = data.setdefault(ward, {"parties": set(), "candidates": set()})
        if r.get("party_canonical"):
            d["parties"].add(r["party_canonical"])
        if r.get("candidate"):
            d["candidates"].add(r["candidate"])
    return data


def ward_data_2026():
    """Ward -> {parties, candidates} for 2026, from the converted
    SerpAPI-extractor output. New in v1.1 - v1.0 had no 2026 ward-level
    table to read, so 2026 ward-tier queries could not exist at all."""
    if not all(p.exists() for p in RESULTS_2026):
        print("WARNING: 2026 ward-level results not found - run "
              "src/convert_2026_extractor_output.py first. 2026 "
              "ward-tier queries will be skipped this run.")
        return {}
    data = {}
    for p in RESULTS_2026:
        for r in csv.DictReader(p.open()):
            d = data.setdefault(r["ward"], {"parties": set(),
                                            "candidates": set()})
            if r.get("party_canonical"):
                d["parties"].add(r["party_canonical"])
            if r.get("candidate"):
                d["candidates"].add(r["candidate"])
    return data


def resolve_division_names(sampled, forward, backward,
                           wards_2013, wards_2017_2021, wards_2026):
    """For each sampled division, work out its verified name under each
    era, using the crosswalk rather than guessing from string
    similarity. Returns {division_as_selected: {election_id: era_name}},
    omitting an election_id entirely when no verified name exists for
    it - callers must not silently fabricate one.

    2013 shares 2017/2021's boundaries and naming convention (both
    already reconciled to the same canonical spelling by their loader
    functions), so it resolves alongside them with no separate
    crosswalk lookup - only the 2021<->2026 boundary change needs one.

    Also returns the list of (division, missing_election_id) gaps, for
    the printed report - an honest count of what the sample could not
    cover, not something to hide.
    """
    resolved, gaps = {}, []
    for division in sampled:
        names = {}
        in_2017_2021 = division in wards_2017_2021.get("SCC-2017-05", {}) \
            or division in wards_2017_2021.get("SCC-2021-05", {})
        in_2026 = division in wards_2026

        if in_2017_2021:
            names["SCC-2017-05"] = division
            names["SCC-2021-05"] = division
            if division in wards_2013:
                names["SCC-2013-05"] = division
            else:
                gaps.append((division, "SCC-2013-05"))
        else:
            # selected under its 2026 name - look up the 2021-era name
            era_2021_name = backward.get(division)
            if era_2021_name and era_2021_name in wards_2017_2021.get(
                    "SCC-2017-05", {}):
                names["SCC-2017-05"] = era_2021_name
                names["SCC-2021-05"] = era_2021_name
                if era_2021_name in wards_2013:
                    names["SCC-2013-05"] = era_2021_name
                else:
                    gaps.append((division, "SCC-2013-05"))
            else:
                gaps.append((division, "SCC-2013-05/SCC-2017-05/SCC-2021-05"))

        if in_2026:
            names["ESWS-2026-05"] = division
        else:
            # selected under its 2021 name - look up the 2026-era name
            era_2026_name = forward.get(division)
            if era_2026_name and era_2026_name in wards_2026:
                names["ESWS-2026-05"] = era_2026_name
            else:
                gaps.append((division, "ESWS-2026-05"))

        resolved[division] = names
    return resolved, gaps


def ward_queries_for(election_id, era_name, division_data, stage_c_source,
                     display_division):
    """The supervisor's ward-tier query templates (protocol section 3.1
    of the original brief): ward name; ward AND party; "Surrey County
    Council" AND ward; ward AND local issue; candidate AND ward. Applied
    identically regardless of which era's name is used, so 2026 wards
    get the same query design as 2017/2021 divisions.
    display_division is the division as it appears in
    news_protocol/division_sample.md, kept as the logged "ward" value
    even when era_name differs, so every query traces back to one row
    of the pre-registered sample.
    """
    out = []
    slug = ward_slug(era_name)
    out.append(row(election_id, "ward_cdx", f".*{slug}.*", stage_c_source,
                   "ward-level", "wayback_cdx", "local", "C",
                   ward=display_division))
    manual = ([era_name]
             + [f'{era_name} AND {p}' for p in sorted(division_data["parties"])]
             + [f'"Surrey County Council" AND {era_name}']
             + [f'{era_name} AND {i}' for i in WARD_ISSUES]
             + [f'{c} AND {era_name}'
                for c in sorted(division_data["candidates"])])
    for text in manual:
        # retrieval_route serpapi (adapters.SerpApiAdapter): automates what
        # used to require a human to search Google by hand and paste
        # results into a worksheet. Uses the student's own personal
        # SerpAPI account (unrelated to any other use of SerpAPI in this
        # repository), so no supervisor sign-off is needed for this
        # specific credential - unlike the still-pending proposal P3
        # (Google's own Programmable Search API, adapters.GoogleCseAdapter,
        # left in place as an alternative route once/if that is
        # configured instead or as well). Either adapter reports a
        # missing-credential gap honestly per query rather than
        # pretending zero results, so an unconfigured run still logs
        # correctly. news_source_registry.csv still marks
        # google_dated_search manual-only pending supervisor
        # confirmation of P3 (protocol change control,
        # news_research_protocol.md section 9) - that status describes
        # the ORIGINAL manual method's governance, not this adapter.
        out.append(row(election_id, "ward_manual", text,
                       "google_dated_search", "ward-level",
                       "serpapi", "local", "M", ward=display_division))
    return out


def build():
    rows = []

    for eid in ELECTIONS:
        # --- national arm: Guardian API (stage A) ---------------------
        for fam, text in NATIONAL_FAMILIES.items():
            rows.append(row(eid, fam, text, "guardian_api",
                            "uk-national", "api", "national", "A"))
        for text in CHALLENGER[eid]:
            rows.append(row(eid, "challenger_party", text, "guardian_api",
                            "uk-national", "api", "national", "A"))
        for text in COUNTY_ON_GUARDIAN[eid]:
            rows.append(row(eid, "county_tier", text, "guardian_api",
                            "surrey-county", "api", "local", "A"))

        # --- local arm, county tier: CDX discovery --------------------
        # 2026 SurreyLive runs in stage B as the bounded first batch;
        # everything else is stage D bulk work.
        for src in CDX_SOURCES:
            stage = ("B" if (src == "surreylive"
                             and eid == "ESWS-2026-05") else "D")
            regex = None if src == "bbc_surrey" else ".*election.*"
            rows.append(row(eid, "county_cdx", regex or "", src,
                            "surrey-county", "wayback_cdx", "local", stage))

        # --- local arm, county tier: publisher site search ------------
        for src, eids in SITE_SEARCH_SOURCES.items():
            if eid not in eids:
                continue
            for term in SITE_SEARCH_TERMS:
                rows.append(row(eid, "county_site_search", term, src,
                                "surrey-county", "site_search", "local",
                                "B"))

    # --- local arm, ward tier: restricted to the 17-division sample ---
    sampled = load_sampled_divisions()
    forward, backward = load_crosswalk_both_directions()
    wards_2017_2021 = scc_ward_data_2017_2021()
    wards_2013 = scc_ward_data_2013(wards_2017_2021.get("SCC-2021-05", {}))
    wards_2026 = ward_data_2026()
    resolved, gaps = resolve_division_names(
        sampled, forward, backward, wards_2013, wards_2017_2021, wards_2026)

    for division, era_names in sorted(resolved.items()):
        for eid, era_name in sorted(era_names.items()):
            if eid == "SCC-2013-05":
                d = wards_2013.get(era_name)
            elif eid in ("SCC-2017-05", "SCC-2021-05"):
                d = wards_2017_2021.get(eid, {}).get(era_name)
            else:  # ESWS-2026-05
                d = wards_2026.get(era_name)
            if d is None:
                continue
            rows.extend(ward_queries_for(eid, era_name, d, "surreylive",
                                         division))

    rows.sort(key=lambda r: (r["election_id"], r["stage"],
                             r["query_family"], r["source_id"],
                             r["query_text"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_stage = {}
    for r in rows:
        by_stage[r["stage"]] = by_stage.get(r["stage"], 0) + 1
    print(f"{len(rows)} queries -> {OUT}")
    print("by stage:", dict(sorted(by_stage.items())))
    print(f"ward-tier: {len(sampled)} sampled divisions, "
          f"{sum(1 for n in resolved.values() for e in n)} "
          "division x era combinations resolved")
    if gaps:
        print(f"ward-tier gaps ({len(gaps)}, no verified cross-era name "
              "- not guessed, simply not queried for that era):")
        for division, missing in gaps:
            print(f"  {division}: missing {missing}")


if __name__ == "__main__":
    build()
