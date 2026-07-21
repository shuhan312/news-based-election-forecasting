"""Integration check for the temporal-validation-report command-line runner."""

import json
from pathlib import Path

from scripts.run_temporal_validation_report import run_temporal_validation_report


def test_runner_reads_contract_and_writes_the_report(tmp_path: Path) -> None:
    features = {
        "rows": [
            {
                "party_contest_id": "e13",
                "election_id": "2013",
                "election_date": "2 May 2013",
                "election_year": 2013,
                "election_type": "County Council election",
                "division_id": "area",
                "division_name": "Area",
                "standard_party_name": "Party A",
                "contest_structure": "single_member",
                "geographic_reference_eligibility": "approved_historical_reference",
                "party_identity_scope": "reviewed_standard_party",
                "baseline_eligibility": "excluded_no_approved_exact_label_previous_party_share",
                "previous_party_vote_share": None,
                "party_was_previous_winner": None,
                "historical_source_url": "https://official.example/previous",
            },
            {
                "party_contest_id": "e17",
                "election_id": "2017",
                "election_date": "4 May 2017",
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
        ]
    }
    targets = {
        "rows": [
            {
                "party_contest_id": "e13",
                "standard_party_name": "Party A",
                "target_party_vote_share": 60.0,
                "target_party_elected": "Yes",
                "target_source_urls": "https://official.example/current",
            },
            {
                "party_contest_id": "e17",
                "standard_party_name": "Party A",
                "target_party_vote_share": 55.0,
                "target_party_elected": "Yes",
                "target_source_urls": "https://official.example/current",
            },
        ]
    }
    feature_path = tmp_path / "features.json"
    target_path = tmp_path / "targets.json"
    output = tmp_path / "release"
    feature_path.write_text(json.dumps(features), encoding="utf-8")
    target_path.write_text(json.dumps(targets), encoding="utf-8")

    output_path = run_temporal_validation_report(feature_path, target_path, output)

    assert output_path == output / "temporal_validation_report.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [row["election_id"] for row in payload["rows"]] == ["2017"]
    assert (
        payload["rows"][0]["previous_result_persistence_v1"][
            "party_share_mae_percentage_points"
        ]
        == 5.0
    )
