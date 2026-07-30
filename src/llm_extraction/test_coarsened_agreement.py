"""Phase 6 / D4 addendum - test whether the four failing fields reach the
gate at a coarser granularity, before accepting their exclusion.

Why this exists. Dropping stance, framing, consequence and horizon
removes the tonal and mechanism signals the news question is largely
about, so a later null result could not be told apart from "the retained
features were too thin to show anything". Content analysis has a standard
answer when fine-grained coding fails reliability: coarsen the scheme and
re-test. That costs nothing here - the model outputs and the human labels
already exist, so no re-labelling and no API spend.

Discipline. ONE coarsening per field, defined by what the modelling
actually needs rather than by which partition scores best. Sweeping every
possible collapse and keeping the winner would manufacture a pass. Each
mapping below is stated with its modelling rationale, and the fact that
these were written after seeing the fine-grained failures is disclosed
here rather than hidden - which is why a pass at this level is reported
as "adopted at coarse granularity", never as if the original field had
passed.

Usage:
    python3 -m src.llm_extraction.test_coarsened_agreement [arm]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.compare_d4_agreement import (PARTIES, extract_model_fields,
                                                     judge)

HUMAN = Path("llm_context/d4_human_labels_v1.csv")
ARM = sys.argv[1] if len(sys.argv) > 1 else "haiku"
SUFFIX = "" if ARM == "sonnet" else f"_{ARM}"
LLM = Path(f"llm_context/d4_llm_outputs{SUFFIX}.json")
OUT_JSON = Path(f"llm_context/d4_coarsened_agreement{SUFFIX}.json")
OUT_MD = Path(f"llm_context/d4_coarsened_agreement{SUFFIX}.md")

# --- stance: the modelling wants negative coverage counts per party, so
# the question that matters is whether the article is hostile to a party,
# not whether the remainder is warm or merely factual.
STANCE_COARSE = {
    "negative": "negative",
    "mixed": "negative",        # mixed carries a negative component
    "positive": "not_negative",
    "neutral": "not_negative",
    "not_mentioned": "not_negative",
}

# --- consequence: the modelling wants a count of articles carrying any
# electoral implication. Direction at four levels is finer than any
# feature would use.
CONSEQUENCE_COARSE = {
    "potential_damage": "has_implication",
    "potential_benefit": "has_implication",
    "mixed_impact": "has_implication",
    "unclear": "has_implication",
    "none": "no_implication",
}

# --- horizon: the six news windows already carry timing. What horizon
# could add beyond them is whether an effect is transient or structural.
HORIZON_COARSE = {
    "immediate": "transient",
    "short_term": "transient",
    "medium_term": "persistent",
    "long_term": "persistent",
    "mixed": "persistent",
    "uncertain": "uncertain",
}

# --- framing: sixteen categories is far finer than a feature needs. The
# grouping follows the three mechanisms the research question names -
# how the incumbent administration is judged, how the contest itself is
# portrayed, and local consequences.
FRAME_COARSE = {
    "government_performance": "incumbent_judgement",
    "governance_failure": "incumbent_judgement",
    "financial_pressure": "incumbent_judgement",
    "public_service_quality": "incumbent_judgement",
    "accountability": "incumbent_judgement",
    "competence": "incumbent_judgement",
    "integrity": "incumbent_judgement",
    "leadership": "incumbent_judgement",
    "electoral_competition": "contest",
    "challenger_emergence": "contest",
    "anti_incumbent_sentiment": "contest",
    "voter_dissatisfaction": "contest",
    "national_political_momentum": "contest",
    "policy_conflict": "local_impact",
    "local_community_impact": "local_impact",
    "other": "other",
    "none": "other",
}


def main() -> None:
    human = {r["article_id"]: r for r in csv.DictReader(HUMAN.open())}
    llm = json.loads(LLM.read_text())
    model, _failures = extract_model_fields(llm)

    report: dict = {"arm": ARM, "model": llm.get("model"),
                    "note": ("one pre-stated coarsening per field, chosen "
                             "for what the modelling needs, applied after "
                             "the fine-grained gate failed - disclosed"),
                    "fields": {}}

    def scalar(field, mapping):
        pairs = []
        for aid, h in human.items():
            m = model.get(aid, {})
            if field not in m:
                continue
            hv, mv = h[field], m[field]
            if hv not in mapping or mv not in mapping:
                continue
            pairs.append((mapping[hv], mapping[mv]))
        return pairs

    report["fields"]["frame_category__grouped"] = judge(
        scalar("frame_category", FRAME_COARSE))
    report["fields"]["consequence_direction__binary"] = judge(
        scalar("consequence_direction", CONSEQUENCE_COARSE))
    report["fields"]["impact_horizon__binary"] = judge(
        scalar("impact_horizon", HORIZON_COARSE))

    # stance: same union rule as the fine-grained gate - only pairs where
    # at least one side is negative under the coarse mapping, since
    # all-not_negative pairs are trivial agreement.
    pairs = []
    for aid, h in human.items():
        m = model.get(aid, {})
        for party in PARTIES:
            f = f"stance_{party}"
            if f not in m:
                continue
            hv, mv = STANCE_COARSE.get(h[f]), STANCE_COARSE.get(m[f])
            if hv is None or mv is None:
                continue
            if hv == "negative" or mv == "negative":
                pairs.append((hv, mv))
    report["fields"]["stance_negative__binary"] = judge(pairs)

    report["adopted_at_coarse_granularity"] = [
        f for f, r in report["fields"].items() if r["passes"]]
    report["still_failing"] = [
        f for f, r in report["fields"].items() if not r["passes"]]

    OUT_JSON.write_text(json.dumps(report, indent=2))
    lines = [f"# Coarsened-granularity re-test ({ARM})", "",
             f"Model: {report['model']}", "",
             "| coarsened field | pairs | agreement | kappa | AC1 | verdict |",
             "|---|---|---|---|---|---|"]
    for f, r in report["fields"].items():
        lines.append(f"| {f} | {r['pairs']} | {r.get('percent_agreement')} "
                     f"| {r.get('kappa')} | {r.get('ac1')} | {r['verdict']} |")
    lines += ["",
              f"Adopted at coarse granularity: "
              f"{report['adopted_at_coarse_granularity'] or 'none'}",
              f"Still failing: {report['still_failing'] or 'none'}"]
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
