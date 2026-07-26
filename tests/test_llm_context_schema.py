"""Phase 6 / Step 1 tests (v1.1 contract): structural validation,
evidence grounding, confidence routing, Reform UK layer consistency,
party-row uniqueness, leakage flags, ambiguity representability,
versioning and determinism. No LLM is involved anywhere."""

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
    assert rec["issues"]["primary_issue"] is None
    assert rec["entities"] == []
    assert validate_record(rec, body, title) == []

# -------------------------------------------------- required fields

def test_missing_required_field_rejected():
    rec, body, title = example("full_extraction_local_article")
    del rec["party_context"]
    assert any("party_context" in e for e in validate_structure(rec))


def test_unknown_field_rejected():
    rec, body, title = example("full_extraction_local_article")
    rec["sentiment_score"] = 0.9          # the reduction the spec bans
    assert any("sentiment_score" in e for e in validate_structure(rec))


def test_optional_fields_may_be_absent_or_null():
    rec, body, title = example("full_extraction_local_article")
    rec["electoral_consequences"][0]["voter_group"] = None
    rec["party_context"][0]["switching_origin_party"] = None
    del rec["frames"]                     # frames layer is optional
    assert validate_record(rec, body, title) == []

# ------------------------------------------------ evidence grounding

def test_evidence_span_is_mandatory_for_claims():
    rec, body, title = example("full_extraction_local_article")
    del rec["entities"][0]["evidence_span"]
    assert any("evidence_span" in e for e in validate_structure(rec))


def test_fabricated_evidence_span_fails_hard():
    rec, body, title = example("full_extraction_local_article")
    rec["party_context"][0]["evidence_span"]["text"] = \
        "this sentence does not appear in the article at all"
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R1") for e in errs)


def test_wrong_offsets_fail_and_correct_offsets_pass():
    rec, body, title = example("full_extraction_local_article")
    span = rec["entities"][0]["evidence_span"]
    span["char_start"], span["char_end"] = 0, 5
    assert any(e.startswith("R2")
               for e in validate_record(rec, body, title))
    start = body.index(span["text"])
    span["char_start"], span["char_end"] = start, start + len(span["text"])
    assert validate_record(rec, body, title) == []

# ------------------------------------------- confidence and statuses

def test_low_confidence_requires_review_routing():
    rec, body, title = example("full_extraction_local_article")
    rec["candidate_context"][0]["confidence"] = 0.3
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R3") for e in errs)
    rec["review_status"] = "flagged"
    assert validate_record(rec, body, title) == []


def test_confidence_and_score_bounds_enforced():
    rec, body, title = example("full_extraction_local_article")
    rec["party_context"][0]["local_relevance_score"] = 1.7
    assert any("1.7" in e for e in validate_structure(rec))


def test_empty_extraction_cannot_claim_extracted():
    rec, body, title = example("partial_extraction_ambiguous_article")
    rec["extraction_status"] = "extracted"
    assert any(e.startswith("R4")
               for e in validate_record(rec, body, title))


def test_not_attempted_must_be_empty():
    rec, body, title = example("full_extraction_local_article")
    rec["extraction_status"] = "not_attempted"
    assert any(e.startswith("R5")
               for e in validate_record(rec, body, title))

# ------------------------------------------------ Reform UK layer

def test_reform_example_validates_and_flags_are_grounded():
    rec, body, title = example("reform_uk_emergence_article")
    assert rec["reform_uk"]["reform_uk_present"] is True
    assert rec["reform_uk"]["switching_con_to_reform"] is True
    assert validate_record(rec, body, title) == []


def test_reform_absent_forbids_positive_flags():
    rec, body, title = example("full_extraction_local_article")
    rec["reform_uk"]["gaining_support"] = True   # but present=false
    assert any(e.startswith("R6")
               for e in validate_record(rec, body, title))


def test_reform_positive_flags_require_evidence():
    rec, body, title = example("reform_uk_emergence_article")
    rec["reform_uk"]["evidence_span"] = None
    assert any(e.startswith("R6")
               for e in validate_record(rec, body, title))


def test_reform_scores_forbidden_when_absent():
    rec, body, title = example("full_extraction_local_article")
    rec["reform_uk"]["credibility_score"] = 0.8
    assert any(e.startswith("R6")
               for e in validate_record(rec, body, title))

# ----------------------------------------- party / candidate rows

def test_multiple_party_rows_supported():
    rec, body, title = example("full_extraction_local_article")
    assert len(rec["party_context"]) == 2
    assert validate_record(rec, body, title) == []


def test_duplicate_party_rows_rejected():
    rec, body, title = example("full_extraction_local_article")
    rec["party_context"].append(
        copy.deepcopy(rec["party_context"][0]))
    assert any(e.startswith("R8")
               for e in validate_record(rec, body, title))


def test_multiple_candidate_rows_supported():
    rec, body, title = example("full_extraction_local_article")
    assert len(rec["candidate_context"]) == 2
    assert validate_record(rec, body, title) == []

# --------------------------------------------------------- leakage

def test_leakage_flags_require_evidence():
    rec, body, title = example("full_extraction_local_article")
    rec["leakage"]["contains_election_result"] = True
    assert any(e.startswith("R7")
               for e in validate_record(rec, body, title))


