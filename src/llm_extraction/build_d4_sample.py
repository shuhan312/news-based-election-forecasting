"""Phase 6 / D4 - draw the human-validation sample for the context
extraction gate (decision D4 in phase6_research_decisions_v1.md).

Method (recorded, deterministic, no cherry-picking - the pilot sampler's
method, applied to a fresh frame and made disjoint from the pilot):

    frame       every article whose assembled eligibility decision is
                include (corpus_eligibility_decisions.csv, the adjudicated
                remaining pool) AND whose extracted text file exists,
                MINUS the 67 pilot articles (D4 must measure agreement on
                articles the prompt was never tuned against);
    strata      election_id x arm;
    quotas      D4_LOCAL_QUOTA local + D4_NATIONAL_QUOTA national per
                election (~50 articles total, per the D4 decision);
    ordering    within each stratum, sha256(article_id) - fixed,
                unsteerable, reproducible; first k taken;
    Reform UK   topped up (same hash order) until the sample holds
                >= D4_REFORM_MIN articles whose title or body mentions
                "reform uk" - the per-party stance comparison needs
                real positives.

Disclosed limits: the frame predates the corpus-v2 freeze (the ward-first
re-harvest delta is still under E5 review), so it reflects the adjudicated
old pool; if the delta materially shifts the corpus mix, a disclosed
local-arm top-up draw follows the same method. The provisional duplicate
mapping is not consulted - a near-duplicate pair in a 52-article hash
draw is unlikely and would not bias an agreement measurement.

Usage:
    python3 -m src.llm_extraction.build_d4_sample
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .pilot_sample import _hash_order

DECISIONS = Path("news_collection/corpus_eligibility_decisions.csv")
PILOT = Path("llm_context/llm_context_pilot_sample_v1.csv")
SHEET = Path("news_collection/full_corpus_review.csv")
TEXT_DIR = Path("data/raw/news/text")
OUT_CSV = Path("llm_context/d4_validation_sample_v1.csv")
OUT_AUDIT = Path("llm_context/d4_validation_sample_audit.json")

D4_LOCAL_QUOTA = 7
D4_NATIONAL_QUOTA = 6
D4_REFORM_MIN = 10

D4_VERSION = "d4-sample-v1.0-2026-07-29"


def main() -> None:
    pilot_ids = {r["article_id"] for r in csv.DictReader(PILOT.open())}
    headlines = {r["article_id"]: r["headline"]
                 for r in csv.DictReader(SHEET.open())}

    frame = []
    n_include = n_no_text = 0
    for r in csv.DictReader(DECISIONS.open()):
        if r["overall_decision"] != "include":
            continue
        n_include += 1
        if r["article_id"] in pilot_ids:
            continue
        txt = TEXT_DIR / f"{r['article_id']}.txt"
        if not txt.is_file():
            n_no_text += 1
            continue
        body = txt.read_text(encoding="utf-8", errors="replace")
        frame.append({
            "article_id": r["article_id"],
            "election_id": r["election_id"],
            "arm": r["arm"],
            "mentions_reform": "reform uk" in
            (headlines.get(r["article_id"], "") + " " + body).lower(),
        })

    by_stratum: dict[tuple, list[dict]] = {}
    for a in frame:
        by_stratum.setdefault((a["election_id"], a["arm"]), []).append(a)

    selected: list[str] = []
    strata_report = {}
    for (election, arm), members in sorted(by_stratum.items()):
        quota = D4_LOCAL_QUOTA if arm == "local" else D4_NATIONAL_QUOTA
        ranked = sorted(members, key=lambda a: _hash_order(a["article_id"]))
        take = [a["article_id"] for a in ranked[:quota]]
        selected.extend(take)
        strata_report[f"{election}/{arm}"] = {
            "pool": len(members), "quota": quota, "taken": len(take)}

    by_id = {a["article_id"]: a for a in frame}
    have = {aid for aid in selected if by_id[aid]["mentions_reform"]}
    reform_pool = sorted(
        (a for a in frame
         if a["mentions_reform"] and a["article_id"] not in selected),
        key=lambda a: _hash_order(a["article_id"]))
    topped_up = []
    while len(have) + len(topped_up) < D4_REFORM_MIN and reform_pool:
        topped_up.append(reform_pool.pop(0)["article_id"])
    selected.extend(topped_up)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["article_id", "election_id", "arm", "mentions_reform",
                    "headline"])
        for aid in sorted(selected):
            a = by_id[aid]
            w.writerow([aid, a["election_id"], a["arm"],
                        str(a["mentions_reform"]).lower(),
                        headlines.get(aid, "")])

    audit = {
        "version": D4_VERSION,
        "frame": {"assembled_includes": n_include,
                  "pilot_excluded": len(pilot_ids),
                  "no_text_file": n_no_text,
                  "frame_size": len(frame)},
        "strata": strata_report,
        "reform_in_base": len(have),
        "reform_topped_up": len(topped_up),
        "selected_count": len(selected),
        "method": (
            "Frame: adjudicated includes from corpus_eligibility_decisions"
            ".csv with an extracted text file, minus the 67 pilot articles. "
            f"Strata: election x arm. Quotas: {D4_LOCAL_QUOTA} local + "
            f"{D4_NATIONAL_QUOTA} national per election. Within-stratum "
            "order: sha256(article_id); first k taken. Reform UK top-up to "
            f">= {D4_REFORM_MIN} mentioning articles in the same hash "
            "order. Drawn before the corpus-v2 freeze (re-harvest delta "
            "still under E5 review) and without the provisional duplicate "
            "mapping; both disclosed in build_d4_sample.py. No manual "
            "selection."),
    }
    OUT_AUDIT.write_text(json.dumps(audit, indent=2))

    print(f"{len(selected)} articles -> {OUT_CSV}")
    print(json.dumps(audit["strata"], indent=1))
    print(f"reform: {len(have)} in base, {len(topped_up)} topped up")


if __name__ == "__main__":
    main()
