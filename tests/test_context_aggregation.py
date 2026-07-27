"""Tests for the Phase 7 Step 5 context aggregation."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.llm_extraction.freeze_layer import sha256_file
from src.news_features.context_aggregation import KEY_COLS

AGG_CSV = Path("news_features/context_aggregated_features.csv")
CONTRIB = Path("news_features/context_aggregation_contributions.json")
ART_CSV = Path("news_features/article_level_news_features.csv")
FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")

needs_data = pytest.mark.skipif(
    not (AGG_CSV.exists() and ART_CSV.exists()),
    reason="aggregation inputs not present")


@pytest.fixture(scope="module")
def agg():
    return pd.read_csv(AGG_CSV)


@pytest.fixture(scope="module")
def art():
    return pd.read_csv(ART_CSV)


@needs_data
def test_keys_unique_counts_nonneg_props_in_range(agg):
    assert not agg.duplicated(subset=KEY_COLS).any()
    for c in [c for c in agg.columns if c.endswith("_n")
              or c.startswith("cov_n")]:
        v = agg[c].dropna()
        assert (v == v.astype(int)).all(), c
        if c != "net_credit_minus_blame_n":   # net may be negative
            assert (v >= 0).all(), c
    for c in [c for c in agg.columns if c.endswith("_prop")]:
        v = agg[c].dropna()
        assert ((v >= 0) & (v <= 1)).all(), c


@needs_data
def test_exact_count_reconciliation_individual_windows(agg, art):
    """Individual windows partition articles, so summing group
    counts across windows must reproduce the article layer exactly
    for every election x target x party x scope combination."""
    ind = agg[agg["window_type"] == "individual"]
    art2 = art.copy()
    art2["focal_party_id"] = art2["focal_party_id"].fillna(
        "(no_focal_party)")
    got = ind.groupby(["election_id", "geographic_target_id",
                       "focal_party_id", "scope_classification"]
                      )["cov_n_articles"].sum()
    want = art2.groupby(["election_id", "geographic_target_id",
                         "focal_party_id", "scope_classification"]
                        )["article_id"].nunique()
    pd.testing.assert_series_equal(
        got.sort_index(), want.sort_index(), check_names=False)


@needs_data
def test_stance_counts_reconcile_for_focal_party(agg, art):
    """Focal-party stance separation: one concrete group's negative
    count must equal the article layer filtered to exactly that
    focal party - no other party's stance leaks in."""
    ind = agg[(agg["window_type"] == "individual")
              & (agg["stance_denom"] > 0)]
    row = ind.loc[ind["negative_stance_n"].idxmax()]
    subset = art[
        (art["election_id"] == row["election_id"])
        & (art["geographic_target_id"]
           == row["geographic_target_id"])
        & (art["focal_party_id"] == row["focal_party_id"])
        & (art["scope_classification"]
           == row["scope_classification"])
        & (art["individual_time_window"] == row["window"])]
    assert int(subset["negative_stance"].sum()) \
        == int(row["negative_stance_n"])


@needs_data
def test_multi_label_issues_any_geq_primary(agg):
    codes = [c.removeprefix("issue_").removesuffix("_primary_n")
             for c in agg.columns if c.startswith("issue_")
             and c.endswith("_primary_n")]
    for c in codes:
        ok = agg[f"issue_{c}_any_n"] >= agg[f"issue_{c}_primary_n"]
        assert ok.all(), c
    # a single primary per article: primaries sum <= issues_denom
    prim_cols = [f"issue_{c}_primary_n" for c in codes]
    assert (agg[prim_cols].sum(axis=1) <= agg["issues_denom"]).all()


@needs_data
def test_zero_observation_vs_no_news_distinct(agg):
    """denominator 0 -> proportion None (no news observed);
    denominator > 0 with zero signal -> real 0.0."""
    no_news = agg[agg["stance_denom"] == 0]
    assert len(no_news) > 0
    assert no_news["positive_stance_prop"].isna().all()
    observed_zero = agg[(agg["stance_denom"] > 0)
                        & (agg["positive_stance_n"] == 0)]
    assert len(observed_zero) > 0
    assert (observed_zero["positive_stance_prop"] == 0).all()


@needs_data
def test_national_rows_stay_election_wide(agg):
    nat = agg[agg["scope_classification"] == "national_political"]
    assert nat["geographic_target_id"].str.endswith(
        "ELECTION_WIDE").all()


@needs_data
def test_reform_and_ukip_separation(agg, art):
    ukip_pid = art.loc[art["focal_party_name"]
                       == "UK Independence Party",
                       "focal_party_id"].iloc[0]
    reform_pid = art.loc[art["focal_party_name"] == "Reform UK",
                         "focal_party_id"].iloc[0]
    assert (agg.loc[agg["focal_party_id"] == ukip_pid,
                    "reform_agg_status"] == "not_applicable").all()
    assert (agg.loc[agg["focal_party_id"] == reform_pid,
                    "reform_agg_status"] == "aggregated").all()


@needs_data
def test_contribution_mapping_full_provenance(agg):
    data = json.loads(CONTRIB.read_text())
    contrib = data["contributions"]
    assert len(contrib) == len(agg)
    for _, row in agg.iterrows():
        key = "|".join(str(row[k]) for k in KEY_COLS)
        ids = contrib[key]
        assert len(ids) == len(set(ids)) == row["cov_n_articles"]


@needs_data
def test_cumulative_nesting_monotone(agg):
    """Within one election x target x party x scope, a smaller
    cumulative window can never contain more articles than a larger
    one."""
    order = ["previous_72_hours", "previous_7_days",
             "previous_14_days", "previous_30_days",
             "previous_90_days", "previous_180_days"]
    cum = agg[agg["window_type"] == "cumulative"]
    for _, g in cum.groupby(["election_id", "geographic_target_id",
                             "focal_party_id",
                             "scope_classification"]):
        counts = {r["window"]: r["cov_n_articles"]
                  for _, r in g.iterrows()}
        present = [w for w in order if w in counts]
        for a, b in zip(present, present[1:]):
            assert counts[a] <= counts[b]


@needs_data
def test_deterministic_rebuild_and_previous_unchanged():
    m = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == m["frozen_output_sha256"][FROZEN.name]
    art_before = ART_CSV.read_bytes()
    from src.news_features.run_context_aggregation import build
    before = AGG_CSV.read_bytes()
    build()
    assert AGG_CSV.read_bytes() == before
    assert ART_CSV.read_bytes() == art_before   # input untouched
