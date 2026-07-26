"""Phase 6 / Step 4 runner: entity stance extraction over the pilot
sample, under the standing cost policy (frozen claude-sonnet-5,
Batches API at 50%, cached shared system prompt).

Subcommands:

    python3 -m src.llm_extraction.run_stance_classification submit
    python3 -m src.llm_extraction.run_stance_classification collect

The dataset is the SAME 67-article stratified pilot sample as Steps
2 and 3 (method versioned in llm_context_pilot_sample_v1.csv) -
reuse keeps the sampling defensible and enables the cross-layer
stance comparison against the pilot's party_context rows. Full
corpus extraction is NOT run here. Previous layers' outputs are
never touched: this runner reads and writes only its own files.
"""

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import (
    MessageCreateParamsNonStreaming)
from anthropic.types.messages.batch_create_params import Request

from .pilot_sample import parse_model_json
from .run_pilot import MODEL, load_articles
from .stance_classification import (STANCE_PROMPT_VERSION,
                                    STANCE_RULES_VERSION,
                                    STANCE_SCHEMA_VERSION,
                                    build_stance_prompt,
                                    validate_stance_record)

MAX_TOKENS = 16000   # stance rows are chunkier than issue records
                     # (up to 20 entities x 13 fields) - headroom for
                     # thinking + JSON per the pilot's budget lesson

SAMPLE = Path("llm_context/llm_context_pilot_sample_v1.csv")
OUT_BATCH = Path("llm_context/stance_cls_batch_id.txt")
OUT_RESULTS = Path("llm_context/stance_classification_outputs.json")


def _user_message(a: dict) -> str:
    meta = {"article_id": a["article_id"],
            "canonical_article_id": a["canonical_article_id"],
            "election_id": a["election_id"],
            "local_national": "local_surrey" if a["arm"] == "local"
            else "national"}
    return (f"ARTICLE METADATA (copy ids into the record):\n"
            f"{json.dumps(meta, sort_keys=True, ensure_ascii=False)}\n\n"
            f"TITLE: {a['title']}\n\nBODY:\n{a['body']}")


def cmd_submit() -> None:
    arts = load_articles()
    sample = [r["article_id"] for r in csv.DictReader(SAMPLE.open())]
    system = [{"type": "text", "text": build_stance_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user",
                       "content": _user_message(arts[aid])}]))
        for aid in sample]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    OUT_BATCH.write_text(batch.id + "\n")
    print(f"batch {batch.id}: {len(requests)} articles "
          f"({MODEL}, {STANCE_PROMPT_VERSION}, batches 50%)")


def cmd_collect() -> None:
    batch_id = OUT_BATCH.read_text().strip()
    client = anthropic.Anthropic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"status {batch.processing_status} | "
              f"{batch.request_counts}", flush=True)
        time.sleep(60)

    arts = load_articles()
    results, statuses = [], Counter()
    for res in client.messages.batches.results(batch_id):
        aid = res.custom_id
        entry = {"article_id": aid, "batch_result": res.result.type,
                 "validation_errors": [], "record": None, "usage": None}
        if res.result.type == "succeeded":
            msg = res.result.message
            assert msg.model.startswith(MODEL), msg.model
            entry["usage"] = {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "cache_read_input_tokens":
                    msg.usage.cache_read_input_tokens}
            text = next((b.text for b in msg.content
                         if b.type == "text"), "")
            try:
                record = parse_model_json(text)
                a = arts.get(aid, {})
                entry["record"] = record
                entry["validation_errors"] = validate_stance_record(
                    record, a.get("body", ""), a.get("title", ""))
                statuses["valid" if not entry["validation_errors"]
                         else "schema_or_rule_errors"] += 1
            except (ValueError, json.JSONDecodeError) as e:
                entry["validation_errors"] = [f"unparseable: {e}"]
                entry["raw_text"] = text[:2000]
                statuses["unparseable"] += 1
        else:
            statuses[res.result.type] += 1
        results.append(entry)

    results.sort(key=lambda r: r["article_id"])
    OUT_RESULTS.write_text(json.dumps(
        {"schema_version": STANCE_SCHEMA_VERSION,
         "prompt_version": STANCE_PROMPT_VERSION,
         "rules_version": STANCE_RULES_VERSION,
         "model": MODEL, "batch_id": batch_id,
         "status_counts": dict(sorted(statuses.items())),
         "results": results}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(results)} results -> {OUT_RESULTS}")
    print("statuses:", dict(sorted(statuses.items())))


if __name__ == "__main__":
    {"submit": cmd_submit, "collect": cmd_collect}[sys.argv[1]]()
