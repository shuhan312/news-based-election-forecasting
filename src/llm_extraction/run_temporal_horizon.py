"""Phase 6 / Step 9 runner: temporal horizon over the pilot sample.

The deterministic half (election windows, leakage flags) is computed
locally in `deterministic` - free, instant, reproducible. The LLM
half (impact horizon) runs through the Batches API under the
standing cost policy. The two halves are merged per article in the
outputs file, each carrying its own provenance.

Subcommands:

    python3 -m src.llm_extraction.run_temporal_horizon deterministic
    python3 -m src.llm_extraction.run_temporal_horizon submit
    python3 -m src.llm_extraction.run_temporal_horizon collect

The user message for the LLM deliberately EXCLUDES the publication
date and election id (separation by construction). Dataset: the
same 67-article pilot sample; previous layers' outputs untouched.
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
from .temporal_horizon import (TH_PROMPT_VERSION, TH_RULES_VERSION,
                               TH_SCHEMA_VERSION, assign_windows,
                               build_th_prompt, validate_th_record)

MAX_TOKENS = 10000   # single-object record, small

SAMPLE = Path("llm_context/llm_context_pilot_sample_v1.csv")
PILOT_OUTPUTS = Path("llm_context/llm_context_pilot_outputs.json")
OUT_DET = Path("llm_context/temporal_windows_deterministic.json")
OUT_BATCH = Path("llm_context/temporal_batch_id.txt")
OUT_RESULTS = Path("llm_context/temporal_horizon_outputs.json")


def _sample_ids() -> list[str]:
    return [r["article_id"] for r in csv.DictReader(SAMPLE.open())]


def cmd_deterministic() -> None:
    """Compute the date-arithmetic half for every pilot article. The
    contains_election_result flag is sourced from the Step 2 pilot
    leakage layer (provenance recorded); everything else is pure
    dates."""
    arts = load_articles()
    leak = {}
    if PILOT_OUTPUTS.exists():
        for r in json.loads(PILOT_OUTPUTS.read_text())["results"]:
            rec = r.get("record")
            if rec:
                leak[r["article_id"]] = bool(
                    rec.get("leakage", {}).get(
                        "contains_election_result"))
    rows = {}
    for aid in _sample_ids():
        a = arts[aid]
        rows[aid] = assign_windows(a["publication_datetime"][:10]
                                   if a["publication_datetime"] else "",
                                   a["election_id"],
                                   contains_result=leak.get(aid, False))
        rows[aid]["result_flag_provenance"] = (
            "llm_context_pilot_outputs.json leakage layer"
            if aid in leak else "not_available")
    OUT_DET.write_text(json.dumps(rows, indent=1) + "\n")
    windows = Counter(r["election_window"] for r in rows.values())
    flags = Counter(f for r in rows.values() for f in r["flags"])
    print(f"{len(rows)} articles -> {OUT_DET}")
    print("windows:", dict(windows.most_common()))
    print("flags:", dict(flags))


def _user_message(a: dict) -> str:
    # NO publication date, NO election id: the horizon judgement must
    # come from content alone (separation by construction)
    meta = {"article_id": a["article_id"],
            "canonical_article_id": a["canonical_article_id"]}
    return (f"ARTICLE METADATA (copy ids into the record):\n"
            f"{json.dumps(meta, sort_keys=True)}\n\n"
            f"TITLE: {a['title']}\n\nBODY:\n{a['body']}")


def cmd_submit() -> None:
    arts = load_articles()
    system = [{"type": "text", "text": build_th_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user",
                       "content": _user_message(arts[aid])}]))
        for aid in _sample_ids()]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    OUT_BATCH.write_text(batch.id + "\n")
    print(f"batch {batch.id}: {len(requests)} articles "
          f"({MODEL}, {TH_PROMPT_VERSION}, batches 50%)")


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
    det = json.loads(OUT_DET.read_text())
    results, statuses = [], Counter()
    for res in client.messages.batches.results(batch_id):
        aid = res.custom_id
        entry = {"article_id": aid, "batch_result": res.result.type,
                 "validation_errors": [], "record": None,
                 "deterministic": det.get(aid), "usage": None}
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
                entry["validation_errors"] = validate_th_record(
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
        {"schema_version": TH_SCHEMA_VERSION,
         "prompt_version": TH_PROMPT_VERSION,
         "rules_version": TH_RULES_VERSION,
         "model": MODEL, "batch_id": batch_id,
         "status_counts": dict(sorted(statuses.items())),
         "results": results}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(results)} results -> {OUT_RESULTS}")
    print("statuses:", dict(sorted(statuses.items())))


if __name__ == "__main__":
    {"deterministic": cmd_deterministic, "submit": cmd_submit,
     "collect": cmd_collect}[sys.argv[1]]()
