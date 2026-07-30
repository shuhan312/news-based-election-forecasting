"""Scores the revised attribution layer against the human gold labels.

Applies the rule declared in `attribution_rescue`'s docstring before the batch
was submitted, and nothing else. Each binary is judged on its own, as the four
framing frames were; the human's `unclear` labels are excluded from both
because they record that an attribution exists whose direction is not
determinable; and a binary with fewer than ten human positives is reported
undetermined rather than failed.

Reported alongside each figure: the same binary derived from the *frozen*
layer's output, so the before-and-after sits on one denominator. That
derivation is what diagnosed the layer in the first place - it showed blame at
0.564 and credit at 0.181 where the five-way field reported one number, 0.521,
for both.

Usage:
    python3 -m src.llm_extraction.compare_attribution_rescue
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.compare_d4_agreement import extract_model_fields
from src.news_collection.compute_review_agreement import (cohens_kappa,
                                                          gwet_ac1)

HUMAN = Path("llm_context/d4_human_labels_v1.csv")
ARM_OUTPUTS = {
    "sonnet": Path("llm_context/attribution_rescue_outputs.json"),
    "haiku": Path("llm_context/attribution_rescue_outputs_haiku.json"),
}
FROZEN_OUTPUTS = {
    "sonnet": Path("llm_context/d4_llm_outputs.json"),
    "haiku": Path("llm_context/d4_llm_outputs_haiku.json"),
}
OUT_JSON = Path("llm_context/attribution_rescue_agreement.json")

GATE = 0.60
SKEW_TRIGGER = 0.90
FALLBACK_AGREEMENT = 0.80
MIN_POSITIVES = 10

# The human mapping, from the pre-statement. `mixed` is positive for both
# binaries - that is the whole point of splitting the field, since a single
# attribution carrying both directions is exactly two positives. `unclear` is
# excluded from both: the reviewer recorded that an attribution exists but its
# direction is not determinable, which is not an answer either binary can be
# paired against.
HUMAN_POSITIVE = {"blame": {"blame", "mixed"}, "credit": {"credit", "mixed"}}
HUMAN_EXCLUDED = {"unclear"}
DIRECTIONS = ("blame", "credit")


def judge(pairs: list[tuple[str, str]], *, positives: int) -> dict:
    """The pre-registered gate, plus the framing rescue's positive minimum."""
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
    out = {"pairs": n, "human_positives": positives,
           "percent_agreement": round(agree, 3),
           "kappa": None if kappa is None else round(kappa, 3),
           "ac1": None if ac1 is None else round(ac1, 3),
           "max_marginal": round(max(marginals), 3), "skew_trigger": skewed}
    if positives < MIN_POSITIVES:
        # Not a failure. Below this many positives a single disagreement moves
        # kappa by more than a tenth, so the figure is not a verdict either
        # way. Same minimum, same reasoning, as the framing rescue.
        out.update(verdict=f"undetermined_insufficient_positives "
                           f"({positives} < {MIN_POSITIVES})", passes=False,
                   undetermined=True)
    elif kappa is not None and kappa >= GATE:
        out.update(verdict="passes (primary kappa)", passes=True,
                   undetermined=False)
    elif skewed and ac1 is not None and ac1 >= GATE \
            and agree >= FALLBACK_AGREEMENT:
        out.update(verdict="passes (fallback AC1, skew trigger met)",
                   passes=True, undetermined=False)
    else:
        out.update(verdict="fails", passes=False, undetermined=False)
    return out


def _pairs(human: dict, present: dict, direction: str) -> tuple[list, int]:
    """Paired binaries for one direction, and the human positive count."""
    pairs, positives = [], 0
    for aid, h in human.items():
        if h in HUMAN_EXCLUDED or aid not in present:
            continue
        hp = h in HUMAN_POSITIVE[direction]
        positives += hp
        pairs.append(("yes" if hp else "no",
                      "yes" if present[aid][direction] else "no"))
    return pairs, positives


def revised_present(path: Path) -> dict[str, dict[str, bool]]:
    """Article id to both binaries, for records the validator accepted."""
    d = json.loads(path.read_text())
    return {r["article_id"]: r["attributions"] for r in d["results"]
            if r.get("attributions") and not r.get("validation_errors")}


def frozen_present(path: Path) -> dict[str, dict[str, bool]]:
    """The same two binaries derived from the frozen layer's own output.

    Read off `attribution_type_set`, the set of every type the model used on
    that article, so `mixed` counts as both directions exactly as it does on
    the human side. This is the derivation that diagnosed the layer, and it is
    reported here as the before figure rather than described.
    """
    model, _failures = extract_model_fields(json.loads(path.read_text()))
    out = {}
    for aid, fields in model.items():
        s = fields.get("attribution_type_set")
        if s is None:
            continue
        out[aid] = {"blame": bool({"blame", "mixed"} & s),
                    "credit": bool({"credit", "mixed"} & s)}
    return out


