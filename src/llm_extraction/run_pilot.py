"""Phase 6 / Step 2 runner: pilot LLM context extraction over the
deterministic sample, via the Message Batches API (50% discount).

Three subcommands, so every stage is inspectable and resumable:

    python3 -m src.llm_extraction.run_pilot sample
        build the deterministic sample -> llm_context/
        llm_context_pilot_sample_v1.csv (no API call)
    python3 -m src.llm_extraction.run_pilot submit
        create the message batch -> saves the batch id (one API call
        creating the batch; requests run asynchronously at 50% price)
    python3 -m src.llm_extraction.run_pilot collect
        poll the batch, parse + validate every output against the
        v1.1 schema and rules R1-R8, write the pilot outputs and the
        audit inputs

Model: claude-sonnet-5 - the project's standing frozen model choice
(the same model as the approved eligibility classification pipeline
in src/news_collection/llm_classifier_v2.py), adaptive thinking,
shared system prompt cached across the batch. The full corpus is NOT
processed - only the pilot sample.
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

from .pilot_sample import (PILOT_VERSION, PROMPT_VERSION,
                           build_system_prompt, build_user_message,
                           parse_model_json, select_pilot_sample,
                           select_revalidation_set)
from .validate_context import (RULES_VERSION, SCHEMA_VERSION,
                               validate_record)

MODEL = "claude-sonnet-5"   # pinned frozen model - same as the
                            # approved classification pipeline;
                            # asserted on every collected result
# 40k: adaptive thinking spends from the same budget as the JSON, and
# the pilot showed 16k truncates ~1 in 5 articles mid-string. Batches
# are non-streaming-safe at this size.
MAX_TOKENS = 40000

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
MAPPING = Path(
    "news_collection/duplicate_mapping_layer_v1_provisional.csv")
AVAIL = Path("news_collection/"
             "article_version_temporal_availability_v1_provisional.csv")
URL_MAP = Path("news_collection/url_duplicate_mapping_v1_provisional.csv")

OUT_SAMPLE = Path("llm_context/llm_context_pilot_sample_v1.csv")
OUT_BATCH_ID = Path("llm_context/pilot_batch_id.txt")
OUT_RESULTS = Path("llm_context/llm_context_pilot_outputs.json")


def load_articles() -> dict[str, dict]:
    """Every eligible article with the metadata the prompt needs."""
    usable = {r["article_id"]: r for r in csv.DictReader(MAPPING.open())
              if r["downstream_usage_status"] == "use_as_canonical_input"}
    avail = {r["article_id"]: r for r in csv.DictReader(AVAIL.open())}
    urls = {r["article_id"]: r for r in csv.DictReader(URL_MAP.open())}
    arts = {}
    for line in LAYER.open():
        a = json.loads(line)
        aid = a["article_id"]
        if aid not in usable or a["quality_status"] != "valid_full_text":
            continue
        av = avail.get(aid, {})
        text = (a.get("title", "") + " "
                + a.get("body_text", "")).lower()
        arts[aid] = {
            "article_id": aid,
            "canonical_article_id": usable[aid]["canonical_article_id"],
            "election_id": a.get("election_id", ""),
            "arm": a.get("arm", ""),
            "title": a.get("title", ""),
            "body": a.get("body_text", ""),
            "author": (a.get("author_text") or "").strip() or None,
            "source": a.get("source_name", ""),
            "publication_datetime": av.get("published_at", ""),
            "temporal_availability_status": av.get(
                "availability_status", ""),
            "url": urls.get(aid, {}).get("canonical_url", ""),
            "mentions_reform": "reform uk" in text,
        }
    return arts


def cmd_sample() -> None:
    arts = load_articles()
    result = select_pilot_sample([
        {"article_id": a["article_id"],
         "election_id": a["election_id"], "arm": a["arm"],
         "mentions_reform": a["mentions_reform"]}
        for a in arts.values()])
    with OUT_SAMPLE.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["article_id", "election_id", "arm",
                    "mentions_reform", "pilot_version"])
        for aid in result["selected"]:
            a = arts[aid]
            w.writerow([aid, a["election_id"], a["arm"],
                        a["mentions_reform"], PILOT_VERSION])
    print(f"{len(result['selected'])} articles -> {OUT_SAMPLE}")
    print("strata:", json.dumps(result["strata"], indent=1))
    print(f"reform: {result['reform_in_base']} in base "
          f"+ {result['reform_topped_up']} topped up")
    print("method:", result["method"])


def _meta(a: dict) -> dict:
    """The metadata block the extractor copies into input (matches
    the schema's input section; update_ts absent by design)."""
    return {"article_id": a["article_id"],
            "canonical_article_id": a["canonical_article_id"],
            "title": a["title"], "source": a["source"],
            "author": a["author"],
            "publication_datetime": a["publication_datetime"],
            "temporal_availability_status":
                a["temporal_availability_status"],
            "url": a["url"] or "unknown",
            "article_type": "news_report",
            "local_national": "local_surrey" if a["arm"] == "local"
            else "national",
            "geographic_relevance": "to_be_extracted",
            "election_id": a["election_id"],
            "linked_wards": [], "linked_candidates": [],
            "linked_parties": [],
            "provenance_ref":
                "duplicate_mapping_layer_v1_provisional.csv"}


def cmd_submit() -> None:
    arts = load_articles()
    sample = [r["article_id"] for r in csv.DictReader(OUT_SAMPLE.open())]
    system = [{"type": "text", "text": build_system_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = []
    for aid in sample:
        a = arts[aid]
        requests.append(Request(
            custom_id=aid,
            params=MessageCreateParamsNonStreaming(
                model=MODEL, max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{"role": "user", "content": build_user_message(
                    _meta(a), a["title"], a["body"])}])))
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    OUT_BATCH_ID.write_text(batch.id + "\n")
    print(f"batch {batch.id} created with {len(requests)} requests "
          f"({MODEL}, batches = 50% price)")


def cmd_collect() -> None:
    batch_id = OUT_BATCH_ID.read_text().strip()
    client = anthropic.Anthropic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"status {batch.processing_status} | counts "
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
            assert msg.model.startswith(MODEL), msg.model  # frozen model
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
                errors = validate_record(record, a.get("body", ""),
                                         a.get("title", ""))
                entry["record"] = record
                entry["validation_errors"] = errors
                statuses["valid" if not errors
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
        {"pilot_version": PILOT_VERSION, "schema_version": SCHEMA_VERSION,
         "model": MODEL, "batch_id": batch_id,
         "status_counts": dict(sorted(statuses.items())),
         "results": results}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(results)} results -> {OUT_RESULTS}")
    print("statuses:", dict(sorted(statuses.items())))


def cmd_retry() -> None:
    """Resubmit ONLY the articles whose first-pass output was
    unparseable (max_tokens truncation - a pipeline parameter fault,
    not model quality; rule-error records stay as findings). The
    retry batch id is stored separately; collect_retry merges."""
    data = json.loads(OUT_RESULTS.read_text())
    failed = [r["article_id"] for r in data["results"]
              if any(e.startswith("unparseable") for e
                     in r["validation_errors"])
              or r["batch_result"] != "succeeded"]
    print(f"retrying {len(failed)} articles at max_tokens={MAX_TOKENS}")
    arts = load_articles()
    system = [{"type": "text", "text": build_system_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": build_user_message(
                _meta(arts[aid]), arts[aid]["title"],
                arts[aid]["body"])}]))
        for aid in failed]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    Path("llm_context/pilot_retry_batch_id.txt").write_text(
        batch.id + "\n")
    print(f"retry batch {batch.id}")


