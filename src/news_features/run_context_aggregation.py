"""Phase 7 / Step 5 runner: aggregate article-level features into
context summaries per election x target x party x window x scope.

    news_features/context_aggregated_features.parquet
    news_features/context_aggregated_features.csv
    news_features/context_aggregation_contributions.json

The contributions file maps every aggregate row to the sorted list
of canonical article IDs behind it - full provenance, no quote
text. Deterministic: CSV byte-identical on rebuild.

Usage:
    python3 -m src.news_features.run_context_aggregation build
"""

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from ..llm_extraction.freeze_layer import sha256_file
from .context_aggregation import (AGG_VERSION, KEY_COLS,
                                  aggregate_group,
                                  expand_window_rows)
from .run_article_features import frame_categories

FEATURES = Path("news_features/article_level_news_features.csv")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
FROZEN = Path("llm_context/llm_context_layer_final.json")
TAXONOMY = Path("llm_context/issue_taxonomy_v1.3.json")

OUT_PARQUET = Path("news_features/context_aggregated_features.parquet")
OUT_CSV = Path("news_features/context_aggregated_features.csv")
OUT_CONTRIB = Path(
    "news_features/context_aggregation_contributions.json")


def row_key(vals: dict) -> str:
    """Deterministic string identity of one aggregate row (used by
    the contributions provenance map)."""
    return "|".join(str(vals[k]) for k in KEY_COLS)


def build() -> None:
    # previous layers untouched (frozen hash re-checked)
    manifest = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == manifest["frozen_output_sha256"][FROZEN.name]

    df = pd.read_csv(FEATURES)
    issue_codes = sorted(json.loads(
        TAXONOMY.read_text())["codes"].keys())
    frames = frame_categories()

    # canonical gate is upstream, but assert rather than assume
    assert (df["article_id"] == df["canonical_article_id"]).all()

    # ---- expand each article row into its window memberships --------
    # individual: exactly one window per row (partition - counts add
    # across windows). cumulative: one copy per nested window the
    # article belongs to (overlap - counts must not be summed).
    expanded = expand_window_rows(df.to_dict("records"))

    # ---- group and aggregate ----------------------------------------
    groups: dict[tuple, list[dict]] = {}
    for r in expanded:
        groups.setdefault(tuple(r[k] for k in KEY_COLS),
                          []).append(r)

    rows, contributions = [], {}
    for key in sorted(groups, key=lambda k: tuple(map(str, k))):
        grp = groups[key]
        ids = sorted({g["article_id"] for g in grp})
        # one row per canonical article per group - a duplicate here
        # would double-count and must abort the build
        assert len(ids) == len(grp), f"duplicate article in {key}"
        vals = dict(zip(KEY_COLS, key))
        agg = aggregate_group(grp, issue_codes, frames)
        rows.append({**vals, **agg,
                     "aggregation_version": AGG_VERSION,
                     "features_version": grp[0]["features_version"],
                     "frozen_dataset_version":
                         grp[0]["frozen_dataset_version"]})
        contributions[row_key(vals)] = ids

    out = pd.DataFrame(rows)
    assert not out.duplicated(subset=KEY_COLS).any()
    out = out.sort_values(KEY_COLS, kind="mergesort").reset_index(
        drop=True)

    OUT_CSV.write_text(out.to_csv(index=False, lineterminator="\n"))
    out.to_parquet(OUT_PARQUET, index=False)
    OUT_CONTRIB.write_text(json.dumps(
        {"aggregation_version": AGG_VERSION,
         "row_key_fields": KEY_COLS,
         "contributions": contributions},
        indent=1, ensure_ascii=False) + "\n")

    # ---- audit statistics -------------------------------------------
    ind = out[out["window_type"] == "individual"]
    cum = out[out["window_type"] == "cumulative"]
    print(f"{len(out)} aggregate rows ({len(ind)} individual-window,"
          f" {len(cum)} cumulative-window), "
          f"{len(out.columns)} columns")
    print("rows per scope:",
          dict(Counter(out["scope_classification"])))
    print("rows per election:", dict(Counter(out["election_id"])))
    print("ward-level rows:", int((out["geographic_target_id"]
                                   .str.contains(":") &
                                   ~out["geographic_target_id"]
                                   .str.endswith("ELECTION_WIDE"))
                                  .sum()))
    print("groups with zero stance denom:",
          int((out["stance_denom"] == 0).sum()),
          "| with positive denom:",
          int((out["stance_denom"] > 0).sum()))
    print("reform aggregated rows:",
          int((out["reform_agg_status"] == "aggregated").sum()))
    biggest = out.loc[out["cov_n_articles"].idxmax()]
    print("largest group:", {k: biggest[k] for k in KEY_COLS},
          "n =", int(biggest["cov_n_articles"]))


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
