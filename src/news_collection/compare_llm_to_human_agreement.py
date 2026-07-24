"""Compare the LLM classifier's decisions (manual_review_llm_pilot.csv)
against the human reviewer's decisions on the same 168 articles
(manual_review_sample.csv, review_round=initial), using the same
percent-agreement / Cohen's kappa arithmetic already used for the
human-vs-human blind recheck (compute_review_agreement.py).

This is the actual go/no-go check news_protocol/eligibility_manual_
review_methodology.md §7 describes: a rule's LLM output is only
trustworthy for the ~2,500 articles no human reviewed if its kappa
against the human gold standard clears the same 0.60 bar used
elsewhere in this protocol. Below that, the rule stays fully manual -
this script reports the number, it does not act on it.

Run this only after BOTH manual_review_sample.csv has been filled in
by a human AND manual_review_llm_pilot.csv contains real classifications
(status=ok).

Usage:
    python3 -m src.news_collection.compare_llm_to_human_agreement
"""

import csv
from pathlib import Path

from .compute_review_agreement import KAPPA_ACCEPTABLE, cohens_kappa
from .manual_review_schema import RULES

SAMPLE = Path("news_collection/manual_review_sample.csv")
LLM_PILOT = Path("news_collection/manual_review_llm_pilot.csv")


def load_csv(path):
    return list(csv.DictReader(path.open())) if path.exists() else []


def main():
    human_rows = {r["article_id"]: r for r in load_csv(SAMPLE)
                 if r["review_round"] == "initial"}
    llm_rows = {r["article_id"]: r for r in load_csv(LLM_PILOT)
               if r.get("status") == "ok"}

    if not llm_rows:
        print(f"No 'ok' rows in {LLM_PILOT} yet - the classifier "
             "hasn't been run with a real API key. Nothing to compare.")
        return

    print(f"Comparing {len(llm_rows)} LLM classifications against the "
         "human pilot review\n")

    for rule in RULES:
        field = f"{rule.lower()}_decision"
        pairs = []
        for aid, llm_row in llm_rows.items():
            human_row = human_rows.get(aid)
            if not human_row:
                continue
            h, m = human_row.get(field), llm_row.get(field)
            if not h or not m:
                continue
            pairs.append((h, m))
        if not pairs:
            print(f"{rule}: no comparable pairs yet")
            continue
        result = cohens_kappa(pairs)
        po, pe, kappa = result
        if kappa is None:
            print(f"{rule}: {len(pairs)} pairs, percent agreement={po:.1%} "
                 "(kappa undefined - no variation in decisions)")
            continue
        verdict = ("MEETS bar - eligible to use LLM for the remaining "
                  "corpus on this rule"
                  if kappa >= KAPPA_ACCEPTABLE else
                  "BELOW bar - this rule stays fully manual")
        print(f"{rule}: {len(pairs)} pairs, percent agreement={po:.1%}, "
             f"kappa={kappa:.3f} [{verdict}]")

    print("\nA rule's kappa clearing the bar here is what makes its "
         "LLM output usable on the remaining corpus - any rule below "
         "the bar stays fully manual.")


if __name__ == "__main__":
    main()
