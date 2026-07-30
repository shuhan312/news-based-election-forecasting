"""How much variation does each candidate news feature actually have?

## The problem this measures

A news feature can only teach a model something if it takes different values
across the training rows. The baseline predicts election x area x party, and a
news feature is computed at whatever grain the corpus supports - so the question
is not "how many rows are in one eligibility file" but "how many distinct cells
does the canonical usable release provide inside the training period".

A first pass over the four principal elections found:

    per election                   4 cells total,  2 in training (2013, 2017)
    per election x party          22 cells total, 10 in training

Two cells cannot support a coefficient: a line through two points fits them
exactly and generalises nothing. And Reform UK appears in **zero** training
cells, because the party did not exist in 2013 or 2017 - so no Reform-specific
news effect can be learned, only a party-generic one applied to Reform.

## The routes out, all measured here rather than assumed

1. **By-elections.** Fifteen more election events, each an independent
   election-level observation. They were scoped out of the news layer on
   2026-07-30 because search completeness varies from under 12% to 100%, which
   contaminates any count-based feature. That objection is much weaker for
   proportional features - net portrayal is a ratio, and a ratio is far less
   sensitive to how deeply a contest was searched than a raw count is. Measured
   here per by-election, so the trade is visible.

2. **UKIP as the training-period analogue.** UKIP carries 325 articles across
   2013 and 2017 and occupies, in those elections, the structural position
   Reform occupies in 2026: a right-populist insurgent with no incumbency. The
   brief explicitly permits this while keeping the parties separate - "Reform UK
   must remain separate from UKIP, although a separate party-history field can
   record any relationship between earlier UKIP support and later Reform UK
   performance". Measured here: how much UKIP news exists per election, and
   whether it is enough to estimate a challenger-specific slope.

3. **Party-generic pooling.** The relationship is learned from every party in
   the training period and applied to Reform. This is not a route out so much as
   the only viable design; what is measured here is how many cells and articles
   it rests on.

## What this cannot fix

Area-level features. The 2026 test set has 81 wards and at most fifteen of them
carry any attributable local coverage, so an area-level feature is roughly 85%
missing exactly where it would have to work. No amount of re-scoping changes
that, because the coverage was never collected.

Usage:
    python3 -m src.news_features.diagnose_feature_grain
"""

from __future__ import annotations

import json
import glob
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OUT = Path("news_features/feature_grain_diagnosis.json")

# The supervisor's chronological split, so a cell count can be reported per
# split role rather than pooled - a cell that exists only in the test period
# teaches the model nothing.
SPLIT_ROLE = {
    "SCC-2013-05": "train",
    "SCC-2017-05": "train",
    "SCC-2021-05": "validation",
    "ESWS-2026-05": "test",
}
PRINCIPAL = set(SPLIT_ROLE)

# Two points determine a line exactly, so a grain with two training cells can
# be fitted but not validated. Three is the minimum at which a residual exists
# at all; ten is where a coefficient starts to be worth reporting. Both are
# stated rather than left implicit, because "enough variation" is otherwise a
# judgement made silently.
MIN_CELLS_TO_FIT = 3
MIN_CELLS_TO_REPORT = 10


def by_election_role(election_id: str) -> str:
    """Which split a by-election falls in, from its date in the id.

    By-elections carry their polling date in the identifier, and the split is
    chronological, so the role follows from the date. Anything on or after
    2026-05-07 sits in the holdout period and must not enter training.
    """
    for year in range(2013, 2027):
        token = str(year)
        if token in election_id:
            if year <= 2019:
                return "train"
            if year <= 2021:
                return "validation"
            if year < 2026:
                return "train_late"      # 2022-2025: before the holdout
            return "test"
    return "unknown"


def load_articles() -> list[dict]:
    """Canonical usable articles with election, arm and split role.

    Do not read ``corpus_eligibility_decisions.csv`` directly here. That file
    excludes terminal decisions made in the pilot and validation passes and is
    the source of the stale 120-local diagnostic.
    """

    from src.news_collection.canonical_corpus_release import build_release

    release, articles = build_release()
    out = []
    for article_id, article in articles.items():
        election = article["election_id"]
        out.append({
            "article_id": article_id,
            "election_id": election,
            "arm": article.get("arm") or "unknown",
            "is_principal": election in PRINCIPAL,
            "role": SPLIT_ROLE.get(election) or by_election_role(election),
            "canonical_corpus_release_id": release["release_id"],
        })
    return out


