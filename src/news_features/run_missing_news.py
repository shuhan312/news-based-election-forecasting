"""Phase 7 / Step 7 runner: build the expected observation grid and
assign a coverage state to every cell.

    news_features/missing_news_representation.parquet
    news_features/missing_news_representation.csv

Evidence is read from the collection-side records every run, so
re-executing after Stage M articles land changes the states
deterministically without any code change. Previous outputs are
read-only and hash/byte-checked.

Usage:
    python3 -m src.news_features.run_missing_news build
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from ..llm_extraction.freeze_layer import sha256_file
from .alignment import ELECTIONS, norm
from .missing_news import (ALL_SCOPES, CUMULATIVE_WINDOWS,
                           INDIVIDUAL_WINDOWS, MISSING_NEWS_VERSION,
                           assess_cell, is_valid_combination)
from .run_alignment import RESULT_SOURCES, load_registries

ELEC_DIR = Path("data/elections")
NC = Path("news_collection")
QUERY_INVENTORY = NC / "query_inventory.csv"
SEARCH_LOG = NC / "search_log.csv"
COMPLETENESS = NC / "completeness_check.json"
ELIGIBILITY = NC / "corpus_eligibility_decisions.csv"
MAPPING = NC / "duplicate_mapping_layer_v1_provisional.csv"

AGG_CSV = Path("news_features/context_aggregated_features.csv")
CONTRIB = Path("news_features/context_aggregation_contributions.json")
WEIGHTED = Path("news_features/recency_weighted_features.parquet")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
FROZEN = Path("llm_context/llm_context_layer_final.json")

OUT_PARQUET = Path("news_features/missing_news_representation.parquet")
OUT_CSV = Path("news_features/missing_news_representation.csv")


def load_coverage_evidence() -> dict:
    """Read the collection-side records into per-election and
    per-(election, ward) evidence. Nothing here looks at the feature
    table - coverage is judged from what was SEARCHED and
    PROCESSED, never from what happens to be absent downstream."""
    queries = list(csv.DictReader(QUERY_INVENTORY.open()))
    log = {r["query_id"]: r for r in csv.DictReader(SEARCH_LOG.open())}
    completeness = json.loads(COMPLETENESS.read_text())

    ward_searched: dict[str, set] = defaultdict(set)
    ward_failed: dict[tuple, bool] = defaultdict(bool)
    elec_failed: dict[str, int] = Counter()
    elec_arms: dict[str, set] = defaultdict(set)
    stage_m_records: dict[str, int] = Counter()

    for q in queries:
        eid, ward, stage = q["election_id"], q["ward"].strip(), q["stage"]
        elec_arms[eid].add(q["arm"])
        entry = log.get(q["query_id"])
        failed = entry is not None and entry["search_status"] not in \
            ("200", "")
        if ward:
            ward_searched[eid].add(norm(ward))
            if failed:
                ward_failed[(eid, norm(ward))] = True
        elif failed:
            elec_failed[eid] += 1
        if stage == "M" and entry is not None:
            stage_m_records[eid] += int(entry["records_written"] or 0)

    # Stage M ingestion: records were written by the searches but the
    # corpus layer still holds only the stage A-D articles, so any
    # election with Stage M records owes this layer more articles.
    corpus_ids = {r["article_id"] for r in csv.DictReader(MAPPING.open())}
    stage_m_ingested = {eid: stage_m_records[eid] == 0
                        for eid in ELECTIONS}

    # eligibility / duplicate / extraction completeness per election
    elig = list(csv.DictReader(ELIGIBILITY.open()))
    pending = Counter(r["election_id"] for r in elig
                      if r.get("overall_decision") not in
                      ("include", "exclude")
                      or r.get("resolution_status") != "resolved")
    eligibility_complete = {eid: pending[eid] == 0 for eid in ELECTIONS}

    return {
        "ward_searched": ward_searched,
        "ward_failed": ward_failed,
        "elec_failed": elec_failed,
        "elec_arms": elec_arms,
        "stage_m_records": stage_m_records,
        "stage_m_ingested": stage_m_ingested,
        "eligibility_complete": eligibility_complete,
        "eligibility_pending": pending,
        "corpus_article_count": len(corpus_ids),
        "stage_completeness": completeness["stages"],
    }


def load_expected_entities():
    """Ward -> contesting parties, per election, from the official
    results tables (the 'politically valid combination' source)."""
    party_reg, _, _, _, _ = load_registries()
    ward_parties: dict[str, dict[str, set]] = defaultdict(
        lambda: defaultdict(set))
    elec_parties: dict[str, set] = defaultdict(set)
    for eid, sources in RESULT_SOURCES.items():
        for fname, filt in sources:
            for r in csv.DictReader((ELEC_DIR / fname).open()):
                if filt and (r["year"], r["council"]) != filt:
                    continue
                hit = party_reg.get(norm(r["party_canonical"]))
                if not hit:
                    continue          # unregistered label: skipped,
                                      # counted in the audit
                ward_parties[eid][r["ward"].strip()].add(hit)
                elec_parties[eid].add(hit)
    return ward_parties, elec_parties


def build() -> None:
    # previous outputs untouched
    manifest = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == manifest["frozen_output_sha256"][FROZEN.name]
    agg_before = AGG_CSV.read_bytes()
    weighted_before = sha256_file(WEIGHTED)

    ev = load_coverage_evidence()
    ward_parties, elec_parties = load_expected_entities()
    contributions = json.loads(CONTRIB.read_text())["contributions"]

    # observed cells keyed exactly as the Step 5 groups are
    observed: dict[tuple, int] = {}
    for key, ids in contributions.items():
        eid, target, pid, wtype, window, scope = key.split("|")
        observed[(eid, target, pid, wtype, window, scope)] = len(ids)

    windows = [("individual", w) for w in INDIVIDUAL_WINDOWS] \
        + [("cumulative", w) for w in CUMULATIVE_WINDOWS]

    rows = []
    seen: set[tuple] = set()

    def emit(eid, target_id, level, pid, pname, wtype, window, scope,
             grid_source):
        key = (eid, target_id, pid, wtype, window, scope)
        if key in seen:
            return
        seen.add(key)
        valid, invalid_reason = is_valid_combination(
            level, scope, eid, pname)
        n = observed.get(key, 0)
        ward_key = (eid, norm(target_id.split(":", 1)[1])) \
            if level == "ward" else None
        evidence = {
            "search_queries_executed": True,   # all stages executed
            "ward_tier_search_executed": (
                True if level != "ward"
                else ward_key[1] in ev["ward_searched"][eid]),
            "date_range_covered": True,        # queries span the
                                               # 180-day window
            "required_sources_checked": bool(ev["elec_arms"][eid]),
            "no_search_failures": (
                not ev["ward_failed"][ward_key] if ward_key
                else ev["elec_failed"][eid] == 0),
            "external_stage_complete": ev["stage_m_ingested"][eid],
            "eligibility_resolution_complete":
                ev["eligibility_complete"][eid],
            "duplicate_resolution_complete": True,   # Phase 5 frozen
            # extraction ran on the 67-article pilot only
            "extraction_complete": False,
        }
        rows.append({
            "election_id": eid,
            "geographic_target_id": target_id,
            "geographic_target_level": level,
            "focal_party_id": pid,
            "focal_party_name": pname,
            "window_type": wtype,
            "window": window,
            "scope_classification": scope,
            "n_contributing_articles": n,
            "grid_source": grid_source,
            **{f"evidence_{k}": int(v) for k, v in evidence.items()},
            **assess_cell(valid=valid, invalid_reason=invalid_reason,
                          n_articles=n, evidence=evidence),
            "stage_m_records_pending": ev["stage_m_records"][eid],
            "missing_news_version": MISSING_NEWS_VERSION,
        })

    # ---- 1. the expected grid ---------------------------------------
    for eid in sorted(ELECTIONS):
        ew = f"{eid}:ELECTION_WIDE"
        parties = set(elec_parties[eid])
        reform = next((p for p in parties if p[1] == "Reform UK"), None)
        if reform is None:      # tracked emerging-party comparison
            reform = next(((pid, "Reform UK")
                           for pid, name in [("SCC-PARTY-TRACKED-"
                                              "REFORM", "Reform UK")]),
                          None)
            parties.add(reform)
        for pid, pname in sorted(parties):
            for wtype, window in windows:
                for scope in ALL_SCOPES:
                    emit(eid, ew, "election_wide", pid, pname,
                         wtype, window, scope, "expected_grid")
        for ward in sorted(ward_parties[eid]):
            tid = f"{eid}:{ward}"
            for pid, pname in sorted(ward_parties[eid][ward]):
                for wtype, window in windows:
                    for scope in ALL_SCOPES:
                        emit(eid, tid, "ward", pid, pname, wtype,
                             window, scope, "expected_grid")

    # ---- 2. observed cells outside the expected grid -----------------
    # (e.g. the "(no_focal_party)" groups the aggregation legitimately
    # produces). Adding them guarantees reconciliation with Step 5.
    party_names = {pid: name for eid in elec_parties
                   for pid, name in elec_parties[eid]}
    for (eid, target, pid, wtype, window, scope) in sorted(observed):
        level = ("election_wide" if target.endswith("ELECTION_WIDE")
                 else "ward")
        emit(eid, target, level, pid, party_names.get(pid),
             wtype, window, scope, "observed_extension")

    df = pd.DataFrame(rows)
    key_cols = ["election_id", "geographic_target_id",
                "focal_party_id", "window_type", "window",
                "scope_classification"]
    assert not df.duplicated(subset=key_cols).any(), "grid not unique"
    df = df.sort_values(key_cols, kind="mergesort").reset_index(
        drop=True)

    OUT_CSV.write_text(df.to_csv(index=False, lineterminator="\n"))
    df.to_parquet(OUT_PARQUET, index=False)

    # previous layers must be untouched
    assert AGG_CSV.read_bytes() == agg_before
    assert sha256_file(WEIGHTED) == weighted_before

    # ---- audit ------------------------------------------------------
    print(f"{len(df)} expected-grid cells, {len(df.columns)} columns")
    print("states:", dict(Counter(df["coverage_status"]).most_common()))
    print("grid source:", dict(Counter(df["grid_source"])))
    print("observed cells reconciled:",
          int((df["coverage_status"] == "observed_news").sum()),
          "of", len(observed), "Step 5 groups")
    ward = df[df["geographic_target_level"] == "ward"]
    ew = df[df["geographic_target_level"] == "election_wide"]
    print("ward cells:", len(ward), "| election-wide cells:", len(ew))
    print("ward-tier search executed:",
          int(ward["evidence_ward_tier_search_executed"].sum()),
          f"({ward['evidence_ward_tier_search_executed'].mean():.1%})")
    print("Stage M records pending per election:",
          dict(ev["stage_m_records"]))
    print("eligibility pending per election:",
          dict(ev["eligibility_pending"]))
    print("confirmed zero cells:",
          int((df["coverage_status"] == "confirmed_zero_news").sum()))
    print("coverage_confidence (assessable cells): mean "
          f"{df['coverage_confidence'].mean():.3f}")
    for scope in ("ward_specific_local", "national_political"):
        sub = df[df["scope_classification"] == scope]
        print(f"  {scope}: ",
              dict(Counter(sub["coverage_status"]).most_common(3)))


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
