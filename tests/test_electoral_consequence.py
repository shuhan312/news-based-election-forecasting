"""Phase 6 / Step 7 tests: structural validation, the
no-prediction guarantee, mechanism/evidence discipline, Reform UK
addendum consistency and determinism. No API is called anywhere."""

import copy

from src.llm_extraction.electoral_consequence import (
    EC_PROMPT_VERSION, EC_SCHEMA_VERSION, build_ec_prompt,
    validate_ec_record, validate_structure)

BODY = ("Analysts said the council tax row hands the Liberal "
        "Democrats a clear line of attack, while Reform UK claimed "
        "growing support among former Conservative voters angry at "
        "the administration, positioning itself as the credible "
        "alternative in the county.")
TITLE = "Tax row reshapes the race"


def consequence(**kw):
    base = {"direction": "potential_damage",
            "affected_actor_name": "Conservative administration",
            "affected_actor_type": "council",
            "impact_mechanism": "service_dissatisfaction",
            "mechanism_reasoning": "the tax row links the "
                                   "administration to household "
                                   "financial pain",
            "voter_groups": ["taxpayers", "local_residents"],
            "electoral_signal": "incumbent_vulnerability",
            "evidence_span": {"text": "the council tax row hands the "
                              "Liberal Democrats a clear line of "
                              "attack"},
            "confidence": 0.8}
    base.update(kw)
    return base


def record(**kw):
    base = {"schema_version": EC_SCHEMA_VERSION,
            "article_id": "A", "canonical_article_id": "A",
            "extraction_status": "extracted",
            "review_status": "unreviewed",
            "consequences": [
                consequence(),
                consequence(direction="potential_benefit",
                            affected_actor_name="Reform UK",
                            affected_actor_type="party",
                            impact_mechanism="challenger_credibility",
                            mechanism_reasoning="the article presents "
                            "Reform as the credible alternative "
                            "gaining defectors",
                            voter_groups=["existing_supporters",
                                          "undecided_voters"],
                            electoral_signal="challenger_emergence",
                            evidence_span={"text": "positioning "
                                           "itself as the credible "
                                           "alternative in the "
                                           "county"})],
            "reform_uk": {
                "applicable": True,
                "growth_suggested": True,
                "credible_challenger": True,
                "established_support_affected": ["conservative"],
                "switching_directions": ["con_to_reform"],
                "signal_nature": ["anti_incumbent_sentiment"],
                "evidence_span": {"text": "growing support among "
                                  "former Conservative voters angry "
                                  "at the administration"},
                "confidence": 0.8}}
    base.update(kw)
    return base

# --------------------------------------------------------- happy path

def test_valid_record_passes():
    assert validate_ec_record(record(), BODY, TITLE) == []


def test_empty_consequences_representable():
    r = record(extraction_status="partial", consequences=[],
               reform_uk={"applicable": False, "confidence": 0.9},
               ambiguity_notes=[{"reason": "no electoral implication "
                                 "present"}])
    assert validate_ec_record(r, BODY, TITLE) == []

# ---------------------------------- the no-prediction guarantee

def test_prediction_fields_are_unrepresentable():
    r = record()
    r["predicted_winner"] = "Liberal Democrats"
    assert any("predicted_winner" in e for e in validate_structure(r))
    r2 = record()
    r2["consequences"][0]["vote_share_estimate"] = 0.4
    assert any("vote_share_estimate" in e for e in validate_structure(r2))


def test_direction_vocabulary_is_potential_only():
    r = record()
    r["consequences"][0]["direction"] = "will_win"
    assert any("will_win" in e for e in validate_structure(r))

# ----------------------------------------------------- structure

def test_mechanism_vocabulary_enforced():
    r = record()
    r["consequences"][0]["impact_mechanism"] = "magic"
    assert any("magic" in e for e in validate_structure(r))


def test_voter_groups_vocabulary_enforced():
    r = record()
    r["consequences"][0]["voter_groups"] = ["everyone"]
    assert any("everyone" in e for e in validate_structure(r))


def test_actor_linked_with_name_and_type():
    r = record()
    del r["consequences"][0]["affected_actor_type"]
    assert any("affected_actor_type" in e for e in validate_structure(r))

# ------------------------------------------------------- E-rules

def test_e1_fabricated_evidence_rejected():
    r = record()
    r["consequences"][0]["evidence_span"]["text"] = \
        "this sentence does not appear in the article at all"
    errs = validate_ec_record(r, BODY, TITLE)
    assert any(e.startswith("E1") for e in errs)


def test_e2_low_confidence_forces_flagged():
    r = record()
    r["consequences"][1]["confidence"] = 0.3
    errs = validate_ec_record(r, BODY, TITLE)
    assert any(e.startswith("E2") for e in errs)
    r["review_status"] = "flagged"
    assert validate_ec_record(r, BODY, TITLE) == []


def test_e3_duplicate_consequences_rejected():
    r = record()
    r["consequences"].append(copy.deepcopy(r["consequences"][0]))
    errs = validate_ec_record(r, BODY, TITLE)
    assert any(e.startswith("E3") for e in errs)


def test_e4_reform_not_applicable_must_be_clean():
    r = record()
    r["reform_uk"]["applicable"] = False
    errs = validate_ec_record(r, BODY, TITLE)
    assert any(e.startswith("E4") for e in errs)


def test_e4_reform_content_requires_evidence():
    r = record()
    r["reform_uk"]["evidence_span"] = None
    errs = validate_ec_record(r, BODY, TITLE)
    assert any(e.startswith("E4") for e in errs)


def test_e5_empty_cannot_claim_extracted():
    r = record(consequences=[],
               reform_uk={"applicable": False, "confidence": 0.9})
    errs = validate_ec_record(r, BODY, TITLE)
    assert any(e.startswith("E5") for e in errs)

# ----------------------------------------------------- prompt / misc

def test_prompt_is_stable_and_forbids_prediction():
    p1, p2 = build_ec_prompt(), build_ec_prompt()
    assert p1 == p2
    assert EC_PROMPT_VERSION in p1 and EC_SCHEMA_VERSION in p1
    assert "IMPLICATIONS, NEVER PREDICTIONS" in p1
    assert "CHARACTER-FOR-CHARACTER" in p1
    assert "NEVER assumed to create votes" in p1


def test_deterministic_validation():
    r = record()
    r["consequences"][0]["evidence_span"]["text"] = "nope " * 3
    e1 = validate_ec_record(copy.deepcopy(r), BODY, TITLE)
    e2 = validate_ec_record(copy.deepcopy(r), BODY, TITLE)
    assert e1 == e2 and e1
