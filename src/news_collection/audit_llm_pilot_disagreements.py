"""Create a reproducible row-level audit of v1 LLM disagreements.

The published aggregate kappa values answer whether v1 cleared its gate, but
they do not explain *why* a rule failed. This audit separates:

* field misalignment (a legal reason code was written into ``decision``);
* substantive include-versus-exclude disagreement;
* human or model uncertainty/insufficient evidence;
* evidence visible in the 1,500-character excerpt versus evidence available
  only in the full text.

Important: ``llm_decision_semantic`` is a diagnostic interpretation only.
The raw output is never overwritten and the official v1 agreement result is
never recomputed from repaired values. Post-hoc repair would change the
evaluated classifier after seeing its errors.

Usage:
    python3 -m src.news_collection.audit_llm_pilot_disagreements
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .manual_review_schema import DECISIONS, REASON_CODES, RULES

HUMAN = Path("news_collection/manual_review_sample.csv")
LLM = Path("news_collection/manual_review_llm_pilot.csv")
OUT = Path("news_collection/llm_v1_disagreement_audit.csv")

FIELDS = [
    "article_id",
    "rule",
    "arm",
    "source_id",
    "headline",
    "human_decision",
    "human_reason_code",
    "llm_decision_raw",
    "llm_decision_semantic",
    "llm_reason_code",
    "field_misalignment",
    "raw_agreement",
    "semantic_agreement",
    "disagreement_type",
    "human_evidence_location",
    "excerpt_truncated",
]


def load_initial_human_rows(path: Path = HUMAN) -> dict[str, dict[str, str]]:
    """Load the initial human review only, keyed by article ID."""
    with path.open(newline="") as handle:
        return {
            row["article_id"]: row
            for row in csv.DictReader(handle)
            if row["review_round"] == "initial"
        }


def load_ok_llm_rows(path: Path = LLM) -> dict[str, dict[str, str]]:
    """Load rows v1 labelled as parse-successful."""
    with path.open(newline="") as handle:
        return {
            row["article_id"]: row
            for row in csv.DictReader(handle)
            if row.get("status") == "ok"
        }


def semantic_llm_decision(
    rule: str, raw_decision: str
) -> tuple[str, bool]:
    """Interpret a reason-code-in-decision error without changing raw data.

    The interpreted value is used only to diagnose whether v1 probably meant
    the same polarity as the human reviewer. It must not replace the raw value
    in the official agreement calculation, because doing so would repair the
    classifier after its result was observed.
    """
    if raw_decision in DECISIONS:
        return raw_decision, False
    if raw_decision in REASON_CODES[rule]:
        return REASON_CODES[rule][raw_decision], True
    return raw_decision, False


def evidence_location(human_row: dict[str, str], rule: str) -> str:
    """Locate the human evidence quote relative to the model's v1 input."""
    prefix = rule.lower()
    quote = human_row.get(f"{prefix}_supporting_text", "")
    if not quote:
        return "no_human_quote"
    excerpt = human_row.get("article_text_excerpt", "")
    if quote in excerpt:
        return "in_v1_excerpt"
    path_text = human_row.get("article_text_path", "")
    path = Path(path_text) if path_text else None
    if path and path.is_file():
        full_text = path.read_text(errors="replace")
        if quote in full_text:
            return "full_text_only"
    return "not_exactly_located"


def single_line(value: str) -> str:
    """Collapse source formatting in display-only text such as headlines."""
    return " ".join(value.split())


def disagreement_type(
    human: str,
    raw_model: str,
    semantic_model: str,
    *,
    field_misalignment: bool,
) -> str:
    """Assign one mutually exclusive diagnostic category."""
    if field_misalignment:
        return (
            "field_misalignment_same_semantics"
            if human == semantic_model
            else "field_misalignment_substantive"
        )
    if human == raw_model:
        return "agreement"
    resolved = {"include", "exclude"}
    if human in resolved and raw_model in resolved:
        return "hard_include_exclude"
    if human in ("needs_second_review", "insufficient_evidence"):
        return "human_unresolved"
    if raw_model in ("needs_second_review", "insufficient_evidence"):
        return "llm_unresolved"
    return "other_invalid_or_category_disagreement"


def build_audit_rows(
    human_rows: dict[str, dict[str, str]],
    llm_rows: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Build rows for raw disagreements and every schema-invalid decision."""
    audit_rows = []
    for article_id in sorted(set(human_rows) & set(llm_rows)):
        human_row = human_rows[article_id]
        llm_row = llm_rows[article_id]
        for rule in RULES:
            prefix = rule.lower()
            human_decision = human_row[f"{prefix}_decision"]
            raw_decision = llm_row[f"{prefix}_decision"]
            semantic_decision, misaligned = semantic_llm_decision(
                rule, raw_decision
            )
            raw_agreement = human_decision == raw_decision
            # Agreements with no field error need no row in a disagreement
            # audit. Field errors remain even when their intended semantics
            # happen to agree, because they are still invalid output.
            if raw_agreement and not misaligned:
                continue
            audit_rows.append(
                {
                    "article_id": article_id,
                    "rule": rule,
                    "arm": human_row["arm"],
                    "source_id": human_row["source_id"],
                    "headline": single_line(human_row["headline"]),
                    "human_decision": human_decision,
                    "human_reason_code": human_row[
                        f"{prefix}_reason_code"
                    ],
                    "llm_decision_raw": raw_decision,
                    "llm_decision_semantic": semantic_decision,
                    "llm_reason_code": llm_row[
                        f"{prefix}_reason_code"
                    ],
                    "field_misalignment": str(misaligned),
                    "raw_agreement": str(raw_agreement),
                    "semantic_agreement": str(
                        human_decision == semantic_decision
                    ),
                    "disagreement_type": disagreement_type(
                        human_decision,
                        raw_decision,
                        semantic_decision,
                        field_misalignment=misaligned,
                    ),
                    "human_evidence_location": evidence_location(
                        human_row, rule
                    ),
                    "excerpt_truncated": str(
                        "[truncated,"
                        in human_row.get("article_text_excerpt", "")
                    ),
                }
            )
    return audit_rows


def main() -> None:
    """Write the audit CSV and print concise, reproducible summaries."""
    human_rows = load_initial_human_rows()
    llm_rows = load_ok_llm_rows()
    audit_rows = build_audit_rows(human_rows, llm_rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as handle:
        # Use LF explicitly so the generated research artifact passes the
        # repository's whitespace checks on every platform.
        writer = csv.DictWriter(
            handle, fieldnames=FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(audit_rows)

    print(
        f"{len(human_rows)} human rows, {len(llm_rows)} v1 ok rows, "
        f"{len(audit_rows)} disagreement/invalid cells -> {OUT}"
    )
    for rule in RULES:
        rows = [row for row in audit_rows if row["rule"] == rule]
        by_type = Counter(row["disagreement_type"] for row in rows)
        evidence = Counter(row["human_evidence_location"] for row in rows)
        print(f"\n{rule}: {len(rows)} audited cells")
        print("  type:", dict(sorted(by_type.items())))
        print("  human evidence:", dict(sorted(evidence.items())))


if __name__ == "__main__":
    main()
