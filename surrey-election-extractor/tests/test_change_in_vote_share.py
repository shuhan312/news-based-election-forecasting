"""Tests for outcome-only exact-label vote-share change calculations."""

from collections import Counter

from election_extractor.change_in_vote_share import (
    OUTCOME_ONLY_MODEL_ROLE,
    change_in_vote_share_fields,
)
from election_extractor.master_database import build_master_database, load_audited_elections
from scripts.generate_master_election_database import reviewed_historical_reference_inputs


def test_change_is_percentage_point_difference_for_approved_single_member_row() -> None:
    """The calculation is transparent and records the current-share layer."""

    fields = change_in_vote_share_fields(
        current_vote_share=42.5,
        current_vote_share_provenance="official_result_page",
        current_number_of_seats=1,
        previous_party_vote_share=40.0,
        previous_party_vote_share_status=(
            "derived_single_member_exact_label_prior_candidate_share"
        ),
    )

    assert fields["change_in_vote_share"] == 2.5
    assert fields["change_in_vote_share_provenance"] == (
        "official_result_page_minus_approved_previous_exact_label_share"
    )
    assert fields["change_in_vote_share_model_role"] == OUTCOME_ONLY_MODEL_ROLE


def test_multi_member_current_candidate_share_is_not_called_party_change() -> None:
    """A 2026 candidate share is not comparable with a prior single-seat party share."""

    fields = change_in_vote_share_fields(
        current_vote_share=20.0,
        current_vote_share_provenance="official_result_page",
        current_number_of_seats=2,
        previous_party_vote_share=40.0,
        previous_party_vote_share_status=(
            "derived_single_member_exact_label_prior_candidate_share"
        ),
    )

    assert fields["change_in_vote_share"] is None
    assert fields["change_in_vote_share_status"] == (
        "not_calculated_current_contest_not_single_member"
    )


def test_release_change_coverage_respects_comparability_and_leakage_boundary() -> None:
    """Freeze all eligible changes and every defensible residual NULL category."""

    division_references, party_references = reviewed_historical_reference_inputs()
    payload = build_master_database(
        load_audited_elections(),
        historical_division_references=division_references,
        party_history_references=party_references,
    )
    rows = payload.candidate_results
    statuses = Counter(str(row["change_in_vote_share_status"]) for row in rows)

    assert len(rows) == 1_971
    assert sum(row["change_in_vote_share"] is not None for row in rows) == 775
    assert statuses == {
        "outcome_diagnostic_exact_label_single_member_change_available": 775,
        "not_calculated_current_contest_not_single_member": 246,
        "not_calculated_no_approved_exact_label_previous_share": 950,
    }
    assert all(
        row["change_in_vote_share_model_role"] == OUTCOME_ONLY_MODEL_ROLE
        for row in rows
    )
    assert all(
        row["change_in_vote_share"] is None
        for row in rows
        if row["election_id"]
        in {
            "surrey-county-council-2026-east-surrey",
            "surrey-county-council-2026-west-surrey",
        }
    )
    assert payload.audit_summary["candidate_rows_with_change_in_vote_share"] == 775
    assert payload.audit_summary["candidate_rows_change_blocked_multi_member"] == 246
    assert payload.audit_summary[
        "candidate_rows_change_without_approved_previous_share"
    ] == 950
