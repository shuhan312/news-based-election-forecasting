"""Tests for the gate between the full-corpus features and news models."""

from pathlib import Path

import pytest

from src.news_modelling.production_estimability import (
    ProductionAuditError,
    build_estimability_report,
)


ROOT = Path("surrey-election-no-news-baseline/outputs/model_bundle_v1")

# The Stage 1 bundle is a local-by-design artefact (OneDrive copy; see the
# README's large-artefacts table), so a fresh clone skips rather than fails.
pytestmark = pytest.mark.skipif(
    not (ROOT / "out_of_fold_predictions.csv").exists(),
    reason="requires the local Stage 1 model bundle (OneDrive; README large-artefacts table)",
)


def build_report():
    return build_estimability_report(
        "news_features/news_feature_table_v1.csv",
        "news_features/news_feature_table_v1_metadata.json",
        ROOT / "out_of_fold_predictions.csv",
    )


def test_report_freezes_corpus_windows_and_analysis_roles():
    report = build_report()

    assert report["canonical_release"]["articles"] == 1632
    assert report["canonical_release"]["local_articles"] == 188
    assert report["feature_table"]["rows"] == 288
    assert report["frozen_feature_sets"]["local_sensitivity"][
        "analysis_role"
    ] == "sensitivity_only"


def test_report_states_the_actual_reform_limit():
    report = build_report()

    assert report["baseline_overlap"]["SCC-2017-05"]["reform_uk_rows"] == 0
    assert report["baseline_overlap"]["SCC-2021-05"]["reform_uk_rows"] == 6
    assert report["estimability"]["reform_specific_news_coefficient"] == (
        "not_estimable"
    )


def test_2026_in_out_of_fold_is_a_hard_failure(tmp_path):
    unsafe = tmp_path / "out_of_fold.csv"
    source = (ROOT / "out_of_fold_predictions.csv").read_text(encoding="utf-8")
    header, first, *rest = source.splitlines()
    columns = header.split(",")
    values = first.split(",")
    values[columns.index("election_id")] = "unsafe-2026-election"
    unsafe.write_text("\n".join([header, ",".join(values), *rest]) + "\n")

    with pytest.raises(ProductionAuditError, match="2026 appears"):
        build_estimability_report(
            "news_features/news_feature_table_v1.csv",
            "news_features/news_feature_table_v1_metadata.json",
            unsafe,
        )
