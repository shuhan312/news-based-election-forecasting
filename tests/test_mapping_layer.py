"""Phase 5 / Step 8 tests: mapping integrity, relationship-type
separation, freeze-guard behaviour, Stage M compatibility and
reproducibility."""

import copy

import pytest

from src.dedup.mapping_layer import (RULE_VERSION, build_row,
                                     downstream_usage, freeze_write,
                                     relationship_status,
                                     validate_mapping)


def ctx(**kw):
    base = {"in_family": False, "family_type": "independent_articles",
            "is_canonical": False, "held": False,
            "same_url_archive": False, "canonical_article_id": "",
            "input_refs": "test"}
    base.update(kw)
    return base

# ------------------------------------------------- status derivation

def test_independent_article_status():
    assert relationship_status(ctx()) \
        == "non_duplicate_independent_article"


def test_canonical_and_version_statuses():
    assert relationship_status(ctx(
        in_family=True, family_type="same_article_version_family",
        is_canonical=True)) == "canonical_article"
    assert relationship_status(ctx(
        in_family=True, family_type="same_article_version_family",
        same_url_archive=True)) == "archive_version"
    assert relationship_status(ctx(
        in_family=True,
        family_type="same_article_version_family")) == "updated_version"


def test_exact_syndication_and_near_dup_stay_separate():
    # the four phenomena never collapse into one label
    assert relationship_status(ctx(
        in_family=True,
        family_type="exact_duplicate_family")) == "exact_duplicate"
    assert relationship_status(ctx(
        in_family=True,
        family_type="near_duplicate_family")) == "near_duplicate"
    assert relationship_status(ctx(
        in_family=True,
        family_type="syndication_family")) == "syndicated_copy"
    assert relationship_status(ctx(
        in_family=True,
        family_type="shared_press_release_family")) == "syndicated_copy"


def test_review_beats_everything():
    assert relationship_status(ctx(
        in_family=True, family_type="same_article_version_family",
        is_canonical=True, held=True)) == "manual_review"

# --------------------------------------------------- downstream gates

def test_downstream_usage_gates():
    assert downstream_usage("canonical_article") \
        == "use_as_canonical_input"
    assert downstream_usage("non_duplicate_independent_article") \
        == "use_as_canonical_input"
    for s in ("exact_duplicate", "near_duplicate", "syndicated_copy",
              "archive_version", "updated_version"):
        assert downstream_usage(s) == "retain_as_evidence_only"
    assert downstream_usage("manual_review") \
        == "manual_review_required"      # never silently in or out

# ---------------------------------------------------- mapping integrity

def rows_abz():
    ra = build_row("A", ctx(in_family=True,
                            family_type="same_article_version_family",
                            is_canonical=True,
                            canonical_article_id="A",
                            family_id="VAL-x"))
    rb = build_row("B", ctx(in_family=True,
                            family_type="same_article_version_family",
                            canonical_article_id="A",
                            family_id="VAL-x"))
    rz = build_row("Z", ctx())
    return [ra, rb, rz]


def test_validate_accepts_coherent_mapping():
    validate_mapping(rows_abz(), {"A", "B", "Z"})


def test_missing_or_extra_article_rejected():
    with pytest.raises(AssertionError):
        validate_mapping(rows_abz(), {"A", "B"})
    with pytest.raises(AssertionError):
        validate_mapping(rows_abz(), {"A", "B", "Z", "MISSING"})


def test_dangling_and_chained_canonicals_rejected():
    rows = rows_abz()
    rows[1]["canonical_article_id"] = "GHOST"
    with pytest.raises(AssertionError):
        validate_mapping(rows, {"A", "B", "Z"})
    # chained: B -> A but A itself points elsewhere
    rows = rows_abz()
    rows[0]["canonical_article_id"] = "Z"
    with pytest.raises(AssertionError):
        validate_mapping(rows, {"A", "B", "Z"})


def test_row_preserves_provenance_fields():
    r = build_row("B", ctx(in_family=True,
                           family_type="same_article_version_family",
                           canonical_article_id="A",
                           family_id="VAL-x",
                           originating_steps="step2;step3;step5",
                           best_similarity="0.9145",
                           available_from="2016-12-17T00:00:00+00:00",
                           review_flags="unordered"))
    assert r["source_article_id"] == "A"
    assert r["evidence_ref"] == "VAL-x"
    assert r["originating_steps"] == "step2;step3;step5"
    assert r["best_similarity"] == "0.9145"
    assert r["available_from"] == "2016-12-17T00:00:00+00:00"
    assert r["rule_version"] == RULE_VERSION

# --------------------------------------- freeze guard / Stage M safety

def test_freeze_guard_idempotent_and_refuses_silent_rewrite(tmp_path):
    p = tmp_path / "layer_v1.csv"
    assert freeze_write(p, "snapshot-1\n") == "written"
    assert freeze_write(p, "snapshot-1\n") == "unchanged"   # rerun ok
    with pytest.raises(RuntimeError):
        freeze_write(p, "snapshot-2\n")     # history rewrite refused
    assert p.read_text() == "snapshot-1\n"  # v1 untouched
    # a NEW version lands alongside, never over
    p2 = tmp_path / "layer_v2.csv"
    assert freeze_write(p2, "snapshot-2\n") == "written"
    assert p.read_text() == "snapshot-1\n"


def test_unrelated_addition_leaves_existing_rows_unchanged():
    before = rows_abz()
    with_new = rows_abz() + [build_row("NEW", ctx())]
    validate_mapping(with_new, {"A", "B", "Z", "NEW"})
    assert with_new[:3] == before      # existing mappings untouched


def test_deterministic():
    c = ctx(in_family=True, family_type="same_article_version_family",
            canonical_article_id="A", family_id="VAL-x")
    assert build_row("B", copy.deepcopy(c)) \
        == build_row("B", copy.deepcopy(c))
