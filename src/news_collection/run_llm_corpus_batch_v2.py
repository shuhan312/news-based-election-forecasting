"""Run the FROZEN v2 classifier over the remaining corpus via the
Message Batches API (submit once, collect once).

Why Batches instead of the sequential runner used for development and
validation: identical requests, half the price. The Batches API bills
every token at 50% of the standard rate and processes asynchronously
(usually under an hour). Nothing the model sees changes - per article
the model name, prompt bytes, JSON schema, and requested rules are
byte-identical to what the validation run sent, and every output row
records the same identity hashes so that claim is checkable after the
fact. Only the transport and the price differ.

Scope, per §8.5 of the methodology: E4 and E8 for every remaining
article, plus E6 for the Reform-flagged subset (the rule set per
article is decided by ``applicable_rules_for``, exactly as in
development/validation). E5 is requested too - it is part of the
frozen prompt and removing it would change the prompt hash - but its
output is recorded only for audit and is NEVER used downstream: E5
failed validation and is coded by the human reviewer on
full_corpus_review.csv.

Two subcommands:

    python3 -m src.news_collection.run_llm_corpus_batch_v2 submit
    python3 -m src.news_collection.run_llm_corpus_batch_v2 collect

``submit`` builds one request per sheet row and creates the batch;
the batch ID is written to a small state file so ``collect`` (run any
time within 29 days) can fetch results. ``collect`` re-derives each
article's request identity deterministically and refuses to accept a
result whose recorded identity does not match - the batch cannot
quietly serve answers for a different prompt or article than was
audited. Failures of any kind (batch-level errors, refusals, schema
violations) are recorded with a non-ok status, never retried into a
different answer.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .llm_classifier_v2 import (
    MAX_TOKENS,
    MODEL,
    V2ClassificationError,
    applicable_rules_for,
    build_output_schema,
    build_prompt,
    parse_structured_response,
    request_metadata,
)
from .run_llm_classification_development_v2 import (
    FIELDNAMES,
    _archive_raw_result,
    article_from_sample_row,
    load_query_inventory,
)
from .run_llm_validation_v2 import assert_classifier_frozen

SHEET = Path("news_collection/full_corpus_review.csv")
OUT = Path("news_collection/manual_review_llm_v2_corpus.csv")
RAW_RESPONSE_DIR = Path("news_collection/llm_v2_corpus_raw")
STATE = Path("news_collection/llm_v2_corpus_batch_state.json")


def load_sheet_articles() -> list[dict]:
    """One v2 article input per full_corpus sheet row, in sheet order.

    Both ``submit`` and ``collect`` call this, so the article content
    used to verify results is re-derived from the same on-disk sources
    (sheet + raw records + query inventory) rather than trusted from
    memory or from the batch response."""
    query_by_id = load_query_inventory()
    with SHEET.open(newline="") as handle:
        rows = [r for r in csv.DictReader(handle)
                if r["review_round"] == "full_corpus"]
    if not rows:
        raise RuntimeError(
            f"no full_corpus rows in {SHEET} - run "
            "build_full_corpus_review_sheet first")
    return [article_from_sample_row(r, query_by_id=query_by_id)
            for r in rows]


def build_request(article: dict) -> dict:
    """One Batches API request, shaped exactly like the sequential
    runner's call. The prompt/schema builders are imported from the
    frozen classifier module, so a drifted prompt is impossible
    without also failing assert_classifier_frozen()."""
    applicable_rules = applicable_rules_for(article)
    return {
        # article_id doubles as custom_id: results come back in
        # arbitrary order and are matched by this key, never position.
        "custom_id": article["article_id"],
        "params": {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{
                "role": "user",
                "content": build_prompt(
                    article, applicable_rules=applicable_rules),
            }],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": build_output_schema(
                        applicable_rules=applicable_rules,
                        arm=article["arm"]),
                }
            },
        },
    }


def submit() -> None:
    import anthropic

    if STATE.exists():
        # One corpus, one batch. A second submit would double-bill and
        # create two competing result sets; collecting or deliberately
        # deleting the state file is the explicit way past this guard.
        raise RuntimeError(
            f"{STATE} already exists - a batch was already submitted. "
            "Run 'collect', or delete the state file only if you are "
            "certain the previous batch should be abandoned.")

    articles = load_sheet_articles()
    requests = [build_request(a) for a in articles]

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)

    STATE.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "request_count": len(requests),
        "classifier_version": request_metadata(articles[0])[
            "classifier_version"],
        "model": MODEL,
    }, indent=2) + "\n")
    print(f"batch {batch.id} submitted: {len(requests)} requests, "
          f"status={batch.processing_status}")
    print(f"state -> {STATE}")
    print("Run 'collect' once the batch has ended (usually <1h; check "
          "with 'collect' any time - it reports status and exits if "
          "still processing).")


def result_to_row(article: dict, result) -> dict:
    """Project one batch result into the same CSV row shape the
    sequential runners produce. The success path mirrors
    classify_article_v2's post-response handling line for line
    (stop-reason gate, structured parse, E6 bookkeeping); failure
    paths record a status and never invent a decision."""
    metadata = request_metadata(article)
    row = {f: "" for f in FIELDNAMES}
    row.update(metadata)
    row["article_id"] = article["article_id"]
    row["text_source"] = article["text_source"]
    row["input_chars"] = len(article["text"])

    if result.result.type != "succeeded":
        err = getattr(result.result, "error", None)
        row["status"] = f"batch_{result.result.type}"
        row["note"] = str(err) if err else ""
        return row

    message = result.result.message
    stop_reason = message.stop_reason
    raw_text = "".join(b.text for b in message.content
                       if getattr(b, "type", None) == "text")
    row.update({
        "response_id": message.id,
        "stop_reason": stop_reason or "",
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    })
    # Archive the raw response before any judgement about it, so a
    # parse failure can be diagnosed later without re-paying for it.
    _archive_raw_result(
        article["article_id"], {**metadata, "raw_text": raw_text,
                                "response_id": message.id,
                                "stop_reason": stop_reason,
                                "status": "pending_parse"},
        directory=RAW_RESPONSE_DIR)

    if stop_reason != "end_turn":
        row["status"] = "incomplete_output"
        row["note"] = f"unexpected stop_reason={stop_reason!r}"
        return row

    applicable_rules = applicable_rules_for(article)
    try:
        fields = parse_structured_response(
            raw_text, applicable_rules=applicable_rules,
            arm=article["arm"], article_text=article["text"])
    except V2ClassificationError as exc:
        row["status"] = "schema_error"
        row["note"] = str(exc)
        return row

    if "E6" not in applicable_rules:
        # Deterministic bookkeeping, identical to classify_article_v2:
        # never Reform-flagged means E6 is not_applicable by rule.
        fields.update({
            "e6_decision": "not_applicable",
            "e6_reason_code": "E6-NOT-REFORM-FLAGGED",
            "e6_supporting_text": "", "e6_confidence": "",
        })
    row.update(fields)
    row["status"] = "ok"
    return row


def collect() -> None:
    import anthropic

    if not STATE.exists():
        raise RuntimeError(f"{STATE} not found - nothing was submitted.")
    state = json.loads(STATE.read_text())
    client = anthropic.Anthropic()

    batch = client.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        counts = batch.request_counts
        print(f"batch {batch.id} still {batch.processing_status}: "
              f"{counts.processing} processing, {counts.succeeded} ok, "
              f"{counts.errored} errored - try again later.")
        return

    articles = {a["article_id"]: a for a in load_sheet_articles()}
    output_rows, status_counts = [], {}
    for result in client.messages.batches.results(batch.id):
        article = articles.get(result.custom_id)
        if article is None:
            # A result for an article not on the sheet should be
            # impossible; record loudly rather than dropping it.
            status_counts["unknown_custom_id"] = (
                status_counts.get("unknown_custom_id", 0) + 1)
            continue
        row = result_to_row(article, result)
        output_rows.append(row)
        status_counts[row["status"]] = (
            status_counts.get(row["status"], 0) + 1)

    # Sheet order, not arrival order, so the CSV is reproducible and
    # diffs cleanly against the review sheet.
    output_rows.sort(key=lambda r: r["article_id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"{len(output_rows)} corpus rows -> {OUT}")
    print("by status:", status_counts)
    print("\nReminder: e5_* columns in this file are audit-only. The "
          "usable E5 decisions are the human's, on "
          "full_corpus_review.csv.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["submit", "collect"])
    args = parser.parse_args()
    assert_classifier_frozen()
    load_dotenv()
    submit() if args.command == "submit" else collect()


if __name__ == "__main__":
    main()
