"""Shared deterministic I/O helpers for the frozen v2 eligibility runs.

Blind validation, the full-corpus batch and the local-extension batch use this
module to construct identical classifier inputs and stable output rows.  It
contains no development-set runner and makes no API calls.
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .llm_classifier_v2 import request_metadata
from .manual_review_schema import RULES

QUERY_INVENTORY = Path("news_collection/query_inventory.csv")
RECORDS_DIR = Path("data/raw/news/records")

METADATA_FIELDS = [
    "classifier_version", "model", "input_sha256", "prompt_sha256",
    "schema_sha256", "requested_rules", "response_id", "stop_reason",
    "input_tokens", "output_tokens", "text_source", "input_chars",
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
    """Construct a v2 input with full text and collection context."""
    raw_record = _load_raw_record(row["article_id"], records_dir)
    retrieval = raw_record.get("retrieval") or {}
    query_id = retrieval.get("search_query_id") or ""
    query = query_by_id.get(query_id, {})

    full_text_path = (
        Path(row["article_text_path"])
        if row.get("article_text_path")
        else None
    )
    if full_text_path and full_text_path.is_file():
        text = full_text_path.read_text(errors="replace")
        text_source = "full_text_path"
    else:
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


def load_previous_ok_rows(path: Path) -> dict[str, dict[str, str]]:
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
    """Return true only when every request-identity field still matches."""
    expected = request_metadata(article)
    return all(previous.get(key) == value for key, value in expected.items())


def backup_previous_output(path: Path) -> Path | None:
    """Preserve an aggregate CSV before replacing it."""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}.pre-rerun-{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def archive_raw_result(
    article_id: str,
    result: dict[str, Any],
    *,
    directory: Path,
) -> Path:
    """Archive response identity without placing raw text in the CSV."""
    directory.mkdir(parents=True, exist_ok=True)
    prompt_prefix = str(result.get("prompt_sha256", "no-prompt"))[:12]
    path = directory / f"{article_id}--{prompt_prefix}.json"
    payload = {
        key: value
        for key, value in result.items()
        if key in {
            "classifier_version", "model", "input_sha256", "prompt_sha256",
            "schema_sha256", "requested_rules", "response_id", "stop_reason",
            "input_tokens", "output_tokens", "status", "note", "raw_text",
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def csv_row(
    sample_row: dict[str, str],
    article: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Project an API result into the stable frozen-v2 CSV schema."""
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
        for suffix in ("decision", "reason_code", "supporting_text", "confidence"):
            row[f"{prefix}_{suffix}"] = result.get(f"{prefix}_{suffix}", "")
    return row
