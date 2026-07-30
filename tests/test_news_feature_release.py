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
