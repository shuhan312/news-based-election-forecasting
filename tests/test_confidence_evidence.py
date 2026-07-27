"""Phase 6 / Step 10 tests: claim flattening, consistency checks,
confidence bands, uncertainty representation, aggregation and
determinism. Pure functions - no API, no file IO."""

import copy

from src.llm_extraction.confidence_evidence import (
    article_uncertainty_reasons, band, check_claim, flatten_record,
    summarise)

BODY = ("Residents criticised the Conservative-led council over the "
        "state of local roads, while Reform UK claimed growing "
        "support across the county.")
TITLE = "Roads row grows"


def make_claim(**kw):
    base = {"extraction_field": "party_context[Conservative].stance",
            "extracted_value": "critical",
            "evidence_span": {"text": "Residents criticised the "
                              "Conservative-led council"},
            "confidence_score": 0.86, "layer": "pilot_full_schema"}
    base.update(kw)
    return base

# ------------------------------------------------------------- bands

def test_confidence_bands():
    assert band(0.95) == "high" and band(0.80) == "high"
    assert band(0.79) == "medium" and band(0.50) == "medium"
    assert band(0.49) == "low" and band(0.0) == "low"
    assert band(None) == "missing"

# --------------------------------------------------------- checks

def test_supported_claim_clean():
    c = check_claim(make_claim(), BODY, TITLE, False)
    assert c["evidence_supported"] is True
    assert c["consistency_flags"] == []
    assert c["human_review_required"] is False
    assert c["uncertainty_flag"] is False


def test_hallucinated_evidence_flagged():
    c = check_claim(make_claim(evidence_span={"text": "this text is "
                    "nowhere in the article"}), BODY, TITLE, False)
    assert c["evidence_supported"] is False
    assert "evidence_not_verbatim" in c["consistency_flags"]
    assert c["human_review_required"] is True


def test_definite_value_without_evidence_is_unsupported():
    c = check_claim(make_claim(evidence_span=None), BODY, TITLE, False)
    assert "unsupported" in c["consistency_flags"]
    assert c["human_review_required"] is True


def test_uncertain_value_without_evidence_recorded_not_unsupported():
    c = check_claim(make_claim(extracted_value="uncertain",
                    evidence_span=None, confidence_score=0.6),
                    BODY, TITLE, False)
    assert "missing_evidence_recorded" in c["consistency_flags"]
    assert "unsupported" not in c["consistency_flags"]
    assert c["uncertainty_flag"] is True


def test_weak_evidence_high_confidence_flagged():
    # uncertainty must not be forced into high confidence
    c = check_claim(make_claim(extracted_value="uncertain",
                    confidence_score=0.9), BODY, TITLE, False)
    assert "weak_evidence_high_confidence" in c["consistency_flags"]
    assert c["human_review_required"] is True


def test_low_confidence_routes_to_review():
    c = check_claim(make_claim(confidence_score=0.3), BODY, TITLE,
                    False)
    assert c["confidence_band"] == "low"
    assert c["human_review_required"] is True
    assert "low confidence" in c["uncertainty_reason"]


def test_record_flag_propagates():
    c = check_claim(make_claim(), BODY, TITLE, True)
    assert c["human_review_required"] is True

# ------------------------------------------------------- flattening

def test_flatten_party_context_rows():
    rec = {"party_context": [{
        "party": "Conservative", "overall_context": "negative",
        "stance": "critical", "blame": True, "credit": False,
        "competence": "portrayed_negatively",
        "integrity": "not_addressed",
        "support_trajectory": "losing",
        "challenger_credibility": "not_addressed",
        "voter_switching_discussed": False,
        "evidence_span": {"text": "Residents criticised"},
        "confidence": 0.8}]}
    claims = flatten_record("pilot_full_schema", rec)
    fields = {c["extraction_field"] for c in claims}
    assert "party_context[Conservative].stance" in fields
    assert "party_context[Conservative].blame" in fields
    assert all(c["confidence_score"] == 0.8 for c in claims)


def test_flatten_reform_only_when_present():
    rec = {"reform_uk": {"reform_uk_present": False,
                         "confidence": 0.9}}
    assert flatten_record("pilot_full_schema", rec) == []
    rec2 = {"reform_uk": {"reform_uk_present": True,
                          "gaining_support": True,
                          "national_momentum": True,
                          "evidence_span": {"text": "claimed growing "
                                            "support across"},
                          "confidence": 0.8}}
    claims = flatten_record("pilot_full_schema", rec2)
    assert any(c["extraction_field"] == "reform_uk.gaining_support"
               for c in claims)


def test_flatten_temporal_shares_record_span():
    rec = {"impact_horizon": "medium_term",
           "evidence_span": {"text": "the row will run for months"},
           "confidence": 0.7,
           "temporal_mechanism": {"persistence": "continuing",
                                  "continuing_story": "yes",
                                  "expected_decay": "gradual",
                                  "impact_start": "immediate",
                                  "rationale": "x" * 12}}
    claims = flatten_record("temporal", rec)
    assert len(claims) == 4          # horizon + three mechanism fields
    assert all(c["evidence_span"]["text"].startswith("the row")
               for c in claims)

# --------------------------------------------- article-level reasons

def test_canonical_uncertainty_reasons():
    recs = {"relevance": {"geographic_scope": "national",
                          "electoral_interpretation": "none"},
            "pilot_full_schema": {"reform_uk": {
                "reform_uk_present": True, "national_momentum": True,
                "local_campaign_activity": False}}}
    reasons = article_uncertainty_reasons(recs)
    assert "National issue without explicit local electoral linkage" \
        in reasons
    assert ("Coverage indicates national momentum but local "
            "conversion uncertain") in reasons

# ---------------------------------------------------- aggregation

def test_summarise_counts():
    claims = [check_claim(make_claim(), BODY, TITLE, False),
              check_claim(make_claim(confidence_score=0.3), BODY,
                          TITLE, False),
              check_claim(make_claim(evidence_span=None), BODY,
                          TITLE, False)]
    s = summarise(claims)
    assert s["total_claims"] == 3
    assert s["supported_claims"] == 2
    assert s["unsupported_claims"] == 1
    assert s["confidence_distribution"]["high"] == 2
    assert s["review_required"] == 2


def test_deterministic():
    c1 = check_claim(copy.deepcopy(make_claim()), BODY, TITLE, False)
    c2 = check_claim(copy.deepcopy(make_claim()), BODY, TITLE, False)
    assert c1 == c2
