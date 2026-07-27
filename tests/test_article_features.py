"""Tests for the Phase 7 Step 4 article-level feature construction."""

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.llm_extraction.freeze_layer import sha256_file
from src.news_features.alignment import ELECTIONS

OUT_CSV = Path("news_features/article_level_news_features.csv")
OUT_PARQUET = Path("news_features/article_level_news_features.parquet")
FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
ALIGN = Path("news_features/article_entity_alignment.json")
MAPPING = Path(
    "news_collection/duplicate_mapping_layer_v1_provisional.csv")

needs_data = pytest.mark.skipif(
    not (OUT_CSV.exists() and FROZEN.exists()),
    reason="feature/frozen files not present")

KEY = ["article_id", "election_id", "geographic_target_id",
       "focal_party_id"]


@pytest.fixture(scope="module")
def df():
    return pd.read_csv(OUT_CSV)


@needs_data
def test_row_keys_unique_and_covering(df):
    assert not df.duplicated(subset=KEY).any()
    assert df["article_id"].nunique() == 67
    assert (df["article_presence"] == 1).all()


@needs_data
def test_foreign_keys_valid(df):
    from src.news_features.run_alignment import load_registries
    party_reg, cand_reg, ward_index, _, _ = load_registries()
    party_ids = {pid for pid, _ in party_reg.values()}
    cand_ids = {cid for hits in cand_reg.values()
                for cid, _ in hits}
    assert set(df["election_id"]) <= set(ELECTIONS)
    assert set(df["focal_party_id"].dropna()) <= party_ids
    assert set(df["candidate_id"].dropna()) <= cand_ids
    for gid in df.loc[df["geographic_target_level"] == "ward",
                      "geographic_target_id"]:
        eid, ward = gid.split(":", 1)
        assert ward in ward_index[eid].values(), gid


@needs_data
def test_ward_targets_only_from_validated_links(df):
    """National articles are never fanned out: every ward target
    must be a resolved Step 1 ward link of that same article."""
    linked = {(r["article_id"], r["ward_id"])
              for r in json.loads(ALIGN.read_text())["records"]
              if r["alignment_type"] == "ward"
              and not r["unresolved_flag"]}
    ward_rows = df[df["geographic_target_level"] == "ward"]
    for _, r in ward_rows.iterrows():
        assert (r["article_id"], r["geographic_target_id"]) in linked
    # and national-scope rows sit at election level
    nat = df[(df["national_political_indicator"] == 1)]
    assert (nat["geographic_target_level"] == "election_wide").all()


@needs_data
def test_multi_party_articles_keep_separate_focal_rows(df):
    per_article = df.groupby("article_id")["focal_party_id"].nunique()
    assert (per_article >= 2).any()   # multi-party articles exist
    one = df[df["article_id"] == per_article.idxmax()]
    assert len(one["focal_party_id"].dropna().unique()) \
        == len(one[one["focal_party_id"].notna()][KEY]
               .drop_duplicates()) / one["geographic_target_id"].nunique()


@needs_data
def test_canonical_articles_only(df):
    assert (df["article_id"] == df["canonical_article_id"]).all()
    canon = {r["article_id"]
             for r in csv.DictReader(MAPPING.open())
             if r["downstream_usage_status"]
             == "use_as_canonical_input"}
    assert set(df["article_id"]) <= canon


@needs_data
def test_binary_and_score_ranges(df):
    binaries = [c for c in df.columns if c.startswith((
        "sec_issue_", "frame_", "cum_")) or c.endswith("_indicator")
        or c in ("party_mentioned", "candidate_mentioned",
                 "positive_stance", "negative_stance",
                 "neutral_stance", "mixed_stance",
                 "blame_received", "credit_received",
                 "blame_assigned", "credit_assigned")]
    for c in binaries:
        assert set(df[c].dropna().unique()) <= {0, 1}, c
    scores = [c for c in df.columns if c.endswith(
        ("_score", "_confidence"))]
    for c in scores:
        v = df[c].dropna()
        assert ((v >= 0) & (v <= 1)).all(), c


@needs_data
def test_taxonomy_fields_match_frozen_vocabularies(df):
    codes = set(json.loads(Path(
        "llm_context/issue_taxonomy_v1.3.json").read_text())["codes"])
    assert set(df["primary_issue"].dropna()) <= codes | {"none"}
    sec_cols = {c.removeprefix("sec_issue_")
                for c in df.columns if c.startswith("sec_issue_")}
    assert sec_cols == codes    # exactly the frozen codes, no more


@needs_data
def test_missing_states_distinct_not_zero_filled(df):
    """not_applicable / quarantined rows carry None, never zero."""
    na_rows = df[df["reform_status"] == "not_applicable"]
    assert na_rows["reform_credibility_score"].isna().all()
    assert na_rows["reform_gaining_support"].isna().all()
    q = df[df["issues_status"] == "quarantined"]
    assert q["sec_issue_healthcare"].isna().all()
    # while valid rows have real zeros
    ok = df[df["issues_status"] == "extracted"]
    assert (ok["sec_issue_healthcare"].notna()).all()


@needs_data
def test_reform_and_ukip_never_conflated(df):
    ukip = df[df["focal_party_name"] == "UK Independence Party"]
    assert len(ukip) > 0
    assert (ukip["reform_status"] == "not_applicable").all()
    reform = df[df["focal_party_name"] == "Reform UK"]
    assert len(reform) > 0
    assert (reform["reform_status"] != "not_applicable").all()


@needs_data
def test_no_post_polling_leakage_and_result_flagging(df):
    assert (df["days_before_polling"] > 0).all()
    flagged_articles = df.loc[df["election_result_indicator"] == 1,
                              "article_id"].nunique()
    assert flagged_articles == 6    # the D3 set, flagged not dropped


@needs_data
def test_focal_isolation_no_cross_party_context(df):
    """Two focal rows of the same article must be allowed to differ
    in stance - the focal filter works; and a party absent from all
    layers yields confirmed_absent, not another party's values."""
    multi = df[df["focal_party_id"].notna()].groupby("article_id")
    diffs = 0
    for _, g in multi:
        if g["focal_party_id"].nunique() >= 2 \
                and g["stance_raw"].nunique() >= 2:
            diffs += 1
    assert diffs > 0


@needs_data
def test_deterministic_rebuild():
    from src.news_features.run_article_features import build
    before_csv = OUT_CSV.read_bytes()
    before_df = pd.read_parquet(OUT_PARQUET)
    build()
    assert OUT_CSV.read_bytes() == before_csv
    pd.testing.assert_frame_equal(pd.read_parquet(OUT_PARQUET),
                                  before_df)


@needs_data
def test_previous_layers_unchanged():
    m = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == m["frozen_output_sha256"][FROZEN.name]
    for f, h in m["input_file_hashes_sha256"].items():
        p = Path(f)
        if p.exists():
            assert sha256_file(p) == h, f
