"""Phase 6 / Step 9 tests: deterministic window arithmetic with
boundary cases, leakage flagging, publication/horizon separation,
H-rules and determinism. No API is called anywhere."""

import copy

from src.llm_extraction.temporal_horizon import (
    TH_PROMPT_VERSION, TH_SCHEMA_VERSION, assign_windows,
    build_th_prompt, validate_th_record, validate_structure)

# SCC-2021-05 polling day: 2021-05-06 (from the protocol ELECTIONS)

# ---------------------------------------------- deterministic windows

def test_window_boundaries_exact():
    cases = {
        "2021-05-05": "final_72_hours",     # d=1
        "2021-05-03": "final_72_hours",     # d=3 boundary
        "2021-05-02": "7_to_4_days",        # d=4 boundary
        "2021-04-29": "7_to_4_days",        # d=7
        "2021-04-28": "14_to_8_days",       # d=8
        "2021-04-22": "14_to_8_days",       # d=14
        "2021-04-21": "30_to_15_days",      # d=15
        "2021-04-06": "30_to_15_days",      # d=30
        "2021-04-05": "90_to_31_days",      # d=31
        "2021-02-05": "90_to_31_days",      # d=90
        "2021-02-04": "180_to_91_days",     # d=91
        "2020-11-07": "180_to_91_days",     # d=180
    }
    for pub, expect in cases.items():
        got = assign_windows(pub, "SCC-2021-05")
        assert got["election_window"] == expect, (pub, got)


def test_post_voting_flagged_never_windowed():
    r = assign_windows("2021-05-06", "SCC-2021-05")   # polling day
    assert r["election_window"] == "post_voting"
    assert "published_after_voting_began" in r["flags"]
    assert not any(r["cumulative_window_membership"].values())
    r2 = assign_windows("2021-05-10", "SCC-2021-05")  # after
    assert r2["election_window"] == "post_voting"


def test_outside_180_flagged():
    r = assign_windows("2020-10-01", "SCC-2021-05")
    assert r["election_window"] == "outside_collection_window"
    assert "outside_180_day_window" in r["flags"]


def test_unresolved_date_flagged():
    r = assign_windows("", "SCC-2021-05")
    assert r["election_window"] == "unassignable"
    assert "unresolved_publication_date" in r["flags"]
    assert r["days_before_polling"] is None


def test_result_flag_carried():
    r = assign_windows("2021-05-01", "SCC-2021-05", contains_result=True)
    assert "contains_election_result" in r["flags"]


def test_cumulative_membership_nested():
    r = assign_windows("2021-05-04", "SCC-2021-05")   # d=2
    m = r["cumulative_window_membership"]
    assert all(m.values())                            # inside all six
    r2 = assign_windows("2021-04-16", "SCC-2021-05")  # d=20
    m2 = r2["cumulative_window_membership"]
    assert m2["previous_30_days"] and m2["previous_180_days"]
    assert not m2["previous_14_days"] and not m2["previous_72_hours"]


def test_hours_recorded_with_precision_statement():
    r = assign_windows("2021-05-03", "SCC-2021-05")
    assert r["hours_before_polling"] == 72
    assert r["hours_precision"] == "date_only_lower_bound"


def test_deterministic_repeatable():
    a = assign_windows("2021-04-01", "SCC-2021-05")
    b = assign_windows("2021-04-01", "SCC-2021-05")
    assert a == b

# ------------------------------------------------------- LLM record


def rec(**kw):
    base = {"schema_version": TH_SCHEMA_VERSION,
            "article_id": "A", "canonical_article_id": "A",
            "extraction_status": "extracted",
            "review_status": "unreviewed",
            "impact_horizon": "medium_term",
            "temporal_mechanism": {
                "impact_start": "immediate",
                "persistence": "continuing",
                "continuing_story": "yes",
                "expected_decay": "gradual",
                "rationale": "a budget dispute framed as running "
                             "through the campaign season"},
            "story_type": "developing_controversy",
            "political_linkage": {
                "affected_actor": "Conservative administration",
                "affected_voter_group": "taxpayers",
                "relevant_issue": "council_finance",
                "signal_temporality": "cumulative",
                "national_precedes_local": False},
            "reform_uk": {"applicable": False, "confidence": 0.9},
            "evidence_span": {"text": "the row is set to run until "
                              "polling day as budget scrutiny "
                              "continues"},
            "confidence": 0.8}
    base.update(kw)
    return base


BODY = ("The council tax dispute deepened this week and the row is "
        "set to run until polling day as budget scrutiny continues "
        "in committee after committee.")
TITLE = "Budget row runs on"


def test_valid_record_passes():
    assert validate_th_record(rec(), BODY, TITLE) == []


def test_uncertain_horizon_may_omit_evidence():
    r = rec(impact_horizon="uncertain", evidence_span=None)
    assert validate_th_record(r, BODY, TITLE) == []


def test_h3_definite_horizon_requires_evidence():
    r = rec(evidence_span=None)
    errs = validate_th_record(r, BODY, TITLE)
    assert any(e.startswith("H3") for e in errs)


def test_h1_fabricated_evidence_rejected():
    r = rec()
    r["evidence_span"]["text"] = "not in the article at all, truly"
    errs = validate_th_record(r, BODY, TITLE)
    assert any(e.startswith("H1") for e in errs)


def test_h2_low_confidence_forces_flagged():
    r = rec(confidence=0.3)
    errs = validate_th_record(r, BODY, TITLE)
    assert any(e.startswith("H2") for e in errs)
    r["review_status"] = "flagged"
    assert validate_th_record(r, BODY, TITLE) == []


def test_h4_reform_consistency():
    r = rec()
    r["reform_uk"] = {"applicable": False,
                      "temporal_character": ["short_lived_publicity"],
                      "confidence": 0.8}
    errs = validate_th_record(r, BODY, TITLE)
    assert any(e.startswith("H4") for e in errs)


def test_h6_none_political_needs_uncertain_or_note():
    r = rec(story_type="none_political")
    errs = validate_th_record(r, BODY, TITLE)
    assert any(e.startswith("H6") for e in errs)
    r["ambiguity_notes"] = [{"reason": "human-interest piece with a "
                             "political aside"}]
    assert validate_th_record(r, BODY, TITLE) == []


def test_horizon_vocabulary_constrained():
    r = rec()
    r["impact_horizon"] = "forever"
    assert any("forever" in e for e in validate_structure(r))


def test_prompt_separates_publication_from_horizon():
    p1, p2 = build_th_prompt(), build_th_prompt()
    assert p1 == p2
    assert TH_PROMPT_VERSION in p1
    assert "NOT given the publication date" in p1
    assert "CHARACTER-FOR-CHARACTER" in p1


def test_deterministic_validation():
    r = rec()
    r["evidence_span"]["text"] = "nope " * 3
    e1 = validate_th_record(copy.deepcopy(r), BODY, TITLE)
    e2 = validate_th_record(copy.deepcopy(r), BODY, TITLE)
    assert e1 == e2 and e1
