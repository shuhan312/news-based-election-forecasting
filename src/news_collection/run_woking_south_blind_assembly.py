"""Assemble the Woking South blind-test eligibility decisions (stage 5).

    python3 -m src.news_collection.run_woking_south_blind_assembly

Same shape as the v3 assembly: import the reviewer's completed local
sheet verbatim (sha256-pinned), merge exactly the five reviewed fields
into a copy of the full 459-row review sheet, reshape the two resolved
second reviews into the queue stream, and run the frozen assembler.
Under its production rules the human's E5 decides local rows and the
LLM's audit E5 column decides national rows; E4/E8 (and E6 for the
Reform-flagged 119) come from the LLM verdicts throughout.

The two second reviews were resolved by the reviewer to exclude:
the road-closure report never places itself inside the division
(consistent with the reviewer's standing precedent that unlocated
impact is not L3), and the British Council story fits none of N2's
five closed categories. Their reason narratives live on the imported
sheet; the queue carries the machine-readable form.

Blind discipline unchanged: this stage reads news artefacts only.
The stop-loss check (protocol: abort under 15 usable articles) is
printed from the assembly counts at the end.
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
    "e5_local_review_queue_woking_south_completed.csv")
SOURCE_SHA256 = "5469e29c062340d447c0"

DIR = Path("news_collection/woking_south_blind")
IMPORTED = DIR / "e5_local_review_completed.csv"
PATCHED_SHEET = DIR / "review_sheet_with_human_e5.csv"
RESOLUTIONS = DIR / "second_review_resolutions.csv"
DECISIONS = DIR / "eligibility_decisions.csv"

REVIEW_FIELDS = ("e5_decision", "e5_reason_code", "e5_confidence",
                 "e5_supporting_text", "reviewer_id")


def import_sheet() -> dict[str, dict]:
    digest = hashlib.sha256(SOURCE_SHEET.read_bytes()).hexdigest()
    if not digest.startswith(SOURCE_SHA256):
        raise RuntimeError(f"sheet sha256 {digest[:20]} != {SOURCE_SHA256}")
    shutil.copyfile(SOURCE_SHEET, IMPORTED)
    with IMPORTED.open(newline="", encoding="utf-8-sig") as handle:
        decisions = {row["article_id"]: row for row in csv.DictReader(handle)}
    if len(decisions) != 41:
        raise RuntimeError(f"expected 41 decisions, got {len(decisions)}")
    return decisions


def build_patched_sheet(decisions: dict[str, dict]) -> int:
    with (DIR / "review_sheet.csv").open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = reader.fieldnames
    patched = 0
    for row in rows:
        verdict = decisions.get(row["article_id"])
        if verdict is None:
            continue
        if (row.get("e5_decision") or "").strip():
            raise RuntimeError(f"{row['article_id']} already judged on sheet")
        for field in REVIEW_FIELDS:
            row[field] = verdict.get(field, "")
        patched += 1
    if patched != len(decisions):
        raise RuntimeError(f"{patched} of {len(decisions)} rows matched")
    with PATCHED_SHEET.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return patched


def build_resolutions(decisions: dict[str, dict]) -> int:
    """The reviewer's two final calls, in the assembler's queue layout."""

    rows = [{
        "article_id": aid,
        "e5_decision": "exclude",
        "e5_reason_code": "E5-NO-L-OR-N-RULE-MET",
        "e5_source": "human",
    } for aid, row in decisions.items()
        if row["e5_decision"] == "needs_second_review"]
    with RESOLUTIONS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["article_id", "e5_decision",
                                "e5_reason_code", "e5_source"],
            lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    decisions = import_sheet()
    patched = build_patched_sheet(decisions)
    resolved = build_resolutions(decisions)
    print(f"imported 41 decisions; patched {patched} sheet rows; "
          f"{resolved} second reviews resolved to exclude")

    frozen.SHEETS = (PATCHED_SHEET,)
    frozen.LLM_OUTPUTS = (DIR / "llm_v2.csv",)
    frozen.QUEUE = RESOLUTIONS
    frozen.OUT = DECISIONS
    frozen.main()

    with DECISIONS.open(newline="", encoding="utf-8") as handle:
        includes = sum(1 for r in csv.DictReader(handle)
                       if r.get("overall_decision") == "include")
    print(f"\nSTOP-LOSS CHECK (protocol: abort under 15): "
          f"{includes} usable articles -> "
          f"{'PROCEED' if includes >= 15 else 'ABORT AND RECORD'}")


if __name__ == "__main__":
    main()
