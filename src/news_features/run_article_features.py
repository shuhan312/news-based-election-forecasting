"""Phase 7 / Step 4 runner: build the article-level feature layer.

    news_features/article_level_news_features.parquet
    news_features/article_level_news_features.csv

One row per article x election x geographic target x focal party.
All inputs read-only and hash-verified where a manifest hash
exists. The CSV is byte-deterministic; the parquet is
frame-deterministic (tested by re-read equality - parquet bytes
embed library metadata). No quote text enters the feature files.

Usage:
    python3 -m src.news_features.run_article_features build
"""

import csv as _csv
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from ..llm_extraction.freeze_layer import sha256_file
from . import article_features as af
from .run_alignment import load_registries

FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
ALIGN = Path("news_features/article_entity_alignment.json")
WINDOWS = Path("news_features/article_time_window_assignment.json")
SCOPE = Path("news_features/news_scope_classification.json")
MAPPING = Path("news_collection/duplicate_mapping_layer_v1_provisional.csv")
TAXONOMY = Path("llm_context/issue_taxonomy_v1.3.json")
FRAME_SCHEMA = Path("llm_context/framing_detection_schema_v1.json")

OUT_PARQUET = Path("news_features/article_level_news_features.parquet")
OUT_CSV = Path("news_features/article_level_news_features.csv")


