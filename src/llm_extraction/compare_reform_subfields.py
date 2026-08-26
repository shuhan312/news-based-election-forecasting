"""Phase 6 / D4 addendum - score the reform_uk sub-field block against the
reviewer's blind labels on the 22-article sample (14 the model marked
applicable, 8 controls it marked not).

Same statistics and same two-route gate as compare_d4_agreement.py, so
this block is judged by the ruler every other gate in the project uses.

Scoring rules, stated before the numbers were seen:
    applicable            scored on all 22 pairs - the controls exist
                          precisely to give this field a real marginal
    the five sub-fields   scored only on pairs where BOTH sides say
                          applicable, because the schema (rule E4) forces
                          them to false/empty whenever applicable is
                          false; scoring those would be counting the
                          schema's own constraint as agreement
    list fields           set equality after splitting on commas and
                          mapping an empty cell or "none" to the empty
                          set - order is not meaningful

Usage:
    python3 -m src.llm_extraction.compare_reform_subfields [arm]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.compare_d4_agreement import judge

LABELS = Path("/Users/sl1425/Desktop/"
              "D4_ReformUK_Subfields_Labelling_completed.xlsx")
ARM = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
SUFFIX = "" if ARM == "sonnet" else f"_{ARM}"
LLM = Path(f"llm_context/d4_llm_outputs{SUFFIX}.json")
OUT_JSON = Path(f"llm_context/reform_subfield_agreement{SUFFIX}.json")
OUT_MD = Path(f"llm_context/reform_subfield_agreement{SUFFIX}.md")

BOOL_FIELDS = ["growth_suggested", "credible_challenger"]
LIST_FIELDS = ["established_support_affected", "switching_directions",
               "signal_nature"]


def norm_bool(v) -> str:
    return "yes" if str(v).strip().lower() in ("yes", "true", "1") else "no"


def norm_list(v) -> frozenset:
    raw = str(v or "").strip().lower()
    if raw in ("", "none", "no"):
        return frozenset()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def main() -> None:
    wb = load_workbook(LABELS, data_only=True)
    sheet = next(s for s in wb.sheetnames if "RU" in s)
    ws = wb[sheet]
    hdr = [c.value for c in ws[1]]
    human = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue
        human[row[0]] = dict(zip(hdr, row))

    llm = json.loads(LLM.read_text())
    model = {}
    for r in llm["layers"]["consequence"]:
        rec = r.get("record")
        model[r["article_id"]] = (rec or {}).get("reform_uk") or {}

    report: dict = {"arm": ARM, "model": llm.get("model"),
                    "articles": len(human), "fields": {}}

    app_pairs = []
    for aid, h in human.items():
        m = model.get(aid)
        if m is None:
            continue
        app_pairs.append((norm_bool(h["ru_applicable"]),
                          norm_bool(m.get("applicable"))))
    report["fields"]["applicable"] = judge(app_pairs)

    # Both-applicable subset: the schema forces the sub-fields empty when
    # applicable is false, so only these pairs carry real judgement.
    both = [aid for aid, h in human.items()
            if norm_bool(h["ru_applicable"]) == "yes"
            and norm_bool((model.get(aid) or {}).get("applicable")) == "yes"]
    report["both_applicable_n"] = len(both)

    for f in BOOL_FIELDS:
        pairs = [(norm_bool(human[a][f"ru_{f}"]),
                  norm_bool(model[a].get(f))) for a in both]
        report["fields"][f] = judge(pairs)
    for f in LIST_FIELDS:
        pairs = [(norm_list(human[a][f"ru_{f}"]),
                  norm_list(model[a].get(f))) for a in both]
        # judge() needs hashable labels; frozensets are, but render them
        # readably for the report by joining sorted members.
        pairs = [("|".join(sorted(a)) or "none",
                  "|".join(sorted(b)) or "none") for a, b in pairs]
        report["fields"][f] = judge(pairs)

    # A verdict needs enough pairs to be a verdict. With five pairs a
    # single disagreement moves kappa by roughly 0.2, so neither "passes"
    # nor "fails" carries information - the honest label is undetermined.
    # This is arithmetic, not a results-dependent escape hatch, but it was
    # written after seeing that the both-applicable subset was five, and
    # that ordering is disclosed rather than hidden. The threshold is the
    # smallest subset this project has previously accepted a verdict on
    # (the 35-article judged E6 subset in the eligibility gate), rounded
    # down to 20.
    MIN_PAIRS_FOR_VERDICT = 20
    for f, r in report["fields"].items():
        if r["pairs"] < MIN_PAIRS_FOR_VERDICT:
            r["verdict"] = (f"undetermined - {r['pairs']} pairs is below the "
                            f"{MIN_PAIRS_FOR_VERDICT}-pair minimum for a "
                            f"meaningful verdict")
            r["passes"] = False
            r["undetermined"] = True

    gate = ["applicable"] + BOOL_FIELDS + LIST_FIELDS
    report["adopted"] = [f for f in gate if report["fields"][f]["passes"]]
    report["undetermined"] = [f for f in gate
                              if report["fields"][f].get("undetermined")]
    report["failed"] = [f for f in gate
                        if not report["fields"][f]["passes"]
                        and not report["fields"][f].get("undetermined")]
    report["overall_pass"] = all(report["fields"][f]["passes"] for f in gate)

    OUT_JSON.write_text(json.dumps(report, indent=2))
    lines = ["# reform_uk sub-field validation - agreement report", "",
             f"Model: {report['model']} | arm {ARM} | "
             f"{report['articles']} articles, "
             f"{report['both_applicable_n']} both-applicable", "",
             "| field | pairs | agreement | kappa | AC1 | verdict |",
             "|---|---|---|---|---|---|"]
    for f in gate:
        r = report["fields"][f]
        lines.append(f"| {f} | {r['pairs']} | {r.get('percent_agreement')} "
                     f"| {r.get('kappa')} | {r.get('ac1')} | {r['verdict']} |")
    lines += ["",
              f"Adopted: {report['adopted'] or 'none'}",
              f"Undetermined (insufficient pairs): "
              f"{report['undetermined'] or 'none'}",
              f"Failed on the evidence: {report['failed'] or 'none'}"]
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
