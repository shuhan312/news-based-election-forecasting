"""Phase 6 / D4 - run the six compared extraction layers over the
60-article validation sample, so the human labels in the D4 workbook
can be scored against the frozen extractor (kappa / AC1 >= 0.60 per
field, per decision D4 in phase6_research_decisions_v1.md).

Frozen method, unchanged from the pilot runners: same model, same
per-layer prompt builders and validators, same user-message shapes
(temporal horizon still sees no date and no election id - the
separation-by-construction rule). Only the article list differs.

Article loading, disclosed: 50 of the 60 come from the same
normalised layer the pilot used (run_pilot.load_articles). The other
10 postdate the provisional normalisation freeze, so their text is
the raw extracted text file and their canonical_article_id is their
own id (no mapping row exists yet). The human labelled from exactly
these text files, so both sides of the comparison read the same
words; the corpus-v2 freeze will bring the 10 into the normalised
layer before the full-corpus run.

Usage:
    python3 -m src.llm_extraction.run_d4_validation submit
    python3 -m src.llm_extraction.run_d4_validation collect
"""

from __future__ import annotations

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

from . import (credit_blame, electoral_consequence, framing_detection,
               issue_classification, stance_classification,
               temporal_horizon)
from .pilot_sample import parse_model_json
from .run_pilot import MODEL, load_articles

SAMPLE = Path("llm_context/d4_validation_sample_v1.csv")
DECISIONS = Path("news_collection/corpus_eligibility_decisions.csv")
RECORDS = Path("data/raw/news/records")
TEXT = Path("data/raw/news/text")
OUT_BATCHES = Path("llm_context/d4_batch_ids.json")
OUT_RESULTS = Path("llm_context/d4_llm_outputs.json")

D4_RUN_VERSION = "d4-llm-run-v1.0-2026-07-29"

LAYERS = {
    "issues": (issue_classification.build_issue_prompt,
               issue_classification.validate_issue_record, 12000),
    "stance": (stance_classification.build_stance_prompt,
               stance_classification.validate_stance_record, 16000),
    "framing": (framing_detection.build_framing_prompt,
                framing_detection.validate_framing_record, 12000),
    "credit_blame": (credit_blame.build_cb_prompt,
                     credit_blame.validate_cb_record, 20000),
    "consequence": (electoral_consequence.build_ec_prompt,
                    electoral_consequence.validate_ec_record, 16000),
    "temporal": (temporal_horizon.build_th_prompt,
                 temporal_horizon.validate_th_record, 10000),
}


def load_d4_articles() -> tuple[dict[str, dict], list[str]]:
    """The 60 sampled articles; falls back to raw text for articles
    the provisional normalised layer does not cover. Returns the
    articles and the list of fallback ids (for the audit trail)."""
    sample = [r["article_id"] for r in csv.DictReader(SAMPLE.open())]
    meta = {r["article_id"]: r for r in csv.DictReader(DECISIONS.open())}
    arts = load_articles()
    out, fallback = {}, []
    for aid in sample:
        if aid in arts:
            out[aid] = arts[aid]
            continue
        rec = json.loads((RECORDS / f"{aid}.json").read_text(
            encoding="utf-8", errors="replace"))
        out[aid] = {
            "article_id": aid,
            "canonical_article_id": aid,
            "election_id": meta[aid]["election_id"],
            "arm": meta[aid]["arm"],
            "title": rec["identity"].get("headline") or "",
            "body": (TEXT / f"{aid}.txt").read_text(
                encoding="utf-8", errors="replace"),
        }
        fallback.append(aid)
    return out, fallback