def load_party_judgements() -> dict[str, list[str]]:
    """Article id -> the parties the stance layer judged in it.

    Read from every tranche output, skipping any layer a tranche marked
    superseded, and taking only validator-accepted records - the same rule the
    rest of the pipeline uses, so a cell count here matches what a feature table
    would actually be able to compute.
    """
    out: dict[str, list[str]] = {}
    for path in sorted(glob.glob("llm_context/corpus_extraction_outputs_*.json")):
        payload = json.loads(Path(path).read_text())
        if "stance_revised" in set(payload.get("superseded_layers") or ()):
            continue
        for r in payload.get("layers", {}).get("stance_revised", []):
            if r.get("record") is None or r.get("validation_errors"):
                continue
            out[r["article_id"]] = [j["party"] for j in
                                    r["record"].get("judgements", [])]
    return out


def cell_report(cells: Counter, label: str) -> dict:
    """Cells and articles per split role, with a verdict on each role."""
    by_role: dict[str, Counter] = defaultdict(Counter)
    for (role, *rest), n in cells.items():
        by_role[role][tuple(rest)] += n
    report = {}
    for role in ("train", "train_late", "validation", "test"):
        counts = by_role.get(role, Counter())
        cell_count = len(counts)
        verdict = ("cannot fit" if cell_count < MIN_CELLS_TO_FIT
                   else "fittable, not reportable" if cell_count < MIN_CELLS_TO_REPORT
                   else "usable")
        report[role] = {
            "cells": cell_count,
            "articles": sum(counts.values()),
            "median_articles_per_cell": (sorted(counts.values())[cell_count // 2]
                                         if cell_count else 0),
            "verdict": verdict,
        }
    print(f"\n  {label}")
    for role, block in report.items():
        if not block["cells"]:
            continue
        print(f"    {role:12s} {block['cells']:4d} cells  "
              f"{block['articles']:5d} articles  "
              f"median {block['median_articles_per_cell']:4d}/cell  "
              f"{block['verdict']}")
    return report


def main() -> None:
    articles = load_articles()
    judged = load_party_judgements()
    principal = [a for a in articles if a["is_principal"]]
    by_elec = [a for a in articles if not a["is_principal"]]

    print(f"included articles: {len(articles)}  "
          f"({len(principal)} principal, {len(by_elec)} by-election)")
    print(f"stance judgements available for {len(judged)} articles")

    report: dict = {
                    "canonical_corpus_release_id": (
                        articles[0]["canonical_corpus_release_id"]
                        if articles else None
                    ),
                    "canonical_corpus_manifest":
                        "news_collection/canonical_corpus_release_v1.json",
                    "articles": len(articles),
                    "principal": len(principal),
                    "by_election": len(by_elec),
                    "thresholds": {"min_cells_to_fit": MIN_CELLS_TO_FIT,
                                   "min_cells_to_report": MIN_CELLS_TO_REPORT},
                    "grains": {}}

    print("\n=== A. Per election (volume, issues, framing) ===")
    report["grains"]["election__principal_only"] = cell_report(
        Counter((a["role"], a["election_id"]) for a in principal),
        "principal elections only")
    report["grains"]["election__with_by_elections"] = cell_report(
        Counter((a["role"], a["election_id"]) for a in articles),
        "with by-elections added back")

    print("\n=== B. Per election x party (stance) ===")
    def party_cells(rows):
        c = Counter()
        for a in rows:
            for party in judged.get(a["article_id"], []):
                c[(a["role"], a["election_id"], party)] += 1
        return c
    report["grains"]["election_party__principal_only"] = cell_report(
        party_cells(principal), "principal elections only")
    report["grains"]["election_party__with_by_elections"] = cell_report(
        party_cells(articles), "with by-elections added back")

    print("\n=== C. The training-period analogue: UKIP and Reform by role ===")
    per_party: dict[str, Counter] = defaultdict(Counter)
    for a in articles:
        for party in judged.get(a["article_id"], []):
            per_party[party][a["role"]] += 1
    rows = []
    for party in sorted(per_party, key=lambda p: -sum(per_party[p].values())):
        counts = per_party[party]
        rows.append({"party": party, **dict(counts)})
        marker = ("  <- the study party" if party == "reform_uk"
                  else "  <- the training-period analogue" if party == "ukip" else "")
        print(f"    {party:20s} train {counts.get('train',0):4d}  "
              f"train_late {counts.get('train_late',0):3d}  "
              f"validation {counts.get('validation',0):4d}  "
              f"test {counts.get('test',0):4d}{marker}")
    report["party_by_role"] = rows

    print("\n=== D. By-election search completeness, the reason they were scoped out ===")
    be_counts = Counter(a["election_id"] for a in by_elec)
    print(f"    {len(be_counts)} by-elections carry articles; "
          f"{sum(be_counts.values())} articles in total")
    for e, n in be_counts.most_common():
        print(f"      {e[-34:]:36s} {n:3d}")
    report["by_election_article_counts"] = dict(be_counts)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
