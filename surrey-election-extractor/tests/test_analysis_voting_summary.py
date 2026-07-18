"""Tests for the provenance-preserving analysis voting-summary layer."""

from election_extractor.analysis_voting_summary import build_analysis_voting_summary


def test_analysis_layer_uses_governed_precedence_without_filling_official_null() -> None:
    """Secondary and derived values must remain visibly distinct from official data."""

    rows = build_analysis_voting_summary(
        ({"election_id": "e", "division_id": "d", "division_name": "D", "official_number_of_seats": None, "secondary_number_of_seats": 2, "ballot_papers_issued": None, "turnout": None, "rejected_ballots": None},),
        ({"metadata_id": "s", "division_id": "d", "field_name": "secondary_division_turnout", "value": 40.0},),
        ({"metadata_id": "m", "division_id": "d", "field_name": "derived_ballot_papers_issued", "value": 100},),
    )
    values = {row["field_name"]: row for row in rows}
    assert values["analysis_number_of_seats"]["value"] == 2
    assert values["analysis_number_of_seats"]["provenance_layer"] == "supplementary_official_evidence"
    assert values["analysis_turnout"]["value"] == 40.0
    assert values["analysis_ballot_papers_issued"]["provenance_layer"] == "governed_derived_value"
    assert values["analysis_rejected_ballots"]["value"] is None
