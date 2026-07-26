"""Phase 6 / Step 1 tests: structural validation, cross-field
research-integrity rules (evidence grounding, review routing),
representability of ambiguity, versioning and determinism. No LLM is
involved anywhere."""

import copy
import json
from pathlib import Path

from src.llm_extraction.validate_context import (SCHEMA_VERSION,
                                                 validate_record,
                                                 validate_rules,
                                                 validate_structure)

EXAMPLES = json.loads(
    Path("llm_context/llm_context_example_outputs_v1.json").read_text())


def example(name):
    e = next(x for x in EXAMPLES["examples"] if x["name"] == name)
    return (copy.deepcopy(e["record"]), e["body_text"], e["title"])

# ------------------------------------------------------- happy paths

def test_all_shipped_examples_validate_cleanly():
    for e in EXAMPLES["examples"]:
        errs = validate_record(e["record"], e["body_text"], e["title"])
        assert errs == [], f"{e['name']}: {errs}"


def test_ambiguous_and_missing_information_is_representable():
    rec, body, title = example("partial_extraction_ambiguous_article")
    # null primary issue, empty sections and ambiguity notes all pass
    assert rec["issues"]["primary_issue"] is None
    assert rec["entities"] == []
    assert validate_record(rec, body, title) == []

# -------------------------------------------------- required fields

def test_missing_required_field_rejected():
    rec, body, title = example("full_extraction_local_article")
    del rec["canonical_article_id"]
    errs = validate_structure(rec)
    assert any("canonical_article_id" in e for e in errs)


def test_unknown_field_rejected():
    rec, body, title = example("full_extraction_local_article")
    rec["sentiment_score"] = 0.9          # the reduction the spec bans
    assert any("sentiment_score" in e for e in validate_structure(rec))


def test_optional_fields_may_be_absent_or_null():
    rec, body, title = example("full_extraction_local_article")
    rec["electoral_consequences"][0]["voter_group"] = None
    rec["electoral_consequences"][0]["mechanism"] = None
    del rec["stances"][0]["sentiment"]
    assert validate_record(rec, body, title) == []

# ------------------------------------------------ evidence grounding

def test_evidence_span_is_mandatory_for_claims():
    rec, body, title = example("full_extraction_local_article")
    del rec["entities"][0]["evidence_span"]
    assert any("evidence_span" in e for e in validate_structure(rec))


def test_fabricated_evidence_span_fails_hard():
    rec, body, title = example("full_extraction_local_article")
    rec["entities"][0]["evidence_span"]["text"] = \
        "this sentence does not appear in the article at all"
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R1") for e in errs)


def test_wrong_offsets_fail():
    rec, body, title = example("full_extraction_local_article")
    span = rec["entities"][0]["evidence_span"]
    span["char_start"], span["char_end"] = 0, 5   # does not slice text
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R2") for e in errs)


def test_correct_offsets_pass():
    rec, body, title = example("full_extraction_local_article")
    span = rec["entities"][0]["evidence_span"]
    start = body.index(span["text"])
    span["char_start"], span["char_end"] = start, start + len(span["text"])
    assert validate_record(rec, body, title) == []

# ------------------------------------------- confidence and statuses

def test_low_confidence_requires_review_routing():
    rec, body, title = example("full_extraction_local_article")
    rec["entities"][0]["confidence"] = 0.3     # below 0.5, unflagged
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R3") for e in errs)
    rec["review_status"] = "flagged"
    assert validate_record(rec, body, title) == []


def test_confidence_bounds_enforced():
    rec, body, title = example("full_extraction_local_article")
    rec["entities"][0]["confidence"] = 1.7
    assert any("1.7" in e for e in validate_structure(rec))


def test_empty_extraction_cannot_claim_extracted():
    rec, body, title = example("partial_extraction_ambiguous_article")
    rec["extraction_status"] = "extracted"
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R4") for e in errs)


def test_not_attempted_must_be_empty():
    rec, body, title = example("full_extraction_local_article")
    rec["extraction_status"] = "not_attempted"
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R5") for e in errs)

# --------------------------------------------- versioning / Stage M

def test_schema_version_is_pinned_and_explicit():
    rec, body, title = example("full_extraction_local_article")
    assert rec["schema_version"] == SCHEMA_VERSION
    rec["schema_version"] = "llm-context-v9.9-2030-01-01"
    assert any("schema_version" in e or "llm-context" in e
               for e in validate_structure(rec))


def test_taxonomy_version_is_pinned():
    rec, body, title = example("full_extraction_local_article")
    rec["issues"]["taxonomy_version"] = "issues-v0.1"
    assert validate_structure(rec)


def test_future_stage_m_article_uses_same_contract():
    # a brand-new article id validates against the same pinned schema
    # with no change to any existing record - Stage M compatibility
    rec, body, title = example("full_extraction_local_article")
    rec["article_id"] = "NEWS-stagem-future0000001"
    rec["canonical_article_id"] = "NEWS-stagem-future0000001"
    assert validate_record(rec, body, title) == []

# ------------------------------------------------------ determinism

def test_repeated_validation_identical_results():
    rec, body, title = example("full_extraction_local_article")
    rec["entities"][0]["evidence_span"]["text"] = "nope " * 3
    r1 = validate_record(copy.deepcopy(rec), body, title)
    r2 = validate_record(copy.deepcopy(rec), body, title)
    assert r1 == r2 and r1                       # same errors, same order


def test_rules_layer_is_pure():
    rec, body, title = example("full_extraction_local_article")
    snapshot = copy.deepcopy(rec)
    validate_rules(rec, body, title)
    assert rec == snapshot                       # input never mutated
