"""Tests for the Article Eligibility Manual Review infrastructure:
schema/validation rules (manual_review_schema.py), stratified-sampling
reproducibility (build_manual_review_sample.py), and the Cohen's kappa
arithmetic (compute_review_agreement.py).

These tests never touch the real corpus (data/raw/news/records or the
gitignored eligibility_assessment.csv) - every case builds its own
small, explicit rows in memory, so the suite runs the same way with or
without a populated news_collection/ directory, and a future reader can
see exactly what input produced each expected result.
"""

import pytest

from src.news_collection.build_manual_review_sample import (
    select_kappa_subset, select_sample)
from src.news_collection.compute_review_agreement import cohens_kappa
from src.news_collection.manual_review_schema import (
    REASON_CODES, RULES, ValidationError, derive_overall_decision,
    is_eligible_for_downstream, needs_second_review_flag, validate_row)


# ---------------------------------------------------------------------------
# Helpers - build a fully-specified review row so each test only needs
# to override the one or two fields it's actually exercising.
# ---------------------------------------------------------------------------

def make_row(**overrides):
    row = {
        "article_id": "NEWS-test-0001",
        "e4_decision": "include", "e4_reason_code": "E4-CLEAR",
        "e4_supporting_text": "quoted evidence", "e4_confidence": "high",
        "e5_decision": "include", "e5_reason_code": "E5-L1-PLACE",
        "e5_supporting_text": "quoted evidence", "e5_confidence": "high",
        "e6_decision": "not_applicable",
        "e6_reason_code": "E6-NOT-REFORM-FLAGGED",
        "e6_supporting_text": "", "e6_confidence": "",
        "e8_decision": "include", "e8_reason_code": "E8-EDITORIAL-CONFIRMED",
        "e8_supporting_text": "quoted evidence", "e8_confidence": "high",
        "original_manual_decision": "include",
        "second_review_required": "False",
        "final_reviewed_decision": "include",
        "correction_reason": "",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Schema sanity - every registered reason code names a real decision
# ---------------------------------------------------------------------------

class TestReasonCodeRegistry:
    def test_every_reason_code_maps_to_a_real_decision(self):
        from src.news_collection.manual_review_schema import DECISIONS
        for rule in RULES:
            for code, decision in REASON_CODES[rule].items():
                assert decision in DECISIONS, (
                    f"{rule}'s {code} claims decision {decision!r}, not "
                    "a real value in DECISIONS")

    def test_not_applicable_only_registered_for_e6(self):
        for rule in RULES:
            for code, decision in REASON_CODES[rule].items():
                if decision == "not_applicable":
                    assert rule == "E6", (
                        f"{rule}'s {code} is registered as "
                        "not_applicable, but only E6 may ever be n/a")


# ---------------------------------------------------------------------------
# derive_overall_decision - precedence and the not_applicable carve-out
# ---------------------------------------------------------------------------

class TestDeriveOverallDecision:
    def test_all_include_is_include(self):
        assert derive_overall_decision(
            "include", "include", "not_applicable", "include") == "include"

    def test_any_exclude_wins_outright(self):
        assert derive_overall_decision(
            "include", "exclude", "not_applicable", "include") == "exclude"

    def test_exclude_beats_needs_second_review(self):
        assert derive_overall_decision(
            "needs_second_review", "exclude", "not_applicable",
            "include") == "exclude"

    def test_needs_second_review_beats_insufficient_evidence(self):
        assert derive_overall_decision(
            "insufficient_evidence", "needs_second_review",
            "not_applicable", "include") == "needs_second_review"

    def test_needs_second_review_blocks_include(self):
        assert derive_overall_decision(
            "include", "include", "not_applicable",
            "needs_second_review") == "needs_second_review"

    def test_insufficient_evidence_blocks_include_when_nothing_worse(self):
        assert derive_overall_decision(
            "include", "insufficient_evidence", "not_applicable",
            "include") == "insufficient_evidence"

    def test_e6_not_applicable_does_not_block_include(self):
        # a non-Reform-flagged article can still be fully included -
        # not_applicable must never be treated as "unresolved"
        assert derive_overall_decision(
            "include", "include", "not_applicable", "include") == "include"

    def test_e6_real_decision_participates_like_any_other_rule(self):
        assert derive_overall_decision(
            "include", "include", "exclude", "include") == "exclude"


class TestNeedsSecondReviewFlag:
    def test_false_when_nothing_flagged(self):
        assert needs_second_review_flag(
            "include", "include", "not_applicable", "include") is False

    def test_true_when_any_rule_flagged(self):
        assert needs_second_review_flag(
            "include", "needs_second_review", "not_applicable",
            "include") is True


# ---------------------------------------------------------------------------
# validate_row - requirement 6's checks
# ---------------------------------------------------------------------------

class TestValidateRow:
    def test_a_fully_consistent_row_passes(self):
        assert validate_row(make_row()) is True

    def test_missing_reason_code_fails(self):
        row = make_row(e4_reason_code="")
        with pytest.raises(ValidationError, match="no reason_code"):
            validate_row(row)

    def test_unregistered_reason_code_fails(self):
        row = make_row(e4_reason_code="E4-MADE-UP-CODE")
        with pytest.raises(ValidationError, match="not a registered"):
            validate_row(row)

    def test_reason_code_decision_mismatch_fails(self):
        # E4-LEAK-RESULT is registered under "exclude", not "include"
        row = make_row(e4_decision="include", e4_reason_code="E4-LEAK-RESULT")
        with pytest.raises(ValidationError, match="code/decision mismatch"):
            validate_row(row)

    def test_judgement_without_supporting_text_fails(self):
        row = make_row(e5_supporting_text="")
        with pytest.raises(ValidationError, match="no supporting_text"):
            validate_row(row)

    def test_insufficient_evidence_does_not_require_supporting_text(self):
        row = make_row(
            e5_decision="insufficient_evidence",
            e5_reason_code="E5-NO-FULL-TEXT",
            e5_supporting_text="", e5_confidence="",
            original_manual_decision="insufficient_evidence",
            final_reviewed_decision="insufficient_evidence")
        assert validate_row(row) is True

    def test_include_or_exclude_requires_a_confidence_level(self):
        row = make_row(e4_confidence="")
        with pytest.raises(ValidationError, match="needs a confidence"):
            validate_row(row)

    def test_e6_not_applicable_valid_only_for_e6(self):
        row = make_row(e4_decision="not_applicable",
                       e4_reason_code="E4-CLEAR")
        with pytest.raises(ValidationError,
                          match="only a valid decision for E6"):
            validate_row(row)

    def test_original_decision_must_match_derivation(self):
        # original and final agree with EACH OTHER (so this isn't a
        # "corrected later" case) but neither matches what the actual
        # per-rule decisions derive to (should be "include")
        row = make_row(original_manual_decision="exclude",
                       final_reviewed_decision="exclude")
        with pytest.raises(ValidationError, match="does not match what"):
            validate_row(row)

    def test_conflicting_decision_needs_reason(self):
        row = make_row(final_reviewed_decision="exclude",
                       correction_reason="")
        with pytest.raises(ValidationError, match="correction_reason"):
            validate_row(row)

    def test_conflicting_decision_with_reason_passes(self):
        row = make_row(
            e8_decision="exclude", e8_reason_code="E8-NOTICE-ONLY",
            final_reviewed_decision="exclude",
            correction_reason="Second reviewer judged this a bare notice.")
        assert validate_row(row) is True

    def test_cannot_mark_final_include_with_an_unresolved_rule(self):
        row = make_row(
            e5_decision="needs_second_review",
            e5_reason_code="", e5_supporting_text="",
            e5_confidence="",
            original_manual_decision="needs_second_review",
            second_review_required="True",
            final_reviewed_decision="include")   # contradiction
        with pytest.raises(ValidationError, match="still.*unresolved"):
            validate_row(row)

    def test_second_review_required_must_match_the_flags(self):
        row = make_row(second_review_required="True")   # nothing flagged
        with pytest.raises(ValidationError,
                          match="second_review_required"):
            validate_row(row)


class TestIsEligibleForDownstream:
    def test_valid_include_is_eligible(self):
        assert is_eligible_for_downstream(make_row()) is True

    def test_needs_second_review_is_not_eligible(self):
        row = make_row(
            e4_decision="needs_second_review", e4_reason_code="",
            e4_supporting_text="", e4_confidence="",
            original_manual_decision="needs_second_review",
            second_review_required="True",
            final_reviewed_decision="needs_second_review")
        assert is_eligible_for_downstream(row) is False

    def test_an_internally_invalid_row_is_not_eligible_even_if_labelled_include(self):
        # final_reviewed_decision says "include" but the row is broken
        # (missing reason code) - must not leak into the corpus anyway
        row = make_row(e4_reason_code="")
        assert row["final_reviewed_decision"] == "include"
        assert is_eligible_for_downstream(row) is False


# ---------------------------------------------------------------------------
# Stratified sampling - reproducibility and rare-category coverage
# ---------------------------------------------------------------------------

def _synthetic_pool():
    """A small hand-built pool exercising every stratification
    dimension select_sample() cares about, so these tests don't depend
    on the real (gitignored, environment-specific) corpus existing."""
    pool = []
    idx = 0
    elections = ["SCC-2013-05", "SCC-2017-05", "SCC-2021-05", "ESWS-2026-05"]
    for election in elections:
        for arm in ("local", "national"):
            for i in range(15):
                idx += 1
                pool.append({
                    "article_id": f"NEWS-synth-{idx:04d}",
                    "election_id": election, "arm": arm,
                    "source_id": "synth_source",
                    "needs_reform_disambiguation": (
                        "yes" if i % 5 == 0 else ""),
                    "status": "pending_human_review", "note": "",
                    "_route": "guardian" if arm == "national" else "wayback",
                    "_text_completeness": "full",
                })
    # a handful of deliberately rare cells
    for i, route in enumerate(("serpapi", "serpapi", "site_search")):
        idx += 1
        pool.append({
            "article_id": f"NEWS-synth-rare-route-{idx:04d}",
            "election_id": "ESWS-2026-05", "arm": "local",
            "source_id": "synth_source", "needs_reform_disambiguation": "",
            "status": "pending_human_review", "note": "",
            "_route": route, "_text_completeness": "full",
        })
    for i, completeness in enumerate(("missing", "partial")):
        idx += 1
        pool.append({
            "article_id": f"NEWS-synth-rare-text-{idx:04d}",
            "election_id": "SCC-2013-05", "arm": "national",
            "source_id": "synth_source", "needs_reform_disambiguation": "",
            "status": "pending_human_review", "note": "",
            "_route": "guardian", "_text_completeness": completeness,
        })
    return pool


class TestStratifiedSampling:
    def test_sampling_is_reproducible(self):
        pool = _synthetic_pool()
        first = select_sample(pool)
        second = select_sample(pool)
        first_ids = [r["article_id"] for r in first]
        second_ids = [r["article_id"] for r in second]
        assert first_ids == second_ids, (
            "the same pool must yield the same sample, in the same "
            "order, on every run")

    def test_kappa_subset_is_reproducible(self):
        pool = _synthetic_pool()
        sample = select_sample(pool)
        first = select_kappa_subset(sample)
        second = select_kappa_subset(sample)
        assert ([r["article_id"] for r in first] ==
               [r["article_id"] for r in second])

    def test_rare_route_categories_are_all_included(self):
        pool = _synthetic_pool()
        sample = select_sample(pool)
        routes = {r["_route"] for r in sample}
        assert "serpapi" in routes and "site_search" in routes, (
            "near-census categories (serpapi, site_search) must never "
            "be left out of the sample")

    def test_rare_text_completeness_categories_are_all_included(self):
        pool = _synthetic_pool()
        sample = select_sample(pool)
        completeness = {r["_text_completeness"] for r in sample}
        assert "missing" in completeness and "partial" in completeness

    def test_every_election_is_represented(self):
        pool = _synthetic_pool()
        sample = select_sample(pool)
        elections = {r["election_id"] for r in sample}
        assert elections == {"SCC-2013-05", "SCC-2017-05", "SCC-2021-05",
                            "ESWS-2026-05"}

    def test_kappa_subset_is_a_subset_of_the_sample(self):
        pool = _synthetic_pool()
        sample = select_sample(pool)
        sample_ids = {r["article_id"] for r in sample}
        kappa = select_kappa_subset(sample)
        assert {r["article_id"] for r in kappa} <= sample_ids


# ---------------------------------------------------------------------------
# Cohen's kappa arithmetic
# ---------------------------------------------------------------------------

class TestCohensKappa:
    def test_perfect_agreement_gives_kappa_of_one(self):
        pairs = [("include", "include")] * 10 + [("exclude", "exclude")] * 10
        po, pe, kappa = cohens_kappa(pairs)
        assert po == 1.0
        assert kappa == pytest.approx(1.0)

    def test_no_pairs_returns_none(self):
        assert cohens_kappa([]) is None

    def test_single_category_only_kappa_is_undefined(self):
        # every pair agrees on the same single label - chance agreement
        # is already 100%, so kappa is mathematically undefined (0/0
        # avoided by returning None rather than raising)
        pairs = [("include", "include")] * 5
        po, pe, kappa = cohens_kappa(pairs)
        assert po == 1.0
        assert pe == 1.0
        assert kappa is None

    def test_chance_level_agreement_gives_kappa_near_zero(self):
        # two raters whose decisions are independent of each other but
        # share the same marginal distribution: kappa should sit near 0
        import random
        rng = random.Random("kappa-chance-test")
        labels = ["include", "exclude"]
        pairs = [(rng.choice(labels), rng.choice(labels))
                for _ in range(2000)]
        po, pe, kappa = cohens_kappa(pairs)
        assert kappa is not None
        assert abs(kappa) < 0.15

    def test_systematic_disagreement_gives_negative_kappa(self):
        # raters always disagree, on a balanced 50/50 split - agreement
        # is worse than chance, so kappa must be negative
        pairs = ([("include", "exclude")] * 10 +
                [("exclude", "include")] * 10)
        po, pe, kappa = cohens_kappa(pairs)
        assert po == 0.0
        assert kappa < 0