def test_post_voting_article_identifiable():
    rec, body, title = example("partial_extraction_ambiguous_article")
    assert rec["leakage"]["leakage_risk"] == "high"
    assert validate_record(rec, body, title) == []

# --------------------------------------------- versioning / Stage M

def test_schema_and_taxonomy_versions_pinned():
    rec, body, title = example("full_extraction_local_article")
    assert rec["schema_version"] == SCHEMA_VERSION
    rec2 = copy.deepcopy(rec)
    rec2["schema_version"] = "llm-context-v9.9-2030-01-01"
    assert validate_structure(rec2)
    rec3 = copy.deepcopy(rec)
    rec3["issues"]["taxonomy_version"] = "issues-v0.1"
    assert validate_structure(rec3)


def test_future_stage_m_article_uses_same_contract():
    rec, body, title = example("reform_uk_emergence_article")
    rec["article_id"] = "NEWS-stagem-future0000001"
    rec["canonical_article_id"] = "NEWS-stagem-future0000001"
    assert validate_record(rec, body, title) == []

# ------------------------------------------------------ determinism

def test_repeated_validation_identical_results():
    rec, body, title = example("full_extraction_local_article")
    rec["entities"][0]["evidence_span"]["text"] = "nope " * 3
    r1 = validate_record(copy.deepcopy(rec), body, title)
    r2 = validate_record(copy.deepcopy(rec), body, title)
    assert r1 == r2 and r1


def test_rules_layer_is_pure():
    rec, body, title = example("reform_uk_emergence_article")
    snapshot = copy.deepcopy(rec)
    validate_rules(rec, body, title)
    assert rec == snapshot

# ------------------------------------- Step 2.5: rules v1.1 additions

def test_taxonomy_v12_accepts_election_administration():
    rec, body, title = example("partial_extraction_ambiguous_article")
    rec["issues"]["taxonomy_version"] = "issues-v1.2"
    rec["issues"]["secondary_issues"] = [{
        "issue_code": "election_administration",
        "evidence_span": {"text": "Polling stations opened across the "
                                  "county at seven this morning."},
        "confidence": 0.9}]
    assert validate_record(rec, body, title) == []


def test_r9_new_code_forbidden_under_v11_stamp():
    rec, body, title = example("partial_extraction_ambiguous_article")
    assert rec["issues"]["taxonomy_version"] == "issues-v1.1"
    rec["issues"]["secondary_issues"] = [{
        "issue_code": "election_administration",
        "evidence_span": {"text": "Polling stations opened across the "
                                  "county at seven this morning."},
        "confidence": 0.9}]
    errs = validate_record(rec, body, title)
    assert any(e.startswith("R9") for e in errs)


def test_old_v11_records_still_validate():
    # traceability: every shipped example is stamped issues-v1.1 and
    # must keep validating under the revised schema and rules
    for e in EXAMPLES["examples"]:
        assert validate_record(e["record"], e["body_text"],
                               e["title"]) == []


def test_r7_leakage_flags_require_explanation():
    rec, body, title = example("full_extraction_local_article")
    rec["leakage"]["contains_poll"] = True
    rec["leakage"]["evidence_span"] = {
        "text": "The Liberal Democrat opposition warned the increase "
                "would squeeze household budgets"}
    errs = validate_record(rec, body, title)
    assert any("without an explanation" in e for e in errs)
    rec["leakage"]["explanation"] = ("contains polling-style claims "
                                     "about party support levels")
    assert validate_record(rec, body, title) == []


def test_prompt_v11_carries_refinements():
    from src.llm_extraction.pilot_sample import (PROMPT_VERSION,
                                                 build_system_prompt)
    p = build_system_prompt()
    assert PROMPT_VERSION in p
    assert "NEVER shorten a quote" in p
    assert "Do NOT output char_start" in p
    assert "issues-v1.2" in p and "election_administration" in p
    assert "leakage.explanation" in p


def test_revalidation_sampler_covers_categories():
    from src.llm_extraction.pilot_sample import select_revalidation_set
    pilot = []
    for i in range(6):
        pilot.append({"article_id": f"F{i}", "batch_result": "succeeded",
                      "validation_errors": ["R1 x"], "record": None})
    def rec(flagged=False, reform=False, leak=False):
        return {"review_status": "flagged" if flagged else "unreviewed",
                "reform_uk": {"reform_uk_present": reform},
                "leakage": {"leakage_risk": "high" if leak else "none",
                            "contains_poll": False,
                            "contains_prediction": False,
                            "contains_election_result": False}}
    for i in range(4):
        pilot.append({"article_id": f"V{i}", "batch_result": "succeeded",
                      "validation_errors": [],
                      "record": rec(flagged=i < 2, reform=i >= 2,
                                    leak=i == 3)})
    arts = {f"{k}{i}": {"title": "x", "body": "w " * (10 + i)}
            for k in ("F", "V") for i in range(6)}
    arts["ADMIN1"] = {"title": "Polling station changes announced",
                      "body": "w"}
    r = select_revalidation_set(pilot, arts)
    assert set(f"F{i}" for i in range(6)) <= set(r["selected"])
    assert "ADMIN1" in r["selected"]
    assert "sha256" in r["method"]
    r2 = select_revalidation_set(list(reversed(pilot)), arts)
    assert r["selected"] == r2["selected"]
