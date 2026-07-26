"""Phase 6 / Step 6 tests: structural validation, attribution
discipline (four elements, source separation, no invented
responsibility), evidence rules and determinism. No API is called
anywhere in this file."""

import copy

from src.llm_extraction.credit_blame import (CB_PROMPT_VERSION,
                                             CB_SCHEMA_VERSION,
                                             build_cb_prompt,
                                             validate_cb_record,
                                             validate_structure)

BODY = ("Opposition finance spokesman Will Forster said families in "
        "Woking would pay the price for a decade of poor financial "
        "management at County Hall. Council leader Tim Oliver "
        "defended the budget, saying officials had protected social "
        "care despite national funding cuts imposed by the "
        "government.")
TITLE = "Budget row: who is to blame for the squeeze?"


def attribution(**kw):
    base = {"attribution_type": "blame",
            "target_name": "Conservative administration",
            "target_type": "council",
            "source_type": "politician",
            "source_name": "Will Forster",
            "attributed_outcome": "a decade of poor financial "
                                  "management leading to higher bills",
            "reasoning": "the opposition spokesman holds the "
                         "administration responsible for the "
                         "financial position",
            "affected_issue": "council_finance",
            "electoral_implication": "framing the incumbents as "
                                     "responsible for the squeeze "
                                     "ahead of the elections",
            "implication_direction": "may_damage",
            "evidence_span": {"text": "pay the price for a decade of "
                              "poor financial management at County "
                              "Hall"},
            "confidence": 0.85}
    base.update(kw)
    return base


def record(**kw):
    base = {"schema_version": CB_SCHEMA_VERSION,
            "article_id": "A", "canonical_article_id": "A",
            "extraction_status": "extracted",
            "review_status": "unreviewed",
            "attributions": [
                attribution(),
                attribution(attribution_type="credit",
                            target_name="Council officials",
                            target_type="organisation",
                            source_type="politician",
                            source_name="Tim Oliver",
                            attributed_outcome="protecting social "
                            "care despite funding cuts",
                            reasoning="the council leader credits "
                            "officials with shielding services",
                            affected_issue="social_care",
                            electoral_implication="defensive credit "
                            "framing may soften the budget attack",
                            implication_direction="may_benefit",
                            evidence_span={"text": "officials had "
                                           "protected social care "
                                           "despite national funding "
                                           "cuts"}),
                attribution(target_name="national government",
                            target_type="government",
                            source_type="politician",
                            source_name="Tim Oliver",
                            attributed_outcome="national funding cuts",
                            reasoning="the leader shifts blame upward "
                            "to central government",
                            affected_issue="council_finance",
                            evidence_span={"text": "national funding "
                                           "cuts imposed by the "
                                           "government"})]}
    base.update(kw)
    return base

# --------------------------------------------------------- happy path

def test_valid_record_passes():
    assert validate_cb_record(record(), BODY, TITLE) == []


def test_empty_attribution_set_is_representable():
    r = record(extraction_status="partial", attributions=[],
               ambiguity_notes=[{"reason": "nobody is credited or "
                                 "blamed"}])
    assert validate_cb_record(r, BODY, TITLE) == []

# ----------------------------------------------------- structure

def test_attribution_type_constrained():
    r = record()
    r["attributions"][0]["attribution_type"] = "strong_blame"
    assert any("strong_blame" in e for e in validate_structure(r))


def test_source_type_required_and_constrained():
    r = record()
    del r["attributions"][0]["source_type"]
    assert any("source_type" in e for e in validate_structure(r))
    r2 = record()
    r2["attributions"][0]["source_type"] = "anonymous_tip"
    assert any("anonymous_tip" in e for e in validate_structure(r2))


def test_outcome_and_reasoning_required():
    r = record()
    del r["attributions"][0]["attributed_outcome"]
    assert any("attributed_outcome" in e for e in validate_structure(r))


def test_affected_issue_uses_taxonomy_codes():
    r = record()
    r["attributions"][0]["affected_issue"] = "made_up_issue"
    assert any("made_up_issue" in e for e in validate_structure(r))

# ------------------------------------------------------- C-rules

def test_c1_fabricated_evidence_rejected():
    r = record()
    r["attributions"][0]["evidence_span"]["text"] = \
        "this sentence does not appear in the article at all"
    errs = validate_cb_record(r, BODY, TITLE)
    assert any(e.startswith("C1") for e in errs)


def test_c2_low_confidence_forces_flagged():
    r = record()
    r["attributions"][1]["confidence"] = 0.3
    errs = validate_cb_record(r, BODY, TITLE)
    assert any(e.startswith("C2") for e in errs)
    r["review_status"] = "flagged"
    assert validate_cb_record(r, BODY, TITLE) == []


def test_c3_duplicate_attribution_rejected():
    r = record()
    r["attributions"].append(copy.deepcopy(r["attributions"][0]))
    errs = validate_cb_record(r, BODY, TITLE)
    assert any(e.startswith("C3") for e in errs)


def test_c3_blame_and_credit_for_same_target_are_separate_rows():
    # the same target may receive blame for one outcome and credit
    # for another - separated rows, not merged into one judgement
    r = record()
    extra = attribution(attribution_type="credit",
                        attributed_outcome="protecting frontline "
                        "services in the budget",
                        reasoning="the same administration is also "
                        "credited for shielding services",
                        implication_direction="may_benefit",
                        electoral_implication="partial offset of the "
                        "blame framing",
                        evidence_span={"text": "officials had "
                                       "protected social care despite "
                                       "national funding cuts"})
    r["attributions"].append(extra)
    assert validate_cb_record(r, BODY, TITLE) == []


def test_c4_directional_implication_needs_text():
    r = record()
    r["attributions"][0]["electoral_implication"] = None
    errs = validate_cb_record(r, BODY, TITLE)
    assert any(e.startswith("C4") for e in errs)
    r["attributions"][0]["implication_direction"] = "unclear"
    assert validate_cb_record(r, BODY, TITLE) == []


def test_c5_empty_cannot_claim_extracted():
    r = record(attributions=[])
    errs = validate_cb_record(r, BODY, TITLE)
    assert any(e.startswith("C5") for e in errs)

# ----------------------------------------------------- prompt / misc

def test_prompt_is_stable_and_carries_boundaries():
    p1, p2 = build_cb_prompt(), build_cb_prompt()
    assert p1 == p2
    assert CB_PROMPT_VERSION in p1 and CB_SCHEMA_VERSION in p1
    assert "CHARACTER-FOR-CHARACTER" in p1
    assert "NO INVENTED RESPONSIBILITY" in p1
    assert "Do NOT predict election results" in p1


def test_deterministic_validation():
    r = record()
    r["attributions"][0]["evidence_span"]["text"] = "nope " * 3
    e1 = validate_cb_record(copy.deepcopy(r), BODY, TITLE)
    e2 = validate_cb_record(copy.deepcopy(r), BODY, TITLE)
    assert e1 == e2 and e1

# ----------------------- schema v1.1: politician target type

def test_politician_target_type_valid_under_v11():
    r = record()
    r["attributions"][0]["target_name"] = "Rishi Sunak"
    r["attributions"][0]["target_type"] = "politician"
    assert validate_cb_record(r, BODY, TITLE) == []


def test_old_v10_records_remain_valid():
    r = record()
    r["schema_version"] = "credit-blame-v1.0-2026-07-27"
    assert validate_cb_record(r, BODY, TITLE) == []


def test_prompt_v11_explains_politician_vs_candidate():
    p = build_cb_prompt()
    assert '"politician" for other named individual' in p
