"""Run the v2 classifier on the 168-article *development* set only.

This runner is intentionally separate from
``run_llm_classification_pilot.py`` and writes to a new file. It cannot
overwrite or carry forward the v1 pilot by accident.

Methodological boundary
-----------------------
The human labels in ``manual_review_sample.csv`` have already been examined
while diagnosing and designing v2. Results produced here are therefore
in-sample development diagnostics, never independent validation evidence.
Do not run this module on the remaining corpus. Do not use its agreement
statistics as a go/no-go gate. After supervisor approval, freeze v2 and draw
a new blind validation sample with a separate runner.

Input parity
------------
Human reviewers were allowed to open ``article_text_path`` when the
spreadsheet excerpt was truncated. V1 sent only the first 1,500 characters
to the model. This runner uses the same full text when the file exists and
falls back transparently to the stored excerpt only when it does not.

Audit and anti-cherry-picking controls
--------------------------------------
* Successful rows are reused only when classifier version, model, input,
  prompt, schema, and requested rules all have identical hashes.
* Every API response, including successful structured JSON, is archived.
* Previous aggregate CSVs are timestamped before replacement.
* A failed or interrupted response remains a failure; the runner never
  invents a decision or selects between multiple successful answers.
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .llm_classifier_v2 import classify_article_v2, request_metadata
from .manual_review_schema import RULES

SAMPLE = Path("news_collection/manual_review_sample.csv")
QUERY_INVENTORY = Path("news_collection/query_inventory.csv")
RECORDS_DIR = Path("data/raw/news/records")

OUT = Path("news_collection/manual_review_llm_v2_development.csv")
RAW_RESPONSE_DIR = Path("news_collection/llm_v2_development_raw")

METADATA_FIELDS = [
    "classifier_version",
    "model",
    "input_sha256",
    "prompt_sha256",
    "schema_sha256",
    "requested_rules",
    "response_id",
    "stop_reason",
    "input_tokens",
    "output_tokens",
    "text_source",
    "input_chars",
]
FIELDNAMES = (
    ["article_id", "status", "note"]
    + METADATA_FIELDS
    + [f"{rule.lower()}_decision" for rule in RULES]
    + [f"{rule.lower()}_reason_code" for rule in RULES]
    + [f"{rule.lower()}_supporting_text" for rule in RULES]
    + [f"{rule.lower()}_confidence" for rule in RULES]
)


def load_query_inventory(path: Path = QUERY_INVENTORY) -> dict[str, dict]:
    """Load originating-query context keyed by stable query ID."""
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        return {row["query_id"]: row for row in csv.DictReader(handle)}


def _load_raw_record(article_id: str, records_dir: Path) -> dict[str, Any]:
    """Load the preserved raw record, returning an honest empty object."""
    path = records_dir / f"{article_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(errors="replace"))


def article_from_sample_row(
    row: dict[str, str],
    *,
    query_by_id: dict[str, dict],
    records_dir: Path = RECORDS_DIR,
) -> dict[str, Any]:
    """Construct a v2 input with full text and collection context.

    ``text_source`` is part of the hashed article input. Changing from an
    excerpt to full text therefore invalidates reuse automatically.
    """
    raw_record = _load_raw_record(row["article_id"], records_dir)
    retrieval = raw_record.get("retrieval") or {}
    query_id = retrieval.get("search_query_id") or ""
    query = query_by_id.get(query_id, {})

    full_text_path = Path(row["article_text_path"]) \
        if row.get("article_text_path") else None
    if full_text_path and full_text_path.is_file():
        text = full_text_path.read_text(errors="replace")
        text_source = "full_text_path"
    else:
        # This is an explicit fallback, not a claim that the excerpt is full.
        # The model receives the abstention rule and may use
        # insufficient_evidence only when the limitation prevents a decision.
        text = row.get("article_text_excerpt") or ""
        text_source = "sample_excerpt_fallback"

    day_index = row.get("day_index_from_polling_day")
    return {
        "article_id": row["article_id"],
        "headline": row["headline"],
        "text": text,
        "text_source": text_source,
        "source_id": row["source_id"],
        "election_id": row["election_id"],
        "arm": row["arm"],
        "day_index_from_polling_day": int(day_index) if day_index else None,
        "needs_reform_disambiguation": row["needs_reform_disambiguation"],
        "search_query_id": query_id,
        "ward": query.get("ward", ""),
        "query_text": query.get("query_text", ""),
        "query_family": query.get("query_family", ""),
        "geographic_scope": query.get("geographic_scope", ""),
    }


def load_previous_ok_rows(path: Path = OUT) -> dict[str, dict[str, str]]:
    """Return previously successful v2 rows, keyed by article ID."""
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        return {
            row["article_id"]: row
            for row in csv.DictReader(handle)
            if row.get("status") == "ok"
        }


def can_reuse(previous: dict[str, str], article: dict[str, Any]) -> bool:
    """True only when every versioned request identity field still matches."""
    expected = request_metadata(article)
    return all(previous.get(key) == value for key, value in expected.items())


def backup_previous_output(path: Path = OUT) -> Path | None:
    """Preserve the aggregate CSV before replacing it."""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}.pre-rerun-{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def _archive_raw_result(
    article_id: str,
    result: dict[str, Any],
    *,
    directory: Path = RAW_RESPONSE_DIR,
) -> Path:
    """Archive response and request identity without placing raw text in CSV."""
    directory.mkdir(parents=True, exist_ok=True)
    prompt_prefix = str(result.get("prompt_sha256", "no-prompt"))[:12]
    path = directory / f"{article_id}--{prompt_prefix}.json"
    payload = {
        key: value
        for key, value in result.items()
        if key
        in {
            "classifier_version",
            "model",
            "input_sha256",
            "prompt_sha256",
            "schema_sha256",
            "requested_rules",
            "response_id",
            "stop_reason",
            "input_tokens",
            "output_tokens",
            "status",
            "note",
            "raw_text",
        }
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    return path


def _csv_row(
    sample_row: dict[str, str],
    article: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Project an API result into the stable development CSV schema."""
    row: dict[str, Any] = {
        "article_id": sample_row["article_id"],
        "status": result.get("status", "unknown"),
        "note": result.get("note", ""),
        "text_source": article["text_source"],
        "input_chars": len(article["text"]),
    }
    for field in METADATA_FIELDS:
        if field not in row:
            row[field] = result.get(field, "")
    for rule in RULES:
        prefix = rule.lower()
        for suffix in (
            "decision",
            "reason_code",
            "supporting_text",
            "confidence",
        ):
            field = f"{prefix}_{suffix}"
            row[field] = result.get(field, "")
    return row


