"""Tests for the provenance-preserving no-news electoral baseline."""

from types import SimpleNamespace

from election_extractor.no_news_baseline import build_no_news_electoral_baseline


def test_baseline_uses_supplementary_official_prior_turnout_without_overwriting_it() -> None:
    """A reviewed prior turnout statement is usable only in the analysis layer."""

    previous = {
        "election_id": "2013", "division_id": "2013:a", "division_name": "A", "turnout": None,
        "historical_reference_status": "not_approved_or_not_applicable", "previous_election_id": None,
        "previous_division_name": None, "previous_winning_party": None,
        "previous_winning_candidate_vote_share": None, "previous_electorate": None,
        "historical_source_url": None, "historical_permission_source_urls": None,
    }
    target = {
        "election_id": "2017", "division_id": "2017:a", "division_name": "A", "turnout": 30.0,
        "historical_reference_status": "approved_pre_2024_legal_continuity", "previous_election_id": "2013",
        "previous_division_name": "A", "previous_winning_party": "Party",
        "previous_winning_candidate_vote_share": 40.0, "previous_electorate": 100,
        "historical_source_url": "https://official.example/2013", "historical_permission_source_urls": "https://law.example",
    }
    payload = SimpleNamespace(
        divisions_and_wards=(previous, target),
        supplementary_metadata=(
            {"metadata_id": "2013:a:turnout", "division_id": "2013:a", "field_name": "secondary_division_turnout", "value": 31.0},
        ),
    )
    rows, coverage = build_no_news_electoral_baseline(payload)
    row = next(item for item in rows if item["division_id"] == "2017:a")
    assert row["analysis_previous_turnout"] == 31.0
    assert row["analysis_previous_turnout_provenance"] == "supplementary_official_evidence"
    assert row["analysis_previous_turnout_source_metadata_id"] == "2013:a:turnout"
    assert coverage["baseline_approved_historical_reference"] == 1
