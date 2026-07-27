"""Tests for the Phase 7 Step 1 article-to-entity alignment layer.

Unit tests exercise the pure matchers on synthetic fixtures;
integrity tests run against the real alignment file + official
tables (skipped cleanly when the gitignored frozen inputs are
absent, e.g. on a fresh clone).
"""

import json
from pathlib import Path

import pytest

from src.llm_extraction.freeze_layer import sha256_file
from src.news_features.alignment import (ELECTIONS, align_candidates,
                                         align_election,
                                         align_geography, dedupe,
                                         match_party, norm,
                                         norm_candidate, norm_ward)

CARD = {"article_id": "A1",
        "article_metadata": {"election_id": "SCC-2017-05"},
        "local_national_relevance": {
            "confidence": 0.9,
            "geographic_entities": {
                "wards": ["Shalford ward"], "divisions": [],
                "towns_villages": ["Stanwell"],
                "boroughs": ["Guildford Borough"],
                "surrey_county": True, "uk_wide": False}},
        "political_entities": {
            "candidate_context": [{"name": "Sir John Smith*",
                                   "confidence": 0.8}]}}

WARD_INDEX = {"SCC-2017-05": {"shalford": "Shalford"}}


def test_normalisers_are_conservative():
    assert norm_ward("Shalford ward") == norm_ward("Shalford") \
        == "shalford"
    assert norm_ward("Ashtead Ward") == "ashtead"
    assert norm("Nork & Tattenhams") == "nork and tattenhams"
    assert norm_candidate("Sir John Furey*") == "john furey"
    # different names must NOT unify
    assert norm_ward("Guildford East") != norm_ward("Guildford West")


def test_election_alignment_uses_collection_window():
    row = align_election(CARD, {"polling_date": "2017-05-04"})
    assert row["election_id"] == "SCC-2017-05"
    assert row["confidence_score"] == 1.0
    assert not row["unresolved_flag"]


def test_election_alignment_rejects_polling_date_mismatch():
    with pytest.raises(ValueError):
        align_election(CARD, {"polling_date": "2021-05-06"})


def test_ward_exact_match_and_town_never_promoted():
    rows = align_geography(CARD, WARD_INDEX, {"guildford", "surrey"})
    ward = [r for r in rows if r["alignment_type"] == "ward"][0]
    assert ward["ward_id"] == "SCC-2017-05:Shalford"
    assert ward["matching_method"] == "exact_ward_mention"
    town = [r for r in rows
            if r["alignment_type"] == "town_reference"][0]
    assert town["ward_id"] is None and town["unresolved_flag"]
    boro = [r for r in rows if r["alignment_type"] == "borough"][0]
    assert boro["matching_method"] == "council_area"
    assert any(r["alignment_type"] == "county" for r in rows)


def test_unknown_ward_stays_unresolved():
    card = json.loads(json.dumps(CARD))
    card["local_national_relevance"]["geographic_entities"]["wards"] \
        = ["North Ward (Shere and Gomshall)"]
    rows = align_geography(card, WARD_INDEX, set())
    ward = [r for r in rows if r["alignment_type"] == "ward"][0]
    assert ward["unresolved_flag"] and ward["ward_id"] is None


def test_party_synonyms_and_registry_boundary():
    reg = {"conservative": ("P1", "Conservative"),
           "green": ("P2", "Green")}
    assert match_party("Conservatives", reg) == ("P1", "Conservative")
    assert match_party("Greens", reg) == ("P2", "Green")
    # national parties outside the Surrey registry stay unmatched
    assert match_party("Scottish National Party", reg) is None


def test_candidate_exact_match_ambiguity_and_ward_via_candidate():
    reg = {"john smith": {("C1", "Conservative")},
           "jane doe": {("C2", "Labour"), ("C3", "Green")}}
    results = {"SCC-2017-05": {"john smith": {"Shalford"}}}
    rows = align_candidates(CARD, reg, results)
    cand = [r for r in rows if r["alignment_type"] == "candidate"][0]
    assert cand["candidate_id"] == "C1" and not cand["unresolved_flag"]
    ward = [r for r in rows if r["alignment_type"] == "ward"][0]
    assert ward["matching_method"] == "candidate_location"
    assert ward["ward_id"] == "SCC-2017-05:Shalford"

    card2 = json.loads(json.dumps(CARD))
    card2["political_entities"]["candidate_context"] = [
        {"name": "Jane Doe", "confidence": 0.7}]
    amb = align_candidates(card2, reg, results)[0]
    assert amb["unresolved_flag"]
    assert amb["matching_method"] == "ambiguous_multiple_registry_matches"


