"""Measure what the keyword prefilter keeps and what it loses, on V1 data.

Three questions, all answered from V1 articles already on disk (no API call,
no human labelling):

  M1  feature recall: of the articles that actually fed V1's party features
      (at least one LLM stance judgement on a party), how many pass? These
      are the articles V2 cannot afford to lose. Primary.
  M2  relevance recall: of the local articles a human judged relevant, how
      many pass? Secondary, because a relevant article that names no party
      and uses no civic word cannot feed party features anyway.
  M3  removal rate: of the local articles a human judged irrelevant, how many
      are removed? This is the filter's benefit. Reported, no bar.

Usage:
  PYTHONPATH=.:src python -m v2_design.prefilter_eval            # dev only
  PYTHONPATH=.:src python -m v2_design.prefilter_eval --split test

The test split is run once, on the final keyword version, as fixed in
v2_design/keyword_prefilter_v1/criteria.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from src.news_features.build_feature_table import load_records
from v2_design import keyword_prefilter as kp
from v2_design.local_relevance_eval import human_labels, load_split

TEXT_DIR = Path("data/raw/news/text")
RECORD_DIR = Path("data/raw/news/records")
OUT_DIR = Path("v2_design/keyword_prefilter_v1")
SALT = "v2-prefilter-2026-10-07"
RESAMPLES, SEED = 2000, 20261007


def text_of(article_id: str) -> str:
    return (TEXT_DIR / f"{article_id}.txt").read_text(encoding="utf-8",
                                                      errors="replace")


def stance_split(article_id: str) -> str:
    # The 1,945 feature articles are not in the classifier split, so they get
    # their own 50/50 split. A salted hash of the id alone decides, so no
    # property of the article can steer it.
    digest = hashlib.sha256(f"{SALT}:{article_id}".encode()).hexdigest()
    return "test" if int(digest, 16) % 2 == 0 else "dev"


def feature_articles() -> list[dict]:
    """V1 articles with at least one party stance judgement, with arm."""
    records, _ = load_records()
    out = []
    for aid, rec in records["stance_revised"].items():
        if rec["record"].get("judgements"):
            arm = json.loads((RECORD_DIR / f"{aid}.json").read_text())["arm"]
            out.append({"article_id": aid, "arm": arm,
                        "split": stance_split(aid)})
    return out


def rate_with_ci(flags: list[bool]) -> dict:
    """Share of True with a percentile bootstrap interval."""
    a = np.array(flags, dtype=float)
    if len(a) == 0:
        return {"n": 0}
    rng = np.random.default_rng(SEED)
    draws = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(RESAMPLES)]
    return {"n": int(len(a)), "rate": round(float(a.mean()), 4),
            "ci95": [round(float(np.percentile(draws, q)), 4) for q in (2.5, 97.5)]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    split = parser.parse_args().split

    # --- M1: feature recall ------------------------------------------------
    feats = [f for f in feature_articles() if f["split"] == split]
    passed = {f["article_id"]: kp.passes(text_of(f["article_id"])) for f in feats}
    m1 = {
        "all": rate_with_ci([passed[f["article_id"]] for f in feats]),
        "local_arm": rate_with_ci([passed[f["article_id"]] for f in feats
                                   if f["arm"] == "local"]),
        "national_arm": rate_with_ci([passed[f["article_id"]] for f in feats
                                      if f["arm"] == "national"]),
    }
    # The misses are the most useful output: each one shows a gap in the list.
    m1_misses = sorted(aid for aid, ok in passed.items() if not ok)

    # --- M2 and M3: human-labelled local articles --------------------------
    labels = human_labels()
    rows = [r for r in load_split() if r["split"] == split]
    rel = {r["article_id"]: kp.passes(text_of(r["article_id"])) for r in rows}
    includes = [r["article_id"] for r in rows if labels[r["article_id"]] == 1]
    excludes = [r["article_id"] for r in rows if labels[r["article_id"]] == 0]
    m2 = rate_with_ci([rel[a] for a in includes])
    m3 = rate_with_ci([not rel[a] for a in excludes])
    m2_misses = sorted(a for a in includes if not rel[a])

    # Which keywords did the work: how often each term appears among the
    # passing feature articles. A term that never fires is dead weight; one
    # that fires everywhere is the reason the filter passes what it passes.
    term_counts = Counter(t for f in feats if passed[f["article_id"]]
                          for t in kp.matched_terms(text_of(f["article_id"])))

    payload = {
        "keyword_version": kp.VERSION,
        "split": split,
        "criteria": "v2_design/keyword_prefilter_v1/criteria.md",
        "M1_feature_recall": m1,
        "M2_relevance_recall_local": m2,
        "M3_removal_rate_local_irrelevant": m3,
        "term_counts_in_passing_feature_articles": term_counts.most_common(),
        "M1_missed_article_ids": m1_misses,
        "M2_missed_article_ids": m2_misses,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"prefilter_{kp.VERSION}_{split}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items()
                      if not k.endswith("article_ids")
                      and not k.startswith("term_counts")}, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
