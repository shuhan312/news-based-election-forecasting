"""Phase 7 / Step 6 runner: build the recency-weighted feature layer
alongside (never over) the Step 5 unweighted aggregates.

    news_features/recency_weighted_features.parquet
    news_features/recency_weighted_features.csv
    news_features/recency_weighting_exclusions.json

Rows are keyed by the Step 5 aggregation keys PLUS the half-life,
so the pre-registered grid (7/14/30/60/90 days) ships in one file
and a later sensitivity comparison needs no re-run and no fresh
contact with the data.

No LLM call, no API cost. Deterministic: CSV byte-identical on
rebuild. Previous layers are read-only and hash-checked.

Usage:
    python3 -m src.news_features.run_recency_weighting build
"""

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from ..llm_extraction.freeze_layer import sha256_file
from .context_aggregation import (CONSQ_BINS, KEY_COLS,
                                  REFORM_COUNT_BINS, STANCE_BINS,
                                  expand_window_rows)
from .recency_weighting import (HALF_LIVES, PRIMARY_HALF_LIFE,
                                WEIGHTING_VERSION, lambda_for,
                                recency_weight, weighted_group)
from .run_article_features import frame_categories

FEATURES = Path("news_features/article_level_news_features.csv")
AGG_CSV = Path("news_features/context_aggregated_features.csv")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
FROZEN = Path("llm_context/llm_context_layer_final.json")
TAXONOMY = Path("llm_context/issue_taxonomy_v1.3.json")

OUT_PARQUET = Path("news_features/recency_weighted_features.parquet")
OUT_CSV = Path("news_features/recency_weighted_features.csv")
OUT_EXCL = Path("news_features/recency_weighting_exclusions.json")

WKEY = KEY_COLS + ["half_life_days"]


def build() -> None:
    # previous layers untouched
    manifest = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == manifest["frozen_output_sha256"][FROZEN.name]
    agg_before = AGG_CSV.read_bytes()

    df = pd.read_csv(FEATURES)
    issue_codes = sorted(json.loads(
        TAXONOMY.read_text())["codes"].keys())
    frames = frame_categories()

    # identical window expansion to Step 5 (shared function - the
    # two layers cannot disagree about group membership)
    expanded = expand_window_rows(df.to_dict("records"))

    groups: dict[tuple, list[dict]] = {}
    for r in expanded:
        groups.setdefault(tuple(r[k] for k in KEY_COLS), []).append(r)

    rows, exclusions = [], []
    for half_life in HALF_LIVES:
        for key in sorted(groups, key=lambda k: tuple(map(str, k))):
            grp = groups[key]
            kept, weights = [], []
            for r in grp:
                w, reason = recency_weight(
                    r.get("days_before_polling"), half_life)
                if w is None:
                    # no artificial weight: excluded, reason recorded
                    exclusions.append({
                        "article_id": r["article_id"],
                        "half_life_days": half_life,
                        "reason": reason,
                        "group": dict(zip(KEY_COLS, key))})
                    continue
                kept.append(r)
                weights.append(w)
            vals = dict(zip(KEY_COLS, key))
            vals["half_life_days"] = half_life
            body = weighted_group(kept, weights, issue_codes, frames,
                                  STANCE_BINS, CONSQ_BINS,
                                  REFORM_COUNT_BINS) if kept else {
                "weighted_article_count": 0.0,
                "unweighted_article_count": 0,
                "w_reform_agg_status": "no_weighted_articles"}
            rows.append({
                **vals, **body,
                "lambda": round(lambda_for(half_life), 8),
                "is_primary_half_life": int(
                    half_life == PRIMARY_HALF_LIFE),
                "n_articles_excluded_no_date": len(grp) - len(kept),
                "weighting_version": WEIGHTING_VERSION,
                "aggregation_keys_source": "context-aggregation-v1.0"})

    out = pd.DataFrame(rows)
    assert not out.duplicated(subset=WKEY).any(), "keys not unique"
    out = out.sort_values(WKEY, kind="mergesort").reset_index(
        drop=True)

    OUT_CSV.write_text(out.to_csv(index=False, lineterminator="\n"))
    out.to_parquet(OUT_PARQUET, index=False)
    OUT_EXCL.write_text(json.dumps(
        {"weighting_version": WEIGHTING_VERSION,
         "excluded_count": len(exclusions),
         "exclusions": exclusions}, indent=1,
        ensure_ascii=False) + "\n")

    # the unweighted layer must be bit-for-bit untouched
    assert AGG_CSV.read_bytes() == agg_before, \
        "Step 5 aggregates were modified - must never happen"

    # ---- audit statistics -------------------------------------------
    prim = out[out["is_primary_half_life"] == 1]
    print(f"{len(out)} weighted rows over {len(HALF_LIVES)} "
          f"half-lives ({len(prim)} rows per half-life), "
          f"{len(out.columns)} columns")
    print("lambda per half-life:",
          {h: round(lambda_for(h), 5) for h in HALF_LIVES})
    print("example weights (days -> weight, primary "
          f"{PRIMARY_HALF_LIFE}d):",
          {d: round(recency_weight(d, PRIMARY_HALF_LIFE)[0], 4)
           for d in (1, 3, 7, 14, 30, 60, 90, 180)})
    print("excluded (no reliable date):", len(exclusions))
    print("rows per scope (primary):",
          dict(Counter(prim["scope_classification"])))
    # weighted vs unweighted headline comparison
    cmp = prim[["weighted_article_count",
                "unweighted_article_count"]].sum()
    print(f"primary half-life: weighted article mass "
          f"{cmp['weighted_article_count']:.2f} vs unweighted "
          f"{int(cmp['unweighted_article_count'])} rows "
          f"(ratio {cmp['weighted_article_count'] / cmp['unweighted_article_count']:.3f})")
    for h in HALF_LIVES:
        sub = out[out["half_life_days"] == h]
        print(f"  half-life {h:>3}d: total weighted mass "
              f"{sub['weighted_article_count'].sum():.2f}")


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
