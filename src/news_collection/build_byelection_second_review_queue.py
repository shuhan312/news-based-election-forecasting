"""Build the by-election second-review queue for human adjudication.

    python3 -m src.news_collection.build_byelection_second_review_queue

Two kinds of row end up here, mirroring the principal corpus's queue:

- **llm_failed_twice** - articles whose frozen-classifier request failed
  the schema validator on both the batch and its retry. Per the
  principal procedure, all four rules are judged by hand for these, with
  E6 auto-filled ``not_applicable`` on rows that were never
  Reform-flagged (that is a deterministic fact, not a judgement).
- **needs_second_review** - articles the LLM resolved but where at least
  one rule's answer was a borderline code, so the derived overall
  decision is ``needs_second_review``. The LLM's own cells are shown for
  context with their ``llm_v2`` source labels; assembly only honours a
  cell whose source is ``human`` or ``auto``, so nothing here is decided
  until the reviewer overwrites the disputed cell.

Existing human work is never overwritten: if the queue file already
exists, rows whose article already carries any human-sourced cell are
kept verbatim and only genuinely new articles are appended.
"""

from __future__ import annotations

import csv
from pathlib import Path

DECISIONS = Path("news_collection/byelection_eligibility_decisions.csv")
LLM_OUTPUT = Path("news_collection/byelection_llm_v2.csv")
SHEET = Path("news_collection/byelection_review.csv")
OUT = Path("news_collection/byelection_second_review_queue.csv")

RULES = ("e4", "e5", "e6", "e8")
FIELDS = (
    ["article_id", "election_id", "arm", "queue_reason"]
    + [f"{rule}_{suffix}" for rule in RULES
       for suffix in ("decision", "reason_code", "source")]
    + ["final_decision", "final_reason_code", "reviewer_note",
       "headline", "article_text_excerpt", "article_text_path"]
)


def main() -> None:
    sheet = {row["article_id"]: row
             for row in csv.DictReader(SHEET.open(encoding="utf-8-sig"))}
    llm = {row["article_id"]: row
           for row in csv.DictReader(LLM_OUTPUT.open(encoding="utf-8-sig"))}
    decisions = list(csv.DictReader(DECISIONS.open(encoding="utf-8-sig")))

    existing: dict[str, dict] = {}
    if OUT.exists():
        existing = {row["article_id"]: row
                    for row in csv.DictReader(OUT.open(encoding="utf-8-sig"))}

    rows = []
    for decision in decisions:
        article_id = decision["article_id"]
        llm_row = llm.get(article_id, {})
        failed_twice = llm_row.get("status") not in ("ok", None) \
            and llm_row.get("status") != "ok"
        needs_second = decision["overall_decision"] == "needs_second_review"
        if not failed_twice and not needs_second:
            continue
        if article_id in existing:
            rows.append(existing[article_id])   # never discard human work
            continue

        sheet_row = sheet.get(article_id, {})
        row = {field: "" for field in FIELDS}
        row.update({
            "article_id": article_id,
            "election_id": decision["election_id"],
            "arm": decision["arm"],
            "queue_reason": ("llm_failed_twice" if failed_twice
                             else "needs_second_review"),
            "headline": sheet_row.get("headline", ""),
            "article_text_excerpt": sheet_row.get("article_text_excerpt", ""),
            "article_text_path": sheet_row.get("article_text_path", ""),
        })
        if failed_twice:
            # E6 is deterministic bookkeeping when the row was never
            # Reform-flagged; everything else awaits the human.
            if decision["needs_reform_disambiguation"] != "yes":
                row.update({"e6_decision": "not_applicable",
                            "e6_reason_code": "E6-NOT-REFORM-FLAGGED",
                            "e6_source": "auto"})
        else:
            for rule in RULES:
                row[f"{rule}_decision"] = decision[f"{rule}_decision"]
                row[f"{rule}_reason_code"] = decision[f"{rule}_reason_code"]
                row[f"{rule}_source"] = decision[f"{rule}_source"]
        rows.append(row)

    rows.sort(key=lambda row: (row["queue_reason"], row["article_id"]))
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    from collections import Counter
    print(f"{len(rows)} rows -> {OUT}")
    print("by reason:", dict(Counter(row['queue_reason'] for row in rows)))
    print("by arm   :", dict(Counter(row['arm'] for row in rows)))


if __name__ == "__main__":
    main()
