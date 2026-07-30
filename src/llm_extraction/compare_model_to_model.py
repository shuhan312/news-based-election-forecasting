"""Phase 6 / D4 addendum - measure inter-model reliability on the six
compared fields, using the two arms already run on the same 60 articles.

Why this test, and why it is not a lower bar. The D4 gate scored the
extractor against a single-pass human coding that was never itself
checked for reproducibility. The eligibility protocol does check: it
re-coded 34 of its 168 pilot articles blind and reported human-to-human
kappa (1.000 / 0.922 / 1.000 / 1.000) before comparing any LLM output.
D4 skipped that step, so a low human-machine kappa cannot be attributed
to the model - it may equally reflect an unstable or differently-scoped
human construct. Two of the six fields turned out to have been scored
against instructions that contradicted the extraction prompts outright.

Inter-model agreement answers a different and, for a feature applied
uniformly to 3,584 articles, more directly relevant question: is this
field measured reproducibly? Two independently prompted models scoring
the same articles under the same schema either converge, in which case
the measurement is stable and can be documented as an instrument, or
they do not, in which case the field is unstable no matter whose labels
it is compared against. This is the calibration frame the D4 decision
already named: machine-machine cross-layer agreement sat in the 0.6-0.8
band in the pilots.

Neither figure replaces the other. Human-machine agreement speaks to
construct match; inter-model agreement speaks to reproducibility. Both
are reported, and a field is adopted only where the reproducibility is
sound AND the human comparison is either supportive or explicably
divergent - the divergence being explained in the decision record, not
waved away.

Usage:
    python3 -m src.llm_extraction.compare_model_to_model
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.compare_d4_agreement import (PARTIES, extract_model_fields,
                                                     judge)

SONNET = Path("llm_context/d4_llm_outputs.json")
HAIKU = Path("llm_context/d4_llm_outputs_haiku.json")
OUT_JSON = Path("llm_context/d4_inter_model_agreement.json")
OUT_MD = Path("llm_context/d4_inter_model_agreement.md")

SCALARS = ["primary_issue", "frame_category", "attribution_type",
           "consequence_direction", "impact_horizon"]


def main() -> None:
    a, _ = extract_model_fields(json.loads(SONNET.read_text()))
    b, _ = extract_model_fields(json.loads(HAIKU.read_text()))
    shared = sorted(set(a) & set(b))

    report: dict = {"arm_a": "claude-sonnet-5", "arm_b": "claude-haiku-4-5",
                    "articles_compared": len(shared), "fields": {}}

    for f in SCALARS:
        pairs = [(a[i][f], b[i][f]) for i in shared
                 if f in a[i] and f in b[i]]
        report["fields"][f] = judge(pairs)

    # Stance, on the same union rule the human gate used: pairs where at
    # least one arm records an evaluative stance for that party.
    union, allp = [], []
    for i in shared:
        for party in PARTIES:
            f = f"stance_{party}"
            if f not in a[i] or f not in b[i]:
                continue
            pair = (a[i][f], b[i][f])
            allp.append(pair)
            if pair[0] != "not_mentioned" or pair[1] != "not_mentioned":
                union.append(pair)
    report["fields"]["stance_per_party"] = judge(union)
    report["fields"]["stance_per_party"]["all_pairs_including_trivial"] = \
        judge(allp)

    report["reproducible"] = [f for f, r in report["fields"].items()
                              if r["passes"]]
    report["not_reproducible"] = [f for f, r in report["fields"].items()
                                  if not r["passes"]]

    OUT_JSON.write_text(json.dumps(report, indent=2))
    lines = ["# Inter-model reliability (Sonnet vs Haiku, same 60 articles)",
             "",
             "Measures whether each field is *reproducible* across two "
             "independently prompted models. Complements, and does not "
             "replace, the human comparison in `d4_agreement_report*.md`.",
             "", f"Articles compared: {report['articles_compared']}", "",
             "| field | pairs | agreement | kappa | AC1 | verdict |",
             "|---|---|---|---|---|---|"]
    for f, r in report["fields"].items():
        lines.append(f"| {f} | {r['pairs']} | {r.get('percent_agreement')} "
                     f"| {r.get('kappa')} | {r.get('ac1')} | {r['verdict']} |")
    lines += ["",
              f"Reproducible across models: {report['reproducible'] or 'none'}",
              f"Not reproducible: {report['not_reproducible'] or 'none'}"]
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
