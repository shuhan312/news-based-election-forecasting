"""Release and safeguard tests for the candidate analysis vote-share layer."""

from dataclasses import replace

from election_extractor.analysis_vote_share import build_analysis_vote_share_rows
from election_extractor.master_database import build_master_database, load_audited_elections
from scripts.generate_master_election_database import reviewed_historical_reference_inputs


EPSOM_EVENT_ID = "surrey-county-council-by-election-epsom-west-2015-11-19"


def _epsom_records():
    """Return the six official declaration rows with unpublished percentages."""

    election = next(
        item
        for item in load_audited_elections()
        if item.configuration.election_id == EPSOM_EVENT_ID
    )
    return election.records


def test_epsom_west_missing_official_shares_receive_separate_analysis_values() -> None:
    """Complete single-seat official votes recover all six analysis percentages."""

    records = _epsom_records()
    rows = build_analysis_vote_share_rows(records)
    total_votes = sum(record.votes_received for record in records)

    assert total_votes == 2_595
    for record in records:
        row = rows[(record.source_url, record.candidate_name)]
        assert record.vote_share is None
        assert row["analysis_vote_share"] == round(
            record.votes_received / total_votes * 100, 6
        )
        assert row["analysis_vote_share_provenance"] == (
            "governed_derived_from_official_candidate_votes"
        )
        assert row["analysis_vote_share_status"] == (
            "derived_single_member_complete_official_candidate_vote_total"
        )


def test_missing_share_is_not_derived_for_a_multi_member_result() -> None:
    """Candidate-vote percentages are not invented under a different ballot structure."""

    records = tuple(replace(record, number_of_seats=2) for record in _epsom_records())
    rows = build_analysis_vote_share_rows(records)

    assert all(row["analysis_vote_share"] is None for row in rows.values())
    assert {
        row["analysis_vote_share_status"] for row in rows.values()
    } == {"not_derived_not_single_member_result"}


def test_release_has_complete_analysis_share_without_filling_official_nulls() -> None:
    """Freeze the supervisor-field closure and its official/derived separation."""

    division_references, party_references = reviewed_historical_reference_inputs()
    payload = build_master_database(
        load_audited_elections(),
        historical_division_references=division_references,
        party_history_references=party_references,
    )
    rows = payload.candidate_results
    epsom_rows = [row for row in rows if row["election_id"] == EPSOM_EVENT_ID]

    assert len(rows) == 1_987
    assert sum(row["vote_share"] is not None for row in rows) == 1_981
    assert sum(row["analysis_vote_share"] is not None for row in rows) == 1_987
    assert len(epsom_rows) == 6
    assert all(row["vote_share"] is None for row in epsom_rows)
    assert all(row["analysis_vote_share"] is not None for row in epsom_rows)
    assert payload.audit_summary["candidate_rows_with_official_vote_share"] == 1_981
    assert payload.audit_summary["candidate_rows_with_analysis_vote_share"] == 1_987
    assert payload.audit_summary["candidate_rows_with_derived_analysis_vote_share"] == 6
