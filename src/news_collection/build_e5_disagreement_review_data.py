"""Assemble the 48 hard E5 disagreements for transparent human review.

This script prepares data; it does not adjudicate any disagreement. The
original human and v1 LLM decisions are copied verbatim into a separate
review dataset, while all diagnostic fields start empty. Keeping source
values and later interpretation separate preserves the audit trail required
for a publishable development analysis.

The output is JSON rather than an edited copy of either source CSV. A
separate workbook export can therefore add formatting and data validation
without changing the research records from which the review was derived.

Usage:
    python3 -m src.news_collection.build_e5_disagreement_review_data
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

HUMAN = Path("news_collection/manual_review_sample.csv")
LLM = Path("news_collection/manual_review_llm_pilot.csv")
AUDIT = Path("news_collection/llm_v1_disagreement_audit.csv")
QUERY_INVENTORY = Path("news_collection/query_inventory.csv")
RECORDS_DIR = Path("data/raw/news/records")
OUT = Path("news_collection/e5_hard_disagreement_review_data.json")


def _load_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV without changing values or normalising labels."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_raw_record(
    article_id: str, records_dir: Path = RECORDS_DIR
) -> dict[str, Any]:
    """Return the preserved raw article record, or an explicit empty record."""
    path = records_dir / f"{article_id}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _article_text(
    human_row: dict[str, str], raw_record: dict[str, Any]
) -> tuple[str, str]:
    """Load full text where available and disclose any excerpt fallback.

    The source is stored alongside the text so a reviewer can distinguish
    genuine content ambiguity from a limitation in the available input.
    """
    candidate_paths = [
        human_row.get("article_text_path", ""),
        (raw_record.get("content") or {}).get("text_path", ""),
    ]
    for candidate in candidate_paths:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace"), str(path)
    return (
        human_row.get("article_text_excerpt", ""),
        "sample_excerpt_fallback",
    )


def build_review_rows(
    *,
    human_path: Path = HUMAN,
    llm_path: Path = LLM,
    audit_path: Path = AUDIT,
    query_path: Path = QUERY_INVENTORY,
    records_dir: Path = RECORDS_DIR,
) -> list[dict[str, Any]]:
    """Join source records into one row per hard E5 disagreement.

    Only ``rule=E5`` and ``disagreement_type=hard_include_exclude`` are
    eligible. This fixed filter excludes field-position errors and unresolved
    answers because those are different failure mechanisms and should not be
    mixed into the substantive relevance analysis.
    """
    human = {
        row["article_id"]: row
        for row in _load_rows(human_path)
        if row["review_round"] == "initial"
    }
    llm = {
        row["article_id"]: row
        for row in _load_rows(llm_path)
        if row.get("status") == "ok"
    }
    queries = {
        row["query_id"]: row
        for row in _load_rows(query_path)
    }
    disagreements = [
        row
        for row in _load_rows(audit_path)
        if row["rule"] == "E5"
        and row["disagreement_type"] == "hard_include_exclude"
    ]

    review_rows: list[dict[str, Any]] = []
    for index, audit_row in enumerate(
        sorted(disagreements, key=lambda row: row["article_id"]), start=1
    ):
        article_id = audit_row["article_id"]
        human_row = human[article_id]
        llm_row = llm[article_id]
        raw_record = _load_raw_record(article_id, records_dir)
        retrieval = raw_record.get("retrieval") or {}
        identity = raw_record.get("identity") or {}
        dates = raw_record.get("dates") or {}
        query_id = retrieval.get("search_query_id") or ""
        query = queries.get(query_id, {})
        article_text, text_source = _article_text(human_row, raw_record)

        # Source fields above this line are copied or deterministically joined.
        # Review fields below start empty so no automated inference is mistaken
        # for the researcher's later diagnosis.
        review_rows.append(
            {
                "review_index": index,
                "article_id": article_id,
                "election_id": human_row["election_id"],
                "arm": human_row["arm"],
                "source_id": human_row["source_id"],
                "headline": human_row["headline"],
                "published_date": dates.get("published_date", ""),
                "ward": query.get("ward", ""),
                "query_id": query_id,
                "query_text": query.get("query_text", ""),
                "query_family": query.get("query_family", ""),
                "geographic_scope": query.get("geographic_scope", ""),
                # These flags expose missing collection context separately from
                # the later human diagnosis. In particular, a local record
                # without a ward cannot be assumed to satisfy the supervisor's
                # requested ward/town linkage merely because its source is
                # locally branded.
                "query_context_missing": (
                    "yes"
                    if not query_id
                    or not query
                    or not query.get("query_text", "").strip()
                    else "no"
                ),
                "ward_context_missing": (
                    "yes"
                    if human_row["arm"] == "local"
                    and not query.get("ward", "").strip()
                    else "no"
                ),
                "publisher_url": (
                    identity.get("canonical_url")
                    or retrieval.get("final_url")
                    or ""
                ),
                "article_text_path": human_row.get(
                    "article_text_path", ""
                ),
                "review_text_source": text_source,
                "article_text": article_text,
                "human_decision": human_row["e5_decision"],
                "human_reason_code": human_row["e5_reason_code"],
                "human_supporting_text": human_row[
                    "e5_supporting_text"
                ],
                "llm_decision": llm_row["e5_decision"],
                "llm_reason_code": llm_row["e5_reason_code"],
                "llm_supporting_text": llm_row[
                    "e5_supporting_text"
                ],
                # V1 left evidence blank for some exclusion decisions. Preserve
                # that absence and flag it explicitly instead of inventing a
                # justification during review-data preparation.
                "llm_supporting_text_missing": (
                    "yes"
                    if not llm_row["e5_supporting_text"].strip()
                    else "no"
                ),
                "direction": (
                    f"human_{human_row['e5_decision']}"
                    f"__llm_{llm_row['e5_decision']}"
                ),
                "human_evidence_location": audit_row[
                    "human_evidence_location"
                ],
                "excerpt_truncated": audit_row["excerpt_truncated"],
                "review_status": "not_started",
                "independent_reassessment": "",
                "rule_at_issue": "",
                "input_issue": "",
                "error_mechanism": "",
                "human_label_review": "",
                "recommended_action": "",
                "few_shot_candidate": "",
                "review_evidence": "",
                "review_notes": "",
                "reviewer_id": "",
                "reviewed_at": "",
            }
        )

    return review_rows


def main() -> None:
    """Write the review dataset and report its fixed inclusion count."""
    rows = build_review_rows()
    if len(rows) != 48:
        raise RuntimeError(
            "Expected 48 hard E5 disagreements from the frozen v1 audit, "
            f"found {len(rows)}. Investigate source-version drift."
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} hard E5 disagreements -> {OUT}")


if __name__ == "__main__":
    main()
