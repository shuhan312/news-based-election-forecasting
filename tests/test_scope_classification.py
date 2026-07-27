"""Tests for the Phase 7 Step 3 local/national news separation."""

import json
from pathlib import Path

import pytest

from src.llm_extraction.freeze_layer import sha256_file
from src.news_features.scope_classification import (FIVE_SCOPES,
                                                    SCOPE_MAP,
                                                    affected_area,
                                                    check_record,
                                                    classify_article)


def _card(rel):
    return {"article_id": "A1",
            "article_metadata": {"election_id": "SCC-2017-05",
                                 "arm": "local"},
            "validation_status": {"per_layer":
                                  {"relevance": "quarantined"}},
            "local_national_relevance": rel}


REL = {"schema_version": "loc-nat-v1.0-2026-07-27",
       "geographic_scope": "ward_specific_local",
       "geographic_entities": {"wards": ["Shalford"],
                               "towns_villages": ["Guildford"],
                               "surrey_county": True},
       "mention_flags": {"ward_mentioned": True,
                         "surrey_mentioned": True,
                         "candidate_mentioned": False,
                         "national_leader_mentioned": False},
       "issue_scope": "local_issue",
       "relevance": {"local_score": 0.9, "national_score": 0.1,
                     "reasoning": "r"},
       "evidence_span": {"text": "quoted sentence"},
       "confidence": 0.85, "review_status": "unreviewed"}


def test_five_way_mapping_is_total_and_onto():
    assert sorted(SCOPE_MAP.values()) == FIVE_SCOPES
    assert len(FIVE_SCOPES) == 5


def test_classified_record_carries_frozen_evidence_verbatim():
    rec = classify_article(_card(REL), ["SCC-2017-05:Shalford"], ["P1"])
    assert rec["scope_classification"] == "ward_specific_local"
    assert rec["evidence"]["text"] == "quoted sentence"
    assert rec["confidence"] == 0.85
    assert rec["local_relevance_score"] == 0.9
    assert rec["ward_links"] == ["SCC-2017-05:Shalford"]
    assert rec["party_links"] == ["P1"]
    assert check_record(rec) == []


def test_missing_frozen_record_stays_uncertain_and_flagged():
    rec = classify_article(_card(None), [], [])
    assert rec["scope_classification"] == "uncertain"
    assert rec["evidence"] is None and rec["confidence"] is None
    assert rec["review_status"] == "flagged"
    assert check_record(rec) == []


def test_affected_area_prefers_most_specific_level():
    assert affected_area({"wards": ["Shalford"],
                          "towns_villages": ["Guildford"]}) \
        == {"level": "ward_division", "names": ["Shalford"]}
    assert affected_area({"towns_villages": ["Stanwell"]})["level"] \
        == "town_village"
    assert affected_area({"surrey_county": True})["level"] \
        == "surrey_county"
    assert affected_area({}) == {"level": "unknown", "names": []}


def test_check_rejects_out_of_range_score_and_fake_evidence():
    rec = classify_article(_card(REL), [], [])
    bad = dict(rec, local_relevance_score=1.4)
    assert any(e.startswith("L2") for e in check_record(bad))
    bad2 = dict(rec, evidence={"text": None})
    assert any(e.startswith("L3") for e in check_record(bad2))
    unc = classify_article(_card(None), [], [])
    bad3 = dict(unc, confidence=0.9)
    assert any(e.startswith("L4") for e in check_record(bad3))


# ---- integrity tests against the real files ------------------------

OUT = Path("news_features/news_scope_classification.json")
FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")

needs_data = pytest.mark.skipif(
    not (OUT.exists() and FROZEN.exists()),
    reason="scope/frozen files not present")


@needs_data
def test_every_article_has_exactly_one_valid_scope():
    data = json.loads(OUT.read_text())
    assert data["record_count"] == len(data["records"]) == 67
    ids = [r["article_id"] for r in data["records"]]
    assert len(ids) == len(set(ids))
    for r in data["records"]:
        assert check_record(r) == [], r["article_id"]


@needs_data
def test_uncertain_cases_preserved_not_forced():
    recs = json.loads(OUT.read_text())["records"]
    unc = [r for r in recs
           if r["scope_classification"] == "uncertain"]
    assert len(unc) == 2
    for r in unc:
        assert r["review_status"] == "flagged"
        assert r["confidence"] is None


@needs_data
def test_source_is_not_the_classification_rule():
    """The spec forbids source-only classification. Two structural
    proofs: (1) at least one source spreads over >=3 scope
    categories; (2) collection-arm/content mismatches exist and are
    carried as provenance, not corrected away."""
    recs = json.loads(OUT.read_text())["records"]
    by_source = {}
    for r in recs:
        src = r["article_id"].split("-")[1]
        by_source.setdefault(src, set()).add(
            r["scope_classification"])
    assert any(len(v) >= 3 for v in by_source.values())
    mismatch = [r for r in recs
                if r["collection_arm_provenance_only"] == "local"
                and r["scope_classification"] == "national_political"]
    assert mismatch, "expected arm/content mismatches to survive"


@needs_data
def test_previous_layers_unchanged_and_reproducible():
    m = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == m["frozen_output_sha256"][FROZEN.name]
    from src.news_features.run_scope_classification import build
    before = OUT.read_bytes()
    build()
    assert OUT.read_bytes() == before
