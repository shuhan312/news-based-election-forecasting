"""Tests for the release-facing final-position QA package."""

from election_extractor.final_position_qa import build_final_position_qa
from election_extractor.master_database import load_audited_elections


def test_tie_pages_are_enriched_only_by_recorded_official_second_sources() -> None:
    """All four tie pages must expose their independent source and evidence scope."""

    package = build_final_position_qa(load_audited_elections())
    ties = package["tie_candidate_review_list"]

    assert len(ties) == 8
    assert all(tie["second_source_review_status"] == "verified" for tie in ties)
    assert all(tie["second_official_source_url"] for tie in ties)
    assert all("candidate_votes" in tie["second_source_reviewed_fields"] for tie in ties)
    assert package["summary"]["tied_candidate_rows"] == 8


def test_page_report_keeps_official_and_derived_checks_separate() -> None:
    """Page QA reports eligibility without converting derived ranks into facts."""

    package = build_final_position_qa(load_audited_elections())
    page = next(
        row
        for row in package["page_validation"]
        if row["election_id"] == "surrey-county-council-2013"
        and row["division_or_ward"] == "Farnham South"
    )

    assert page["votes_complete"] is True
    assert page["derived_rank_count"] == page["candidate_count"]
    assert page["has_tied_vote_rank"] is True
    assert page["validation_result"] == "passed_complete_rank_and_seats_checks"
    assert page["seats_consistency_status"] == "passed"
    assert package["summary"]["analysis_readiness_status"] == (
        "analysis_ready_from_primary_official_sources"
    )
    assert package["summary"]["secondary_risk_sample_status"] == (
        "secondary_risk_sample_complete"
    )