def main() -> None:
    human = {r["article_id"]: r["attribution_type"]
             for r in csv.DictReader(HUMAN.open())}
    report: dict = {
        "gate": {"primary": f"kappa >= {GATE}",
                 "fallback": (f"AC1 >= {GATE} and agreement >= "
                              f"{FALLBACK_AGREEMENT} when a marginal >= "
                              f"{SKEW_TRIGGER}"),
                 "minimum_human_positives": MIN_POSITIVES},
        "scoring_rule": ("declared in attribution_rescue's docstring before "
                         "submission: each binary judged alone, human mixed "
                         "positive for both, human unclear excluded from "
                         "both, under-10-positive binaries undetermined"),
        "arms": {}}

    revised: dict[str, dict] = {}
    for arm, path in ARM_OUTPUTS.items():
        if not path.exists():
            report["arms"][arm] = {"error": f"{path} not collected yet"}
            continue
        present = revised_present(path)
        revised[arm] = present
        raw = json.loads(path.read_text())
        frozen = frozen_present(FROZEN_OUTPUTS[arm])

        entry: dict = {
            "model": raw["model"],
            "records_accepted": len(present),
            "records_total": raw["articles_total"],
            "validator_rejected": raw["articles_total"] - raw["articles_ok"],
            "human_excluded_unclear": sum(1 for h in human.values()
                                          if h in HUMAN_EXCLUDED),
            "usage": raw["usage"], "binaries": {}}
        for d in DIRECTIONS:
            p, pos = _pairs(human, present, d)
            fp, fpos = _pairs(human, frozen, d)
            entry["binaries"][d] = {
                "revised": judge(p, positives=pos),
                "frozen_same_test": judge(fp, positives=fpos),
                "model_positives": sum(1 for _h, m in p if m == "yes"),
            }
        report["arms"][arm] = entry

    if len(revised) == 2:
        shared = sorted(set(revised["sonnet"]) & set(revised["haiku"]))
        report["inter_model"] = {"shared_articles": len(shared), "binaries": {}}
        for d in DIRECTIONS:
            pairs = [("yes" if revised["sonnet"][a][d] else "no",
                      "yes" if revised["haiku"][a][d] else "no")
                     for a in shared]
            report["inter_model"]["binaries"][d] = judge(
                pairs, positives=MIN_POSITIVES)  # minimum n/a between arms

    passing = {d: [a for a, v in report["arms"].items()
                   if v.get("binaries", {}).get(d, {}).get("revised", {})
                   .get("passes")]
               for d in DIRECTIONS}
    scored = [a for a, v in report["arms"].items() if "error" not in v]
    if not scored:
        report["verdict"] = "NOT SCORED - no arm collected yet"
        report["overall_pass"] = None
    else:
        won = [d for d in DIRECTIONS if passing[d]]
        recovered = []
        if "blame" in won:
            recovered += ["blame_count", "recency_weighted_blame"]
        if "credit" in won:
            recovered += ["credit_count"]
        if len(won) == 2:
            recovered += ["net_attribution"]
        report["features_recovered"] = recovered
        report["verdict"] = (
            f"{', '.join(won)} clears on {', '.join(passing[won[0]])}; "
            f"recovers {len(recovered)} of 4 features: {recovered}" if won
            else "NEITHER binary clears - the layer is dropped. Per the "
                 "pre-statement no further scoring variant is tried")
        report["overall_pass"] = bool(won)

    OUT_JSON.write_text(json.dumps(report, indent=2))

    print("# Attribution rescue vs human gold labels\n")
    print("| arm | binary | n | human pos | model pos | revised kappa "
          "| frozen kappa | verdict |")
    print("|---|---|---|---|---|---|---|---|")
    for arm, v in report["arms"].items():
        if "error" in v:
            print(f"| {arm} | - | - | - | - | {v['error']} | | |")
            continue
        for d, b in v["binaries"].items():
            r, f = b["revised"], b["frozen_same_test"]
            print(f"| {arm} | {d} | {r['pairs']} | {r['human_positives']} "
                  f"| {b['model_positives']} | **{r['kappa']}** "
                  f"| {f['kappa']} | {r['verdict']} |")
    if "inter_model" in report:
        for d, b in report["inter_model"]["binaries"].items():
            print(f"\ninter-model {d}: kappa {b['kappa']} on "
                  f"{report['inter_model']['shared_articles']} shared")
    print(f"\n**{report['verdict']}**")
    print(f"-> {OUT_JSON}")


if __name__ == "__main__":
    main()
