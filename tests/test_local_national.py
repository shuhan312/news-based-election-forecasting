"""Phase 6 / Step 8 tests: structural validation, scope/score
coherence, flag/entity coherence, Reform national-to-local rules and
determinism. No API is called anywhere."""

import copy

from src.llm_extraction.local_national_relevance import (
    LN_PROMPT_VERSION, LN_SCHEMA_VERSION, build_ln_prompt,
    validate_ln_record, validate_structure)

BODY = ("Reform UK opened a campaign office in Spelthorne this week, "
        "claiming growing national momentum after strong polling, "
        "and said its forty volunteers in the borough would target "
        "the Staines ward at May's county elections in Surrey.")
TITLE = "Reform targets Surrey wards as national polling climbs"


def record(**kw):
    base = {"schema_version": LN_SCHEMA_VERSION,
            "article_id": "A", "canonical_article_id": "A",
            "extraction_status": "extracted",
            "review_status": "unreviewed",
            "geographic_scope": "mixed_national_local",
            "geographic_entities": {
                "wards": ["Staines"], "divisions": [],
                "towns_villages": [], "boroughs": ["Spelthorne"],
                "surrey_county": True, "uk_wide": True},
            "mention_flags": {
                "surrey_mentioned": True, "ward_mentioned": True,
                "candidate_mentioned": False,
                "national_leader_mentioned": False},
            "issue_scope": "both_local_and_national",
            "relevance": {
                "local_score": 0.8, "national_score": 0.6,
                "reasoning": "named ward and borough with concrete "
                             "local organising, tied to national "
                             "polling momentum"},
            "electoral_interpretation": "national_local_interaction",
            "reform_uk": {
                "applicable": True,
                "national_momentum": True,
                "local_surrey_activity": True,
                "connects_national_to_local": True,
                "ward_level_conversion_signal": True,
                "evidence_span": {"text": "its forty volunteers in "
                                  "the borough would target the "
                                  "Staines ward"},
                "confidence": 0.8},
            "evidence_span": {"text": "opened a campaign office in "
                              "Spelthorne this week"},
            "confidence": 0.85}
    base.update(kw)
    return base

# --------------------------------------------------------- happy path

def test_valid_record_passes():
    assert validate_ln_record(record(), BODY, TITLE) == []

# ----------------------------------------------------- structure

def test_scope_vocabulary_enforced():
    r = record()
    r["geographic_scope"] = "hyperlocal"
    assert any("hyperlocal" in e for e in validate_structure(r))


def test_scores_bounded():
    r = record()
    r["relevance"]["local_score"] = 1.4
    assert any("1.4" in e for e in validate_structure(r))


def test_reasoning_required():
    r = record()
    del r["relevance"]["reasoning"]
    assert any("reasoning" in e for e in validate_structure(r))

# ------------------------------------------------------- G-rules

def test_g1_fabricated_evidence_rejected():
    r = record()
    r["evidence_span"]["text"] = "this text is not in the article"
    errs = validate_ln_record(r, BODY, TITLE)
    assert any(e.startswith("G1") for e in errs)


def test_g2_low_confidence_forces_flagged():
    r = record()
    r["confidence"] = 0.4
    errs = validate_ln_record(r, BODY, TITLE)
    assert any(e.startswith("G2") for e in errs)
    r["review_status"] = "flagged"
    assert validate_ln_record(r, BODY, TITLE) == []


def test_g3_flag_without_named_ward_rejected():
    r = record()
    r["geographic_entities"]["wards"] = []
    errs = validate_ln_record(r, BODY, TITLE)
    assert any(e.startswith("G3") for e in errs)


def test_g3_named_ward_without_flag_rejected():
    r = record()
    r["mention_flags"]["ward_mentioned"] = False
    errs = validate_ln_record(r, BODY, TITLE)
    assert any(e.startswith("G3") for e in errs)


def test_g4_scope_and_scores_must_agree():
    r = record()
    r["geographic_scope"] = "national"     # but local 0.8 > national 0.6
    errs = validate_ln_record(r, BODY, TITLE)
    assert any(e.startswith("G4") for e in errs)
    r2 = record()
    r2["relevance"]["national_score"] = 0.1   # mixed needs both >= 0.3
    errs2 = validate_ln_record(r2, BODY, TITLE)
    assert any(e.startswith("G4") for e in errs2)


def test_g5_reform_connection_requires_both_elements():
    r = record()
    r["reform_uk"]["national_momentum"] = False
    errs = validate_ln_record(r, BODY, TITLE)
    assert any("connects_national_to_local" in e for e in errs)


def test_g5_reform_not_applicable_must_be_clean():
    r = record()
    r["reform_uk"]["applicable"] = False
    errs = validate_ln_record(r, BODY, TITLE)
    assert any(e.startswith("G5") for e in errs)

# ----------------------------------------------------- prompt / misc

def test_prompt_is_stable_and_guards_assumptions():
    p1, p2 = build_ln_prompt(), build_ln_prompt()
    assert p1 == p2
    assert LN_PROMPT_VERSION in p1 and LN_SCHEMA_VERSION in p1
    assert "CHARACTER-FOR-CHARACTER" in p1
    assert "NEVER assume national coverage affects local voting" in p1
    assert "NEVER assumed to convert into local votes" in p1


def test_deterministic_validation():
    r = record()
    r["evidence_span"]["text"] = "nope " * 3
    e1 = validate_ln_record(copy.deepcopy(r), BODY, TITLE)
    e2 = validate_ln_record(copy.deepcopy(r), BODY, TITLE)
    assert e1 == e2 and e1
