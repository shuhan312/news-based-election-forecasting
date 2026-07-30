"""Turn extracted article records into the news feature table the model joins.

## The grain, and why it is not the one the brief imagines

The brief asks for features per ward. The corpus cannot deliver that: of 1,452
included articles, 37 came from a ward-specific search and body-text matching
against the 108 published area names recovers only 19 more - **3.9% carry an
unambiguous area, 94.8% name no Surrey area at all**. On the 2026 test set, at
most fifteen of 81 wards have any attributable local coverage, so an area-level
feature would be roughly 85% missing exactly where it has to work.

So the table is keyed on **(election, party, window)**. Joining it to the
baseline's (election, area, party) rows broadcasts each value across the areas
of its election. That is a real limitation and it is stated here rather than
hidden by a feature name: a news feature in this table can explain differences
between elections and between parties, never between areas within an election.

## Which features can carry a coefficient, measured rather than assumed

Cell counts inside the training period (2013 + 2017), from
`diagnose_feature_grain`:

    per election                2 cells  - cannot fit; two points determine a
                                          line exactly and generalise nothing
    per election x party       10 cells  - usable, median 162 articles per cell

Every feature is therefore emitted with a `training_variation` verdict, and the
election-level ones say `insufficient` rather than being silently offered to a
model that cannot learn from them. They are still computed: the 3,122 collected
but unprocessed by-election articles would add eight more election-level cells
if that pipeline is ever run, and a column that already exists costs nothing to
populate later.

**Reform UK has zero training-period articles** - the party did not exist in
2013 or 2017. No Reform-specific news coefficient can be estimated. Any
relationship must be learned party-generically, from the five parties present in
the training period, and applied to Reform. That is the central extrapolation of
this project and it belongs in the report, not in a footnote.

## Counts and shares, both, for a measured reason

A count is contaminated by how deeply a contest was searched; a share is not,
because search depth moves numerator and denominator together. By-election
search completeness ranges from under 12% to 100%, which is why by-elections
were scoped out of count-based features - so every count here has a companion
share, and the share is what a specification should prefer whenever contests
with different search depths are compared.

## Deduplication, and the assertion that guards it

Tranche output files overlap: far2's articles were re-extracted in the full run
while its stance and framing records were left in place, so concatenating the
files double-counts **98 articles for framing and 66 for stance** - raw rows
exceeded the corpus, 1,730 framing rows against 1,632 articles. Records are
therefore deduplicated on `article_id`, newest tranche winning, and the build
asserts that the unique article count never exceeds the corpus size. A silent
double count would inflate every volume feature for the affected elections.

Usage:
    python3 -m src.news_features.build_feature_table
"""

from __future__ import annotations

import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction.run_corpus_extraction import (EXCLUDED_LAYERS,
                                                     FRAME_KEYS, LAYER_ARMS,
                                                     load_tranche)
from src.llm_extraction.stance_rescue import PARTY_ALIASES

OUT_CSV = Path("news_features/news_feature_table_v1.csv")
OUT_META = Path("news_features/news_feature_table_v1_metadata.json")

# The six windows the supervisor confirmed on 2026-07-30 ("Keep the news windows
# you already implemented... That is fine. No need to change them"), ordered from
# earliest to latest so a cumulative snapshot is a prefix of this list.
WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

# Cumulative periods, taken from `window_schemes.ORIGINAL_EMAIL.cumulative`
# rather than invented here. That definition cites the supervisor's own email
# and reads "everything from 1 to N days before polling" - the trailing N days,
# accumulating backwards from polling day.
#
# The first version of this file got both the count and the direction wrong: it
# emitted four snapshots named `as_at_90_days` and so on, built from
# `WINDOWS[:1]`, which is the 180-to-91-day band - the *earliest* coverage, the
# complement of what the definition asks for. `previous_90_days` is the last 90
# days before polling, which is `90_to_31_days` and everything after it. Reusing
# the scheme's own labels also means a feature name here matches the one the
# extraction pipeline already assigns, instead of introducing a second
# vocabulary for the same periods.
def _cumulative_members() -> dict[str, tuple[str, ...]]:
    """Window names inside each cumulative period, from the frozen scheme."""
    from src.news_modelling.window_schemes import ORIGINAL_EMAIL
    spans = {name: (lo, hi) for name, lo, hi in ORIGINAL_EMAIL.windows}
    out: dict[str, tuple[str, ...]] = {}
    for label, limit in ORIGINAL_EMAIL.cumulative:
        # A window belongs to a cumulative period when it lies entirely inside
        # it. `previous_7_days` therefore takes final_72_hours and 7_to_4_days
        # and not the 14-to-8-day band, which straddles the boundary.
        out[label] = tuple(w for w in WINDOWS if spans[w][1] <= limit)
    return out