def frame_categories() -> list[str]:
    """The approved 16-frame enum, read from the frozen schema file
    (never hand-copied, so a taxonomy edit cannot desync silently)."""
    txt = json.loads(FRAME_SCHEMA.read_text())
    def find(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "frame_category" and isinstance(v, dict) \
                        and "enum" in v:
                    return v["enum"]
                r = find(v)
                if r:
                    return r
        elif isinstance(node, list):
            for item in node:
                r = find(item)
                if r:
                    return r
    cats = find(txt)
    assert cats, "frame enum not found in frozen schema"
    return cats


def build() -> None:
    manifest = json.loads(MANIFEST.read_text())
    frozen_hash = sha256_file(FROZEN)
    assert frozen_hash \
        == manifest["frozen_output_sha256"][FROZEN.name]

    cards = {c["article_id"]: c
             for c in json.loads(FROZEN.read_text())["cards"]}
    align = json.loads(ALIGN.read_text())
    windows = {r["article_id"]: r
               for r in json.loads(WINDOWS.read_text())["assigned"]}
    scope = {r["article_id"]: r
             for r in json.loads(SCOPE.read_text())["records"]}
    taxonomy_codes = sorted(json.loads(
        TAXONOMY.read_text())["codes"].keys())
    frames = frame_categories()
    party_reg, cand_reg, ward_index, results_index, _ = \
        load_registries()

    # canonical duplicate gate: only use_as_canonical_input articles
    # may contribute (they are the pilot corpus by construction -
    # asserted, not assumed)
    canonical = {r["article_id"]: r["canonical_article_id"]
                 for r in _csv.DictReader(MAPPING.open())
                 if r["downstream_usage_status"]
                 == "use_as_canonical_input"}

    # ---- per-article link sets from Step 1 --------------------------
    wards, parties, unresolved_w, unresolved_p, cand_links = \
        ({} for _ in range(5))
    party_names = {}   # (aid, pid) -> {normalised mention strings}
    std_name = {}      # pid -> standardised party name
    for r in align["records"]:
        aid = r["article_id"]
        t = r["alignment_type"]
        if t == "ward":
            if r["unresolved_flag"]:
                unresolved_w[aid] = unresolved_w.get(aid, 0) + 1
            elif r["ward_id"]:
                wards.setdefault(aid, set()).add(r["ward_id"])
        elif t == "party":
            if r["unresolved_flag"]:
                unresolved_p[aid] = unresolved_p.get(aid, 0) + 1
            elif r["party_id"]:
                parties.setdefault(aid, set()).add(r["party_id"])
                std_name[r["party_id"]] = r["matched_entity"]
                party_names.setdefault(
                    (aid, r["party_id"]), set()).add(
                    af.norm(r.get("party_name_as_mentioned")
                            or r["matched_entity"]))
        elif t == "candidate" and not r["unresolved_flag"]:
            cand_links.setdefault(aid, []).append(r["candidate_id"])

    reform_pid = next(pid for pid, name in std_name.items()
                      if name == "Reform UK") \
        if any(n == "Reform UK" for n in std_name.values()) else None

    # ---- assemble rows ----------------------------------------------
    rows = []
    for aid in sorted(cards):
        card = cards[aid]
        meta = card["article_metadata"]
        assert aid in canonical and canonical[aid] == aid, \
            f"non-canonical article {aid} must not contribute"
        targets = sorted(wards.get(aid, set())) or [ELECTION := None]
        focals = sorted(parties.get(aid, set())) or [None]
        w = windows[aid]
        s = scope[aid]
        ce = card.get("confidence_evidence") or {}
        summ = ce.get("summary") or {}
        extraction_conf = (round(1 - summ["review_required"]
                                 / summ["total_claims"], 3)
                          if summ.get("total_claims") else None)
        flagged_layers = [k for k, v in
                          card["validation_status"]["per_layer"]
                          .items() if v == "flagged"]
        for target in targets:
            for pid in focals:
                names = party_names.get((aid, pid), set()) \
                    | ({af.norm(std_name[pid])} if pid else set())
                base = {
                    "article_id": aid,
                    "canonical_article_id":
                        meta["canonical_article_id"],
                    "election_id": meta["election_id"],
                    "geographic_target_id":
                        target or f"{meta['election_id']}:"
                                  f"{af.ELECTION_WIDE}",
                    "geographic_target_level":
                        "ward" if target else "election_wide",
                    "focal_party_id": pid,
                    "focal_party_name":
                        std_name.get(pid) if pid else None,
                    "candidate_id": (cand_links.get(aid) or [None])[0],
                    "publication_id": meta["source"],
                    "source_type": meta["arm"],
                    "article_presence": 1,
                    "full_text_availability": "valid_full_text",
                    "extraction_confidence": extraction_conf,
                    "human_review_status": ("flagged"
                                            if flagged_layers
                                            else "auto_validated"),
                    "flagged_layer_count": len(flagged_layers),
                    "unresolved_ward_mentions":
                        unresolved_w.get(aid, 0),
                    "unresolved_party_mentions":
                        unresolved_p.get(aid, 0),
                    "features_version": af.FEATURES_VERSION,
                    "frozen_dataset_version":
                        manifest["dataset_version"],
                }
                base.update(af.mention_features(card, pid, names,
                                                party_reg))
                base.update(af.scope_features(
                    s, bool(target), unresolved_w.get(aid, 0)))
                base.update(af.issue_features(
                    card, taxonomy_codes,
                    "contains_election_result" in w["flags"]))
                base.update(af.stance_features(card, pid, names,
                                               party_reg))
                base.update(af.framing_features(card, frames))
                base.update(af.attribution_features(card, pid, names,
                                                    party_reg))
                base.update(af.consequence_features(card, pid, names,
                                                    party_reg))
                base.update(af.reform_features(
                    card, focal_is_reform=(pid is not None
                                           and pid == reform_pid)))
                base.update(af.temporal_features(card, w))
                rows.append(base)

    df = pd.DataFrame(rows)
    key = ["article_id", "election_id", "geographic_target_id",
           "focal_party_id"]
    dup = df.duplicated(subset=key)
    assert not dup.any(), "row keys not unique"
    df = df.sort_values(key, na_position="first",
                        kind="mergesort").reset_index(drop=True)

    OUT_CSV.write_text(df.to_csv(index=False, lineterminator="\n"))
    df.to_parquet(OUT_PARQUET, index=False)

    # ---- audit statistics -------------------------------------------
    print(f"{len(df)} rows, {df['article_id'].nunique()} articles, "
          f"{len(df.columns)} columns -> {OUT_CSV.name}/.parquet")
    print("rows per election:",
          dict(Counter(df["election_id"])))
    print("target levels:",
          dict(Counter(df["geographic_target_level"])))
    print("focal parties:",
          dict(Counter(df["focal_party_name"].fillna("(none)"))))
    for col in ("mention_status", "stance_status",
                "attribution_status", "consequence_status",
                "reform_status", "issues_status", "framing_status",
                "temporal_llm_status"):
        print(f"{col}:", dict(Counter(df[col])))
    print("result-flagged rows:",
          int(df["election_result_indicator"].sum()))


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
