"""Phase 6 / Step 3 tests: structural validation, taxonomy
discipline, primary/secondary separation, evidence and relevance
rules, determinism. No API is called anywhere in this file."""

import copy

from src.llm_extraction.issue_classification import (
    CLS_PROMPT_VERSION, CLS_SCHEMA_VERSION, build_issue_prompt,
    validate_issue_record, validate_structure)

BODY = ("Surrey County Council approved a 4.99% council tax increase "
        "on Tuesday after years of rising social care demand. The "
        "Liberal Democrat opposition warned the rise would squeeze "
        "household budgets across Woking before May's elections.")
TITLE = "Council tax rise approved ahead of elections"


def issue(code="council_tax", text="approved a 4.99% council tax "
          "increase on Tuesday", conf=0.9):
    return {"issue_code": code,
            "explanation": "the article reports the council tax "
                           "decision itself",
            "evidence_span": {"text": text}, "confidence": conf}


def record(**kw):
    base = {"schema_version": CLS_SCHEMA_VERSION,
            "article_id": "A", "canonical_article_id": "A",
            "extraction_status": "extracted",
            "review_status": "unreviewed",
            "issues": {"taxonomy_version": "issues-v1.2",
                       "primary_issue": issue(),
                       "secondary_issues": [
                           issue("social_care", "after years of rising "
                                 "social care demand", 0.8)]},
            "political_relevance": {
                "election_competition_related": True,
                "affected_actors": ["Liberal Democrats"],
                "may_influence_voter_perceptions": True,
                "explanation": "tax rise framed against the coming "
                               "elections",
                "evidence_span": {"text": "squeeze household budgets "
                                  "across Woking before May's "
                                  "elections"}}}
    base.update(kw)
    return base

# --------------------------------------------------------- happy path

def test_valid_record_passes():
    assert validate_issue_record(record(), BODY, TITLE) == []


def test_empty_classification_is_representable():
    r = record(extraction_status="partial",
               issues={"taxonomy_version": "issues-v1.2",
                       "primary_issue": None, "secondary_issues": []},
               political_relevance={
                   "election_competition_related": False,
                   "affected_actors": [],
                   "may_influence_voter_perceptions": False},
               ambiguity_notes=[{"reason": "no political issue "
                                 "discussed"}])
    assert validate_issue_record(r, BODY, TITLE) == []

# ---------------------------------------------------------- taxonomy

def test_invented_category_rejected():
    r = record()
    r["issues"]["primary_issue"]["issue_code"] = "made_up_issue"
    assert any("made_up_issue" in e for e in validate_structure(r))


def test_taxonomy_version_pinned():
    r = record()
    r["issues"]["taxonomy_version"] = "issues-v1.1"
    assert validate_structure(r)


def test_election_administration_available():
    r = record()
    r["issues"]["primary_issue"] = issue(
        "election_administration",
        "approved a 4.99% council tax increase on Tuesday")
    assert validate_issue_record(r, BODY, TITLE) == []

# ------------------------------------------- primary / secondary (S3)

def test_primary_repeated_in_secondary_rejected():
    r = record()
    r["issues"]["secondary_issues"].append(issue())   # same code again
    errs = validate_issue_record(r, BODY, TITLE)
    assert any(e.startswith("S3") for e in errs)


def test_duplicate_secondary_codes_rejected():
    r = record()
    r["issues"]["secondary_issues"] = [
        issue("social_care", "after years of rising social care demand"),
        issue("social_care", "after years of rising social care demand")]
    errs = validate_issue_record(r, BODY, TITLE)
    assert any("duplicate secondary" in e for e in errs)

# --------------------------------------------------- evidence (S1/S2)

def test_fabricated_evidence_rejected():
    r = record()
    r["issues"]["primary_issue"]["evidence_span"]["text"] = \
        "this text is nowhere in the article body at all"
    errs = validate_issue_record(r, BODY, TITLE)
    assert any(e.startswith("S1") for e in errs)


def test_evidence_and_explanation_required_by_structure():
    # the oneOf wrapper reports at the primary_issue path; dropping a
    # required field must make the record structurally invalid
    r = record()
    del r["issues"]["primary_issue"]["evidence_span"]
    assert any("primary_issue" in e for e in validate_structure(r))
    r2 = record()
    del r2["issues"]["primary_issue"]["explanation"]
    assert any("primary_issue" in e for e in validate_structure(r2))
    # a secondary issue reports the field name directly
    r3 = record()
    del r3["issues"]["secondary_issues"][0]["explanation"]
    assert any("explanation" in e for e in validate_structure(r3))


def test_low_confidence_forces_flagged():
    r = record()
    r["issues"]["secondary_issues"][0]["confidence"] = 0.3
    errs = validate_issue_record(r, BODY, TITLE)
    assert any(e.startswith("S2") for e in errs)
    r["review_status"] = "flagged"
    assert validate_issue_record(r, BODY, TITLE) == []

# ------------------------------------------------- relevance (S4)

def test_relevance_claims_need_evidence():
    r = record()
    r["political_relevance"]["evidence_span"] = None
    errs = validate_issue_record(r, BODY, TITLE)
    assert any(e.startswith("S4") for e in errs)
    r["political_relevance"]["election_competition_related"] = False
    r["political_relevance"]["may_influence_voter_perceptions"] = False
    assert validate_issue_record(r, BODY, TITLE) == []

# ----------------------------------------------- statuses / misc

def test_empty_cannot_claim_extracted():
    r = record(issues={"taxonomy_version": "issues-v1.2",
                       "primary_issue": None, "secondary_issues": []},
               political_relevance={
                   "election_competition_related": False,
                   "affected_actors": [],
                   "may_influence_voter_perceptions": False})
    errs = validate_issue_record(r, BODY, TITLE)
    assert any(e.startswith("S5") for e in errs)


def test_prompt_is_stable_and_grounded_in_taxonomy():
    p1, p2 = build_issue_prompt(), build_issue_prompt()
    assert p1 == p2
    assert CLS_PROMPT_VERSION in p1 and CLS_SCHEMA_VERSION in p1
    assert "election_administration" in p1
    assert "CHARACTER-FOR-CHARACTER" in p1
    assert "never invent" in p1


def test_deterministic_validation():
    r = record()
    r["issues"]["primary_issue"]["evidence_span"]["text"] = "nope " * 3
    e1 = validate_issue_record(copy.deepcopy(r), BODY, TITLE)
    e2 = validate_issue_record(copy.deepcopy(r), BODY, TITLE)
    assert e1 == e2 and e1
