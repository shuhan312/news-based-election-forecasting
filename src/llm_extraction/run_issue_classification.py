"""Phase 6 / Step 3 runner: issue classification over ALL canonical
articles (the specification says "each canonical news article"),
via the Message Batches API under the standing cost policy: frozen
claude-sonnet-5, batches at 50% pricing, cached shared system
prompt.

Subcommands:

    python3 -m src.llm_extraction.run_issue_classification submit [scope]
    python3 -m src.llm_extraction.run_issue_classification collect

``scope`` is "pilot" (default: the Step 2 pilot's 67-article
stratified sample - same articles, so this layer's output can be
cross-checked against the pilot's full-schema issues for stability)
or "full" (all canonical articles - pending the supervisor's budget
sign-off; ~$25-30 at current pricing).

The output token budget is 12k per article - this layer's records
are small (issues + relevance only), and the pilot's lesson about
thinking sharing the budget is respected with generous headroom.
Previous extraction outputs (pilot, re-validation) are never
touched: this runner reads and writes only its own files.
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import (
    MessageCreateParamsNonStreaming)
from anthropic.types.messages.batch_create_params import Request

from .issue_classification import (CLS_PROMPT_VERSION,
                                   CLS_RULES_VERSION,
                                   CLS_SCHEMA_VERSION,
                                   build_issue_prompt,
                                   validate_issue_record)
from .pilot_sample import parse_model_json
from .run_pilot import MODEL, load_articles

MAX_TOKENS = 12000

OUT_BATCH = Path("llm_context/issue_cls_batch_id.txt")
OUT_RESULTS = Path("llm_context/issue_classification_outputs.json")


def _user_message(a: dict) -> str:
    meta = {"article_id": a["article_id"],
            "canonical_article_id": a["canonical_article_id"],
            "election_id": a["election_id"],
            "local_national": "local_surrey" if a["arm"] == "local"
            else "national"}
    return (f"ARTICLE METADATA (copy ids into the record):\n"
            f"{json.dumps(meta, sort_keys=True, ensure_ascii=False)}\n\n"
            f"TITLE: {a['title']}\n\nBODY:\n{a['body']}")


def cmd_submit(scope: str = "pilot") -> None:
    import csv
    arts = load_articles()
    if scope == "pilot":
        sample = [r["article_id"] for r in csv.DictReader(
            open("llm_context/llm_context_pilot_sample_v1.csv"))]
        arts = {aid: arts[aid] for aid in sample}
    system = [{"type": "text", "text": build_issue_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user",
                       "content": _user_message(a)}]))
        for aid, a in sorted(arts.items())]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    OUT_BATCH.write_text(batch.id + "\n")
    print(f"batch {batch.id}: {len(requests)} articles "
          f"({MODEL}, {CLS_PROMPT_VERSION}, batches 50%)")


def cmd_collect() -> None:
    batch_id = OUT_BATCH.read_text().strip()
    client = anthropic.Anthropic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"status {batch.processing_status} | "
              f"{batch.request_counts}", flush=True)
        time.sleep(120)

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
                entry["validation_errors"] = validate_issue_record(
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
        {"schema_version": CLS_SCHEMA_VERSION,
         "prompt_version": CLS_PROMPT_VERSION,
         "rules_version": CLS_RULES_VERSION,
         "model": MODEL, "batch_id": batch_id,
         "status_counts": dict(sorted(statuses.items())),
         "results": results}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(results)} results -> {OUT_RESULTS}")
    print("statuses:", dict(sorted(statuses.items())))


if __name__ == "__main__":
    if sys.argv[1] == "submit":
        cmd_submit(sys.argv[2] if len(sys.argv) > 2 else "pilot")
    else:
        {"collect": cmd_collect}[sys.argv[1]]()
