"""Phase 6 / Step 4 tests: structural validation, stance discipline
(per-entity rows, origin, no inference), evidence rules and
determinism. No API is called anywhere in this file."""

import copy

from src.llm_extraction.stance_classification import (
    STANCE_PROMPT_VERSION, STANCE_SCHEMA_VERSION, build_stance_prompt,
    validate_stance_record, validate_structure)

BODY = ("The Conservative administration was accused of a decade of "
        "poor financial management at County Hall. Council leader "
        "Tim Oliver said the alternative was cutting vital services. "
        "Analysts said Reform UK is gaining ground as voters drift "
        "from the Conservatives towards the insurgent party.")
TITLE = "Council tax row deepens ahead of elections"


def row(name="Conservative", ttype="party", stance="negative",
        origin="both", conf=0.85, **kw):
    base = {"target_name": name, "target_type": ttype,
            "stance": stance, "stance_origin": origin,
            "explanation": "the article foregrounds criticism of the "
                           "administration's financial record",
            "competence_perception": "portrayed_negatively",
            "integrity_perception": "not_addressed",
            "public_support_perception": "not_addressed",
            "challenger_perception": "not_addressed",
            "support_trajectory": "losing",
            "voter_switching_mentioned": True,
            "switching_detail": "voters drifting from the "
                                "Conservatives to Reform UK",
            "evidence_span": {"text": "accused of a decade of poor "
                              "financial management at County Hall"},
            "confidence": conf}
    base.update(kw)
    return base


def record(**kw):
    base = {"schema_version": STANCE_SCHEMA_VERSION,
            "article_id": "A", "canonical_article_id": "A",
            "extraction_status": "extracted",
            "review_status": "unreviewed",
            "entity_stances": [
                row(),
                row("Reform UK", stance="mixed",
                    origin="journalist_narration",
                    competence_perception="not_addressed",
                    support_trajectory="gaining",
                    challenger_perception="credible",
                    evidence_span={"text": "Reform UK is gaining "
                                   "ground as voters drift"})]}
    base.update(kw)
    return base

# --------------------------------------------------------- happy path

def test_valid_record_passes():
    assert validate_stance_record(record(), BODY, TITLE) == []


def test_empty_stance_set_is_representable():
    r = record(extraction_status="partial", entity_stances=[],
               ambiguity_notes=[{"reason": "no entity is evaluatively "
                                 "represented"}])
    assert validate_stance_record(r, BODY, TITLE) == []

# ----------------------------------------------------- structure

def test_stance_values_are_constrained():
    r = record()
    r["entity_stances"][0]["stance"] = "very_negative"
    assert any("very_negative" in e for e in validate_structure(r))


def test_article_level_sentiment_is_unrepresentable():
    r = record()
    r["overall_sentiment"] = "negative"      # the banned reduction
    assert any("overall_sentiment" in e for e in validate_structure(r))


def test_origin_field_required():
    r = record()
    del r["entity_stances"][0]["stance_origin"]
    assert any("stance_origin" in e for e in validate_structure(r))


def test_perceptions_default_vocabulary_enforced():
    r = record()
    r["entity_stances"][0]["integrity_perception"] = "unknown"
    assert any("unknown" in e for e in validate_structure(r))

# ------------------------------------------------------- T-rules

def test_t1_fabricated_evidence_rejected():
    r = record()
    r["entity_stances"][0]["evidence_span"]["text"] = \
        "this sentence does not appear in the article at all"
    errs = validate_stance_record(r, BODY, TITLE)
    assert any(e.startswith("T1") for e in errs)


def test_t2_low_confidence_forces_flagged():
    r = record()
    r["entity_stances"][1]["confidence"] = 0.3
    errs = validate_stance_record(r, BODY, TITLE)
    assert any(e.startswith("T2") for e in errs)
    r["review_status"] = "flagged"
    assert validate_stance_record(r, BODY, TITLE) == []


def test_t3_duplicate_entity_rows_rejected():
    r = record()
    r["entity_stances"].append(copy.deepcopy(r["entity_stances"][0]))
    errs = validate_stance_record(r, BODY, TITLE)
    assert any(e.startswith("T3") for e in errs)


def test_t3_same_name_different_type_allowed():
    # a council and a party sharing a name string are distinct targets
    r = record()
    extra = row("Conservative", ttype="council",
                evidence_span={"text": "Council leader Tim Oliver said "
                               "the alternative was cutting vital "
                               "services"})
    r["entity_stances"].append(extra)
    assert validate_stance_record(r, BODY, TITLE) == []


def test_t4_switching_claim_needs_detail():
    r = record()
    r["entity_stances"][0]["switching_detail"] = None
    errs = validate_stance_record(r, BODY, TITLE)
    assert any(e.startswith("T4") for e in errs)


def test_t5_empty_cannot_claim_extracted():
    r = record(entity_stances=[])
    errs = validate_stance_record(r, BODY, TITLE)
    assert any(e.startswith("T5") for e in errs)

# ----------------------------------------------------- prompt / misc

def test_prompt_is_stable_and_carries_boundaries():
    p1, p2 = build_stance_prompt(), build_stance_prompt()
    assert p1 == p2
    assert STANCE_PROMPT_VERSION in p1 and STANCE_SCHEMA_VERSION in p1
    assert "CHARACTER-FOR-CHARACTER" in p1
    assert "never one overall article sentiment" in p1
    assert "OUT OF SCOPE" in p1 and "framing" in p1


def test_deterministic_validation():
    r = record()
    r["entity_stances"][0]["evidence_span"]["text"] = "nope " * 3
    e1 = validate_stance_record(copy.deepcopy(r), BODY, TITLE)
    e2 = validate_stance_record(copy.deepcopy(r), BODY, TITLE)
    assert e1 == e2 and e1
