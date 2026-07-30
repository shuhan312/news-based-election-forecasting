"""Safety and population tests for the round-two local LLM extension.

No test creates an Anthropic client or submits an API request.
"""

import csv
from pathlib import Path

import pytest

from src.news_collection import assemble_corpus_decisions as assembly
from src.news_collection import build_e5_local_queue as local_queue
from src.news_collection import run_llm_corpus_batch_v2 as original
from src.news_collection import run_llm_local_extension_v2 as extension


def test_extension_paths_cannot_overwrite_original_batch():
    """The new request set must have a completely separate audit trail."""

    assert extension.STATE != original.STATE
    assert extension.OUT != original.OUT
    assert extension.RAW_RESPONSE_DIR != original.RAW_RESPONSE_DIR
    assert extension.SHEET != original.SHEET


def test_dry_run_describes_the_current_queue_without_an_api_call():
    """The manifest reconciles all 1,060 rows before money is spent."""

    manifest = extension.build_manifest()
    assert manifest["queue_rows"] == 1060
    assert manifest["request_count"] == 1037
    assert manifest["not_submitted_no_full_text"] == 23
    assert sum(manifest["by_election"].values()) == 1037
    assert sum(manifest["by_requested_rule_set"].values()) == 1037
    assert manifest["by_requested_rule_set"]["E4,E5,E6,E8"] == 20
    assert manifest["decision_ownership"]["E5"].startswith("human")


def test_request_set_is_deterministic():
    """Repeated dry runs over unchanged inputs must identify the same batch."""

    first = extension.build_manifest()
    second = extension.build_manifest()
    assert first["sheet_sha256"] == second["sheet_sha256"]
    assert first["request_set_sha256"] == second["request_set_sha256"]
    assert first["article_ids_sha256"] == second["article_ids_sha256"]


def test_disjoint_loader_rejects_duplicate_article_ids(tmp_path: Path):
    """Assembly cannot silently let one LLM/review stream overwrite another."""

    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    for path in (first, second):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["article_id"], lineterminator="\n"
            )
            writer.writeheader()
            writer.writerow({"article_id": "NEWS-duplicate"})

    with pytest.raises(RuntimeError, match="multiple test-stream files"):
        assembly.load_disjoint_rows(
            (first, second), label="test-stream"
        )


def test_cleared_filter_reads_original_and_extension_outputs(
    tmp_path: Path, monkeypatch
):
    """Human E5 filtering recognises both disjoint LLM production batches."""

    paths = []
    for index in range(2):
        path = tmp_path / f"llm-{index}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "article_id", "status", "e4_decision",
                    "e6_decision", "e8_decision",
                ],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerow({
                "article_id": f"NEWS-{index}",
                "status": "ok",
                "e4_decision": "include",
                "e6_decision": "not_applicable",
                "e8_decision": "include",
            })
        paths.append(path)

    monkeypatch.setattr(local_queue, "LLM_OUTPUTS", tuple(paths))
    assert local_queue.llm_cleared_ids() == {"NEWS-0", "NEWS-1"}
