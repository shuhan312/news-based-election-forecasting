"""Wire the six stages together from one TOML config.

    load -> audit -> (estimate -> run, API only) -> score -> report

Everything task-specific is named in the config and looked up in two small
registries below, so adding a new task means registering a Task factory and,
for API runs, a payload loader. The stages themselves never change.
"""

from __future__ import annotations

import csv
import tomllib
from pathlib import Path
from typing import Any, Callable

from llm_eval import audit, metrics, runner
from llm_eval.dataset import Example, hash_split, load_labels, load_split_file
from llm_eval.task import Task, v1_local_relevance_task

# name in config -> factory(**task_options) -> Task
TASKS: dict[str, Callable[..., Task]] = {
    "v1_local_relevance": v1_local_relevance_task,
}


def _v1_review_sheet_payloads(ids: list[str], *, paths: list[str]) -> dict:
    """V1 article inputs, built exactly as V1's classifier runners built them."""
    from news_collection.llm_v2_io import (article_from_sample_row,
                                           load_query_inventory)
    wanted, rows = set(ids), {}
    for path in paths:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                if r["article_id"] in wanted:
                    rows[r["article_id"]] = r
    queries = load_query_inventory()
    return {i: article_from_sample_row(rows[i], query_by_id=queries)
            for i in ids if i in rows}


# name in config -> loader(ids, **options) -> {item_id: payload}
PAYLOADS: dict[str, Callable[..., dict]] = {
    "v1_review_sheet": _v1_review_sheet_payloads,
}


def load_config(path: str | Path) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


# --- stage 1: load --------------------------------------------------------------------

def load_examples(cfg: dict) -> list[Example]:
    examples, seen = [], set()
    for spec in cfg["labels"]:
        spec = dict(spec)
        batch = load_labels(spec.pop("path"), **{
            **spec, "group_cols": tuple(spec.get("group_cols", ()))})
        for e in batch:
            if e.id in seen:
                raise ValueError(f"{e.id} is labelled in two batches")
            seen.add(e.id)
            examples.append(e)
    return examples


def select_split(cfg: dict, examples: list[Example]) -> list[Example]:
    """The examples scored: the configured split, from a committed file or
    recomputed by hash."""
    s = cfg["split"]
    if "file" in s:
        split = load_split_file(s["file"])
    else:
        split = hash_split(examples, salt=s["salt"], force_dev_origins=tuple(
            s.get("force_dev_origins", ())))
    return [e for e in examples if split.get(e.id) == s["evaluate"]]


# --- stage 3/4: predictions -------------------------------------------------------

def archived_predictions(cfg: dict) -> dict[str, int]:
    """Predictions a classifier already produced, read from file. No API call."""
    preds = {}
    for spec in cfg["predictions"]["archived"]:
        with open(spec["path"], encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                preds[r[spec["id_col"]]] = int(
                    r[spec["label_col"]] == spec["positive"])
    return preds


def _task_and_payloads(cfg: dict, ids: list[str]) -> tuple[Task, dict]:
    t = cfg["task"]
    task = TASKS[t["classifier"]](**t.get("options", {}))
    p = cfg["predictions"]["payloads"]
    payloads = PAYLOADS[p["loader"]](ids, **p.get("options", {}))
    return task, payloads


def estimate_cost(cfg: dict, examples: list[Example], *, client) -> dict:
    task, payloads = _task_and_payloads(cfg, [e.id for e in examples])
    return runner.estimate(task, payloads, client=client,
                           cache_dir=cfg["predictions"]["cache_dir"])


def api_predictions(cfg: dict, examples: list[Example], *, client) -> dict:
    task, payloads = _task_and_payloads(cfg, [e.id for e in examples])
    p = cfg["predictions"]
    return runner.run(task, payloads, client=client,
                      cache_dir=p["cache_dir"], budget_usd=p["budget_usd"],
                      poll_seconds=p.get("poll_seconds", 60))


# --- the whole pipeline ---------------------------------------------------------------

def run_pipeline(cfg: dict, *, client: Any = None) -> dict:
    """All stages. `client` is needed only when predictions.source = "api"."""
    examples = load_examples(cfg)
    a = cfg.get("audit", {})
    audit_result = audit.run_audit(
        examples,                       # audit every label, not just one split
        stratum_field=a.get("stratum_field"),
        allowed_prefixes=a.get("allowed_prefixes"),
        drift_within=a.get("drift_within"),
        classifier_is_llm=cfg["task"].get("classifier_is_llm", True))

    scored = select_split(cfg, examples)
    source = cfg["predictions"]["source"]
    run_info: dict = {"source": source}
    if source == "archived":
        preds = archived_predictions(cfg)
    elif source == "api":
        if client is None:
            raise ValueError("predictions.source = 'api' needs a client")
        out = api_predictions(cfg, scored, client=client)
        preds = out["predictions"]
        run_info.update(failed=out["failed"], estimate=out["estimate"],
                        usage=out["usage"])
    else:
        raise ValueError(f"unknown predictions.source {source!r}")

    missing = [e.id for e in scored if e.id not in preds]
    y = [e.label for e in scored]
    p = [preds.get(e.id, 0) for e in scored]
    subgroups = {f: metrics.score_by(scored, preds, f)
                 for f in cfg.get("score", {}).get("by", [])}
    return {"task": cfg["task"]["name"], "split": cfg["split"]["evaluate"],
            "run": run_info, "audit": audit_result,
            "overall": metrics.score(y, p),
            "missing_predictions_counted_negative": len(missing),
            "subgroups": subgroups, "gate": _gate(cfg, metrics.score(y, p))}


def _gate(cfg: dict, overall: dict) -> dict | None:
    """Optional pass/fail bars from the config, read on point estimates."""
    bars = cfg.get("gate")
    if not bars:
        return None
    checks = {name: {"value": overall.get(name), "bar": bar,
                     "pass": overall.get(name) is not None
                     and overall[name] >= bar}
              for name, bar in bars.items()}
    return {"checks": checks, "pass": all(c["pass"] for c in checks.values())}