def _user_message(a: dict, layer: str) -> str:
    if layer == "temporal":
        # No publication date, no election id: the horizon judgement
        # must come from content alone (separation by construction).
        meta = {"article_id": a["article_id"],
                "canonical_article_id": a["canonical_article_id"]}
        return (f"ARTICLE METADATA (copy ids into the record):\n"
                f"{json.dumps(meta, sort_keys=True)}\n\n"
                f"TITLE: {a['title']}\n\nBODY:\n{a['body']}")
    meta = {"article_id": a["article_id"],
            "canonical_article_id": a["canonical_article_id"],
            "election_id": a["election_id"],
            "local_national": "local_surrey" if a["arm"] == "local"
            else "national"}
    return (f"ARTICLE METADATA (copy ids into the record):\n"
            f"{json.dumps(meta, sort_keys=True, ensure_ascii=False)}\n\n"
            f"TITLE: {a['title']}\n\nBODY:\n{a['body']}")


def cmd_submit() -> None:
    arts, fallback = load_d4_articles()
    client = anthropic.Anthropic()
    batches = {"run_version": D4_RUN_VERSION, "model": MODEL,
               "articles": len(arts), "fallback_raw_text_ids": fallback,
               "layers": {}}
    for layer, (build_prompt, _validate, max_tokens) in LAYERS.items():
        system = [{"type": "text", "text": build_prompt(),
                   "cache_control": {"type": "ephemeral"}}]
        requests = [Request(
            custom_id=aid,
            params=MessageCreateParamsNonStreaming(
                model=MODEL, max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{"role": "user",
                           "content": _user_message(a, layer)}]))
            for aid, a in sorted(arts.items())]
        batch = client.messages.batches.create(requests=requests)
        batches["layers"][layer] = batch.id
        print(f"{layer}: batch {batch.id} ({len(requests)} articles)")
    OUT_BATCHES.write_text(json.dumps(batches, indent=2))
    print(f"-> {OUT_BATCHES} ({len(fallback)} articles on raw-text "
          f"fallback: {fallback})")


def cmd_collect() -> None:
    batches = json.loads(OUT_BATCHES.read_text())
    arts, _fallback = load_d4_articles()
    client = anthropic.Anthropic()
    pending = dict(batches["layers"])
    while pending:
        for layer, bid in list(pending.items()):
            b = client.messages.batches.retrieve(bid)
            if b.processing_status == "ended":
                del pending[layer]
            else:
                print(f"{layer}: {b.processing_status} "
                      f"{b.request_counts}", flush=True)
        if pending:
            time.sleep(120)

    results = {"run_version": D4_RUN_VERSION, "model": MODEL,
               "layers": {}}
    usage_in = usage_out = 0
    for layer, bid in batches["layers"].items():
        _build, validate, _mt = LAYERS[layer]
        rows, statuses = [], Counter()
        for res in client.messages.batches.results(bid):
            aid = res.custom_id
            entry = {"article_id": aid,
                     "batch_result": res.result.type,
                     "validation_errors": [], "record": None}
            if res.result.type == "succeeded":
                msg = res.result.message
                usage_in += msg.usage.input_tokens
                usage_out += msg.usage.output_tokens
                text = next((b.text for b in msg.content
                             if b.type == "text"), "")
                try:
                    record = parse_model_json(text)
                    a = arts.get(aid, {})
                    entry["record"] = record
                    entry["validation_errors"] = validate(
                        record, a.get("body", ""), a.get("title", ""))
                except (ValueError, json.JSONDecodeError) as e:
                    entry["validation_errors"] = [f"parse: {e}"]
            statuses["ok" if entry["record"] is not None
                     and not entry["validation_errors"]
                     else "failed"] += 1
            rows.append(entry)
        results["layers"][layer] = rows
        print(f"{layer}: {dict(statuses)}")
    results["usage"] = {"input_tokens": usage_in,
                        "output_tokens": usage_out}
    OUT_RESULTS.write_text(json.dumps(results, indent=2))
    print(f"-> {OUT_RESULTS}")


if __name__ == "__main__":
    {"submit": cmd_submit, "collect": cmd_collect}[sys.argv[1]]()
