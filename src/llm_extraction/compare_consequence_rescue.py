"""Scores the revised consequence layer against the human gold labels.

Applies the rule declared in `consequence_rescue`'s docstring before the
batch was submitted, and nothing else. The frozen layer's verdict moved three
times under successive scoring corrections - validator gating, set membership,
positional pairing - each of which was a real fault, but the pattern is one to
break rather than extend. So the primary test here is the presence binary the
diagnosis identified, the secondary test is direction on the articles both
sides call present, and no third scoring variant is computed.

Reported alongside:

* the frozen layer's figures on the same articles, so the before-and-after is
  on one denominator rather than two;
* inter-model agreement, which is what made the diagnosis in the first place.
  If the revised layer still disagrees with the human while the two models
  agree closely with each other, the honest reading is that the human's
  threshold differs from both models' - not that the model is wrong - and the
  layer is still unusable, because a construct neither side can be shown to
  measure the same way cannot carry a feature.

Usage:
    python3 -m src.llm_extraction.compare_consequence_rescue
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.news_collection.compute_review_agreement import (cohens_kappa,
                                                          gwet_ac1)

HUMAN = Path("llm_context/d4_human_labels_v1.csv")
ARM_OUTPUTS = {
    "sonnet": Path("llm_context/consequence_rescue_outputs.json"),
    "haiku": Path("llm_context/consequence_rescue_outputs_haiku.json"),
}
FROZEN_OUTPUTS = {
    "sonnet": Path("llm_context/d4_llm_outputs.json"),
    "haiku": Path("llm_context/d4_llm_outputs_haiku.json"),
}
OUT_JSON = Path("llm_context/consequence_rescue_agreement.json")

GATE = 0.60
SKEW_TRIGGER = 0.90
FALLBACK_AGREEMENT = 0.80

# The presence mapping, from the pre-statement. Every human value other than
# "none" asserts that a consequence exists, whatever its direction or however
# uncertain the reviewer was about it.
HUMAN_ABSENT = "none"
# Human values with no counterpart in the revised three-value vocabulary.
# Excluded from the direction test only, never from the presence test - they
# are unambiguous about presence, which is what the primary test measures.
NO_DIRECTION = {"mixed_impact", "unclear"}
HUMAN_DIRECTION = {"potential_damage": "damage",
                   "potential_benefit": "benefit"}


def judge(pairs: list[tuple[str, str]]) -> dict:
    """The pre-registered two-route gate, unchanged from the D4 comparer."""
    n = len(pairs)
    if n == 0:
        return {"pairs": 0, "verdict": "NO_PAIRS", "passes": False}
    agree = sum(1 for a, b in pairs if a == b) / n
    k_res = cohens_kappa(pairs)
    kappa = k_res[2] if k_res else None
    a_res = gwet_ac1(pairs)
    ac1 = a_res[2] if a_res else None
    marginals = [max(Counter(p[s] for p in pairs).values()) / n
                 for s in (0, 1)]
    skewed = max(marginals) >= SKEW_TRIGGER
    if kappa is not None and kappa >= GATE:
        verdict, passes = "passes (primary kappa)", True
    elif skewed and ac1 is not None and ac1 >= GATE \
            and agree >= FALLBACK_AGREEMENT:
        verdict, passes = "passes (fallback AC1, skew trigger met)", True
    else:
        verdict, passes = "fails", False
    return {"pairs": n, "percent_agreement": round(agree, 3),
            "kappa": None if kappa is None else round(kappa, 3),
            "ac1": None if ac1 is None else round(ac1, 3),
            "max_marginal": round(max(marginals), 3),
            "skew_trigger": skewed, "verdict": verdict, "passes": passes}


def revised_answers(path: Path) -> dict[str, str]:
    """Article id to decision, for records the validator accepted.

    Gated on `validation_errors` for the same reason the D4 comparer is: a
    record the validator rejects is discarded downstream, so scoring it
    credits the model for an answer no feature can be built from. That
    omission inflated a kappa by 0.13 earlier in this layer's history.
    """
    d = json.loads(path.read_text())
    return {r["article_id"]: r["decision"] for r in d["results"]
            if r.get("decision") and not r.get("validation_errors")}


def frozen_answers(path: Path) -> dict[str, str]:
    """The frozen layer's per-article direction, on the same gating."""
    d = json.loads(path.read_text())
    out = {}
    for r in d["layers"]["consequence"]:
        if r.get("record") is None or r.get("validation_errors"):
            continue
        rows = r["record"].get("consequences") or []
        out[r["article_id"]] = (rows[0].get("direction")
                               if rows else "none") or "none"
    return out


