"""Run the frozen v2 eligibility classifier on the new local backlog.

This is deliberately separate from ``run_llm_corpus_batch_v2``.  The original
batch contains 2,370 articles and has its own state, aggregate output and raw
responses.  None of the 1,060 round-two local rows appears in that batch.  A
second runner with separate paths prevents a new submission from overwriting
the old evidence or being mistaken for a retry of the old request set.

Methodological boundary
-----------------------
The frozen classifier requests E4, E5 and E8 for every local article, plus E6
when Reform disambiguation is applicable.  E5 remains in the request because
removing it would change the validated prompt and schema hashes.  Its answer is
stored for audit only: downstream assembly always takes local E5 from the human
review sheet.  Only E4, E6 and E8 are machine-owned decisions.

Rows without stored full text are not submitted.  The development/validation
runner can fall back to a short excerpt, but these rows are already known to
need a full-text eligibility decision and there is no reason to pay for a
request that cannot provide input parity.  They are retained in the eventual
output with ``not_submitted_no_full_text`` so the gap remains visible.

Commands
--------
The dry run is local and free:

    PYTHONPATH=src .venv/bin/python \
      -m news_collection.run_llm_local_extension_v2 dry-run

The remaining commands use the Anthropic Message Batches API:

    ... submit
    ... collect
    ... retry

``submit`` is intentionally not called by the dry run.  It creates external
state and incurs cost, so the manifest should be reviewed first.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .llm_classifier_v2 import MODEL, request_metadata
from .run_llm_classification_development_v2 import (
    FIELDNAMES,
    article_from_sample_row,
    backup_previous_output,
    load_query_inventory,
)
from .run_llm_corpus_batch_v2 import build_request, result_to_row
from .run_llm_validation_v2 import assert_classifier_frozen

SHEET = Path("news_collection/e5_local_review_queue_round2.csv")
OUT = Path("news_collection/manual_review_llm_v2_local_extension.csv")
RAW_RESPONSE_DIR = Path("news_collection/llm_v2_local_extension_raw")
STATE = Path("news_collection/llm_v2_local_extension_batch_state.json")
MANIFEST = Path("news_collection/llm_v2_local_extension_dry_run.json")

REVIEW_ROUND = "e5_local_round2"
NO_FULL_TEXT_STATUS = "not_submitted_no_full_text"
RETRYABLE_STATUSES = {
    "batch_errored",
    "batch_canceled",
    "batch_expired",
    "incomplete_output",
    "schema_error",
    "missing_batch_result",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    """Hash the exact queue bytes used to construct the request population."""

    return _sha256_bytes(path.read_bytes())


def load_population() -> tuple[list[dict], list[dict]]:
    """Return submittable articles and visible no-full-text exclusions.

    Input order follows the review queue, whose ordering already records the
    expected-yield and training-period priority.  Batch results are still
    matched by article id, never by this position.
    """

    if not SHEET.exists():
        raise RuntimeError(
            f"{SHEET} does not exist; build the round-two local queue first."
        )

    query_by_id = load_query_inventory()
    with SHEET.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row.get("review_round") == REVIEW_ROUND
        ]
    if not rows:
        raise RuntimeError(f"no {REVIEW_ROUND!r} rows in {SHEET}")

    ids = [row["article_id"] for row in rows]
    if len(ids) != len(set(ids)):
        duplicates = sorted(
            article_id for article_id, count in Counter(ids).items()
            if count > 1
        )
        raise RuntimeError(
            f"duplicate article ids in extension queue: {duplicates[:5]}"
        )

    articles, excluded = [], []
    for row in rows:
        if row.get("arm") != "local":
            raise RuntimeError(
                f"{row['article_id']} has arm={row.get('arm')!r}; this runner "
                "is restricted to the local extension."
            )
        article = article_from_sample_row(row, query_by_id=query_by_id)
        if article["text_source"] != "full_text_path" or not article["text"].strip():
            excluded.append({
                "article_id": article["article_id"],
                "election_id": article["election_id"],
                "source_id": article["source_id"],
                "reason": "stored full text is unavailable or empty",
            })
            continue
        articles.append(article)
    return articles, excluded


def build_manifest() -> dict:
    """Describe the exact request set without creating an API request."""

    articles, excluded = load_population()
    requests = [build_request(article) for article in articles]
    requested_rules = Counter(
        request_metadata(article)["requested_rules"] for article in articles
    )
    by_election = Counter(article["election_id"] for article in articles)
    by_source = Counter(article["source_id"] for article in articles)

    # Hash the complete request objects, not just article ids. If text, prompt,
    # schema, model or requested rules change after submission, collect refuses
    # to accept the responses against the changed local inputs.
    request_bytes = json.dumps(
        requests, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "purpose": "local eligibility extension after the original corpus batch",
        "sheet": str(SHEET),
        "sheet_sha256": _sha256_file(SHEET),
        "classifier_model": MODEL,
        "queue_rows": len(articles) + len(excluded),
        "request_count": len(articles),
        "not_submitted_no_full_text": len(excluded),
        "request_set_sha256": _sha256_bytes(request_bytes),
        "article_ids_sha256": _sha256_bytes(
            "\n".join(sorted(a["article_id"] for a in articles)).encode("utf-8")
        ),
        "total_input_characters": sum(len(a["text"]) for a in articles),
        "by_election": dict(sorted(by_election.items())),
        "by_source": dict(sorted(by_source.items())),
        "by_requested_rule_set": dict(sorted(requested_rules.items())),
        "excluded_rows": excluded,
        "decision_ownership": {
            "E4": "llm_v2",
            "E5": "human; model field is audit-only",
            "E6": "llm_v2 when applicable, otherwise deterministic not_applicable",
            "E8": "llm_v2",
        },
        "separate_from_original_batch": {
            "state": str(STATE),
            "output": str(OUT),
            "raw_responses": str(RAW_RESPONSE_DIR),
        },
    }


def write_manifest() -> dict:
    manifest = build_manifest()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def print_manifest(manifest: dict) -> None:
    print(f"queue rows:                 {manifest['queue_rows']:,}")
    print(f"requests ready to submit:   {manifest['request_count']:,}")
    print(f"not submitted, no text:     "
          f"{manifest['not_submitted_no_full_text']:,}")
    print(f"request set sha256:         "
          f"{manifest['request_set_sha256'][:16]}...")
    print(f"by election:                {manifest['by_election']}")
    print(f"by requested rule set:      {manifest['by_requested_rule_set']}")
    print(f"dry-run manifest -> {MANIFEST}")
    print("\nE5 reminder: it remains in the frozen request for prompt parity, "
          "but its model answer is audit-only. Human E5 is authoritative.")


def dry_run() -> None:
    """Write the free, reviewable manifest; never instantiate an API client."""

    print_manifest(write_manifest())
    print("\nNo API request was submitted.")


def _load_state_and_verify(manifest: dict) -> dict:
    """Refuse collection/retry if the on-disk request population drifted."""

    if not STATE.exists():
        raise RuntimeError(f"{STATE} not found; nothing was submitted.")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    for key in ("request_count", "request_set_sha256", "sheet_sha256"):
        if state.get(key) != manifest.get(key):
            raise RuntimeError(
                f"extension input changed after submission: {key} is "
                f"{manifest.get(key)!r}, submitted value was "
                f"{state.get(key)!r}. Restore the submitted queue before "
                "collecting; do not attach responses to changed inputs."
            )
    return state


def submit() -> None:
    """Submit exactly the reviewed manifest once."""

    import anthropic

    if STATE.exists():
        raise RuntimeError(
            f"{STATE} already exists. Run collect, or inspect the recorded "
            "batch before taking any action; a second submit would double-bill."
        )
    if OUT.exists():
        raise RuntimeError(
            f"{OUT} already exists while {STATE} does not. Refusing to create "
            "a competing result set; investigate the missing state first."
        )

    manifest = write_manifest()
    articles, _excluded = load_population()
    requests = [build_request(article) for article in articles]
    if len(requests) != manifest["request_count"]:
        raise RuntimeError("request count changed while preparing submission")

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    STATE.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "request_count": manifest["request_count"],
        "request_set_sha256": manifest["request_set_sha256"],
        "sheet_sha256": manifest["sheet_sha256"],
        "model": MODEL,
        "retry_batch_ids": [],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"batch {batch.id} submitted: {len(requests):,} requests, "
          f"status={batch.processing_status}")
    print(f"state -> {STATE}")


def _failure_row(article: dict, status: str, note: str) -> dict:
    """Create an explicit non-result without inventing any rule decision."""

    row = {field: "" for field in FIELDNAMES}
    row.update({
        "article_id": article["article_id"],
        "status": status,
        "note": note,
        "model": MODEL,
        "text_source": article.get("text_source", ""),
        "input_chars": len(article.get("text") or ""),
    })
    return row


def _normalise_aggregate_cell(value):
    """Keep the review CSV to one physical row per article.

    Claude can copy publisher boilerplate containing embedded line breaks into
    ``supporting_text``. The exact API response remains in the ignored raw
    archive; only the review-friendly aggregate replaces those line breaks
    with spaces.
    """

    if not isinstance(value, str):
        return value
    return re.sub(r"\s*[\r\n]+\s*", " ", value)


def retry() -> None:
    """Retry only technical failures with byte-identical requests."""

    import anthropic

    manifest = write_manifest()
    state = _load_state_and_verify(manifest)
    if not OUT.exists():
        raise RuntimeError(f"{OUT} not found; run collect first.")

    with OUT.open(encoding="utf-8-sig", newline="") as handle:
        failed_ids = {
            row["article_id"] for row in csv.DictReader(handle)
            if row.get("status") in RETRYABLE_STATUSES
        }
    if not failed_ids:
        print("no retryable rows; nothing submitted.")
        return

    articles = {a["article_id"]: a for a in load_population()[0]}
    requests = [
        build_request(articles[article_id])
        for article_id in sorted(failed_ids)
        if article_id in articles
    ]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    state.setdefault("retry_batch_ids", []).append(batch.id)
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"retry batch {batch.id}: {len(requests):,} technical failures")


def collect() -> None:
    """Collect all attempts and write one auditable row per queue article."""

    import anthropic

    manifest = write_manifest()
    state = _load_state_and_verify(manifest)
    client = anthropic.Anthropic()
    batch_ids = [state["batch_id"]] + state.get("retry_batch_ids", [])

    for batch_id in batch_ids:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            counts = batch.request_counts
            print(f"batch {batch_id} still {batch.processing_status}: "
                  f"{counts.processing} processing, "
                  f"{counts.succeeded} succeeded, "
                  f"{counts.errored} errored")
            return

    articles, excluded = load_population()
    by_id = {article["article_id"]: article for article in articles}
    rows_by_id: dict[str, dict] = {}
    for item in excluded:
        # Reconstructing the fallback article is unnecessary: this row records
        # why no request existed and deliberately carries no prompt identity.
        rows_by_id[item["article_id"]] = _failure_row(
            {"article_id": item["article_id"], "text": "", "text_source": ""},
            NO_FULL_TEXT_STATUS,
            item["reason"],
        )

    unknown_ids = []
    for attempt, batch_id in enumerate(batch_ids):
        raw_dir = (
            RAW_RESPONSE_DIR if attempt == 0
            else RAW_RESPONSE_DIR / f"retry{attempt}"
        )
        for result in client.messages.batches.results(batch_id):
            article = by_id.get(result.custom_id)
            if article is None:
                unknown_ids.append(result.custom_id)
                continue
            previous = rows_by_id.get(result.custom_id)
            if previous is not None and previous.get("status") == "ok":
                continue
            rows_by_id[result.custom_id] = result_to_row(
                article, result, raw_dir
            )

    # Every submitted id must be represented even if the API result iterator
    # unexpectedly omits it. Missing results remain retryable non-results.
    for article_id, article in by_id.items():
        rows_by_id.setdefault(
            article_id,
            _failure_row(
                article,
                "missing_batch_result",
                "no result returned by any recorded batch attempt",
            ),
        )
    if unknown_ids:
        raise RuntimeError(
            f"batch returned {len(unknown_ids)} unknown custom ids; first: "
            f"{sorted(unknown_ids)[:5]}"
        )

    rows = [rows_by_id[article_id] for article_id in sorted(rows_by_id)]
    rows = [
        {key: _normalise_aggregate_cell(value) for key, value in row.items()}
        for row in rows
    ]
    backup = backup_previous_output(OUT)
    if backup:
        print(f"previous output backed up -> {backup}")
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=FIELDNAMES, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    statuses = Counter(row["status"] for row in rows)
    print(f"{len(rows):,} extension rows -> {OUT}")
    print("by status:", dict(statuses))
    print("E5 model fields are audit-only; human E5 remains authoritative.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("dry-run", "submit", "collect", "retry")
    )
    args = parser.parse_args()
    assert_classifier_frozen()
    load_dotenv()
    {
        "dry-run": dry_run,
        "submit": submit,
        "collect": collect,
        "retry": retry,
    }[args.command]()


if __name__ == "__main__":
    main()
