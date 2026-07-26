"""Phase 6 / Step 5 tests: structural validation, frame taxonomy
discipline, primary/secondary separation, evidence rules and
determinism. No API is called anywhere in this file."""

import copy

from src.llm_extraction.framing_detection import (
    FRAME_PROMPT_VERSION, FRAME_SCHEMA_VERSION, build_framing_prompt,
    validate_framing_record, validate_structure)

BODY = ("The Conservative administration was accused of a decade of "
        "poor financial management at County Hall, leaving residents "
        "facing higher bills for weaker services. Analysts said the "
        "row hands the Liberal Democrats a clear line of attack "
        "before May's elections.")
TITLE = "Council tax row deepens ahead of elections"


def frame(cat="governance_failure", **kw):
    base = {"frame_category": cat,
            "frame_other_label": None,
            "affected_entity": "Conservative administration",
            "explanation": "the article builds a narrative of "
                           "sustained mismanagement producing worse "
                           "outcomes for residents",
            "political_mechanism": "sustained failure framing invites "
                                   "readers to hold the incumbent "
                                   "administration responsible",
            "benefits": "Liberal Democrats",
            "damages": "Conservatives",
            "evidence_span": {"text": "accused of a decade of poor "
                              "financial management at County Hall"},
            "confidence": 0.85}
    base.update(kw)
    return base


def record(**kw):
    base = {"schema_version": FRAME_SCHEMA_VERSION,
            "article_id": "A", "canonical_article_id": "A",
            "extraction_status": "extracted",
            "review_status": "unreviewed",
            "primary_frame": frame(),
            "secondary_frames": [
                frame("electoral_competition",
                      affected_entity="Liberal Democrats",
                      benefits="Liberal Democrats", damages=None,
                      evidence_span={"text": "hands the Liberal "
                                     "Democrats a clear line of "
                                     "attack before May's elections"})]}
    base.update(kw)
    return base

# --------------------------------------------------------- happy path

def test_valid_record_passes():
    assert validate_framing_record(record(), BODY, TITLE) == []


def test_empty_framing_is_representable():
    r = record(extraction_status="partial", primary_frame=None,
               secondary_frames=[],
               ambiguity_notes=[{"reason": "no political framing "
                                 "present"}])
    assert validate_framing_record(r, BODY, TITLE) == []

# ----------------------------------------------------- structure

def test_invented_frame_category_rejected():
    r = record()
    r["primary_frame"]["frame_category"] = "made_up_frame"
    assert any("made_up_frame" in e for e in validate_structure(r))


def test_mechanism_and_explanation_required():
    r = record()
    del r["secondary_frames"][0]["political_mechanism"]
    assert any("political_mechanism" in e for e in validate_structure(r))


def test_benefits_damages_nullable_but_required_fields():
    r = record()
    r["primary_frame"]["benefits"] = None
    r["primary_frame"]["damages"] = None
    assert validate_framing_record(r, BODY, TITLE) == []
    del r["primary_frame"]["benefits"]
    assert any("primary_frame" in e or "benefits" in e
               for e in validate_structure(r))

# ------------------------------------------------------- F-rules

def test_f1_fabricated_evidence_rejected():
    r = record()
    r["primary_frame"]["evidence_span"]["text"] = \
        "this sentence does not appear in the article at all"
    errs = validate_framing_record(r, BODY, TITLE)
    assert any(e.startswith("F1") for e in errs)


def test_f2_low_confidence_forces_flagged():
    r = record()
    r["secondary_frames"][0]["confidence"] = 0.3
    errs = validate_framing_record(r, BODY, TITLE)
    assert any(e.startswith("F2") for e in errs)
    r["review_status"] = "flagged"
    assert validate_framing_record(r, BODY, TITLE) == []


def test_f3_primary_repeated_in_secondary_rejected():
    r = record()
    r["secondary_frames"].append(copy.deepcopy(r["primary_frame"]))
    errs = validate_framing_record(r, BODY, TITLE)
    assert any(e.startswith("F3") for e in errs)


def test_f3_duplicate_secondary_frames_rejected():
    r = record()
    r["secondary_frames"] = [
        frame("electoral_competition",
              evidence_span={"text": "hands the Liberal Democrats a "
                             "clear line of attack"}),
        frame("electoral_competition",
              evidence_span={"text": "hands the Liberal Democrats a "
                             "clear line of attack"})]
    errs = validate_framing_record(r, BODY, TITLE)
    assert any("duplicate secondary" in e for e in errs)


def test_f4_other_requires_label():
    r = record()
    r["primary_frame"]["frame_category"] = "other"
    errs = validate_framing_record(r, BODY, TITLE)
    assert any(e.startswith("F4") for e in errs)
    r["primary_frame"]["frame_other_label"] = "media conduct"
    assert validate_framing_record(r, BODY, TITLE) == []


def test_f5_empty_cannot_claim_extracted():
    r = record(primary_frame=None, secondary_frames=[])
    errs = validate_framing_record(r, BODY, TITLE)
    assert any(e.startswith("F5") for e in errs)

# ----------------------------------------------------- prompt / misc

def test_prompt_is_stable_and_carries_boundaries():
    p1, p2 = build_framing_prompt(), build_framing_prompt()
    assert p1 == p2
    assert FRAME_PROMPT_VERSION in p1 and FRAME_SCHEMA_VERSION in p1
    assert "CHARACTER-FOR-CHARACTER" in p1
    assert "not its topic and not its sentiment" in p1
    assert "do NOT attribute blame or credit" in p1


def test_deterministic_validation():
    r = record()
    r["primary_frame"]["evidence_span"]["text"] = "nope " * 3
    e1 = validate_framing_record(copy.deepcopy(r), BODY, TITLE)
    e2 = validate_framing_record(copy.deepcopy(r), BODY, TITLE)
    assert e1 == e2 and e1
