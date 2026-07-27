"""Tests for the Phase 7 Step 2 election time window assignment."""

import json
from pathlib import Path

import pytest

from src.llm_extraction.freeze_layer import sha256_file
from src.news_features.time_windows import (CUMULATIVE_NAMES,
                                            WINDOW_NAMES,
                                            build_assignment,
                                            check_assignment)


def _stored(pub, eid="SCC-2017-05", flags=()):
    """A synthetic deterministic-layer entry built by the SAME frozen
    function the pipeline used - keeps fixtures honest."""
    from src.llm_extraction.temporal_horizon import assign_windows
    out = assign_windows(pub, eid, "contains_election_result" in flags)
    return out


def test_assignment_matches_spec_windows():
    # 2017-05-04 polling; 100 days before = 2017-01-24
    rec, exc = build_assignment("A1", "SCC-2017-05",
                                _stored("2017-01-24"))
    assert exc is None
    assert rec["days_before_polling"] == 100
    assert rec["individual_time_window"] == "180_to_91_days"
    assert rec["cumulative_windows"]["previous_180_days"] is True
    assert rec["cumulative_windows"]["previous_90_days"] is False
    assert check_assignment(rec) == []


def test_final_72_hours_and_nesting():
    rec, _ = build_assignment("A1", "SCC-2017-05", _stored("2017-05-02"))
    assert rec["days_before_polling"] == 2
    assert rec["individual_time_window"] == "final_72_hours"
    # membership of the smallest window implies every larger one
    assert all(rec["cumulative_windows"][n] for n in CUMULATIVE_NAMES)
    assert check_assignment(rec) == []


def test_post_polling_article_excluded_not_assigned():
    rec, exc = build_assignment("A1", "SCC-2017-05", _stored("2017-05-04"))
    assert rec is None
    assert exc["exclusion_reason"] == "post_voting"


def test_outside_180_days_excluded():
    rec, exc = build_assignment("A1", "SCC-2017-05", _stored("2016-01-01"))
    assert rec is None
    assert exc["exclusion_reason"] == "outside_collection_window"


def test_unresolved_date_excluded():
    rec, exc = build_assignment("A1", "SCC-2017-05", _stored(""))
    assert rec is None
    assert exc["exclusion_reason"] == "unassignable"


def test_w2_drift_detection_raises():
    stored = _stored("2017-01-24")
    stored["days_before_polling"] = 99          # tampered input
    with pytest.raises(ValueError, match="W2 drift"):
        build_assignment("A1", "SCC-2017-05", stored)


def test_check_assignment_catches_wrong_window():
    rec, _ = build_assignment("A1", "SCC-2017-05", _stored("2017-01-24"))
    bad = dict(rec, individual_time_window="final_72_hours")
    assert any(e.startswith("W3") for e in check_assignment(bad))


def test_check_assignment_catches_cumulative_inconsistency():
    rec, _ = build_assignment("A1", "SCC-2017-05", _stored("2017-01-24"))
    cum = dict(rec["cumulative_windows"], previous_90_days=True)
    bad = dict(rec, cumulative_windows=cum)
    assert any(e.startswith("W4") for e in check_assignment(bad))


# ---- integrity tests against the real files ------------------------

OUT = Path("news_features/article_time_window_assignment.json")
ALIGN = Path("news_features/article_entity_alignment.json")
WINDOWS_FILE = Path("llm_context/temporal_windows_deterministic.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")

needs_data = pytest.mark.skipif(
    not (OUT.exists() and WINDOWS_FILE.exists()),
    reason="assignment/deterministic files not present")


@needs_data
def test_every_assigned_record_valid_and_unique_window():
    data = json.loads(OUT.read_text())
    assert data["assigned_count"] == len(data["assigned"]) == 67
    for rec in data["assigned"]:
        assert check_assignment(rec) == [], rec["article_id"]
        assert rec["individual_time_window"] in WINDOW_NAMES
        assert rec["days_before_polling"] > 0     # post-polling out


@needs_data
def test_assignment_covers_exactly_the_aligned_articles():
    data = json.loads(OUT.read_text())
    aligned = {r["article_id"]
               for r in json.loads(ALIGN.read_text())["records"]
               if r["alignment_type"] == "election"}
    got = {r["article_id"] for r in data["assigned"]} \
        | {r["article_id"]
           for r in data["excluded_post_or_out_of_window"]}
    assert got == aligned


@needs_data
def test_previous_layers_unchanged():
    m = json.loads(MANIFEST.read_text())
    assert sha256_file(WINDOWS_FILE) \
        == m["input_file_hashes_sha256"][str(WINDOWS_FILE)]
    data = json.loads(OUT.read_text())
    assert data["deterministic_layer_sha256"] \
        == m["input_file_hashes_sha256"][str(WINDOWS_FILE)]


@needs_data
def test_rebuild_is_byte_identical():
    from src.news_features.run_time_windows import build
    before = OUT.read_bytes()
    build()
    assert OUT.read_bytes() == before
