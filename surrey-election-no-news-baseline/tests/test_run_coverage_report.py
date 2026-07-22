"""Integration check for the Task 3 coverage-report command-line runner."""

import csv
import json
from pathlib import Path

from scripts.run_coverage_report import run_coverage_report


def _feature_dict(contest_id, election_id, date, area, party, prev, winner, elig, geo):
    return {
        "party_contest_id": contest_id,
        "election_id": election_id,
        "election_date": date,
        "election_year": int(date[-4:]),
        "election_type": "County Council election",
        "division_id": area,
        "division_name": area,
        "standard_party_name": party,
        "contest_structure": "single_member",
        "geographic_reference_eligibility": geo,
        "party_identity_scope": "reviewed_standard_party",
        "baseline_eligibility": elig,
        "previous_party_vote_share": prev,
        "previous_party_vote_share_status": "derived_single_member_exact_label_prior_candidate_share",
        "party_was_previous_winner": winner,
        "historical_source_url": "https://official.example/previous",
        "analysis_previous_turnout": 35.0,
        "previous_electorate": 10000,
        "incumbent_candidate_any_yes_no": "No",
        "incumbent_party_yes_no": "No",
        "party_previously_contested": True,
        "first_appearance_of_party_in_area": False,
    }


def _target_dict(contest_id, party, share, elected):
    return {
        "party_contest_id": contest_id,
        "standard_party_name": party,
        "target_party_vote_share": share,
        "target_party_vote_share_status": "analysis_candidate_share_equals_single_member_party_share",
        "target_party_elected": elected,
        "target_source_urls": "https://official.example/current",
    }


def test_runner_writes_both_csvs_with_expected_row_counts(tmp_path: Path) -> None:
    elig = "eligible_primary_single_member_party_share"
    geo = "approved_historical_reference"
    features = {
        "rows": [
            _feature_dict("e17-a", "2017", "4 May 2017", "area", "Party A", 55.0, True, elig, geo),
            _feature_dict("e17-b", "2017", "4 May 2017", "area", "Party B", 45.0, False, elig, geo),
            _feature_dict("e21-a", "2021", "6 May 2021", "area", "Party A", 52.0, True, elig, geo),
            _feature_dict("e21-b", "2021", "6 May 2021", "area", "Party B", 48.0, False, elig, geo),
        ]
    }
    targets = {
        "rows": [
            _target_dict("e17-a", "Party A", 55.0, "Yes"),
            _target_dict("e17-b", "Party B", 45.0, "No"),
            _target_dict("e21-a", "Party A", 50.0, "Yes"),
            _target_dict("e21-b", "Party B", 50.0, "No"),
        ]
    }
    feature_path = tmp_path / "features.json"
    target_path = tmp_path / "targets.json"
    output = tmp_path / "release"
    feature_path.write_text(json.dumps(features), encoding="utf-8")
    target_path.write_text(json.dumps(targets), encoding="utf-8")

    coverage_path, comparison_path = run_coverage_report(feature_path, target_path, output)

    with coverage_path.open(encoding="utf-8") as handle:
        coverage_rows = list(csv.DictReader(handle))
    # 4 universe rows x 4 models = 16 long-format rows.
    assert len(coverage_rows) == 16

    with comparison_path.open(encoding="utf-8") as handle:
        comparison_rows = list(csv.DictReader(handle))
    assert len(comparison_rows) == 4
    assert {row["model_id"] for row in comparison_rows} == {
        "equal_share_reference_v1",
        "party_historical_mean_reference_v1",
        "previous_result_persistence_v1",
        "ridge_fundamentals_v1",
    }

    audit_path = output / "coverage_report_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["join_report"]["mismatch_count"] == 0
