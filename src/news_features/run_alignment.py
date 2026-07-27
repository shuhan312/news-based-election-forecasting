"""Phase 7 / Step 1 runner: build the article-to-entity alignment
layer from the frozen context cards + the official election tables.

    news_features/article_entity_alignment.json

No LLM call, no API cost, no article text re-read. The frozen
context layer is verified against its manifest hash before use and
is never written to. Deterministic: rebuilding from unchanged
inputs is byte-identical.

Usage:
    python3 -m src.news_features.run_alignment build
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from ..llm_extraction.freeze_layer import sha256_file
from .alignment import (ALIGNMENT_VERSION, ELECTIONS, align_candidates,
                        align_election, align_geography, align_parties,
                        dedupe, norm, norm_candidate, norm_ward)

FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
WINDOWS = Path("llm_context/temporal_windows_deterministic.json")
ELEC_DIR = Path("data/elections")
OUT = Path("news_features/article_entity_alignment.json")

# election_id -> (results file, filter) mapping the official tables
RESULT_SOURCES = {
    "SCC-2013-05": [("2013_scc_results.csv", None)],
    "SCC-2017-05": [("results_2017_2024.csv",
                     ("2017", "Surrey County Council"))],
    "SCC-2021-05": [("results_2017_2024.csv",
                     ("2021", "Surrey County Council"))],
    "ESWS-2026-05": [("2026_east_surrey_results.csv", None),
                     ("2026_west_surrey_results.csv", None)],
}


def load_registries():
    """Official tables -> exact-match indices. All keys pass through
    the same normalisers the matchers use, so matching is symmetric."""
    # party registry: published AND standardised names -> (id, std)
    party = {}
    for r in csv.DictReader((ELEC_DIR
                             / "party_name_standardisation.csv").open()):
        entry = (r["Party ID"], r["Standardised Party Name"])
        party[norm(r["Party Name As Published"])] = entry
        party[norm(r["Standardised Party Name"])] = entry

    # candidate registry: any known name form -> {(id, party), ...};
    # sets keep genuine same-name collisions visible as ambiguity
    cand = {}
    for r in csv.DictReader(
            (ELEC_DIR / "candidate_name_standardisation.csv").open()):
        names = {r["Candidate Name As Published"],
                 r["Standardised Candidate Name"]}
        names |= {v.strip() for v in r["Known Variants"].split(";")
                  if v.strip()}
        for n in names:
            cand.setdefault(norm_candidate(n), set()).add(
                (r["Candidate ID"], r["Current/Last Known Party"]))

    # per-election ward lists + candidate->ward index from results
    ward_index, results_index = {}, {}
    for eid, sources in RESULT_SOURCES.items():
        wards, cand_wards = {}, {}
        for fname, filt in sources:
            for r in csv.DictReader((ELEC_DIR / fname).open()):
                if filt and (r["year"], r["council"]) != filt:
                    continue
                official = r["ward"].strip()
                wards[norm_ward(official)] = official
                if r.get("candidate"):
                    cand_wards.setdefault(
                        norm_candidate(r["candidate"]),
                        set()).add(official)
        ward_index[eid], results_index[eid] = wards, cand_wards

    # Surrey council-area names (normalised, suffixes stripped)
    boroughs = {"east surrey", "west surrey", "surrey"}
    for r in csv.DictReader((ELEC_DIR / "election_calendar.csv").open()):
        name = r["council"]
        for suffix in (" Borough Council", " District Council",
                       " County Council", " Council"):
            name = name.removesuffix(suffix)
        boroughs.add(norm(name))
    return party, cand, ward_index, results_index, boroughs


def build() -> None:
    # freeze integrity: refuse to align against a drifted layer
    manifest = json.loads(MANIFEST.read_text())
    actual = sha256_file(FROZEN)
    expected = manifest["frozen_output_sha256"][FROZEN.name]
    assert actual == expected, "frozen context layer hash mismatch"

    cards = json.loads(FROZEN.read_text())["cards"]
    windows = json.loads(WINDOWS.read_text())
    party, cand, ward_index, results_index, boroughs = load_registries()

    rows = []
    for card in sorted(cards, key=lambda c: c["article_id"]):
        aid = card["article_id"]
        rows.append(align_election(card, windows.get(aid)))
        rows.extend(align_geography(card, ward_index, boroughs))
        rows.extend(align_parties(card, party))
        rows.extend(align_candidates(card, cand, results_index))
    rows = dedupe(rows)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(
        {"alignment_version": ALIGNMENT_VERSION,
         "frozen_layer_sha256": actual,
         "frozen_dataset_version": manifest["dataset_version"],
         "elections": ELECTIONS,
         "record_count": len(rows),
         "records": rows}, indent=1, ensure_ascii=False) + "\n")

    # ---- audit statistics -------------------------------------------
    by_type = Counter(r["alignment_type"] for r in rows)
    unresolved = Counter(r["alignment_type"] for r in rows
                         if r["unresolved_flag"])
    ward_articles = {r["article_id"] for r in rows
                     if r["alignment_type"] == "ward"
                     and not r["unresolved_flag"]}
    party_articles = {r["article_id"] for r in rows
                      if r["alignment_type"] == "party"
                      and not r["unresolved_flag"]}
    methods = Counter(r["matching_method"] for r in rows)
    top_parties = Counter(r["matched_entity"] for r in rows
                          if r["alignment_type"] == "party"
                          and not r["unresolved_flag"])
    print(f"{len(rows)} alignment records for "
          f"{len({r['article_id'] for r in rows})} articles -> {OUT}")
    print("by type:", dict(sorted(by_type.items())))
    print("unresolved by type:", dict(sorted(unresolved.items())))
    print("methods:", dict(sorted(methods.items())))
    print(f"articles with >=1 resolved ward link: {len(ward_articles)}")
    print(f"articles with >=1 resolved party link: "
          f"{len(party_articles)}")
    print("resolved party links:", dict(top_parties.most_common()))
    print("unresolved party names:", sorted(
        {r['matched_entity'] for r in rows
         if r['alignment_type'] == 'party' and r['unresolved_flag']}))
    print("unresolved candidates:", sorted(
        {r['matched_entity'] for r in rows
         if r['alignment_type'] == 'candidate'
         and r['unresolved_flag']}))
    print("resolved candidates:", sorted(
        {r['matched_entity'] for r in rows
         if r['alignment_type'] == 'candidate'
         and not r['unresolved_flag']}))


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
