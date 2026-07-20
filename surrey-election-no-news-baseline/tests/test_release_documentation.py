"""Tie headline documentation to the local extractor contract when available."""

import json
import re
from pathlib import Path

import pytest

from no_news_baseline.persistence_benchmark import evaluate_previous_result_persistence
from no_news_baseline.electoral_fundamentals_release import (
    RELEASE_METHOD_VERSION,
    create_electoral_fundamentals_release,
)


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


def test_frozen_feature_record_matches_current_release(tmp_path: Path) -> None:
    """Fail when code or extractor inputs drift beyond the frozen release."""

    required = (
        INPUT_DIRECTORY / "no_news_party_contest_features.json",
        INPUT_DIRECTORY / "no_news_party_contest_targets.json",
        PROJECT_ROOT.parent
        / "surrey-election-extractor/outputs/master_surrey_election_database/master_election_database_payload.json",
        PROJECT_ROOT.parent
        / "surrey-election-extractor/outputs/geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json",
    )
    if not all(path.exists() for path in required):
        pytest.skip("Regenerate extractor outputs for frozen-release QA.")

    # Regenerate into pytest's temporary directory so this check does not
    # depend on, or modify, the ignored publication output directory.
    _, _, _, report_path = create_electoral_fundamentals_release(
        *required,
        output_directory=tmp_path,
    )
    report = report_path.read_text(encoding="utf-8")
    record = (PROJECT_ROOT / "docs/electoral_feature_release.md").read_text(
        encoding="utf-8"
    )

    input_version = re.search(r"\*\*Input data version:\*\* `([^`]+)`", report)
    release_version = re.search(r"\*\*Release version:\*\* `([^`]+)`", report)
    assert input_version and input_version.group(1) in record
    assert release_version and release_version.group(1) in record
    assert RELEASE_METHOD_VERSION in record
    assert "Rows and unique keys: 1,592" in record
