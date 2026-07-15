"""Tests for the pre-extraction 2013 supplementary-metadata policy audit."""

from election_extractor.supplementary_metadata_audit import (
    ELECTORAL_COMMISSION_URL,
    SURREY_NEWS_URL,
    WIKIPEDIA_URL,
    audit_markdown,
    build_2013_supplementary_metadata_audit,
)


def policy_for(audit: dict[str, object], field: str) -> dict[str, object]:
    """Find one field policy without relying on its table position."""

    return next(item for item in audit["field_policies"] if item["field"] == field)


def test_election_turnout_is_secondary_and_has_higher_priority_evidence() -> None:
    """County-wide turnout is separate from individual official result-page fields."""

    audit = build_2013_supplementary_metadata_audit()
    turnout = policy_for(audit, "overall_turnout")
    approved = audit["approved_supplementary_policy"]["election_level_turnout"]

    assert turnout["recommended_storage_location"] == "supplementary election metadata field"
    assert approved["value"] == "30%"
    assert approved["primary_evidence_source"] == SURREY_NEWS_URL
    assert approved["corroborating_source"] == ELECTORAL_COMMISSION_URL


def test_division_values_remain_conditional_and_candidate_values_are_not_supplemented() -> None:
    """The audit must not convert incomplete official records into secondary replacements."""

    audit = build_2013_supplementary_metadata_audit()

    assert policy_for(audit, "turnout")["can_be_supplemented"] == "conditionally"
    assert policy_for(audit, "ballot_papers_issued")["can_be_supplemented"] == "conditionally"
    assert policy_for(audit, "candidate_name, original_party_name, votes, vote_share, outcome")["can_be_supplemented"] is False
    assert audit["approved_supplementary_policy"]["division_level_values"]["status"] == "Not integrated by this audit."


def test_wikipedia_is_documented_but_not_approved_when_better_sources_exist() -> None:
    """Wikipedia remains a recorded fallback, not a division-level data replacement."""

    audit = build_2013_supplementary_metadata_audit()
    wikipedia = next(
        item for item in audit["source_evaluations"] if item["source_url"] == WIKIPEDIA_URL
    )

    assert wikipedia["use_decision"].startswith("Do not use.")
    assert "never overwrites" in audit_markdown(audit)
