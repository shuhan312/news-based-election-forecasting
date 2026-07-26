"""Phase 6 / Step 5 runner: framing detection over the pilot sample,
under the standing cost policy (frozen claude-sonnet-5, Batches API
at 50%, cached shared system prompt).

Subcommands:

    python3 -m src.llm_extraction.run_framing_detection submit
    python3 -m src.llm_extraction.run_framing_detection collect

The dataset is the SAME 67-article stratified pilot sample as Steps
2-4 (method versioned in llm_context_pilot_sample_v1.csv). Full
corpus extraction is NOT run here; previous layers' outputs are
never touched.
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

from .framing_detection import (FRAME_PROMPT_VERSION,
                                FRAME_RULES_VERSION,
                                FRAME_SCHEMA_VERSION,
                                build_framing_prompt,
                                validate_framing_record)
from .pilot_sample import parse_model_json
from .run_pilot import MODEL, load_articles

MAX_TOKENS = 12000   # up to 5 frames x 8 fields - smaller than the
                     # stance layer; headroom for adaptive thinking
                     # per the pilot's shared-budget lesson

SAMPLE = Path("llm_context/llm_context_pilot_sample_v1.csv")
OUT_BATCH = Path("llm_context/framing_batch_id.txt")
OUT_RESULTS = Path("llm_context/framing_detection_outputs.json")


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
    system = [{"type": "text", "text": build_framing_prompt(),
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
          f"({MODEL}, {FRAME_PROMPT_VERSION}, batches 50%)")


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
                entry["validation_errors"] = validate_framing_record(
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
        {"schema_version": FRAME_SCHEMA_VERSION,
         "prompt_version": FRAME_PROMPT_VERSION,
         "rules_version": FRAME_RULES_VERSION,
         "model": MODEL, "batch_id": batch_id,
         "status_counts": dict(sorted(statuses.items())),
         "results": results}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(results)} results -> {OUT_RESULTS}")
    print("statuses:", dict(sorted(statuses.items())))


if __name__ == "__main__":
    {"submit": cmd_submit, "collect": cmd_collect}[sys.argv[1]]()
