"""Integration tests for the final, non-mutating election-data release audit."""

from scripts.generate_master_election_database import (
    reviewed_geographic_mapping_rows,
    reviewed_historical_reference_inputs,
)
from election_extractor.candidate_continuity_evidence import (
    evidence_by_candidate_key,
    load_candidate_continuity_evidence,
)
from election_extractor.final_data_release_audit import (
    build_final_data_release_audit,
    final_data_release_audit_markdown,
    load_missing_field_evidence_index,
)
from election_extractor.master_database import build_master_database, load_audited_elections


def _audited_payload():
    """Build the production payload from local audits without network access."""

    elections = load_audited_elections()
    division_references, party_references = reviewed_historical_reference_inputs()
    continuity_evidence = evidence_by_candidate_key(
        load_candidate_continuity_evidence(
            permitted_election_ids=(election.configuration.election_id for election in elections)
        )
    )
    return build_master_database(
        elections,
        geographic_mapping=reviewed_geographic_mapping_rows(),
        historical_division_references=division_references,
        party_history_references=party_references,
        candidate_continuity_evidence=continuity_evidence,
    )


def test_final_audit_matches_current_residual_field_boundary() -> None:
    """Every unresolved value has one evidence-index entry and no hidden gap."""

    report = build_final_data_release_audit(
        _audited_payload(), evidence_index=load_missing_field_evidence_index()
    )

    assert report["dataset_counts"] == {
        "election_events": 23,
        "candidate_rows": 1987,
        "division_or_ward_rows": 342,
    }
    assert report["residual_missing_counts"] == {
        # Two now: the pre-existing gap, plus Woking South 2025, where Surrey
        # publishes 3,058 ballot papers issued and the Woking Borough Council
        # returning-officer page publishes 3,048. Only the latter reconciles
        # with 3,039 total votes plus 9 rejected, so the field stays NULL
        # rather than resolving a conflict between two official publishers by
        # preferring the arithmetic that happens to close.
        "ballot_papers_issued": 2,
        "electorate": 1,
        "rejected_ballots": 1,
        "turnout": 2,
        "vote_share": 1,
    }
    # The vote-share entry is one source-level gap affecting six candidate rows.
    assert sum(item["record_count"] for item in report["residual_missing_after_all_permitted_layers"]) == 12


def test_final_audit_checks_materialised_fields_and_event_samples() -> None:
    """Release checks protect the required database columns and source links."""

    report = build_final_data_release_audit(
        _audited_payload(), evidence_index=load_missing_field_evidence_index()
    )
    materialised = report["materialised_supervisor_fields"]
    reconciliation = report["reconciliation_summary"]

    assert materialised["missing_columns"] == {
        "candidate_results": [],
        "divisions_and_wards": [],
    }
    assert materialised["single_official_winners"] == 261
    assert materialised["multi_member_elected_name_lists"] == 81
    assert materialised["separate_derived_winning_margins"] == 233
    assert materialised["candidate_change_in_vote_share_diagnostics"] == 791
    assert reconciliation["event_samples"] == 23
    assert reconciliation["candidate_field_checks_passed"] == 23
    assert reconciliation["source_url_checks_passed"] == 23


def test_final_audit_markdown_includes_rendered_scope_counts() -> None:
    """Human-readable reporting must render counts, not template placeholders."""

    report = build_final_data_release_audit(
        _audited_payload(), evidence_index=load_missing_field_evidence_index()
    )

    markdown = final_data_release_audit_markdown(report)
    assert "- Election events: 23" in markdown
    assert "Post-election change-in-vote-share diagnostics: 791" in markdown
    # The scope sentence is interpolated from the same count, so the document
    # cannot describe a different release from the one it tabulates.
    assert "23-event master payload" in markdown
    assert "{election_events}" not in markdown
