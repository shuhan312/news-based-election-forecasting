"""Tests for the blind, risk-based local E5 review plan."""

from src.news_collection import build_e5_risk_review_plan as risk

from pathlib import Path

import pytest

# The round-two local queue is a regenerable collection output kept out of
# git; a fresh clone skips the one test that reads the repository copy.
_needs_round2_queue = pytest.mark.skipif(
    not Path("news_collection/e5_local_review_queue_round2.csv").exists(),
    reason="requires the regenerable round-two local queue (build_e5_local_queue)",
)


def _queue_row(article_id, election="E1", source="source"):
    return {
        "article_id": article_id,
        "election_id": election,
        "source_id": source,
        "arm": "local",
        "sample_stratum": "",
        "headline": f"Headline {article_id}",
    }


def _model_row(
    decision="include",
    confidence="high",
    *,
    status="ok",
    e8="include",
):
    return {
        "status": status,
        "e4_decision": "include",
        "e6_decision": "not_applicable",
        "e8_decision": e8,
        "e5_decision": decision,
        "e5_confidence": confidence,
    }


def test_ambiguous_and_low_confidence_rows_are_always_mandatory():
    queue = [_queue_row(f"A{i}") for i in range(5)]
    models = {
        "A0": _model_row("needs_second_review", ""),
        "A1": _model_row("include", "low"),
        "A2": _model_row("exclude", "medium"),
        "A3": _model_row("include", "high"),
        "A4": _model_row("include", "high", e8="exclude"),
    }

    plan = risk.build_plan(queue, models, target_human_rows=3)

    assert {row["article_id"] for row, _ in plan["mandatory"]} == {
        "A0",
        "A1",
    }
    assert len(plan["validation"]) == 1
    assert len(plan["cleared"]) == 4
    assert plan["not_cleared"] == {"E8=exclude": 1}


def test_stratified_selection_is_deterministic_and_covers_strata():
    candidates = []
    for election in ("E1", "E2"):
        for decision in ("include", "exclude"):
            for index in range(4):
                article_id = f"{election}-{decision}-{index}"
                candidates.append(
                    (
                        _queue_row(article_id, election=election),
                        _model_row(decision, "high"),
                    )
                )

    first = risk._stratified_sample(candidates, 8)
    second = risk._stratified_sample(list(reversed(candidates)), 8)

    assert [row["article_id"] for row, _ in first] == [
        row["article_id"] for row, _ in second
    ]
    assert {
        risk._sampling_stratum(row, model) for row, model in first
    } == {
        risk._sampling_stratum(row, model) for row, model in candidates
    }


def test_blind_row_contains_no_model_e5_answer():
    queue = _queue_row("A1")
    queue.update(
        {
            "e5_decision": "model-value-must-not-leak",
            "e5_reason_code": "model-reason-must-not-leak",
            "e5_supporting_text": "model-evidence-must-not-leak",
            "e5_confidence": "high",
            "reviewer_id": "old",
        }
    )

    blind = risk._blind_row(queue, review_stage="blind_validation")

    assert blind["blind_review_id"].startswith("E5R-")
    assert blind["review_stage"] == "blind_validation"
    assert blind["e5_decision"] == ""
    assert blind["e5_reason_code"] == ""
    assert blind["e5_supporting_text"] == ""
    assert blind["e5_confidence"] == ""
    assert blind["reviewer_id"] == ""


def test_frozen_review_ids_come_from_saved_stage_labels():
    rows = [
        {"article_id": "A1", "review_stage": "blind_validation"},
        {"article_id": "A2", "review_stage": "blind_validation"},
        {"article_id": "A3", "review_stage": "mandatory_resolution"},
    ]

    validation, mandatory = risk._frozen_review_ids(rows)

    assert validation == {"A1", "A2"}
    assert mandatory == {"A3"}


@_needs_round2_queue
def test_current_repository_plan_reconciles_the_current_population():
    queue = risk._read_csv(risk.OUT_QUEUE)
    plan = risk.build_plan(queue, risk._load_llm_rows())

    assert len(queue) == 1060
    assert len(plan["cleared"]) + sum(plan["not_cleared"].values()) == len(queue)
    assert (
        len(plan["mandatory"])
        + len(plan["validation"])
        + len(plan["deferred_ids"])
        == len(plan["cleared"])
    )
    assert len(plan["mandatory"]) + len(plan["validation"]) == min(
        risk.TARGET_HUMAN_ROWS, len(plan["cleared"])
    )
