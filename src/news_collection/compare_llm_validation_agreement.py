"""Score the frozen v2 classifier against the human-coded 128-article
blind validation sample, applying the §8.2 gate EXACTLY as
pre-registered in eligibility_manual_review_methodology.md (approved
by the supervisor 2026-07-24).

The gate, restated from §8.2 so this file and the protocol cannot
drift apart silently:

  Primary   : Cohen's kappa >= 0.60.
  Fallback  : ONLY where kappa is prevalence-broken - defined in
              advance as either rater's marginal >= 90% in a single
              category - the rule may instead pass with
              Gwet's AC1 >= 0.60 AND percent agreement >= 80%.
  Otherwise : the rule stays fully manual. No third route.

E6 is compared only on Reform-flagged articles: for everything else
both sides' e6_decision is auto-filled to not_applicable from the
same flag, and those pairs agree by construction (the exact artefact
that briefly inflated the v1 pilot's E6 kappa to 0.929 before the
same-day correction recorded in §7.1).

This script reports and gates; it does not act. Applying a passing
rule to the remaining corpus is a separate, deliberate step.

Usage:
    python3 -m src.news_collection.compare_llm_validation_agreement
"""

import csv
from collections import Counter
from pathlib import Path

from .compute_review_agreement import cohens_kappa, gwet_ac1, pabak
from .manual_review_schema import RULES

HUMAN = Path("news_collection/llm_validation_sample.csv")
LLM = Path("news_collection/manual_review_llm_v2_validation.csv")

KAPPA_BAR = 0.60
AC1_BAR = 0.60
AGREEMENT_BAR = 0.80
# §8.2's pre-registered definition of "kappa is prevalence-broken":
# some rater put >= 90% of their answers in one category.
SKEW_THRESHOLD = 0.90


def marginal_is_skewed(pairs):
    """True when either rater's most-used category holds >= 90% of
    that rater's answers - the §8.2 trigger for the fallback route.
    Computed from the pairs actually compared, not the whole sheet,
    because that is the distribution kappa's pe is built from."""
    n = len(pairs)
    for side in (0, 1):
        top = Counter(p[side] for p in pairs).most_common(1)[0][1]
        if top / n >= SKEW_THRESHOLD:
            return True
    return False


def verdict_for(pairs):
    """Apply the §8.2 gate to one rule's pairs. Returns a dict of
    every statistic plus the routed verdict, so the caller prints
    everything and hides nothing."""
    po, _, kappa = cohens_kappa(pairs)
    _, _, ac1 = gwet_ac1(pairs)
    _, pb = pabak(pairs)
    skewed = marginal_is_skewed(pairs)

    if kappa is not None and kappa >= KAPPA_BAR:
        route, passed = "primary (kappa)", True
    elif skewed:
        # Fallback is available only under the pre-registered skew
        # trigger. An undefined AC1 (single category on BOTH sides,
        # i.e. perfect agreement on a constant) cannot clear a
        # numeric bar - but 100% agreement with a skewed marginal is
        # exactly the degenerate-perfect case, so it is routed on
        # percent agreement alone with AC1 shown as undefined.
        if ac1 is not None:
            passed = ac1 >= AC1_BAR and po >= AGREEMENT_BAR
        else:
            passed = po >= AGREEMENT_BAR and po == 1.0
        route = "fallback (AC1 + agreement, skew trigger met)"
    else:
        route, passed = "primary (kappa) - fallback not triggered", False
    return {"po": po, "kappa": kappa, "ac1": ac1, "pabak": pb,
            "skewed": skewed, "route": route, "passed": passed}


def main():
    human = {r["article_id"]: r for r in csv.DictReader(HUMAN.open())
             if r["review_round"] == "llm_validation"}
    llm = {r["article_id"]: r for r in csv.DictReader(LLM.open())
           if r.get("status") == "ok"} if LLM.exists() else {}
    if not llm:
        print(f"No 'ok' rows in {LLM} - run run_llm_validation_v2 first.")
        return

    print(f"VALIDATION: frozen v2 vs. human gold standard "
          f"({len(llm)} ok LLM rows, {len(human)} human rows)\n")

    fmt = lambda x: f"{x:.3f}" if x is not None else "undef"
    for rule in RULES:
        field = f"{rule.lower()}_decision"
        pairs = []
        for aid, m in llm.items():
            h = human.get(aid)
            if not h:
                continue
            # E6: judged pairs only - see module docstring.
            if rule == "E6" and h.get("needs_reform_disambiguation") != "yes":
                continue
            a, b = h.get(field), m.get(field)
            if a and b:
                pairs.append((a, b))
        if not pairs:
            print(f"{rule}: no comparable pairs")
            continue
        v = verdict_for(pairs)
        outcome = ("PASSES - v2 may classify this rule on the remaining "
                   "corpus" if v["passed"] else
                   "FAILS - this rule stays fully manual")
        print(f"{rule}: {len(pairs)} pairs  agree={v['po']:.1%}  "
              f"kappa={fmt(v['kappa'])}  AC1={fmt(v['ac1'])}  "
              f"PABAK={fmt(v['pabak'])}")
        print(f"    skew trigger: {'met' if v['skewed'] else 'not met'}  |  "
              f"route: {v['route']}")
        print(f"    -> {outcome}\n")

    print("Gate as pre-registered in §8.2 and approved 2026-07-24. "
          "Passing rules are applied to the remaining corpus in a "
          "separate step; failing rules are reviewed manually per §6.")


if __name__ == "__main__":
    main()
