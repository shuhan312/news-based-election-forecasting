"""Integration checks for the naive-benchmarks command-line runner."""

import json
from pathlib import Path

from scripts.run_naive_benchmarks import run_naive_benchmarks


def test_runner_reads_contract_and_writes_both_benchmarks(tmp_path: Path) -> None:
    # Small synthetic contract, deliberately structured the same way as
    # test_run_persistence_benchmark.py's fixture, so both runners are
    # exercised against an equivalent minimal release.
    features = {
        "rows": [
            {
                "party_contest_id": "a",
                "election_id": "2017",
                "election_date": "4 May 2017",
                "election_year": 2017,
                "election_type": "County Council election",
                "division_id": "area",
                "division_name": "Area",
                "standard_party_name": "Party A",
                "contest_structure": "single_member",
                "geographic_reference_eligibility": "approved_historical_reference",
                "baseline_eligibility": "eligible_primary_single_member_party_share",
            },
            {
                "party_contest_id": "b",
                "election_id": "2017",
                "election_date": "4 May 2017",
                "election_year": 2017,
                "election_type": "County Council election",
                "division_id": "area",
                "division_name": "Area",
                "standard_party_name": "Party B",
                "contest_structure": "single_member",
                "geographic_reference_eligibility": "approved_historical_reference",
                "baseline_eligibility": "eligible_primary_single_member_party_share",
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

    audit_paths = run_naive_benchmarks(feature_path, target_path, output)

    assert len(audit_paths) == 2
    for stem in ("equal_share_reference", "party_historical_mean_reference"):
        assert (output / f"{stem}_predictions.json").exists()
        assert (output / f"{stem}_metrics.json").exists()
        assert (output / f"{stem}_audit.json").exists()

    equal_share_metrics = json.loads(
        (output / "equal_share_reference_metrics.json").read_text(encoding="utf-8")
    )
    # Two parties on one ballot: the uninformed floor predicts 50% each,
    # so the MAE against 55/45 actual shares must be exactly 5 points.
    assert (
        equal_share_metrics["full_cohort"]["overall"]["party_share_mae_percentage_points"] == 5.0
    )

    climatology_metrics = json.loads(
        (output / "party_historical_mean_reference_metrics.json").read_text(encoding="utf-8")
    )
    # Neither party has any qualifying election before 2017 in this minimal
    # fixture, so climatology must report zero scored share rows rather than
    # inventing a value.
    assert climatology_metrics["full_cohort"]["overall"]["party_share_rows"] == 0
