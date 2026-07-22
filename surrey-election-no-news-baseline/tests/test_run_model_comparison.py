"""Integration check for the model-comparison command-line runner."""

import json
from pathlib import Path

from scripts.run_model_comparison import run_model_comparison


def _feature_dict(contest_id, election_id, date, area, party, prev, winner, elig):
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
        "geographic_reference_eligibility": "approved_historical_reference",
        "party_identity_scope": "reviewed_standard_party",
        "baseline_eligibility": elig,
        "previous_party_vote_share": prev,
        "analysis_previous_turnout": 35.0,
        "previous_electorate": 10000,
        "party_was_previous_winner": winner,
        "incumbent_candidate_any_yes_no": "No",
        "incumbent_party_yes_no": "No",
        "party_previously_contested": True,
        "first_appearance_of_party_in_area": False,
        "historical_source_url": "https://official.example/previous",
    }


def _target_dict(contest_id, party, share, elected):
    return {
        "party_contest_id": contest_id,
        "standard_party_name": party,
        "target_party_vote_share": share,
        "target_party_elected": elected,
        "target_source_urls": "https://official.example/current",
    }


def test_runner_writes_comparison_json(tmp_path: Path) -> None:
    elig = "eligible_primary_single_member_party_share"
    features = {
        "rows": [
            _feature_dict("e17-a", "2017", "4 May 2017", "area", "Party A", 55.0, True, elig),
            _feature_dict("e17-b", "2017", "4 May 2017", "area", "Party B", 45.0, False, elig),
            _feature_dict("e21-a", "2021", "6 May 2021", "area", "Party A", 52.0, True, elig),
            _feature_dict("e21-b", "2021", "6 May 2021", "area", "Party B", 48.0, False, elig),
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

    output_path = run_model_comparison(feature_path, target_path, output, l2_penalty=1.0)

    assert output_path == output / "no_news_model_comparison.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["shared_contest_count"] == 2
    assert "ridge_fundamentals_v1" in payload["common_support_share_metrics"]