def main() -> None:
    human = {r["article_id"]: r["consequence_direction"]
             for r in csv.DictReader(HUMAN.open())}
    report: dict = {
        "gate": {"primary": f"kappa >= {GATE}",
                 "fallback": (f"AC1 >= {GATE} and agreement >= "
                              f"{FALLBACK_AGREEMENT} when a marginal "
                              f">= {SKEW_TRIGGER}")},
        "scoring_rule": ("declared in consequence_rescue's docstring before "
                         "submission: presence binary is primary, direction "
                         "on jointly-present articles is secondary, no other "
                         "variant computed"),
        "arms": {}}

    revised: dict[str, dict[str, str]] = {}
    for arm, path in ARM_OUTPUTS.items():
        if not path.exists():
            report["arms"][arm] = {"error": f"{path} not collected yet"}
            continue
        model = revised_answers(path)
        revised[arm] = model
        raw = json.loads(path.read_text())

        # Both sides reduce to the same two labels, "none" and "present" -
        # kappa is computed on label identity, so the two vocabularies have to
        # coincide rather than merely correspond.
        presence = [("none" if human[a] == HUMAN_ABSENT else "present",
                     "none" if m == "none" else "present")
                    for a, m in model.items() if a in human]

        direction = [(HUMAN_DIRECTION[human[a]], m)
                     for a, m in model.items()
                     if a in human and human[a] in HUMAN_DIRECTION
                     and m != "none"]

        frozen = frozen_answers(FROZEN_OUTPUTS[arm])
        frozen_presence = [(HUMAN_ABSENT if human[a] == HUMAN_ABSENT
                            else "present",
                            "none" if f == "none" else "present")
                           for a, f in frozen.items() if a in human]

        report["arms"][arm] = {
            "model": raw["model"],
            "records_accepted": len(model),
            "records_total": raw["articles_total"],
            "validator_rejected": raw["articles_total"] - raw["articles_ok"],
            "decision_marginals": dict(Counter(model.values()).most_common()),
            "human_marginals": dict(Counter(
                human[a] for a in model if a in human).most_common()),
            "primary_presence": judge(presence),
            "secondary_direction": judge(direction),
            "direction_excluded_no_counterpart": sum(
                1 for a in model if a in human and human[a] in NO_DIRECTION),
            "frozen_presence_same_test": judge(frozen_presence),
            "usage": raw["usage"],
        }

    if len(revised) == 2:
        shared = sorted(set(revised["sonnet"]) & set(revised["haiku"]))
        report["inter_model"] = {
            "shared_articles": len(shared),
            "presence": judge([("none" if revised["sonnet"][a] == "none"
                                else "present",
                                "none" if revised["haiku"][a] == "none"
                                else "present") for a in shared]),
            "three_value": judge([(revised["sonnet"][a], revised["haiku"][a])
                                  for a in shared]),
        }

    scored = [a for a, v in report["arms"].items() if "error" not in v]
    passed = [a for a, v in report["arms"].items()
              if v.get("primary_presence", {}).get("passes")]
    # An unscored run is not a failed one. Writing "FAILS" into the record
    # before any arm has been collected would leave a file that reads as a
    # verdict when it is only a placeholder.
    if not scored:
        report["verdict"] = "NOT SCORED - no arm collected yet"
        report["overall_pass"] = None
    else:
        report["verdict"] = (
            f"PRESENCE PASSES on {', '.join(passed)} - the layer survives as "
            f"a presence indicator; direction is reported separately and "
            f"stands or falls on its own figure" if passed else
            f"PRESENCE FAILS on {', '.join(scored)} - the rescue did not "
            f"work. The layer is dropped. Per the pre-statement no further "
            f"scoring variant is tried")
        report["overall_pass"] = bool(passed)

    OUT_JSON.write_text(json.dumps(report, indent=2))

    print("# Consequence rescue vs human gold labels\n")
    print("| arm | n | presence kappa | presence agree | frozen kappa "
          "(same test) | direction kappa | n dir |")
    print("|---|---|---|---|---|---|---|")
    for arm, v in report["arms"].items():
        if "error" in v:
            print(f"| {arm} | - | {v['error']} | | | | |")
            continue
        p, f, d = (v["primary_presence"], v["frozen_presence_same_test"],
                   v["secondary_direction"])
        print(f"| {arm} | {p['pairs']} | **{p['kappa']}** "
              f"| {p['percent_agreement']} | {f['kappa']} "
              f"| {d.get('kappa')} | {d['pairs']} |")
    if "inter_model" in report:
        im = report["inter_model"]
        print(f"\ninter-model on {im['shared_articles']} shared: presence "
              f"kappa {im['presence']['kappa']}, three-value kappa "
              f"{im['three_value']['kappa']}")
    for arm, v in report["arms"].items():
        if "error" not in v:
            print(f"\n{arm} marginals - model {v['decision_marginals']}")
            print(f"{' ' * len(arm)} human {v['human_marginals']}")
    print(f"\n**{report['verdict']}**")
    print(f"-> {OUT_JSON}")


if __name__ == "__main__":
    main()
