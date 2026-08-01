"""Build and assess a smaller, blind human-review plan for local E5.

Why this exists
---------------
The local extension has 936 articles that passed the machine-owned E4, E6
and E8 checks. Reading every article for E5 would be expensive, but the old
168-article pilot does *not* justify trusting E5 automatically: its agreement
with the human labels was only 52.4% and Cohen's kappa was 0.191.

This module therefore reduces immediate work without laundering the model's
E5 answer into the corpus:

* every ambiguous or low-confidence E5 answer is sent to a human;
* a deterministic, stratified sample of the remaining decisive answers is
  reviewed blindly;
* all other articles remain pending until the new validation passes the
  project's existing kappa >= 0.60 gate and the methodology is approved;
* no command in this module automatically admits a deferred article.

The human-facing CSV deliberately omits the model's E5 decision, reason and
evidence. This prevents anchoring during the validation review. The model
answer is recovered by article_id only when ``evaluate`` is run.

Usage
-----
Build the 250-row blind queue and compact audit plan::

    python3 -m src.news_collection.build_e5_risk_review_plan build

After filling the four e5_* fields and reviewer_id in the blind queue::

    python3 -m src.news_collection.build_e5_risk_review_plan evaluate

Copy only completed, schema-valid human E5 judgements back to the original
round-two sheet (deferred model answers are never copied)::

    python3 -m src.news_collection.build_e5_risk_review_plan sync
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .build_e5_local_queue import LLM_OUTPUTS, OUT_QUEUE
from .compute_review_agreement import KAPPA_ACCEPTABLE, cohens_kappa
from .manual_review_schema import (
    CONFIDENCE_LEVELS,
    DECISIONS,
    REASON_CODES,
)

BLIND_QUEUE = Path("news_collection/e5_local_risk_review_queue.csv")
PLAN = Path("news_collection/e5_local_risk_review_plan.json")
EVALUATION = Path("news_collection/e5_local_risk_review_evaluation.json")

# This is an operational review budget, not a claim of statistical power.
# With the current 112 mandatory cases it leaves 138 blind validation cases.
# The plan reports the realised validation size so the report cannot present
# this practical cap as if it were a pre-computed precision guarantee.
TARGET_HUMAN_ROWS = 250
SAMPLE_SEED = "e5-local-risk-review-v1"

AMBIGUOUS_E5_DECISIONS = {
    "needs_second_review",
    "insufficient_evidence",
}
DECISIVE_E5_DECISIONS = {"include", "exclude"}

BLIND_FIELDS = [
    "blind_review_id",
    # This reveals the workflow stage, not the model's direction. It lets the
    # reviewer finish the 138 validation rows before spending time resolving
    # every ambiguous case.
    "review_stage",
    "article_id",
    "election_id",
    "source_id",
    "arm",
    "sample_stratum",
    "e5_decision",
    "e5_reason_code",
    "e5_supporting_text",
    "e5_confidence",
    "reviewer_id",
    "reviewer_note",
    "headline",
    "effective_date",
    "day_index_from_polling_day",
    "article_text_excerpt",
    "article_text_path",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _stable_digest(value: str) -> str:
    """Return a deterministic pseudo-random key without using row order."""

    return hashlib.sha256(f"{SAMPLE_SEED}:{value}".encode()).hexdigest()


def _load_llm_rows() -> dict[str, dict[str, str]]:
    """Union the disjoint production batches and reject identity conflicts."""

    rows: dict[str, dict[str, str]] = {}
    for path in LLM_OUTPUTS:
        if not path.exists():
            continue
        for row in _read_csv(path):
            article_id = row["article_id"]
            if article_id in rows:
                raise RuntimeError(
                    f"{article_id} appears in more than one LLM output"
                )
            rows[article_id] = row
    if not rows:
        raise RuntimeError("no LLM production output is available")
    return rows


def _clears_machine_rules(row: dict[str, str]) -> bool:
    """E5 is intentionally absent: only E4, E6 and E8 are filtered here."""

    return (
        row.get("status") == "ok"
        and all(
            row.get(f"{rule}_decision") in {"include", "not_applicable"}
            for rule in ("e4", "e6", "e8")
        )
    )


def _not_cleared_reason(row: dict[str, str]) -> str:
    """Keep technical failures separate from substantive rule failures."""

    if row.get("status") != "ok":
        return row.get("status") or "missing_status"
    failed_rules = [
        f"{rule.upper()}={row.get(f'{rule}_decision') or 'blank'}"
        for rule in ("e4", "e6", "e8")
        if row.get(f"{rule}_decision") not in {"include", "not_applicable"}
    ]
    return ";".join(failed_rules) or "unknown_non_clearance"


def _mandatory_reason(model_row: dict[str, str]) -> str:
    """Explain why a model answer cannot enter the validation-only pool."""

    decision = model_row.get("e5_decision", "")
    confidence = model_row.get("e5_confidence", "")
    if decision in AMBIGUOUS_E5_DECISIONS:
        return f"ambiguous_model_decision:{decision}"
    if decision not in DECISIVE_E5_DECISIONS:
        return f"unexpected_model_decision:{decision or 'blank'}"
    if confidence not in {"high", "medium"}:
        return f"low_or_missing_model_confidence:{confidence or 'blank'}"
    return ""


def _sampling_stratum(
    queue_row: dict[str, str], model_row: dict[str, str]
) -> tuple[str, str, str, str]:
    """Keep validation coverage across the main sources of model variation."""

    return (
        queue_row["election_id"],
        queue_row["source_id"],
        model_row["e5_decision"],
        model_row["e5_confidence"],
    )


def _stratified_sample(
    candidates: list[tuple[dict[str, str], dict[str, str]]],
    sample_size: int,
) -> list[tuple[dict[str, str], dict[str, str]]]:
    """Select reproducibly, with at least one row per stratum when possible.

    The remaining places are allocated proportionally by the largest-remainder
    method. Within a stratum, SHA-256 rank replaces a mutable random-number
    generator, so the same inputs always select the same article ids.
    """

    if sample_size <= 0:
        return []
    if sample_size >= len(candidates):
        return sorted(candidates, key=lambda pair: _stable_digest(pair[0]["article_id"]))

    groups: dict[
        tuple[str, str, str, str],
        list[tuple[dict[str, str], dict[str, str]]],
    ] = defaultdict(list)
    for pair in candidates:
        groups[_sampling_stratum(*pair)].append(pair)
    for group in groups.values():
        group.sort(key=lambda pair: _stable_digest(pair[0]["article_id"]))

    keys = sorted(groups)
    allocation = {key: 0 for key in keys}
    if sample_size < len(keys):
        # This branch is defensive for unusually small future budgets. It
        # favours larger strata, then uses a stable key to break ties.
        chosen_keys = sorted(
            keys,
            key=lambda key: (
                -len(groups[key]),
                _stable_digest("|".join(key)),
            ),
        )[:sample_size]
        for key in chosen_keys:
            allocation[key] = 1
    else:
        # Give every observed stratum one validation article first.
        for key in keys:
            allocation[key] = 1
        remaining = sample_size - len(keys)
        capacities = {key: len(groups[key]) - 1 for key in keys}
        total_capacity = sum(capacities.values())
        if remaining and total_capacity:
            exact = {
                key: remaining * capacities[key] / total_capacity
                for key in keys
            }
            for key in keys:
                extra = min(capacities[key], math.floor(exact[key]))
                allocation[key] += extra
            left = sample_size - sum(allocation.values())
            remainder_order = sorted(
                keys,
                key=lambda key: (
                    -(exact[key] - math.floor(exact[key])),
                    _stable_digest("|".join(key)),
                ),
            )
            for key in remainder_order:
                if not left:
                    break
                if allocation[key] < len(groups[key]):
                    allocation[key] += 1
                    left -= 1

    selected = [
        pair
        for key in keys
        for pair in groups[key][: allocation[key]]
    ]
    if len(selected) != sample_size:
        raise RuntimeError(
            f"sampling allocation produced {len(selected)} rows, "
            f"expected {sample_size}"
        )
    return sorted(
        selected, key=lambda pair: _stable_digest(pair[0]["article_id"])
    )


def build_plan(
    queue_rows: list[dict[str, str]],
    llm_rows: dict[str, dict[str, str]],
    *,
    target_human_rows: int = TARGET_HUMAN_ROWS,
) -> dict:
    """Partition the cleared population without making an E5 judgement."""

    cleared: list[tuple[dict[str, str], dict[str, str]]] = []
    not_cleared = Counter()
    for queue_row in queue_rows:
        model_row = llm_rows.get(queue_row["article_id"])
        if model_row is None:
            not_cleared["no_llm_row"] += 1
        elif _clears_machine_rules(model_row):
            cleared.append((queue_row, model_row))
        else:
            not_cleared[_not_cleared_reason(model_row)] += 1

    mandatory = [
        pair for pair in cleared if _mandatory_reason(pair[1])
    ]
    validation_pool = [
        pair for pair in cleared if not _mandatory_reason(pair[1])
    ]
    validation_size = min(
        max(target_human_rows - len(mandatory), 0),
        len(validation_pool),
    )
    validation = _stratified_sample(validation_pool, validation_size)

    mandatory_ids = {row["article_id"] for row, _ in mandatory}
    validation_ids = {row["article_id"] for row, _ in validation}
    deferred_ids = {
        row["article_id"] for row, _ in validation_pool
    } - validation_ids
    if mandatory_ids & validation_ids:
        raise RuntimeError("mandatory and validation selections overlap")

    return {
        "cleared": cleared,
        "mandatory": sorted(
            mandatory, key=lambda pair: _stable_digest(pair[0]["article_id"])
        ),
        "validation": validation,
        "deferred_ids": deferred_ids,
        "not_cleared": dict(not_cleared),
    }


def _blind_row(
    queue_row: dict[str, str], *, review_stage: str
) -> dict[str, str]:
    """Expose article evidence and blank human fields, never the model label."""

    row = {field: queue_row.get(field, "") for field in BLIND_FIELDS}
    row["blind_review_id"] = (
        "E5R-" + _stable_digest(queue_row["article_id"])[:12]
    )
    row["review_stage"] = review_stage
    for field in (
        "e5_decision",
        "e5_reason_code",
        "e5_supporting_text",
        "e5_confidence",
        "reviewer_id",
        "reviewer_note",
    ):
        row[field] = ""
    return row


def _historical_pilot_result() -> dict:
    """Report the old failure as context; it is not reused as a new gate."""

    human_path = Path("news_collection/manual_review_sample.csv")
    model_path = Path("news_collection/manual_review_llm_pilot.csv")
    if not human_path.exists() or not model_path.exists():
        return {"available": False}
    human = {
        row["article_id"]: row
        for row in _read_csv(human_path)
        if row.get("review_round") == "initial"
    }
    pairs = []
    for model_row in _read_csv(model_path):
        human_row = human.get(model_row["article_id"])
        if model_row.get("status") != "ok" or not human_row:
            continue
        h = human_row.get("e5_decision", "")
        m = model_row.get("e5_decision", "")
        if h and m:
            pairs.append((h, m))
    result = cohens_kappa(pairs)
    if result is None:
        return {"available": False}
    agreement, _expected, kappa = result
    return {
        "available": True,
        "pairs": len(pairs),
        "agreement": round(agreement, 4),
        "cohens_kappa": None if kappa is None else round(kappa, 4),
        "passed_existing_gate": (
            kappa is not None and kappa >= KAPPA_ACCEPTABLE
        ),
    }


def build() -> None:
    """Write the blind queue and a compact, reproducible audit summary."""

    queue_rows = _read_csv(OUT_QUEUE)
    llm_rows = _load_llm_rows()
    plan = build_plan(queue_rows, llm_rows)

    # Validation comes first operationally. Within each stage the hashed order
    # prevents source order or model output order from guiding the reviewer.
    review_pairs = [
        ("blind_validation", row, model)
        for row, model in plan["validation"]
    ] + [
        ("mandatory_resolution", row, model)
        for row, model in plan["mandatory"]
    ]
    review_pairs.sort(
        key=lambda item: (
            item[0] != "blind_validation",
            _stable_digest(item[1]["article_id"]),
        )
    )
    review_rows = [
        _blind_row(row, review_stage=stage)
        for stage, row, _model in review_pairs
    ]
    with BLIND_QUEUE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=BLIND_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(review_rows)

    mandatory_reasons = Counter(
        _mandatory_reason(model) for _row, model in plan["mandatory"]
    )
    validation_strata = Counter(
        "|".join(_sampling_stratum(row, model))
        for row, model in plan["validation"]
    )
    summary = {
        "method": "blind risk-based E5 validation; no automatic admission",
        "input_queue_rows": len(queue_rows),
        "machine_rule_cleared_population": len(plan["cleared"]),
        "not_machine_cleared": plan["not_cleared"],
        "target_human_rows": TARGET_HUMAN_ROWS,
        "mandatory_human_rows": len(plan["mandatory"]),
        "mandatory_reasons": dict(sorted(mandatory_reasons.items())),
        "blind_validation_rows": len(plan["validation"]),
        "immediate_human_rows": len(review_rows),
        "first_stage_human_rows": len(plan["validation"]),
        "first_stage_instruction": (
            "Filter review_stage=blind_validation and finish these rows "
            "before deciding how to handle the deferred population."
        ),
        "deferred_pending_rows": len(plan["deferred_ids"]),
        "sampling_seed": SAMPLE_SEED,
        "sampling_dimensions": [
            "election_id",
            "source_id",
            "model_e5_decision",
            "model_e5_confidence",
        ],
        "validation_strata": dict(sorted(validation_strata.items())),
        "historical_pilot_e5": _historical_pilot_result(),
        "validation_gate": {
            "metric": "Cohen's kappa",
            "minimum": KAPPA_ACCEPTABLE,
            "scope": "blind validation rows only",
            "effect": (
                "evidence for methodology review only; deferred rows remain "
                "pending until the method is explicitly approved"
            ),
        },
        "blinding": (
            "The human CSV omits model E5 decision, reason, confidence and "
            "supporting text."
        ),
    }
    PLAN.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"machine-rule-cleared E5 population: {len(plan['cleared'])}")
    print(f"mandatory human review:             {len(plan['mandatory'])}")
    print(f"blind validation sample:            {len(plan['validation'])}")
    print(f"immediate human workload:           {len(review_rows)}")
    print(f"deferred and still pending:         {len(plan['deferred_ids'])}")
    print(f"-> {BLIND_QUEUE}")
    print(f"-> {PLAN}")


def _validate_human_e5(row: dict[str, str]) -> list[str]:
    """Validate only the four E5 cells that this focused queue asks for."""

    decision = row.get("e5_decision", "")
    reason = row.get("e5_reason_code", "")
    evidence = row.get("e5_supporting_text", "")
    confidence = row.get("e5_confidence", "")
    problems = []
    if not decision:
        return ["not_started"]
    if decision not in DECISIONS or decision == "not_applicable":
        problems.append(f"invalid E5 decision: {decision!r}")
    if reason not in REASON_CODES["E5"]:
        problems.append(f"invalid E5 reason code: {reason!r}")
    elif REASON_CODES["E5"][reason] != decision:
        problems.append("E5 reason code does not match the decision")
    if decision != "insufficient_evidence" and not evidence:
        problems.append("E5 supporting text is required")
    if decision in DECISIVE_E5_DECISIONS and confidence not in CONFIDENCE_LEVELS:
        problems.append("include/exclude requires high, medium or low confidence")
    if not row.get("reviewer_id", ""):
        problems.append("reviewer_id is required")
    return problems


def _frozen_review_ids(
    review_rows: list[dict[str, str]],
) -> tuple[set[str], set[str]]:
    """Recover the review stages frozen when the blind queue was built.

    The model output may later change after a technical retry.  Re-running the
    sampling algorithm at evaluation time would then compare the completed
    workbook with a different set of articles.  The saved blind queue is the
    auditable sampling frame, so its stage labels are authoritative.
    """

    article_ids = [row.get("article_id", "") for row in review_rows]
    if not all(article_ids):
        raise RuntimeError("the frozen E5 review queue contains a blank article_id")
    if len(article_ids) != len(set(article_ids)):
        raise RuntimeError("the frozen E5 review queue contains duplicate article ids")

    allowed_stages = {"blind_validation", "mandatory_resolution"}
    unexpected = sorted(
        {row.get("review_stage", "") for row in review_rows} - allowed_stages
    )
    if unexpected:
        raise RuntimeError(f"unexpected frozen E5 review stages: {unexpected}")

    validation_ids = {
        row["article_id"]
        for row in review_rows
        if row["review_stage"] == "blind_validation"
    }
    mandatory_ids = {
        row["article_id"]
        for row in review_rows
        if row["review_stage"] == "mandatory_resolution"
    }
    return validation_ids, mandatory_ids


def evaluate() -> None:
    """Evaluate blind labels; never modify the corpus or deferred decisions."""

    if not BLIND_QUEUE.exists():
        raise RuntimeError(f"{BLIND_QUEUE} does not exist; run build first")
    llm_rows = _load_llm_rows()
    review_rows = _read_csv(BLIND_QUEUE)
    validation_ids, mandatory_ids = _frozen_review_ids(review_rows)
    missing_model_rows = (validation_ids | mandatory_ids) - llm_rows.keys()
    if missing_model_rows:
        raise RuntimeError(
            f"{len(missing_model_rows)} frozen review ids have no LLM audit row"
        )

    human_by_id = {row["article_id"]: row for row in review_rows}
    invalid: dict[str, list[str]] = {}
    completed = {}
    for article_id, row in human_by_id.items():
        problems = _validate_human_e5(row)
        if problems == ["not_started"]:
            continue
        if problems:
            invalid[article_id] = problems
        else:
            completed[article_id] = row

    pairs = [
        (
            completed[article_id]["e5_decision"],
            llm_rows[article_id]["e5_decision"],
        )
        for article_id in sorted(validation_ids & completed.keys())
    ]
    result = cohens_kappa(pairs)
    agreement = kappa = None
    if result is not None:
        agreement, _expected, kappa = result
    validation_complete = validation_ids <= completed.keys()
    passed = (
        validation_complete
        and not invalid
        and kappa is not None
        and kappa >= KAPPA_ACCEPTABLE
    )

    per_model_decision = {}
    for decision in sorted(DECISIVE_E5_DECISIONS):
        relevant = [
            (human, model) for human, model in pairs if model == decision
        ]
        per_model_decision[decision] = {
            "n": len(relevant),
            "agreement": (
                round(
                    sum(human == model for human, model in relevant)
                    / len(relevant),
                    4,
                )
                if relevant
                else None
            ),
        }

    report = {
        "mandatory_completed": len(mandatory_ids & completed.keys()),
        "mandatory_total": len(mandatory_ids),
        "validation_completed": len(validation_ids & completed.keys()),
        "validation_total": len(validation_ids),
        "invalid_started_rows": invalid,
        "agreement": None if agreement is None else round(agreement, 4),
        "cohens_kappa": None if kappa is None else round(kappa, 4),
        "required_kappa": KAPPA_ACCEPTABLE,
        "passed_statistical_gate": passed,
        "review_sample_source": str(BLIND_QUEUE),
        "review_sample_is_frozen": True,
        "per_model_decision": per_model_decision,
        "methodological_status": (
            "eligible_for_methodology_review_not_automatic_admission"
            if passed
            else "deferred_model_decisions_remain_pending"
        ),
    }
    EVALUATION.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"validation complete: {report['validation_completed']}/"
        f"{report['validation_total']}"
    )
    print(f"Cohen's kappa: {report['cohens_kappa']}")
    print(f"gate passed: {passed}")
    print(f"-> {EVALUATION}")


def sync() -> None:
    """Copy only completed human E5 labels into the original queue safely."""

    if not BLIND_QUEUE.exists():
        raise RuntimeError(f"{BLIND_QUEUE} does not exist; run build first")
    review_rows = _read_csv(BLIND_QUEUE)
    completed = {}
    invalid = {}
    for row in review_rows:
        problems = _validate_human_e5(row)
        if problems == ["not_started"]:
            continue
        if problems:
            invalid[row["article_id"]] = problems
        else:
            completed[row["article_id"]] = row
    if invalid:
        raise RuntimeError(
            f"{len(invalid)} started review rows are invalid; run evaluate "
            "and fix them before sync"
        )

    original_rows = _read_csv(OUT_QUEUE)
    seen = set()
    copied = 0
    for row in original_rows:
        human = completed.get(row["article_id"])
        if human is None:
            continue
        seen.add(row["article_id"])
        for field in (
            "e5_decision",
            "e5_reason_code",
            "e5_supporting_text",
            "e5_confidence",
        ):
            existing = row.get(field, "")
            incoming = human[field]
            if existing and existing != incoming:
                raise RuntimeError(
                    f"{row['article_id']} already has a different {field}; "
                    "refusing to overwrite human work"
                )
            row[field] = incoming
        row["reviewer_id"] = human["reviewer_id"]
        row["reviewer_note"] = human.get("reviewer_note", "")
        copied += 1
    missing = completed.keys() - seen
    if missing:
        raise RuntimeError(
            f"{len(missing)} reviewed ids are absent from {OUT_QUEUE}"
        )

    with OUT_QUEUE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=original_rows[0].keys(), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(original_rows)
    print(f"copied {copied} completed human E5 judgements -> {OUT_QUEUE}")
    print("No deferred model E5 decision was copied.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "evaluate", "sync"))
    args = parser.parse_args()
    {"build": build, "evaluate": evaluate, "sync": sync}[args.command]()


if __name__ == "__main__":
    main()
