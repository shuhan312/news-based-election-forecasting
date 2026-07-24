"""Assemble the remaining corpus's final eligibility decisions from
their two provenance streams, under §8.5 + §9 of
eligibility_manual_review_methodology.md (as provisionally adopted
2026-07-24, supervisor ratification due 2026-07-31).

Per-rule sources:

| Rule | arm=national | arm=local |
|---|---|---|
| E4, E8 | frozen v2 (validated §8.5)   | frozen v2 (validated §8.5) |
| E6     | frozen v2 (Reform-flagged only; else not_applicable) | same |
| E5     | frozen v2 (§9, provisional) | HUMAN, from full_corpus_review.csv |

Every output row records, per rule, which stream the decision came
from (``llm_v2`` / ``human`` / empty when unresolved). Reversing §9
therefore requires no data surgery: filter e5_source and re-derive.

A row's overall decision is computed by the same
``derive_overall_decision`` used everywhere else, and ONLY when all
four rules are present. Rows blocked on the LLM retry (non-ok status)
or on human E5 coding are reported as pending, never guessed.

Usage:
    python3 -m src.news_collection.assemble_corpus_decisions
"""

import csv
from collections import Counter
from pathlib import Path

from .manual_review_schema import RULES, derive_overall_decision

SHEET = Path("news_collection/full_corpus_review.csv")
LLM = Path("news_collection/manual_review_llm_v2_corpus.csv")
OUT = Path("news_collection/corpus_eligibility_decisions.csv")

FIELDS = (
    ["article_id", "election_id", "arm", "needs_reform_disambiguation"]
    + [f"{r.lower()}_{s}" for r in RULES
       for s in ("decision", "reason_code", "source")]
    + ["overall_decision", "resolution_status"]
)


def main() -> None:
    sheet = {r["article_id"]: r for r in csv.DictReader(SHEET.open())}
    llm = {r["article_id"]: r for r in csv.DictReader(LLM.open())}

    rows, statuses = [], Counter()
    for aid, s in sorted(sheet.items()):
        m = llm.get(aid, {})
        llm_ok = m.get("status") == "ok"
        out = {
            "article_id": aid, "election_id": s["election_id"],
            "arm": s["arm"],
            "needs_reform_disambiguation": s["needs_reform_disambiguation"],
        }
        blockers = []
        for rule in RULES:
            f = rule.lower()
            decision = source = reason = ""
            if rule == "E5" and s["arm"] == "local":
                # §9: local relevance stays a human judgement.
                decision = s.get("e5_decision", "")
                reason = s.get("e5_reason_code", "")
                source = "human" if decision else ""
                if not decision:
                    blockers.append("awaiting_human_e5")
            elif llm_ok:
                decision = m.get(f"{f}_decision", "")
                reason = m.get(f"{f}_reason_code", "")
                source = "llm_v2" if decision else ""
                if not decision:
                    blockers.append(f"llm_missing_{f}")
            else:
                blockers.append("awaiting_llm_retry")
            out[f"{f}_decision"] = decision
            out[f"{f}_reason_code"] = reason
            out[f"{f}_source"] = source

        if blockers:
            out["overall_decision"] = ""
            out["resolution_status"] = ";".join(sorted(set(blockers)))
        else:
            out["overall_decision"] = derive_overall_decision(
                out["e4_decision"], out["e5_decision"],
                out["e6_decision"], out["e8_decision"])
            out["resolution_status"] = "resolved"
        statuses[out["resolution_status"].split(";")[0]] += 1
        rows.append(out)

    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} rows -> {OUT}")
    print("resolution:", dict(statuses))
    resolved = [r for r in rows if r["resolution_status"] == "resolved"]
    print("overall (resolved only):",
          dict(Counter(r["overall_decision"] for r in resolved)))
    print("\nRe-run this script whenever the human E5 sheet or the LLM "
          "corpus CSV changes - it derives, never stores judgement.")


if __name__ == "__main__":
    main()
