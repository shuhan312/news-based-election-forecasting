"""Assemble the Haslemere probe's eligibility decisions (stage 5).

    python3 -m src.news_collection.run_haslemere_probe_assembly

Same four-constant adaptation as the enrichment assembly: the merge
rules, human-over-LLM precedence and derive-never-store overall
decision are ``assemble_corpus_decisions``'s frozen code, pointed at
the probe's files. The sheet is the imported human E5 pass (45 rows,
reviewer SL; original file sha256
4fbe4079008cfed4363132c4c5bf97dcf025709cc0450b4b7b1edb676e492b1f) -
the two E8-excluded pool rows never reached the human queue and stay
recorded in ``llm_v2.csv`` only.

The frozen assembler reads second-review adjudications from a QUEUE
stream, not from the sheet's ``final_reviewed_decision`` column, so
``build_resolution_queue()`` derives that stream mechanically from the
sheet: every row whose e5_decision is ``needs_second_review`` and whose
``final_reviewed_decision`` is filled becomes one queue row with
``e5_source=human``. No judgement is made here - the human's final
call and its correction_reason are already on the sheet; this only
reshapes them into the column layout the frozen code consumes.
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import assemble_corpus_decisions as frozen

SHEET = Path("news_collection/haslemere_probe/e5_local_review_completed.csv")
RESOLUTIONS = Path(
    "news_collection/haslemere_probe/second_review_resolutions.csv")

frozen.SHEETS = (SHEET,)
frozen.LLM_OUTPUTS = (Path("news_collection/haslemere_probe/llm_v2.csv"),)
frozen.QUEUE = RESOLUTIONS
frozen.OUT = Path("news_collection/haslemere_probe/eligibility_decisions.csv")


def build_resolution_queue() -> int:
    """Reshape the sheet's resolved second reviews into the QUEUE layout."""

    rows = []
    with SHEET.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["e5_decision"] != "needs_second_review":
                continue
            final = row.get("final_reviewed_decision", "").strip()
            if not final:
                continue  # unresolved -> assembler reports it as pending
            rows.append({
                "article_id": row["article_id"],
                "e5_decision": final,
                # The final call "no L rule shown met" maps to the one
                # exclude code E5 has; the narrative sits in the sheet's
                # correction_reason.
                "e5_reason_code": "E5-NO-L-OR-N-RULE-MET",
                "e5_source": "human",
            })
    with RESOLUTIONS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["article_id", "e5_decision", "e5_reason_code",
                        "e5_source"],
            lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    resolved = build_resolution_queue()
    print(f"second-review resolutions -> {RESOLUTIONS} ({resolved} rows)")
    frozen.main()


if __name__ == "__main__":
    main()
