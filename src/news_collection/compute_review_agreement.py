"""Percent agreement and Cohen's kappa between two independent review
rounds of the same articles (news_protocol/eligibility_manual_review_
methodology.md section on reviewer consistency).

What this measures, and when to run it
-----------------------------------------
build_manual_review_sample.py sets aside a blind-recheck subset
(manual_review_kappa_subset.csv) - the same articles as a subset of
the main sample, with decision fields blank again. The protocol is:
review the main sample once ("initial"), then separately and blindly
review just this subset a second time ("kappa_blind_recheck") without
looking back at the initial answers, THEN run this script. Doing it in
that order is the point: it measures whether the codebook produces
consistent decisions on its own, not whether a reviewer can remember
or match their earlier answer.

This script only computes agreement statistics on two already-filled
columns; it never makes or infers a decision itself (requirement:
no automatic inference of relevance/Reform/leakage/editorial status).

What gets compared
--------------------
Per rule (E4, E5, E6, E8) AND on the derived overall decision - a
codebook can be internally consistent (good E4 agreement) while still
producing different final calls (poor overall agreement) if a rule
combination is unstable, so both levels are reported separately, not
just one blended number.

Cohen's kappa, computed from first principles
-------------------------------------------------
kappa = (po - pe) / (1 - pe)
  po = observed proportion of agreement
  pe = proportion of agreement expected by chance, from each rater's
       own marginal distribution of decisions (sum over categories c of
       P(rater1=c) * P(rater2=c))
No ML library dependency for a five-line formula - anyone reviewing
this code can check the arithmetic directly against Cohen's 1960
paper without trusting an opaque implementation.

Usage:
    python3 -m src.news_collection.compute_review_agreement
"""

import csv
from pathlib import Path

from .manual_review_schema import RULES

SAMPLE = Path("news_collection/manual_review_sample.csv")
KAPPA_SUBSET = Path("news_collection/manual_review_kappa_subset.csv")

# Below this, kappa is not considered evidence the codebook is ready to
# freeze (news_protocol/eligibility_manual_review_methodology.md) -
# used only for the human-readable verdict this script prints, not
# enforced as a hard gate in code.
KAPPA_ACCEPTABLE = 0.60


def load_csv(path):
    return list(csv.DictReader(path.open())) if path.exists() else []


def cohens_kappa(pairs):
    """pairs: list of (rater1_label, rater2_label) tuples, already
    filtered to fully-answered rows. Returns (po, pe, kappa) or None if
    there are too few pairs, or only one category was ever used (kappa
    is undefined when pe == 1, i.e. no variation to explain)."""
    n = len(pairs)
    if n == 0:
        return None
    categories = sorted({c for pair in pairs for c in pair})
    r1_counts = {c: 0 for c in categories}
    r2_counts = {c: 0 for c in categories}
    agree = 0
    for a, b in pairs:
        r1_counts[a] += 1
        r2_counts[b] += 1
        if a == b:
            agree += 1
    po = agree / n
    pe = sum((r1_counts[c] / n) * (r2_counts[c] / n) for c in categories)
    if pe >= 1.0:
        return po, pe, None
    kappa = (po - pe) / (1 - pe)
    return po, pe, kappa


def compare_round(initial_by_id, recheck_by_id, field):
    pairs = []
    skipped_unanswered = 0
    for aid, recheck_row in recheck_by_id.items():
        initial_row = initial_by_id.get(aid)
        if initial_row is None:
            continue
        a, b = initial_row.get(field), recheck_row.get(field)
        if not a or not b:
            skipped_unanswered += 1
            continue
        pairs.append((a, b))
    return pairs, skipped_unanswered


def main():
    initial_rows = {r["article_id"]: r for r in load_csv(SAMPLE)
                    if r["review_round"] == "initial"}
    recheck_rows = {r["article_id"]: r for r in load_csv(KAPPA_SUBSET)
                    if r["review_round"] == "kappa_blind_recheck"}

    if not recheck_rows:
        print(f"No rows in {KAPPA_SUBSET} yet - nothing to compare. Fill "
             "in the blind recheck round first (see module docstring).")
        return

    print(f"Comparing {len(recheck_rows)} articles' initial vs. blind "
         "recheck decisions\n")

    any_computed = False
    for rule in (*RULES, "overall"):
        field = "final_reviewed_decision" if rule == "overall" \
            else f"{rule.lower()}_decision"
        pairs, skipped = compare_round(initial_rows, recheck_rows, field)
        label = "OVERALL" if rule == "overall" else rule
        if not pairs:
            print(f"{label}: no fully-answered pairs yet "
                 f"({skipped} skipped as unanswered)")
            continue
        result = cohens_kappa(pairs)
        po, pe, kappa = result
        any_computed = True
        if kappa is None:
            print(f"{label}: {len(pairs)} pairs, percent agreement="
                 f"{po:.1%} (kappa undefined - every decision was the "
                 "same category, so chance-agreement is 100%)")
        else:
            verdict = ("ACCEPTABLE" if kappa >= KAPPA_ACCEPTABLE
                      else "BELOW THRESHOLD - codebook needs revision "
                           "before full-corpus review")
            print(f"{label}: {len(pairs)} pairs, percent agreement="
                 f"{po:.1%}, Cohen's kappa={kappa:.3f} [{verdict}]")
        if skipped:
            print(f"  ({skipped} of {len(pairs) + skipped} article(s) "
                 "still missing an answer in one round or the other)")

    if not any_computed:
        print("\nNothing computable yet - both review rounds need at "
             "least some completed, matching decisions.")


if __name__ == "__main__":
    main()