def main() -> None:
    """Run/reuse development classifications and write the versioned CSV."""
    with SAMPLE.open(newline="") as handle:
        sample_rows = [
            row
            for row in csv.DictReader(handle)
            if row["review_round"] == "initial"
        ]
    query_by_id = load_query_inventory()
    previous_ok = load_previous_ok_rows()
    backup = backup_previous_output()
    if backup:
        print(f"previous development output backed up -> {backup}")

    output_rows = []
    status_counts: dict[str, int] = {}
    reused = attempted = 0
    for sample_row in sample_rows:
        article = article_from_sample_row(
            sample_row,
            query_by_id=query_by_id,
        )
        previous = previous_ok.get(sample_row["article_id"])
        if previous and can_reuse(previous, article):
            output_rows.append(previous)
            status = "ok"
            reused += 1
        else:
            result = classify_article_v2(article)
            _archive_raw_result(sample_row["article_id"], result)
            output_rows.append(_csv_row(sample_row, article, result))
            status = result.get("status", "unknown")
            attempted += 1
        status_counts[status] = status_counts.get(status, 0) + 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"{len(output_rows)} development rows -> {OUT}")
    print(f"{reused} identical successful row(s) reused; {attempted} attempted")
    print("by status:", status_counts)
    print(
        "\nThese are development-set diagnostics only. They must not be "
        "reported as independent validation or applied to the remaining "
        "corpus."
    )


if __name__ == "__main__":
    main()
