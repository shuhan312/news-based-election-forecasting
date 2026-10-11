"""Run a Task over items: estimate first, refuse over budget, never pay twice.

    estimate()  exact input tokens from the free token-counting endpoint,
                plus an output estimate, priced at the batch rate
    run()       estimate -> budget guard -> one Batches API submission ->
                poll -> collect -> parse -> cache

The cache key is the request hash (task.request_hash): one file per answered
request. An item already answered with the identical request is never sent
again, so reruns and resumed runs cost nothing for finished work. A failed
or unparseable answer is recorded separately and is NOT cached as an answer,
so the next run retries it.

The client is injected, so tests run against a fake with no network or key.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from llm_eval.pricing import cost_usd
from llm_eval.task import Task, request_hash


class BudgetExceeded(RuntimeError):
    """Raised before any paid call when the estimate exceeds the budget."""


def _cache_file(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _pending(task: Task, items: dict[str, Any],
             cache_dir: Path) -> dict[str, tuple[str, dict]]:
    """item_id -> (request hash, params) for items with no cached answer."""
    out = {}
    for item_id, payload in items.items():
        params = task.params(payload)
        key = request_hash(params)
        if not _cache_file(cache_dir, key).exists():
            out[item_id] = (key, params)
    return out


def estimate(task: Task, items: dict[str, Any], *, client,
             cache_dir: str | Path) -> dict:
    """Cost of the requests a run would actually send (cached ones excluded).

    Token counting is free, so this spends nothing.
    """
    cache_dir = Path(cache_dir)
    pending = _pending(task, items, cache_dir)
    input_tokens = 0
    for _, params in pending.values():
        counted = client.messages.count_tokens(
            **{k: v for k, v in params.items() if k != "max_tokens"})
        input_tokens += counted.input_tokens
    output_tokens = task.expected_output_tokens * len(pending)
    return {"requests": len(pending), "cached": len(items) - len(pending),
            "input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
            "estimated_cost_usd": round(cost_usd(task.model, input_tokens,
                                                 output_tokens), 4)}


def run(task: Task, items: dict[str, Any], *, client, cache_dir: str | Path,
        budget_usd: float, poll_seconds: float = 60) -> dict:
    """Answer every item, spending at most `budget_usd` (estimated).

    Returns {"predictions": {item_id: 1/0}, "failed": [...], "estimate":
    {...}, "usage": {...}}. Items whose answer could not be used appear in
    "failed" and are retried on the next run.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_file = cache_dir / "_batch_state.json"

    est = estimate(task, items, client=client, cache_dir=cache_dir)
    pending = _pending(task, items, cache_dir)
    usage = {"input_tokens": 0, "output_tokens": 0}

    if pending:
        if state_file.exists():
            # A batch was already submitted and not collected: resume it,
            # never submit (and pay for) the same work twice.
            batch_id = json.loads(state_file.read_text())["batch_id"]
        else:
            if est["estimated_cost_usd"] > budget_usd:
                raise BudgetExceeded(
                    f"estimated ${est['estimated_cost_usd']} exceeds budget "
                    f"${budget_usd}; nothing was sent")
            batch = client.messages.batches.create(requests=[
                {"custom_id": key, "params": params}
                for key, params in pending.values()])
            batch_id = batch.id
            state_file.write_text(json.dumps({"batch_id": batch_id}))

        while client.messages.batches.retrieve(batch_id).processing_status \
                != "ended":
            time.sleep(poll_seconds)

        by_key = {key: item_id for item_id, (key, _) in pending.items()}
        for result in client.messages.batches.results(batch_id):
            item_id = by_key.get(result.custom_id)
            if item_id is None:
                continue
            if result.result.type != "succeeded":
                continue          # not cached: retried next run
            msg = result.result.message
            usage["input_tokens"] += msg.usage.input_tokens
            usage["output_tokens"] += msg.usage.output_tokens
            raw = "".join(b.text for b in msg.content
                          if getattr(b, "type", None) == "text")
            label = (task.parse(raw, items[item_id])
                     if msg.stop_reason == "end_turn" else None)
            if label is None:
                continue          # unusable answer: not cached, retried
            _cache_file(cache_dir, result.custom_id).write_text(json.dumps(
                {"item_id": item_id, "label": label, "raw_text": raw}))
        state_file.unlink()       # this batch is fully collected

    predictions, failed = {}, []
    for item_id, payload in items.items():
        path = _cache_file(cache_dir, request_hash(task.params(payload)))
        if path.exists():
            predictions[item_id] = json.loads(path.read_text())["label"]
        else:
            failed.append(item_id)
    usage["actual_cost_usd"] = round(cost_usd(
        task.model, usage["input_tokens"], usage["output_tokens"]), 4)
    return {"predictions": predictions, "failed": failed,
            "estimate": est, "usage": usage}
