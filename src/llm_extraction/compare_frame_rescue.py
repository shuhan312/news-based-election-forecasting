"""Score the revised framing layer: inter-model first, human as reference.

Same criterion hierarchy as the stance rescue, for the same reason: the D4
human labels were single-pass and never checked for reproducibility, so
inter-model agreement is the primary gate and the human comparison is a
reference that shows whether the layer measures something a person
recognises.

Mapping the old human labels onto four binary frames
----------------------------------------------------
The reviewer recorded ONE `frame_category` per article, from sixteen. This
layer asks four independent yes/no questions. The two cannot be compared
symmetrically, and pretending otherwise would invent agreement:

* A human label of `governance_failure` says `incumbent_judgement` is
  present. It says **nothing** about whether `voter_discontent` is also
  present, because the reviewer was never asked - they were choosing one
  winner from sixteen.
* So the human comparison is restricted to **the frame the human's label
  maps to**, scored as "the model also says present: yes/no". Positive
  agreement only.

That is a weaker test than the inter-model one and is reported as such. It
can detect a model that misses frames a human saw; it cannot detect a model
that reports frames a human would have rejected, because the human data
simply does not contain those judgements. The asymmetry is a limit of the
original labels, not of this layer, and the honest response is to say so
rather than to construct a symmetric-looking number from data that cannot
support one.

Usage:
    python3 -m src.llm_extraction.compare_frame_rescue
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.compare_d4_agreement import judge
from src.llm_extraction.frame_rescue import FRAMES

SONNET = Path("llm_context/frame_rescue_outputs.json")
HAIKU = Path("llm_context/frame_rescue_outputs_haiku.json")
HUMAN = Path("llm_context/d4_human_labels_v1.csv")
OUT_JSON = Path("llm_context/frame_rescue_agreement.json")
OUT_MD = Path("llm_context/frame_rescue_agreement.md")

# Which of the four frames each original sixteen-way category implies. Used
# for the one-sided human reference only. The four categories absent here
# (`other`, `none`, and the genre-like ones) map to no frame and are
# dropped with a count.
HUMAN_LABEL_TO_FRAME = {
    "government_performance": "incumbent_judgement",
    "governance_failure": "incumbent_judgement",
    "financial_pressure": "incumbent_judgement",
    "public_service_quality": "incumbent_judgement",
    "accountability": "incumbent_judgement",
    "competence": "incumbent_judgement",
    "integrity": "incumbent_judgement",
    "leadership": "incumbent_judgement",
    "challenger_emergence": "challenger_emergence",
    "electoral_competition": "challenger_emergence",
    "national_political_momentum": "challenger_emergence",
    "anti_incumbent_sentiment": "voter_discontent",
    "voter_dissatisfaction": "voter_discontent",
    "local_community_impact": "local_impact",
    "policy_conflict": "local_impact",
}


def load_arm(path: Path) -> dict[str, dict[str, bool]]:
    """article_id -> {frame: present}, clean rows only."""
    data = json.loads(path.read_text())
    return {r["article_id"]: r["frames"] for r in data["results"]
            if r.get("frames") and not r.get("validation_errors")}


def main() -> None:
    a, b = load_arm(SONNET), load_arm(HAIKU)
    shared = sorted(set(a) & set(b))

    report: dict = {
        "arm_a": "claude-sonnet-5", "arm_b": "claude-haiku-4-5",
        "articles_clean_in_both": len(shared),
        "articles_clean_sonnet_only": sorted(set(a) - set(b)),
        "articles_clean_haiku_only": sorted(set(b) - set(a)),
    }

    # --- primary: inter-model reliability -------------------------------
    # Booleans are rendered as strings because the kappa helper builds its
    # category set from the label values, and "present"/"absent" reads
    # correctly in the output where True/False would not.
    def label(v: bool) -> str:
        return "present" if v else "absent"

    pooled, per_frame = [], {}
    for aid in shared:
        for frame in FRAMES:
            pair = (label(a[aid][frame]), label(b[aid][frame]))
            pooled.append(pair)
            per_frame.setdefault(frame, []).append(pair)

    report["inter_model_pooled"] = judge(pooled)
    report["inter_model_per_frame"] = {f: judge(v)
                                       for f, v in per_frame.items()}

    # A binary frame's agreement is only testable on the articles where at
    # least one arm says present. A frame detected in 2 of 55 articles
    # produces 53 trivial "both say absent" agreements, which carry the
    # percent-agreement figure to 0.95 and leave the actual judgement
    # resting on single digits - and the AC1 fallback, designed for
    # prevalence-skewed but genuinely tested fields, will pass it. That is
    # the same overstatement the reform_uk sub-fields were protected from
    # with a 20-pair minimum, so the same discipline applies here in the
    # form appropriate to a binary field: a minimum number of POSITIVE
    # cases, on both arms.
    #
    # Ten is the threshold. Below it a single disagreement moves kappa by
    # more than a tenth, so no verdict either way is informative. The rule
    # was written after seeing the prevalence counts; that ordering is
    # disclosed rather than hidden, and it is applied uniformly to all four
    # frames rather than to the ones that happen to fail it.
    MIN_POSITIVES_PER_ARM = 10
    for frame, result in report["inter_model_per_frame"].items():
        pos_a = sum(1 for aid in shared if a[aid][frame])
        pos_b = sum(1 for aid in shared if b[aid][frame])
        result["positive_cases"] = {"sonnet": pos_a, "haiku": pos_b}
        result["union_positive_cases"] = sum(
            1 for aid in shared if a[aid][frame] or b[aid][frame])
        if min(pos_a, pos_b) < MIN_POSITIVES_PER_ARM:
            result["verdict"] = (
                f"undetermined - {min(pos_a, pos_b)} positive cases on the "
                f"thinner arm, below the {MIN_POSITIVES_PER_ARM}-case minimum; "
                f"the agreement figure is carried by articles where both arms "
                f"say absent")
            result["passes"] = False
            result["undetermined"] = True
    # Pooling four frames treats each (article, frame) cell as one unit,
    # which is the right base rate question for a feature built by counting
    # cells. The per-frame breakdown is reported alongside because a pooled
    # pass can hide one frame that nobody agrees on, and a feature built on
    # that frame would be noise even if the pool looks healthy.


    # --- reference: one-sided against the human's single label ---------
    human = {r["article_id"]: r for r in csv.DictReader(HUMAN.open())}
    for name, arm in (("sonnet", a), ("haiku", b)):
        hits = misses = unmappable = absent = 0
        detail = {}
        for aid, frames in arm.items():
            h = human.get(aid)
            if h is None:
                absent += 1
                continue
            mapped = HUMAN_LABEL_TO_FRAME.get(h.get("frame_category"))
            if mapped is None:
                unmappable += 1
                continue
            if frames.get(mapped):
                hits += 1
                detail.setdefault(mapped, {"hit": 0, "miss": 0})["hit"] += 1
            else:
                misses += 1
                detail.setdefault(mapped, {"hit": 0, "miss": 0})["miss"] += 1
        scored = hits + misses
        report[f"vs_human_{name}"] = {
            "test": ("one-sided: does the model also mark present the frame "
                     "the human's single label implies"),
            "scored": scored,
            "model_agrees": hits,
            "model_says_absent": misses,
            "recall_of_human_frame": round(hits / scored, 3) if scored else None,
            "human_labels_unmappable_to_any_frame": unmappable,
            "articles_not_in_human_labels": absent,
            "by_frame": detail,
        }

    adopted = [f for f, r in report["inter_model_per_frame"].items()
               if r["passes"]]
    undetermined = [f for f, r in report["inter_model_per_frame"].items()
                    if r.get("undetermined")]
    failed = [f for f, r in report["inter_model_per_frame"].items()
              if not r["passes"] and not r.get("undetermined")]
    report["adopted_frames"] = adopted
    report["undetermined_frames"] = undetermined
    report["failed_frames"] = failed
    report["verdict"] = (
        f"framing partially recovered: {len(adopted)} of {len(FRAMES)} frames "
        f"adopted as binary presence indicators ({', '.join(adopted)}); "
        f"{len(undetermined)} undetermined on too few positive cases "
        f"({', '.join(undetermined) or 'none'}); "
        f"{len(failed)} failed ({', '.join(failed) or 'none'})"
        if adopted else
        "framing remains unrecoverable - excluded on three independent "
        "attempts (original, coarsened, this redesign; two arms each)")

    OUT_JSON.write_text(json.dumps(report, indent=2))

    lines = ["# Revised framing layer - agreement report", "",
             f"Articles clean in both arms: "
             f"{report['articles_clean_in_both']}", "",
             "## Primary criterion: inter-model reliability", "",
             "| comparison | pairs | agreement | kappa | AC1 | verdict |",
             "|---|---|---|---|---|---|"]
    p = report["inter_model_pooled"]
    lines.append(f"| pooled over four frames | {p['pairs']} "
                 f"| {p.get('percent_agreement')} | {p.get('kappa')} "
                 f"| {p.get('ac1')} | {p['verdict']} |")
    for f, r in report["inter_model_per_frame"].items():
        lines.append(f"| &nbsp;&nbsp;{f} | {r['pairs']} "
                     f"| {r.get('percent_agreement')} | {r.get('kappa')} "
                     f"| {r.get('ac1')} | {r['verdict']} |")
    lines += ["", "## Reference: one-sided recall of the human's frame", "",
              "Weaker by construction - the reviewer picked one frame from "
              "sixteen, so the labels cannot say whether a frame the model "
              "reports would have been rejected.", "",
              "| arm | scored | agrees | says absent | recall |",
              "|---|---|---|---|---|"]
    for name in ("sonnet", "haiku"):
        r = report[f"vs_human_{name}"]
        lines.append(f"| {name} | {r['scored']} | {r['model_agrees']} "
                     f"| {r['model_says_absent']} "
                     f"| {r['recall_of_human_frame']} |")
    lines += ["", f"**{report['verdict']}**"]
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
