"""Integration checks for the JSON-contract benchmark runner."""

import json
from pathlib import Path

from scripts.run_persistence_benchmark import run_persistence_benchmark


def test_runner_reads_contract_and_writes_all_release_files(tmp_path: Path) -> None:
    features = {
        "rows": [
            {
                "party_contest_id": "a",
                "election_id": "2017",
                "election_year": 2017,
                "election_type": "County Council election",
                "division_id": "area",
                "division_name": "Area",
                "standard_party_name": "Party A",
                "contest_structure": "single_member",
                "geographic_reference_eligibility": "approved_historical_reference",
                "party_identity_scope": "reviewed_standard_party",
                "baseline_eligibility": "eligible_primary_single_member_party_share",
                "previous_party_vote_share": 60.0,
                "party_was_previous_winner": True,
                "historical_source_url": "https://official.example/previous",
            },
            {
                "party_contest_id": "b",
                "election_id": "2017",
                "election_year": 2017,
                "election_type": "County Council election",
                "division_id": "area",
                "division_name": "Area",
                "standard_party_name": "Party B",
                "contest_structure": "single_member",
                "geographic_reference_eligibility": "approved_historical_reference",
                "party_identity_scope": "reviewed_standard_party",
                "baseline_eligibility": "eligible_primary_single_member_party_share",
                "previous_party_vote_share": 40.0,
                "party_was_previous_winner": False,
                "historical_source_url": "https://official.example/previous",
            },
        ]
    }
    targets = {
        "rows": [
            {
                "party_contest_id": "a",
                "target_party_vote_share": 55.0,
                "target_party_elected": "Yes",
                "target_source_urls": "https://official.example/current",
            },
            {
                "party_contest_id": "b",
                "target_party_vote_share": 45.0,
                "target_party_elected": "No",
                "target_source_urls": "https://official.example/current",
            },
        ]
    }
    feature_path = tmp_path / "features.json"
    target_path = tmp_path / "targets.json"
    output = tmp_path / "release"
    feature_path.write_text(json.dumps(features), encoding="utf-8")
    target_path.write_text(json.dumps(targets), encoding="utf-8")

    audit_path = run_persistence_benchmark(feature_path, target_path, output)

    assert audit_path == output / "previous_result_persistence_audit.json"
    assert audit_path.exists()
    assert (output / "previous_result_persistence_predictions.json").exists()
    assert (output / "previous_result_persistence_metrics.json").exists()
    metrics = json.loads(
        (output / "previous_result_persistence_metrics.json").read_text(encoding="utf-8")
    )
    assert metrics["overall"]["party_share_mae_percentage_points"] == 5.0
