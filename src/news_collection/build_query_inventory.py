"""Build the production query inventory (deterministic, version-controlled).

Generates news_collection/query_inventory.csv from committed inputs only:

  * election windows      - news_research_protocol.md section 2
  * national query families - the supervisor's national topic list
  * local publishers + routes - news_source_registry.csv as corrected by
    the verified coverage audit (robots-restricted sites -> wayback_cdx;
    source x election combinations audited 'none' are not queried)
  * ward-tier queries     - instantiated from
    data/elections/results_2017_2024.csv (Surrey County Council rows),
    the repository's committed candidate-level table

Because every input is committed, re-running this script reproduces the
identical inventory (rows are sorted, IDs are content-hashes).  Queries
are NEVER invented at collection time: the runner executes this file.

Ward-tier rows for 2013 and 2026 cannot be generated yet - the repo has
no committed division/candidate table for those elections (2013 exists
only in outputs/ workbooks; data/elections/2026_*.csv not yet produced).
The script says so loudly; the collection report records it as an
unresolved issue.  When those tables land, regenerate as v1.1.

Usage:
    python3 -m src.news_collection.build_query_inventory
"""

import csv
import hashlib
import re
from pathlib import Path

from . import PROTOCOL_VERSION

OUT = Path("news_collection/query_inventory.csv")
RESULTS = Path("data/elections/results_2017_2024.csv")

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
    matching (Reach/WordPress slugs contain place names).
    'Bagshot, Windlesham and Chobham' -> 'bagshot'."""
    head = re.split(r",| and | & ", ward)[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", head).strip("-")


def scc_ward_data():
    """Ward -> (parties, candidates) per election, from the committed
    candidate-level table.  Only SCC scheduled elections; boroughs are
    out of scope for the ward tier."""
    year_to_eid = {"2017": "SCC-2017-05", "2021": "SCC-2021-05"}
    data = {}
    for r in csv.DictReader(open(RESULTS)):
        eid = year_to_eid.get(r["year"])
        if not eid or r["council"] != "Surrey County Council" \
                or r.get("event_type") not in ("scheduled", "", None):
            continue
        d = data.setdefault(eid, {}).setdefault(r["ward"],
                                                {"parties": set(),
                                                 "candidates": set()})
        if r.get("party_canonical"):
            d["parties"].add(r["party_canonical"])
        if r.get("candidate"):
            d["candidates"].add(r["candidate"])
    return data


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

    # --- local arm, ward tier (2017/2021 from committed data) ---------
    for eid, wards in sorted(scc_ward_data().items()):
        for ward, d in sorted(wards.items()):
            slug = ward_slug(ward)
            # automated: SurreyLive URL-slug discovery via CDX (stage C)
            rows.append(row(eid, "ward_cdx", f".*{slug}.*", "surreylive",
                            "ward-level", "wayback_cdx", "local", "C",
                            ward=ward))
            # manual Google route (stage M), supervisor query templates
            manual = ([ward]
                      + [f'{ward} AND {p}' for p in sorted(d["parties"])]
                      + [f'"Surrey County Council" AND {ward}']
                      + [f'{ward} AND {i}' for i in WARD_ISSUES]
                      + [f'{c} AND {ward}' for c in sorted(d["candidates"])])
            for text in manual:
                rows.append(row(eid, "ward_manual", text,
                                "google_dated_search", "ward-level",
                                "manual_import", "local", "M", ward=ward))

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
    print("NOTE: ward-tier rows for SCC-2013-05 and ESWS-2026-05 are "
          "not generated - no committed division/candidate table yet "
          "(2013: promote official extraction into data/elections/; "
          "2026: run src/fetch_2026_surrey_results.py). Regenerate as "
          "v1.1 when available.")


if __name__ == "__main__":
    build()
