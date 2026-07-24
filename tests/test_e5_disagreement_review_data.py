"""Tests for the human E5 disagreement-review dataset."""

from src.news_collection.build_e5_disagreement_review_data import (
    _exact_place_matches,
    build_review_rows,
)


def test_frozen_v1_sources_produce_48_hard_e5_disagreements():
    rows = build_review_rows()
    assert len(rows) == 48
    assert len({row["article_id"] for row in rows}) == 48
    assert all(
        {row["human_decision"], row["llm_decision"]}
        == {"include", "exclude"}
        for row in rows
    )


def test_diagnostic_fields_begin_unadjudicated():
    rows = build_review_rows()
    diagnostic_fields = (
        "independent_reassessment",
        "rule_at_issue",
        "input_issue",
        "error_mechanism",
        "human_label_review",
        "recommended_action",
        "few_shot_candidate",
        "review_evidence",
        "review_notes",
        "reviewer_id",
        "reviewed_at",
        "confirmed_link_type",
        "confirmed_linked_place",
        "confirmed_sampled_division",
        "confirmed_geographic_evidence",
        "linkage_decision",
    )
    assert all(row["review_status"] == "not_started" for row in rows)
    assert all(
        row[field] == ""
        for row in rows
        for field in diagnostic_fields
    )


def test_review_rows_preserve_both_source_decisions_and_evidence():
    rows = build_review_rows()
    assert all(row["human_reason_code"].startswith("E5-") for row in rows)
    assert all(row["llm_reason_code"].startswith("E5-") for row in rows)
    assert all(row["human_supporting_text"] for row in rows)
    assert all(row["article_text"] for row in rows)
    assert sum(
        row["llm_supporting_text_missing"] == "yes" for row in rows
    ) == 17
    assert all(
        (row["llm_supporting_text_missing"] == "yes")
        == (not row["llm_supporting_text"])
        for row in rows
    )


def test_missing_local_ward_context_is_explicit_not_inferred():
    rows = build_review_rows()
    local_rows = [row for row in rows if row["arm"] == "local"]
    assert len(local_rows) == 28
    assert all(row["ward_context_missing"] == "yes" for row in local_rows)
    assert sum(row["query_context_missing"] == "yes" for row in rows) == 1


def test_geographic_matching_produces_candidates_not_final_decisions():
    rows = build_review_rows()
    local_rows = [row for row in rows if row["arm"] == "local"]
    national_rows = [row for row in rows if row["arm"] == "national"]

    assert all(
        row["automated_linkage_status"]
        in {"candidates_found", "no_candidate_found"}
        for row in local_rows
    )
    assert all(
        row["automated_linkage_status"] == "not_applicable_national"
        for row in national_rows
    )
    assert all(
        row["automated_exact_sample_division_candidates"] == []
        and row["automated_sample_place_candidates"] == []
        and row["automated_authority_signals"] == []
        and row["automated_geographic_evidence"] == []
        for row in national_rows
    )
    assert all(row["linkage_decision"] == "" for row in local_rows)


def test_place_matching_uses_complete_names_and_preserves_evidence():
    rows = build_review_rows()
    redhill_mention = next(
        row
        for row in rows
        if row["article_id"] == "NEWS-guardian_api-299f68788499"
    )

    # The deterministic pass should find the complete place name "Redhill"
    # and retain the source sentence. It must not silently convert that signal
    # into a confirmed L1 judgement because the mention may be incidental.
    assert redhill_mention["automated_linkage_status"] == "candidates_found"
    assert "Redhill" in redhill_mention[
        "automated_sample_place_candidates"
    ]
    assert redhill_mention["automated_geographic_evidence"]
    assert redhill_mention["confirmed_sampled_division"] == ""


def test_short_place_name_does_not_match_inside_another_name():
    assert _exact_place_matches("The story is set in Ashtead.", ["Ash"]) == []
    assert _exact_place_matches("The story is set in Ash.", ["Ash"]) == [
        "Ash"
    ]
