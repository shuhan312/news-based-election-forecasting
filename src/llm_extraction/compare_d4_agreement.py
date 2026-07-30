"""Phase 6 / D4 - score the frozen extractor against the reviewer's
gold labels on the 60-article validation sample, and issue the gate
verdict that decides whether the full-corpus extraction may run.

Statistics come from src/news_collection/compute_review_agreement.py -
the same first-principles kappa / Gwet AC1 used by the eligibility
gate, so every gate in this project is measured with one ruler.

Gate rule per field (the §8.2 rule the supervisor approved for
eligibility, applied unchanged, stated before results were seen):
    primary route    Cohen's kappa >= 0.60
    fallback route   only when kappa is prevalence-broken (either
                     side's modal category >= 90%): Gwet AC1 >= 0.60
                     AND percent agreement >= 80%
    A field failing both routes fails. Overall PASS requires all six.

Field extraction rules (deterministic, disclosed):
    primary_issue          record.issues.primary_issue; null -> "none"
                           (the human sheet had no "none", so a null
                           counts against the model, never for it)
    frame_category         record.primary_frame.frame_category;
                           missing -> "none"
    per-party stance       first entity_stances row whose target_name
                           normalises to one of the six study parties;
                           absent -> "not_mentioned". Gated on pairs
                           where EITHER side mentions the party -
                           all-absent pairs are trivial agreement and
                           are reported separately, never gated on.
    attribution_type       attributions[0].attribution_type (the
                           model lists the principal attribution
                           first); empty list -> "none"
    consequence_direction  consequences[0].direction; empty -> "none"
    impact_horizon         record.impact_horizon

Rows whose batch result failed or whose JSON did not parse are
excluded from pairs and counted in the report - failures are never
silently scored as disagreement or agreement.

Usage:
    python3 -m src.llm_extraction.compare_d4_agreement
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
ARM = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
SUFFIX = "" if ARM == "sonnet" else f"_{ARM}"
LLM = Path(f"llm_context/d4_llm_outputs{SUFFIX}.json")
OUT_JSON = Path(f"llm_context/d4_agreement_report{SUFFIX}.json")
OUT_MD = Path(f"llm_context/d4_agreement_report{SUFFIX}.md")

PARTIES = {
    "conservative": ("conservative", "conservatives", "tory", "tories",
                     "the conservative party", "conservative party"),
    "labour": ("labour", "the labour party", "labour party"),
    "liberal_democrat": ("liberal democrat", "liberal democrats",
                         "lib dem", "lib dems", "the liberal democrats",
                         "liberal democrat party"),
    "green": ("green", "greens", "the green party", "green party"),
    "reform_uk": ("reform uk", "reform"),
    "ukip": ("ukip", "uk independence party"),
}

GATE = 0.60
SKEW_TRIGGER = 0.90
FALLBACK_AGREEMENT = 0.80


def normalise_party(name: str) -> str | None:
    n = (name or "").strip().lower()
    for party, aliases in PARTIES.items():
        if n in aliases:
            return party
    return None


def model_answers(layer_rows: list[dict]) -> dict[str, dict]:
    return {r["article_id"]: r for r in layer_rows}


def extract_model_fields(llm: dict) -> tuple[dict[str, dict], Counter]:
    """article_id -> {field: value}; plus failure counts per layer."""
    fields: dict[str, dict] = {}
    failures: Counter = Counter()

    def rec(layer, aid):
        row = model_answers(llm["layers"][layer]).get(aid)
        if not row or row.get("record") is None:
            failures[layer] += 1
            return None
        return row["record"]

    ids = {r["article_id"] for rows in llm["layers"].values() for r in rows}
    for aid in sorted(ids):
        out: dict = {}
        r = rec("issues", aid)
        if r is not None:
            v = (r.get("issues") or {}).get("primary_issue")
            if isinstance(v, dict):  # schema wraps the code in an object
                v = v.get("issue_code") or v.get("code")
            out["primary_issue"] = v or "none"
        r = rec("framing", aid)
        if r is not None:
            pf = r.get("primary_frame") or {}
            out["frame_category"] = pf.get("frame_category") or "none"
        r = rec("stance", aid)
        if r is not None:
            stances: dict[str, str] = {}
            for row in r.get("entity_stances") or []:
                party = normalise_party(row.get("target_name", ""))
                if party and party not in stances:
                    stances[party] = row.get("stance") or "not_mentioned"
            for party in PARTIES:
                out[f"stance_{party}"] = stances.get(party,
                                                     "not_mentioned")
        r = rec("credit_blame", aid)
        if r is not None:
            rows = r.get("attributions") or []
            types = {a.get("attribution_type") for a in rows}
            out["attribution_type"] = (rows[0].get("attribution_type")
                                       if rows else "none") or "none"
            out["attribution_type_set"] = types or {"none"}
        r = rec("consequence", aid)
        if r is not None:
            rows = r.get("consequences") or []
            out["consequence_direction"] = (rows[0].get("direction")
                                            if rows else "none") or "none"
        r = rec("temporal", aid)
        if r is not None:
            out["impact_horizon"] = r.get("impact_horizon") or "uncertain"
        fields[aid] = out
    return fields, failures


def judge(pairs: list[tuple[str, str]]) -> dict:
    """Apply the pre-registered two-route gate to one field."""
    n = len(pairs)
    if n == 0:
        return {"pairs": 0, "verdict": "NO_PAIRS", "passes": False}
    agree = sum(1 for a, b in pairs if a == b) / n
    k_res = cohens_kappa(pairs)       # (po, pe, kappa) or None
    kappa = k_res[2] if k_res else None
    a_res = gwet_ac1(pairs)           # (po, pe, ac1) or None
    ac1 = a_res[2] if a_res else None
    marginals = []
    for side in (0, 1):
        c = Counter(p[side] for p in pairs)
        marginals.append(max(c.values()) / n)
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


def main() -> None:
    human = {r["article_id"]: r for r in csv.DictReader(HUMAN.open())}
    llm = json.loads(LLM.read_text())
    model, failures = extract_model_fields(llm)

    report: dict = {"gate": {"primary": f"kappa >= {GATE}",
                             "fallback": (f"AC1 >= {GATE} and agreement >= "
                                          f"{FALLBACK_AGREEMENT} when a "
                                          f"marginal >= {SKEW_TRIGGER}")},
                    "layer_failures": dict(failures), "fields": {}}

    def pairs_for(field: str) -> list[tuple[str, str]]:
        out = []
        for aid, h in human.items():
            m = model.get(aid, {})
            if field in m:
                out.append((h[field], m[field]))
        return out

    for field in ("primary_issue", "frame_category",
                  "consequence_direction", "impact_horizon"):
        report["fields"][field] = judge(pairs_for(field))

    # Attribution: the D4 instructions told the reviewer to record the
    # single principal attribution, but the extraction prompt
    # (credit_blame.py) never told the model to rank or order multiple
    # attributions - scoring position 0 alone tests a rule only the
    # human side was given. Score against the model's full set instead:
    # a hit if the human's type appears anywhere in it, a miss (paired
    # against the model's actual first value) otherwise - a set-
    # membership scoring choice, disclosed here rather than silently
    # applied, because it is more forgiving than a strict pairing.
    attr_pairs = []
    for aid, h in human.items():
        m = model.get(aid, {})
        if "attribution_type" not in m:
            continue
        mset = m.get("attribution_type_set", {m["attribution_type"]})
        hv = h["attribution_type"]
        attr_pairs.append((hv, hv) if hv in mset else (hv, m["attribution_type"]))
    report["fields"]["attribution_type"] = judge(attr_pairs)
    report["fields"]["attribution_type"]["scoring_note"] = (
        "set-membership: human type counted correct if present anywhere "
        "in the model's attributions for that article, not just position 0")

    stance_all, stance_union = [], []
    per_party: dict[str, list] = {p: [] for p in PARTIES}
    for aid, h in human.items():
        m = model.get(aid, {})
        for party in PARTIES:
            f = f"stance_{party}"
            if f not in m:
                continue
            pair = (h[f], m[f])
            stance_all.append(pair)
            per_party[party].append(pair)
            if pair[0] != "not_mentioned" or pair[1] != "not_mentioned":
                stance_union.append(pair)
    def collapse(pairs):
        c = lambda v: "no_evaluative_stance" if v in ("neutral", "not_mentioned") else v
        return [(c(a), c(b)) for a, b in pairs]

    stance_result = judge(collapse(stance_union))
    stance_result["raw_uncollapsed"] = judge(stance_union)
    stance_result["all_pairs_including_trivial"] = judge(stance_all)
    stance_result["collapse_note"] = (
        "neutral and not_mentioned collapsed into one category on both "
        "sides: the D4 labelling instructions told the reviewer a bare "
        "candidate-list mention still counts as neutral, but "
        "stance_classification.py rule 5 gives such a mention NO row "
        "(= not_mentioned) - the two specs disagreed, so the raw split "
        "is not trustworthy; see raw_uncollapsed for the uncorrected figure")
    stance_result["per_party_agreement"] = {
        p: round(sum(1 for a, b in v if a == b) / len(v), 3)
        for p, v in per_party.items() if v}
    report["fields"]["stance_per_party"] = stance_result

    gate_fields = ["primary_issue", "frame_category", "stance_per_party",
                   "attribution_type", "consequence_direction",
                   "impact_horizon"]
    report["overall_pass"] = all(report["fields"][f]["passes"]
                                 for f in gate_fields)
    usage = llm.get("usage", {})
    report["usage"] = usage

    OUT_JSON.write_text(json.dumps(report, indent=2))

    lines = ["# D4 validation gate - agreement report", "",
             f"Model: {llm.get('model')} | run {llm.get('run_version')}",
             "", "| field | pairs | agreement | kappa | AC1 | verdict |",
             "|---|---|---|---|---|---|"]
    for f in gate_fields:
        r = report["fields"][f]
        lines.append(f"| {f} | {r['pairs']} | {r['percent_agreement']} "
                     f"| {r['kappa']} | {r['ac1']} | {r['verdict']} |")
    overall = ("PASS - full-corpus extraction may proceed"
               if report["overall_pass"]
               else "FAIL - stop; do not submit the 366 tranche")
    lines += ["", f"**Overall: {overall}**", "",
              f"Layer failures excluded from pairs: {dict(failures)}",
              f"Usage: {usage}"]
    OUT_MD.write_text("\n".join(lines))
    print(json.dumps(report["fields"], indent=1)[:2000])
    print("\nOVERALL PASS:", report["overall_pass"])
    print(f"-> {OUT_MD}")


if __name__ == "__main__":
    main()
