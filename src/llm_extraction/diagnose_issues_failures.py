"""Measure why the issues layer fails on long articles, before changing it.

## Why this exists

The far-window gate failed three times on the issues layer, and each time the
fix was a guess: 5.6%, then 12.4% after a prompt rule that named a field which
does not exist, then 10.1% after correcting the name. Guessing three times is
the symptom; the cause is that failures were recorded as a validation message
and nothing else. There was no `stop_reason`, no raw response text, and no
per-article token count, so "was the JSON truncated" could only be inferred
from the shape of a parse error.

This module measures instead. It re-runs a named set of article ids at a given
`max_tokens` and records, per article: the stop reason, the output token count,
the raw response text, whether it parsed, and what the validator said. One run
answers the question that three runs of guessing did not.

## What the data already establishes, from the far3 tranche

Length is the dividing line, not the source and not the arm:

    Guardian, over 8,000 characters   6 of 24 fail   25.0%
    Guardian, 8,000 or fewer          3 of 62 fail    4.8%

So short articles already clear the 5% bar and the problem is confined to long
ones. An earlier reading of the same tranche claimed the failures contaminated
the local-versus-national comparison; that was overstated - 86 of the 89
articles in the tranche are national, so the tranche cannot speak to the local
failure rate at all.

The nine failures split into two groups that need different answers:

    63,776 chars   evidence span not verbatim
    57,535 chars   unparseable JSON, stops at character 2074
    42,012 chars   evidence span not verbatim
    36,213 chars   invented property 'additionalIssuesNote'
    12,643 chars   unparseable JSON
     9,961 chars   'issue_other_label' at the wrong level
     6,246 chars   'issue_other_label' at the wrong level
     4,420 chars   empty property name
     4,155 chars   'extraction_status' at the wrong level

The four shortest are placement errors, length-independent, and survived two
prompt revisions. Raising a token budget cannot fix a key the model finished
writing in the wrong place, so at most the five longest can improve.

## What this run can and cannot conclude

It CAN establish whether truncation occurred: `stop_reason == "max_tokens"` is
a fact, not an inference.

It CANNOT establish that a larger budget is the fix merely because a record
passes on the re-run. Generation is stochastic, so a record that failed at
8,000 may pass at 16,000 for reasons unrelated to the budget. The stop reasons
are the evidence; the pass count is a hint.

Production config is deliberately untouched: `ORIGINAL_LAYERS` still carries
8,000, and this module takes max_tokens as an argument. Nothing changes until
the measurement says what to change.

Usage:
    python3 -m src.llm_extraction.diagnose_issues_failures far3 16000
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_corpus_extraction import (ARMS, LAYER_ARMS,
                                                      ORIGINAL_LAYERS,
                                                      _user_message,
                                                      _validate_record,
                                                      load_tranche)

LAYER = "issues"


def failed_ids(tranche: str) -> list[str]:
    """The article ids the layer failed on, in the order the outputs list them."""
    payload = json.loads(Path(
        f"llm_context/corpus_extraction_outputs_{tranche}.json").read_text())
    return [r["article_id"] for r in payload["layers"][LAYER]
            if r.get("record") is None or r.get("validation_errors")]


def main() -> None:
    tranche = sys.argv[1]
    max_tokens = int(sys.argv[2])
    ids = failed_ids(tranche)

    # Load the articles the tranche actually used, by id. Never re-derive the
    # tranche: the far sampler excludes what previous draws used, so
    # re-deriving after collection returns a different sample.
    all_ids = {r["article_id"] for rows in json.loads(Path(
        f"llm_context/corpus_extraction_outputs_{tranche}.json").read_text()
        )["layers"].values() for r in rows}
    arts, _fallback, _census = load_tranche(tranche, only_ids=all_ids)
    meta = json.loads(Path(
        f"llm_context/corpus_extraction_batches_{tranche}.json").read_text())

    build, _validate, production_max = ORIGINAL_LAYERS[LAYER]
    arm = ARMS[LAYER_ARMS[LAYER]]
    model = arm["model"] or "claude-sonnet-5"
    system = [{"type": "text", "text": build(),
               "cache_control": {"type": "ephemeral"}}]
    client = anthropic.Anthropic()

    results = []
    print(f"re-running {len(ids)} failed articles at max_tokens={max_tokens} "
          f"(production is {production_max})\n")
    for aid in ids:
        a = arts[aid]
        body_len = len(a.get("body") or "")
        row: dict = {"article_id": aid, "body_chars": body_len,
                     "source": a.get("source"), "arm": a.get("arm")}
        try:
            msg = client.messages.create(
                model=model, max_tokens=max_tokens, thinking=arm["thinking"],
                system=system,
                messages=[{"role": "user", "content": _user_message(a)}])
        except Exception as e:
            row.update(stop_reason=None, error=f"{type(e).__name__}: {e}")
            results.append(row)
            print(f"  {body_len:7,}  API error: {type(e).__name__}")
            continue

        text = "".join(b.text for b in msg.content if b.type == "text")
        row.update(stop_reason=msg.stop_reason,
                   output_tokens=msg.usage.output_tokens,
                   input_tokens=msg.usage.input_tokens,
                   raw_response=text)
        try:
            parsed = json.loads(text.strip().removeprefix("```json")
                                .removeprefix("```").removesuffix("```"))
        except json.JSONDecodeError as e:
            row.update(parsed=False, validation_errors=[f"unparseable: {e}"])
            results.append(row)
            print(f"  {body_len:7,}  stop={msg.stop_reason:11s} "
                  f"out={msg.usage.output_tokens:5d}  UNPARSEABLE")
            continue

        errors, repairs = _validate_record(LAYER, parsed, aid, arts, meta)
        row.update(parsed=True, validation_errors=errors, repairs=repairs)
        verdict = "PASS" if not errors else errors[0][:52]
        print(f"  {body_len:7,}  stop={msg.stop_reason:11s} "
              f"out={msg.usage.output_tokens:5d}  {verdict}")
        results.append(row)

    passed = sum(1 for r in results
                 if r.get("parsed") and not r.get("validation_errors"))
    truncated = sum(1 for r in results if r.get("stop_reason") == "max_tokens")
    out = Path(f"llm_context/issues_failure_diagnosis_{tranche}.json")
    out.write_text(json.dumps({
        "tranche": tranche, "max_tokens_tested": max_tokens,
        "production_max_tokens": production_max, "model": model,
        "articles": len(ids), "passed_on_rerun": passed,
        "stopped_at_max_tokens": truncated,
        "note": ("a pass on re-run is not proof that the budget was the cause; "
                 "generation is stochastic. stop_reason is the evidence."),
        "results": results}, indent=2))

    print(f"\n{passed}/{len(ids)} now pass; {truncated}/{len(ids)} stopped at "
          f"the token ceiling")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