def test_dedupe_merges_sources_keeps_max_confidence():
    a = {"article_id": "A", "alignment_type": "party", "ward_id": None,
         "party_id": "P1", "candidate_id": None,
         "matched_entity": "Conservative",
         "matching_method": "party_registry_exact",
         "confidence_score": 0.6, "evidence_source": ["stance_layer"],
         "unresolved_flag": False, "role_in_article": "stance:critical"}
    b = json.loads(json.dumps(a))
    b["confidence_score"] = 0.9
    b["evidence_source"] = ["credit_blame_layer"]
    b["role_in_article"] = "attribution:blame"
    merged = dedupe([a, b])
    assert len(merged) == 1
    assert merged[0]["confidence_score"] == 0.9
    assert set(merged[0]["evidence_source"]) \
        == {"stance_layer", "credit_blame_layer"}
    assert "attribution:blame" in merged[0]["role_in_article"]


# ---- integrity tests against the real files ------------------------

ALIGN = Path("news_features/article_entity_alignment.json")
FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")

needs_data = pytest.mark.skipif(
    not (ALIGN.exists() and FROZEN.exists()),
    reason="alignment/frozen files not present")


@needs_data
def test_every_linked_entity_exists_in_official_tables():
    from src.news_features.run_alignment import load_registries
    party, cand, ward_index, _, _ = load_registries()
    party_ids = {pid for pid, _ in party.values()}
    cand_ids = {cid for hits in cand.values() for cid, _ in hits}
    for r in json.loads(ALIGN.read_text())["records"]:
        if r["ward_id"]:
            eid, ward = r["ward_id"].split(":", 1)
            assert ward in ward_index[eid].values(), r["ward_id"]
        if r["party_id"]:
            assert r["party_id"] in party_ids
        if r["candidate_id"]:
            assert r["candidate_id"] in cand_ids
        assert r["election_id"] in ELECTIONS


@needs_data
def test_unresolved_rows_carry_no_entity_ids():
    for r in json.loads(ALIGN.read_text())["records"]:
        if r["unresolved_flag"]:
            assert r["ward_id"] is None and r["party_id"] is None \
                and r["candidate_id"] is None
        elif r["matching_method"] != "town_location_reference":
            assert r["matching_method"] not in (
                "unresolved", "ambiguous_multiple_registry_matches")


@needs_data
def test_no_duplicate_entity_links():
    seen = set()
    for r in json.loads(ALIGN.read_text())["records"]:
        key = (r["article_id"], r["alignment_type"], r["ward_id"],
               r["party_id"], r["candidate_id"],
               (r["matched_entity"] or "").lower(),
               r["matching_method"])
        assert key not in seen, key
        seen.add(key)


@needs_data
def test_frozen_context_layer_unchanged():
    """Boundary rule: alignment must not have touched the freeze."""
    m = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == m["frozen_output_sha256"][FROZEN.name]
    data = json.loads(ALIGN.read_text())
    assert data["frozen_layer_sha256"] \
        == m["frozen_output_sha256"][FROZEN.name]


@needs_data
def test_alignment_reproducible():
    """Rebuilding from unchanged inputs is byte-identical."""
    from src.news_features.run_alignment import build
    before = ALIGN.read_bytes()
    build()
    assert ALIGN.read_bytes() == before


@needs_data
def test_every_article_has_election_link():
    recs = json.loads(ALIGN.read_text())["records"]
    with_election = {r["article_id"] for r in recs
                     if r["alignment_type"] == "election"}
    all_articles = {r["article_id"] for r in recs}
    assert with_election == all_articles and len(all_articles) == 67
