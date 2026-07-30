"""Score the revised stance layer: inter-model first, human as reference.

The primary criterion is agreement between the two model arms, for the
reason set out in section 3b of `d4_gate_outcome_and_decisions.md`: the
D4 human labels were single-pass, never checked for reproducibility, and
- for stance specifically - were collected under an instruction that
contradicted the extraction prompt outright. They cannot arbitrate a
layer whose whole purpose is to fix that contradiction.

The human comparison is still computed and reported, mapped onto the
revised three-value vocabulary, because a layer that is reproducible but
measures something no human recognises would be a different problem worth
seeing. It is a reference, not the gate.

Mapping the old human labels onto the new vocabulary
----------------------------------------------------
    negative        -> unfavourable
    positive        -> favourable
    mixed           -> dropped, not mapped
    neutral         -> neither
    not_mentioned   -> dropped, not mapped

`mixed` is dropped rather than assigned a direction because the whole
point of removing it was that a recorded `mixed` does not say which
direction predominated - inventing one now would be exactly the
after-the-fact repair the coarsening test already showed to be
impossible. `not_mentioned` is dropped because the revised layer never
asks about a party the article does not name, so those pairs have no
counterpart on the model side. Both drops shrink the human comparison and
are reported with their counts.

Usage:
    python3 -m src.llm_extraction.compare_stance_rescue
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.compare_d4_agreement import judge

SONNET = Path("llm_context/stance_rescue_outputs.json")
HAIKU = Path("llm_context/stance_rescue_outputs_haiku.json")
HUMAN = Path("llm_context/d4_human_labels_v1.csv")
OUT_JSON = Path("llm_context/stance_rescue_agreement.json")
OUT_MD = Path("llm_context/stance_rescue_agreement.md")

HUMAN_TO_REVISED = {
    "negative": "unfavourable",
    "positive": "favourable",
    "neutral": "neither",
    # "mixed" and "not_mentioned" are intentionally absent - see the
    # module docstring. A KeyError here would be a silent mapping bug, so
    # the lookups below use .get and count the misses.
}


def load_arm(path: Path) -> dict[str, dict[str, str]]:
    """article_id -> {party: portrayal}, clean rows only.

    A row with validation errors is excluded rather than partially used:
    a model that answered about the wrong parties has not answered the
    question that was asked, and scoring the overlap would credit it for
    the part it happened to get right.
    """
    data = json.loads(path.read_text())
    out: dict[str, dict[str, str]] = {}
    for row in data["results"]:
        if row.get("judgements") and not row.get("validation_errors"):
            out[row["article_id"]] = row["judgements"]
    return out


def main() -> None:
    a, b = load_arm(SONNET), load_arm(HAIKU)
    shared = sorted(set(a) & set(b))

    report: dict = {
        "arm_a": "claude-sonnet-5", "arm_b": "claude-haiku-4-5",
        "articles_clean_in_both": len(shared),
        "articles_clean_sonnet_only": sorted(set(a) - set(b)),
        "articles_clean_haiku_only": sorted(set(b) - set(a)),
    }

    # --- primary: inter-model reliability on the revised vocabulary -----
    inter, per_party_inter = [], {}
    for aid in shared:
        # The question sets are fixed by code, so the two arms should
        # cover identical parties for an article. Any mismatch means one
        # arm went off-question; it is recorded rather than intersected
        # away, because it would be a failure of the very fix this layer
        # introduces.
        if set(a[aid]) != set(b[aid]):
            report.setdefault("question_set_mismatches", []).append(aid)
            continue
        for party in sorted(a[aid]):
            pair = (a[aid][party], b[aid][party])
            inter.append(pair)
            per_party_inter.setdefault(party, []).append(pair)

    report["inter_model"] = judge(inter)
    report["inter_model"]["per_party"] = {
        p: judge(v) for p, v in sorted(per_party_inter.items())}

    # --- reference: each arm against the mapped human labels -----------
    human = {r["article_id"]: r for r in csv.DictReader(HUMAN.open())}
    for name, arm in (("sonnet", a), ("haiku", b)):
        pairs, dropped = [], {"mixed": 0, "not_mentioned": 0, "absent": 0}
        for aid, judged in arm.items():
            h = human.get(aid)
            if h is None:
                dropped["absent"] += 1
                continue
            for party, model_value in judged.items():
                raw = h.get(f"stance_{party}")
                if raw in ("mixed", "not_mentioned"):
                    dropped[raw] += 1
                    continue
                mapped = HUMAN_TO_REVISED.get(raw)
                if mapped is None:
                    dropped["absent"] += 1
                    continue
                pairs.append((mapped, model_value))
        result = judge(pairs)
        result["human_pairs_dropped"] = dropped
        report[f"vs_human_{name}"] = result

    gate_pass = report["inter_model"]["passes"]
    report["verdict"] = (
        "stance recovered at reduced granularity under the revised layer"
        if gate_pass else
        "stance remains unrecoverable - the revised layer did not reach the "
        "gate either, so the exclusion stands on four independent attempts")

    OUT_JSON.write_text(json.dumps(report, indent=2))

    lines = ["# Revised stance layer - agreement report", "",
             f"Articles clean in both arms: "
             f"{report['articles_clean_in_both']}", "",
             "## Primary criterion: inter-model reliability", "",
             "| comparison | pairs | agreement | kappa | AC1 | verdict |",
             "|---|---|---|---|---|---|"]
    im = report["inter_model"]
    lines.append(f"| Sonnet vs Haiku | {im['pairs']} "
                 f"| {im.get('percent_agreement')} | {im.get('kappa')} "
                 f"| {im.get('ac1')} | {im['verdict']} |")
    for p, r in im["per_party"].items():
        lines.append(f"| &nbsp;&nbsp;{p} | {r['pairs']} "
                     f"| {r.get('percent_agreement')} | {r.get('kappa')} "
                     f"| {r.get('ac1')} | {r['verdict']} |")
    lines += ["", "## Reference: against the mapped human labels", "",
              "| arm | pairs | agreement | kappa | AC1 |",
              "|---|---|---|---|---|"]
    for name in ("sonnet", "haiku"):
        r = report[f"vs_human_{name}"]
        lines.append(f"| {name} | {r['pairs']} | {r.get('percent_agreement')} "
                     f"| {r.get('kappa')} | {r.get('ac1')} |")
    lines += ["", f"**{report['verdict']}**"]
    if report.get("question_set_mismatches"):
        lines += ["", f"Question-set mismatches (excluded): "
                      f"{report['question_set_mismatches']}"]
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