def cmd_collect_retry() -> None:
    """Poll the retry batch and merge its results into the outputs
    file, replacing the failed first-pass entries."""
    batch_id = Path(
        "llm_context/pilot_retry_batch_id.txt").read_text().strip()
    client = anthropic.Anthropic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"status {batch.processing_status}", flush=True)
        time.sleep(60)

    arts = load_articles()
    data = json.loads(OUT_RESULTS.read_text())
    by_id = {r["article_id"]: r for r in data["results"]}
    for res in client.messages.batches.results(batch_id):
        aid = res.custom_id
        entry = {"article_id": aid, "batch_result": res.result.type,
                 "validation_errors": [], "record": None,
                 "usage": None, "retried": True}
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
                entry["validation_errors"] = validate_record(
                    record, a.get("body", ""), a.get("title", ""))
            except (ValueError, json.JSONDecodeError) as e:
                entry["validation_errors"] = [f"unparseable: {e}"]
                entry["raw_text"] = text[:2000]
        by_id[aid] = entry

    results = sorted(by_id.values(), key=lambda r: r["article_id"])
    statuses = Counter(
        "valid" if r["batch_result"] == "succeeded"
        and not r["validation_errors"]
        else ("unparseable" if any(
            e.startswith("unparseable") for e in r["validation_errors"])
            else ("schema_or_rule_errors"
                  if r["batch_result"] == "succeeded"
                  else r["batch_result"]))
        for r in results)
    data.update({"results": results, "retry_batch_id": batch_id,
                 "status_counts": dict(sorted(statuses.items()))})
    OUT_RESULTS.write_text(json.dumps(data, indent=1,
                                      ensure_ascii=False) + "\n")
    print("merged. statuses:", dict(sorted(statuses.items())))


