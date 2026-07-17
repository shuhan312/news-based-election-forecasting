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
        "election_events": 20,
        "candidate_rows": 1971,
        "division_or_ward_rows": 339,
    }
    assert report["residual_missing_counts"] == {
        "ballot_papers_issued": 1,
        "electorate": 1,
        "rejected_ballots": 1,
        "turnout": 2,
        "vote_share": 1,
    }
    # The vote-share entry is one source-level gap affecting six candidate rows.
    assert sum(item["record_count"] for item in report["residual_missing_after_all_permitted_layers"]) == 11


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
    assert materialised["single_official_winners"] == 258
    assert materialised["multi_member_elected_name_lists"] == 81
    assert materialised["separate_derived_winning_margins"] == 230
    assert reconciliation["event_samples"] == 20
    assert reconciliation["candidate_field_checks_passed"] == 20
    assert reconciliation["source_url_checks_passed"] == 20


def test_final_audit_markdown_includes_rendered_scope_counts() -> None:
    """Human-readable reporting must render counts, not template placeholders."""

    report = build_final_data_release_audit(
        _audited_payload(), evidence_index=load_missing_field_evidence_index()
    )

    markdown = final_data_release_audit_markdown(report)
    assert "- Election events: 20" in markdown
    assert "{election_events}" not in markdown
