"""Audit the reference labels before any model is scored against them.

V2's central finding was that a recorded "model failure" (kappa 0.165) came
mostly from the reference labels: 31 of 39 local-arm includes were justified
by national rules, which the codebook forbids for that arm. These checks make
that kind of defect visible before it is mistaken for a model problem.

Each check returns flags as plain dicts. An empty list means the check found
nothing; it does not prove the labels correct.
"""

from __future__ import annotations

from collections import defaultdict

from scipy.stats import fisher_exact


def rule_consistency(examples, *, stratum_field: str,
                     allowed_prefixes: dict[str, list[str]]) -> list[dict]:
    """Flag labels justified by a reason code outside their stratum's rules.

    `allowed_prefixes` maps a stratum value to the reason-code prefixes it may
    use, e.g. {"local": ["E5-L", "E5-NO-", "E5-BORDERLINE-"]}. Strata absent
    from the map, and examples without a reason code, are not checked.
    Flags are grouped by labelling batch and label, so one bad batch stands
    out from the rest.
    """
    counts = defaultdict(lambda: {"violations": 0, "checked": 0,
                                  "codes": defaultdict(int)})
    for e in examples:
        stratum = e.group.get(stratum_field)
        prefixes = allowed_prefixes.get(stratum)
        if prefixes is None or not e.reason:
            continue
        cell = counts[(e.origin, stratum, e.label)]
        cell["checked"] += 1
        if not any(e.reason.startswith(p) for p in prefixes):
            cell["violations"] += 1
            cell["codes"][e.reason] += 1
    return [{"check": "rule_consistency", "origin": origin,
             "stratum": stratum, "label": label,
             "violations": c["violations"], "checked": c["checked"],
             "share": round(c["violations"] / c["checked"], 4),
             "codes": dict(c["codes"])}
            for (origin, stratum, label), c in sorted(counts.items())
            if c["violations"]]


def base_rate_drift(examples, *, within: str, min_n: int = 10,
                    max_gap: float = 0.25, alpha: float = 0.01) -> list[dict]:
    """Flag labelling batches whose positive rate differs sharply for the
    same kind of item.

    Within each value of `within` (e.g. the news source), every pair of
    batches with at least `min_n` labels is compared. A pair is flagged when
    the rates differ by more than `max_gap` AND Fisher's exact test gives
    p < alpha: a large gap, too large to be sampling noise. Different
    batches can legitimately differ (different samples), so a flag is a
    question to answer, not proof of error.
    """
    cells = defaultdict(lambda: [0, 0])          # (within, origin) -> [pos, n]
    for e in examples:
        cell = cells[(e.group.get(within, ""), e.origin)]
        cell[0] += e.label
        cell[1] += 1
    flags = []
    keys = sorted({w for w, _ in cells})
    for w in keys:
        origins = sorted(o for (ww, o), (_, n) in cells.items()
                         if ww == w and n >= min_n)
        for i, a in enumerate(origins):
            for b in origins[i + 1:]:
                pa, na = cells[(w, a)]
                pb, nb = cells[(w, b)]
                gap = pa / na - pb / nb
                _, pval = fisher_exact([[pa, na - pa], [pb, nb - pb]])
                if abs(gap) > max_gap and pval < alpha:
                    flags.append({"check": "base_rate_drift", within: w,
                                  "origins": [a, b],
                                  "rates": [round(pa / na, 4), round(pb / nb, 4)],
                                  "n": [na, nb], "p_value": float(pval)})
    return flags


def provenance_warning(examples, *, classifier_is_llm: bool) -> list[dict]:
    """Agreement with AI-assisted labels is not independent validation of an
    LLM classifier: shared errors can inflate it."""
    assisted = sum(1 for e in examples if e.provenance == "ai_assisted")
    if classifier_is_llm and assisted:
        return [{"check": "provenance", "ai_assisted_labels": assisted,
                 "total": len(examples),
                 "message": "Reference labels were made with AI assistance; "
                            "agreement with an LLM classifier is consistency "
                            "with that standard, not independent validation."}]
    return []


def run_audit(examples, *, stratum_field: str | None = None,
              allowed_prefixes: dict | None = None,
              drift_within: str | None = None,
              classifier_is_llm: bool = True) -> dict:
    """All configured checks, in one result."""
    flags = []
    if stratum_field and allowed_prefixes:
        flags += rule_consistency(examples, stratum_field=stratum_field,
                                  allowed_prefixes=allowed_prefixes)
    if drift_within:
        flags += base_rate_drift(examples, within=drift_within)
    flags += provenance_warning(examples, classifier_is_llm=classifier_is_llm)
    return {"examples": len(examples), "flags": flags,
            "clean": not any(f["check"] != "provenance" for f in flags)}