OUT_REVAL_SAMPLE = Path(
    "llm_context/llm_context_revalidation_sample_v1.csv")
OUT_REVAL_BATCH = Path("llm_context/reval_batch_id.txt")
OUT_REVAL = Path("llm_context/llm_context_revalidation_outputs.json")


def cmd_reval_sample() -> None:
    """Step 2.5 targeted re-validation set from the pilot results
    plus the full corpus (for election-administration positives)."""
    pilot = json.loads(OUT_RESULTS.read_text())["results"]
    arts = load_articles()
    r = select_revalidation_set(pilot, arts)
    with OUT_REVAL_SAMPLE.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["article_id", "election_id", "arm",
                    "prompt_version"])
        for aid in r["selected"]:
            a = arts[aid]
            w.writerow([aid, a["election_id"], a["arm"],
                        PROMPT_VERSION])
    print(f"{len(r['selected'])} articles -> {OUT_REVAL_SAMPLE}")
    print("method:", r["method"])


def cmd_reval_submit() -> None:
    """Submit the re-validation batch under prompt v1.1 (same model,
    same 40k limit, batches + cached system prompt)."""
    arts = load_articles()
    sample = [r["article_id"]
              for r in csv.DictReader(OUT_REVAL_SAMPLE.open())]
    system = [{"type": "text", "text": build_system_prompt(),
               "cache_control": {"type": "ephemeral"}}]
    requests = [Request(
        custom_id=aid,
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": build_user_message(
                _meta(arts[aid]), arts[aid]["title"],
                arts[aid]["body"])}]))
        for aid in sample]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    OUT_REVAL_BATCH.write_text(batch.id + "\n")
    print(f"reval batch {batch.id}: {len(requests)} requests "
          f"({MODEL}, {PROMPT_VERSION})")


def cmd_reval_collect() -> None:
    """Collect and validate the re-validation batch under rules
    v1.1; writes the outputs file the report is built from."""
    batch_id = OUT_REVAL_BATCH.read_text().strip()
    client = anthropic.Anthropic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"status {batch.processing_status}", flush=True)
        time.sleep(60)

    arts = load_articles()
    results, statuses = [], Counter()
    for res in client.messages.batches.results(batch_id):
        aid = res.custom_id
        entry = {"article_id": aid, "batch_result": res.result.type,
                 "validation_errors": [], "record": None,
                 "usage": None}
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
                entry["validation_errors"] = validate_record(
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
    OUT_REVAL.write_text(json.dumps(
        {"prompt_version": PROMPT_VERSION,
         "rules_version": RULES_VERSION,
         "schema_version": SCHEMA_VERSION, "model": MODEL,
         "batch_id": batch_id,
         "status_counts": dict(sorted(statuses.items())),
         "results": results}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(results)} results -> {OUT_REVAL}")
    print("statuses:", dict(sorted(statuses.items())))


if __name__ == "__main__":
    {"sample": cmd_sample, "submit": cmd_submit,
     "collect": cmd_collect, "retry": cmd_retry,
     "collect_retry": cmd_collect_retry,
     "reval_sample": cmd_reval_sample,
     "reval_submit": cmd_reval_submit,
     "reval_collect": cmd_reval_collect}[sys.argv[1]]()