SNAPSHOTS = _cumulative_members()

# The supervisor's chronological split. Recorded per row so a specification can
# filter on it without re-deriving the split, and so the training-variation
# verdict below can be computed from the table itself.
SPLIT_ROLE = {"SCC-2013-05": "train", "SCC-2017-05": "train",
              "SCC-2021-05": "validation", "ESWS-2026-05": "test"}

# Two points determine a line exactly. Three is where a residual first exists;
# ten is where a coefficient is worth reporting. Stated here because "enough
# variation" is otherwise a judgement made silently inside a model fit.
MIN_CELLS_TO_FIT = 3
MIN_CELLS_TO_REPORT = 10

# Issue codes aggregated into the six pre-registered issue features. Anything
# outside this map lands in `issue_other`, which is reported rather than
# dropped: an issue the taxonomy does not cover is a fact about the coverage.
ISSUE_GROUPS = {
    "immigration": ("immigration", "asylum", "small_boats"),
    "crime_policing": ("crime", "policing", "antisocial_behaviour"),
    "housing_planning": ("housing", "planning", "development", "green_belt"),
    "council_services": ("council_services", "roads_transport", "waste",
                         "social_care", "schools_sen", "council_finance",
                         "council_tax", "council_performance"),
    "national_politics": ("national_politics", "national_economy",
                          "party_leadership", "scandal"),
}


def live_layers() -> list[str]:
    return [l for l in LAYER_ARMS if l not in EXCLUDED_LAYERS]


def load_records() -> tuple[dict[str, dict], dict]:
    """Deduplicated accepted records per layer, newest tranche winning.

    Returns (records, provenance). `records[layer][article_id]` is the accepted
    record; `provenance` counts which tranche and prompt fingerprint each
    article's records came from, so a feature row can be traced to the prompts
    behind it.
    """
    paths = sorted(glob.glob("llm_context/corpus_extraction_outputs_*.json"))
    # "all" is the production run and must win over the gate tranches, so files
    # are applied oldest-first and later writes overwrite earlier ones. Sorting
    # by name puts "all" first alphabetically, which is the wrong order - hence
    # the explicit key rather than relying on the filename.
    order = {"narrow": 0, "far": 1, "far2": 2, "far3": 3, "all": 9}
    def rank(p: str) -> int:
        name = Path(p).stem.replace("corpus_extraction_outputs_", "")
        return order.get(name, 5)

    records: dict[str, dict[str, dict]] = {l: {} for l in live_layers()}
    provenance: Counter = Counter()
    superseded_seen: dict[str, list[str]] = {}

    for path in sorted(paths, key=rank):
        payload = json.loads(Path(path).read_text())
        tranche = payload.get("tranche", Path(path).stem)
        superseded = set(payload.get("superseded_layers") or ())
        if superseded:
            superseded_seen[tranche] = sorted(superseded)
        for layer in live_layers():
            if layer in superseded:
                continue
            for r in payload.get("layers", {}).get(layer, []):
                if r.get("record") is None or r.get("validation_errors"):
                    continue
                records[layer][r["article_id"]] = r
                provenance[(layer, tranche,
                            (r.get("prompt_sha256") or "none")[:12])] += 1
    return records, {"per_layer_tranche_prompt": {f"{k[0]}|{k[1]}|{k[2]}": v
                                                  for k, v in provenance.items()},
                     "superseded_layers_honoured": superseded_seen}


def primary_issue(record: dict) -> str | None:
    """The issue code, unwrapped from whichever shape the schema produced."""
    value = (record.get("issues") or {}).get("primary_issue")
    if isinstance(value, dict):
        value = value.get("issue_code") or value.get("code")
    return value or None


def issue_group(code: str | None) -> str:
    if not code:
        return "none"
    for group, members in ISSUE_GROUPS.items():
        if code in members:
            return group
    return "issue_other"


