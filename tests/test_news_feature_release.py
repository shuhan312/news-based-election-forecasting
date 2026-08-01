"""Regression tests for the production full-corpus news feature table."""

import csv
import json
from pathlib import Path

from src.news_collection.canonical_corpus_release import build_release


def test_feature_rows_reconcile_local_and_national_party_counts():
    """Combined portrayal counts must equal the two collection arms."""

    path = Path("news_features/news_feature_table_v1.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        for stem in (
            "party_article_count",
            "unfavourable_count",
            "favourable_count",
        ):
            assert int(row[stem]) == (
                int(row[f"local_{stem}"]) + int(row[f"national_{stem}"])
            )


def test_feature_metadata_names_the_canonical_release():
    """A current feature table without a release id is not model-ready."""

    release, _ = build_release()
    metadata = json.loads(
        Path("news_features/news_feature_table_v1_metadata.json").read_text()
    )
    assert metadata["canonical_corpus_release_id"] == release["release_id"]
    assert metadata["canonical_corpus_by_arm"] == {
        "local": 188,
        "national": 1444,
    }


def test_feature_table_is_a_complete_design_grid():
    """A zero-news period is data and must not disappear from the table."""

    path = Path("news_features/news_feature_table_v1.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    elections = {row["election_id"] for row in rows}
    parties = {row["standard_party_key"] for row in rows}
    periods = {row["period"] for row in rows}
    keys = {
        (row["election_id"], row["standard_party_key"], row["period"])
        for row in rows
    }

    assert len(rows) == len(keys) == len(elections) * len(parties) * len(periods)
    assert len(rows) == 4 * 6 * 12 == 288


def test_zero_article_periods_keep_zero_counts_and_undefined_shares():
    """Do not turn an empty search result into either a missing row or 0/0."""

    path = Path("news_features/news_feature_table_v1.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    empty = [
        row for row in rows
        if row["election_id"] == "SCC-2017-05"
        and row["period"] == "final_72_hours"
    ]
    assert len(empty) == 6
    assert all(row["article_count"] == "0" for row in empty)
    assert all(row["party_article_count"] == "0" for row in empty)
    assert all(row["party_article_share"] == "" for row in empty)
