"""Tests for the Phase 7 Step 6 recency weighting layer."""

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from src.llm_extraction.freeze_layer import sha256_file
from src.news_features.context_aggregation import KEY_COLS
from src.news_features.recency_weighting import (HALF_LIVES,
                                                 PRIMARY_HALF_LIFE,
                                                 lambda_for,
                                                 recency_weight,
                                                 weighted_group)

W_CSV = Path("news_features/recency_weighted_features.csv")
AGG_CSV = Path("news_features/context_aggregated_features.csv")
EXCL = Path("news_features/recency_weighting_exclusions.json")
FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
WKEY = KEY_COLS + ["half_life_days"]

needs_data = pytest.mark.skipif(
    not (W_CSV.exists() and AGG_CSV.exists()),
    reason="weighted/aggregated files not present")


# ---- formula unit tests --------------------------------------------

def test_lambda_matches_half_life_definition():
    for h in HALF_LIVES:
        lam = lambda_for(h)
        assert math.isclose(lam, math.log(2) / h)
        # an article exactly one half-life old counts half
        assert math.isclose(recency_weight(h, h)[0], 0.5)


def test_weight_formula_exact_values():
    w, reason = recency_weight(30, 30)
    assert reason is None and math.isclose(w, 0.5)
    assert math.isclose(recency_weight(60, 30)[0], 0.25)
    assert math.isclose(recency_weight(1, 30)[0],
                        math.exp(-math.log(2) / 30))


def test_recent_articles_weigh_more_and_range_valid():
    for h in HALF_LIVES:
        ws = [recency_weight(d, h)[0] for d in (1, 3, 7, 30, 90, 180)]
        assert all(a > b for a, b in zip(ws, ws[1:]))   # monotone
        assert all(0 < w <= 1 for w in ws)


def test_missing_or_post_polling_dates_get_no_weight():
    for bad in (None, float("nan"), "", 0, -5):
        w, reason = recency_weight(bad, PRIMARY_HALF_LIFE)
        assert w is None and reason in (
            "incomplete_publication_date", "post_or_on_polling_day")


def test_weighted_group_uses_weighted_denominators():
    rows = [{"publication_id": "P", "source_type": "local",
             "stance_status": "extracted", "negative_stance": 1,
             "party_mentioned": 1},
            {"publication_id": "P", "source_type": "local",
             "stance_status": "extracted", "negative_stance": 0,
             "party_mentioned": 1}]
    out = weighted_group(rows, [0.8, 0.2], [], [], ["negative_stance"],
                         [], [])
    assert math.isclose(out["w_stance_denom"], 1.0)
    assert math.isclose(out["w_negative_stance_n"], 0.8)
    assert math.isclose(out["w_negative_stance_prop"], 0.8)
    # a publication contributes via its most recent article
    assert math.isclose(out["weighted_publication_count"], 0.8)


def test_zero_weighted_denominator_gives_none_not_zero():
    rows = [{"publication_id": "P", "source_type": "local",
             "stance_status": "quarantined"}]
    out = weighted_group(rows, [0.5], [], [], ["negative_stance"],
                         [], [])
    assert out["w_stance_denom"] == 0
    assert out["w_negative_stance_prop"] is None


# ---- integrity tests against the real files ------------------------

@pytest.fixture(scope="module")
def wdf():
    return pd.read_csv(W_CSV)


@pytest.fixture(scope="module")
def agg():
    return pd.read_csv(AGG_CSV)


@needs_data
def test_keys_unique_and_grid_complete(wdf, agg):
    assert not wdf.duplicated(subset=WKEY).any()
    assert set(wdf["half_life_days"]) == set(HALF_LIVES)
    # one weighted row per Step 5 row per half-life
    assert len(wdf) == len(agg) * len(HALF_LIVES)


@needs_data
def test_aggregation_keys_match_step5_exactly(wdf, agg):
    """Provenance: the weighted layer aggregates exactly the same
    groups as the unweighted one - no group appears or disappears."""
    a = agg[KEY_COLS].apply(tuple, axis=1)
    for h in HALF_LIVES:
        w = wdf[wdf["half_life_days"] == h][KEY_COLS].apply(
            tuple, axis=1)
        assert set(w) == set(a)


@needs_data
def test_weighted_counts_below_unweighted_and_ordered(wdf):
    """Every weight is <= 1, so weighted mass never exceeds the raw
    count; and longer half-lives always retain more mass."""
    assert (wdf["weighted_article_count"]
            <= wdf["unweighted_article_count"] + 1e-9).all()
    masses = [wdf.loc[wdf["half_life_days"] == h,
                      "weighted_article_count"].sum()
              for h in sorted(HALF_LIVES)]
    assert all(a < b for a, b in zip(masses, masses[1:]))


@needs_data
def test_weighted_proportions_in_range(wdf):
    for c in [c for c in wdf.columns if c.endswith("_prop")]:
        v = wdf[c].dropna()
        assert ((v >= 0) & (v <= 1 + 1e-9)).all(), c


@needs_data
def test_local_and_national_stay_separate(wdf):
    nat = wdf[wdf["scope_classification"] == "national_political"]
    assert nat["geographic_target_id"].str.endswith(
        "ELECTION_WIDE").all()
    assert wdf["scope_classification"].nunique() >= 4


@needs_data
def test_reform_and_ukip_separation_survives_weighting(wdf):
    art = pd.read_csv(
        "news_features/article_level_news_features.csv")
    ukip = art.loc[art["focal_party_name"] == "UK Independence Party",
                   "focal_party_id"].iloc[0]
    reform = art.loc[art["focal_party_name"] == "Reform UK",
                     "focal_party_id"].iloc[0]
    assert (wdf.loc[wdf["focal_party_id"] == ukip,
                    "w_reform_agg_status"] == "not_applicable").all()
    assert (wdf.loc[wdf["focal_party_id"] == reform,
                    "w_reform_agg_status"] == "aggregated").all()


@needs_data
def test_no_post_polling_contributions_and_exclusions_recorded(wdf):
    data = json.loads(EXCL.read_text())
    assert data["excluded_count"] == len(data["exclusions"])
    assert (wdf["n_articles_excluded_no_date"].sum()
            == data["excluded_count"])
    art = pd.read_csv(
        "news_features/article_level_news_features.csv")
    assert (art["days_before_polling"] > 0).all()


@needs_data
def test_original_features_unchanged_and_rebuild_deterministic():
    m = json.loads(MANIFEST.read_text())
    assert sha256_file(FROZEN) \
        == m["frozen_output_sha256"][FROZEN.name]
    agg_before = AGG_CSV.read_bytes()
    before = W_CSV.read_bytes()
    from src.news_features.run_recency_weighting import build
    build()
    assert W_CSV.read_bytes() == before
    assert AGG_CSV.read_bytes() == agg_before