def main() -> None:
    records, provenance = load_records()
    article_ids = set().union(*(set(v) for v in records.values()))

    # Load the articles these records describe, by id, so window, arm, source
    # and election come from the same place the extraction used. Never
    # re-derive a tranche: the far sampler's rule depends on history.
    articles, _fallback, census = load_tranche("all", only_ids=article_ids)
    corpus_size = sum(census["by_window"].values())

    # The guard the duplicate-counting hazard demands. An inflated article count
    # would inflate every volume feature, and it would do so silently.
    assert len(articles) <= corpus_size, (
        f"deduplication failed: {len(articles)} unique articles against a "
        f"corpus of {corpus_size}. Concatenating tranche files double-counts, "
        f"which is what this assertion exists to catch.")
    print(f"records: {
        {l: len(v) for l, v in records.items()} }")
    print(f"unique articles: {len(articles)} of a {corpus_size}-article corpus")

    # --- accumulate per (election, party, window) -------------------------
    # Party-varying counters. The party key comes from the stance layer's own
    # judgement list, which was built from deterministic alias matching, so a
    # party appears here exactly when the article names it.
    party_cells: dict[tuple, Counter] = defaultdict(Counter)
    # Election-level counters, kept separate because their grain differs and
    # conflating them would hide that one has two training cells and the other
    # has ten.
    election_cells: dict[tuple, Counter] = defaultdict(Counter)

    for aid, article in articles.items():
        election, window, arm = (article["election_id"], article["window"],
                                 article.get("arm") or "unknown")
        ekey = (election, window)
        election_cells[ekey]["article_count"] += 1
        election_cells[ekey][f"{arm}_article_count"] += 1
        election_cells[ekey][f"source__{article.get('source') or 'unknown'}"] += 1
        if article.get("mentions_reform"):
            election_cells[ekey]["reform_named_count"] += 1

        issues = records["issues"].get(aid)
        if issues is not None:
            group = issue_group(primary_issue(issues["record"]))
            election_cells[ekey][f"issue_{group}_count"] += 1
            election_cells[ekey]["issues_coded"] += 1

        framing = records["framing_revised"].get(aid)
        if framing is not None:
            election_cells[ekey]["framing_coded"] += 1
            present = {f["frame"]: bool(f.get("present"))
                       for f in framing["record"].get("frames") or []}
            for frame in FRAME_KEYS:
                if present.get(frame):
                    election_cells[ekey][f"frame_{frame}_count"] += 1

        stance = records["stance_revised"].get(aid)
        if stance is not None:
            for judgement in stance["record"].get("judgements") or []:
                party, portrayal = judgement["party"], judgement.get("portrayal")
                cell = party_cells[(election, party, window)]
                cell["party_article_count"] += 1
                cell[f"portrayal_{portrayal}"] += 1

    # --- emit one row per (election, party, window-or-snapshot) -----------
    def summed(cells: dict, key_prefix: tuple, windows) -> Counter:
        total = Counter()
        for w in windows:
            total.update(cells.get(key_prefix + (w,), Counter()))
        return total

    parties = sorted({p for (_e, p, _w) in party_cells})
    elections = sorted({e for (e, _w) in election_cells})
    periods = [(w, (w,)) for w in WINDOWS] + list(SNAPSHOTS.items())

    rows = []
    for election in elections:
        for party in parties:
            for period_name, member_windows in periods:
                p = summed(party_cells, (election, party), member_windows)
                e = summed(election_cells, (election,), member_windows)
                total = e["article_count"]
                if not total and not p["party_article_count"]:
                    continue
                unfav = p["portrayal_unfavourable"]
                fav = p["portrayal_favourable"]
                row = {
                    "election_id": election,
                    "standard_party_key": party,
                    "period": period_name,
                    "period_kind": "window" if period_name in WINDOWS else "snapshot",
                    "split_role": SPLIT_ROLE.get(election, "unknown"),
                    # --- per election x party: the usable grain -----------
                    "party_article_count": p["party_article_count"],
                    "party_article_share": round(p["party_article_count"] / total, 6) if total else "",
                    "unfavourable_count": unfav,
                    "favourable_count": fav,
                    "net_portrayal": fav - unfav,
                    "net_portrayal_share": round((fav - unfav) / p["party_article_count"], 6)
                                            if p["party_article_count"] else "",
                    # --- per election: two training cells, kept for later --
                    "article_count": total,
                    "local_article_count": e["local_article_count"],
                    "national_article_count": e["national_article_count"],
                    "local_share": round(e["local_article_count"] / total, 6) if total else "",
                    "independent_source_count": sum(
                        1 for k in e if k.startswith("source__")),
                    "reform_named_count": e["reform_named_count"],
                    "reform_share_of_coverage": round(e["reform_named_count"] / total, 6) if total else "",
                }
                for group in list(ISSUE_GROUPS) + ["issue_other", "none"]:
                    n = e[f"issue_{group}_count"]
                    row[f"issue_{group}_count"] = n
                    row[f"issue_{group}_share"] = (
                        round(n / e["issues_coded"], 6) if e["issues_coded"] else "")
                for frame in FRAME_KEYS:
                    n = e[f"frame_{frame}_count"]
                    row[f"frame_{frame}_count"] = n
                    row[f"frame_{frame}_share"] = (
                        round(n / e["framing_coded"], 6) if e["framing_coded"] else "")
                rows.append(row)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # --- the training-variation verdict, computed from the table ----------
    # A feature is only offered to a model if it varies across training rows.
    # Computed here rather than asserted in a docstring so it cannot go stale.
    train_rows = [r for r in rows if r["split_role"] == "train"]
    by_period: dict[str, list] = defaultdict(list)
    for r in train_rows:
        by_period[r["period"]].append(r)

    verdicts = {}
    for column in rows[0]:
        if column in ("election_id", "standard_party_key", "period",
                      "period_kind", "split_role"):
            continue
        # Counted WITHIN a period, not across them. A specification uses one
        # window or one snapshot, so variation between windows is not variation
        # the fit can see. Pooling across periods inflated article_count from 2
        # distinct training values to 14 and would have offered it as usable to
        # a model that sees two - the first version of this verdict did exactly
        # that, which is why it is computed per period now.
        best = max((len({r[column] for r in group if r[column] != ""})
                    for group in by_period.values()), default=0)
        pooled = len({r[column] for r in train_rows if r[column] != ""})
        verdicts[column] = {
            "distinct_training_values_within_period": best,
            "distinct_training_values_pooled_across_periods": pooled,
            "verdict": ("insufficient" if best < MIN_CELLS_TO_FIT
                        else "fittable_not_reportable" if best < MIN_CELLS_TO_REPORT
                        else "usable"),
        }

    usable = [c for c, v in verdicts.items() if v["verdict"] == "usable"]
    OUT_META.write_text(json.dumps({
        "rows": len(rows),
        "elections": elections,
        "parties": parties,
        "periods": [p for p, _ in periods],
        "unique_articles": len(articles),
        "corpus_size": corpus_size,
        "grain": "election x party x period",
        "grain_note": ("Not area-level: 94.8% of included articles name no "
                       "Surrey area, and on the 2026 test set at most fifteen "
                       "of 81 wards carry attributable local coverage."),
        "reform_training_articles": sum(
            1 for r in train_rows if r["standard_party_key"] == "reform_uk"
            and r["party_article_count"]),
        "training_variation": verdicts,
        "usable_columns": usable,
        "provenance": provenance,
    }, indent=2))

    print(f"\nrows: {len(rows)}  ({len(elections)} elections x {len(parties)} "
          f"parties x {len(periods)} periods, empty cells dropped)")
    print(f"columns with usable training variation: {len(usable)} of "
          f"{len(verdicts)}")
    for column, v in sorted(
            verdicts.items(),
            key=lambda kv: -kv[1]["distinct_training_values_within_period"]):
        if v["verdict"] == "insufficient":
            continue
        print(f"    {column:34s} "
              f"{v['distinct_training_values_within_period']:3d} within period"
              f"   ({v['distinct_training_values_pooled_across_periods']:3d} pooled)"
              f"   {v['verdict']}")
    print(f"\n  insufficient: "
          f"{sum(1 for v in verdicts.values() if v['verdict']=='insufficient')} columns")
    print(f"-> {OUT_CSV}\n-> {OUT_META}")


if __name__ == "__main__":
    main()
