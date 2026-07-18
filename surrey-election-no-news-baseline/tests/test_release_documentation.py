"""Tie headline documentation to the local extractor contract when available."""

import json
from pathlib import Path

import pytest

from no_news_baseline.persistence_benchmark import evaluate_previous_result_persistence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIRECTORY = (
    PROJECT_ROOT.parent
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)


def test_documented_release_matches_local_generated_contract() -> None:
    """Check live release claims, but allow clean clones without generated data."""

    feature_path = INPUT_DIRECTORY / "no_news_party_contest_features.json"
    target_path = INPUT_DIRECTORY / "no_news_party_contest_targets.json"
    if not feature_path.exists() or not target_path.exists():
        pytest.skip("Regenerate the extractor party-contest contract for release QA.")

    features = json.loads(feature_path.read_text(encoding="utf-8"))["rows"]
    targets = json.loads(target_path.read_text(encoding="utf-8"))["rows"]
    _, metrics, audit = evaluate_previous_result_persistence(features, targets)
    text = (PROJECT_ROOT / "docs/persistence_benchmark.md").read_text(encoding="utf-8")
    overall = metrics["overall"]

    assert f"{audit['primary_party_share_rows']:,} rows" in text
    assert f"{audit['primary_single_member_areas']:,} approved" in text
    assert f"{audit['winner_area_status_eligible_unique_previous_winner_on_current_ballot']:,} areas" in text
    assert f"{audit['winner_area_status_unavailable_previous_winner_not_uniquely_on_current_ballot']:,} areas" in text
    assert f"{overall['party_share_mae_percentage_points']:.2f}" in text
    assert f"{overall['party_share_rmse_percentage_points']:.2f}" in text
    assert f"{overall['winner_area_accuracy']:.1%}" in text
