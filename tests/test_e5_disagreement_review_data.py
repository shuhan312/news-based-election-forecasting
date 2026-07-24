"""Tests for the human E5 disagreement-review dataset."""

from src.news_collection.build_e5_disagreement_review_data import (
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
