"""Assemble the v3 exploratory decisions after the 38-row E5 opening pass.

    python3 -m src.news_collection.run_e5_backlog_v3_assembly

The reviewer's opening pass (38 rows, reviewer SL, original sheet
sha256 recorded below) admitted 30 local by-election articles across
all four target elections. Those decisions must NOT touch the v2
chain: `byelection_review.csv` and `byelection_eligibility_decisions
.csv` are recorded inputs of the frozen canonical release v2 - their
sha256 digests are part of that release's identity - so this module
builds a PARALLEL v3 lineage instead:

1. import the reviewer's completed sheet verbatim into
   ``news_collection/e5_local_backlog_v3/`` (hash-checked against the
   constant below, so a swapped file fails loudly);
2. write ``byelection_review_v3.csv``: a copy of the frozen sheet with
   ONLY the 38 rows' e5_* fields and reviewer_id merged in - every
   other cell byte-identical, originals untouched;
3. run the frozen assembler over the patched copy with the same LLM
   output and second-review queue the v2 assembly used, writing v3
   decisions beside it.

Everything downstream of these decisions (release, features, refit)
is exploratory by construction and versioned v3exp; the unblinding
happened long before any of these rows were judged.
"""

from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path

from . import assemble_corpus_decisions as frozen

csv.field_size_limit(10_000_000)

SOURCE_SHEET = Path(
    "/Users/sl1425/Documents/Codex/2026-08-01/"
    "referenced-chatgpt-conversation-this-is-untrusted-2/outputs/"
    "e5_local_triage_queue_opening_completed.csv")
# Recorded at import time; a different file (edited after the fact,
# wrong export) fails the run instead of silently entering the lineage.
SOURCE_SHA256 = ("fc9155d597684928fb14")

OUT_DIR = Path("news_collection/e5_local_backlog_v3")
IMPORTED = OUT_DIR / "e5_opening_completed.csv"
PATCHED_SHEET = OUT_DIR / "byelection_review_v3.csv"
DECISIONS_V3 = OUT_DIR / "byelection_eligibility_decisions_v3.csv"

ORIGINAL_SHEET = Path("news_collection/byelection_review.csv")

# The five fields the reviewer owns; nothing else may move between
# sheets, so a stray edit in another column cannot ride along.
REVIEW_FIELDS = ("e5_decision", "e5_reason_code", "e5_confidence",
                 "e5_supporting_text", "reviewer_id")


def import_sheet() -> dict[str, dict]:
    digest = hashlib.sha256(SOURCE_SHEET.read_bytes()).hexdigest()
    if not digest.startswith(SOURCE_SHA256):
        raise RuntimeError(
            f"completed sheet sha256 {digest[:20]} does not match the "
            f"recorded import {SOURCE_SHA256}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_SHEET, IMPORTED)
    with IMPORTED.open(newline="", encoding="utf-8-sig") as handle:
        decisions = {row["article_id"]: row
                     for row in csv.DictReader(handle)}
    if len(decisions) != 38:
        raise RuntimeError(f"expected 38 decisions, got {len(decisions)}")
    return decisions


def build_patched_sheet(decisions: dict[str, dict]) -> int:
    """Copy the frozen sheet, merging in exactly the reviewed fields."""

    patched = 0
    with ORIGINAL_SHEET.open(newline="", encoding="utf-8") as src:
        reader = csv.DictReader(src)
        rows = list(reader)
        fieldnames = reader.fieldnames
    for row in rows:
        verdict = decisions.get(row["article_id"])
        if verdict is None:
            continue
        if (row.get("e5_decision") or "").strip():
            raise RuntimeError(
                f"{row['article_id']} already carries an e5 decision on "
                "the frozen sheet; refusing to overwrite")
        for field in REVIEW_FIELDS:
            row[field] = verdict.get(field, "")
        patched += 1
    if patched != len(decisions):
        raise RuntimeError(
            f"only {patched} of {len(decisions)} reviewed rows found on "
            "the sheet")
    with PATCHED_SHEET.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return patched


def main() -> None:
    decisions = import_sheet()
    patched = build_patched_sheet(decisions)
    print(f"imported {len(decisions)} decisions; patched {patched} rows "
          f"-> {PATCHED_SHEET}")

    frozen.SHEETS = (PATCHED_SHEET,)
    frozen.LLM_OUTPUTS = (Path("news_collection/byelection_llm_v2.csv"),)
    frozen.QUEUE = Path("news_collection/byelection_second_review_queue.csv")
    frozen.OUT = DECISIONS_V3
    frozen.main()


if __name__ == "__main__":
    main()
