"""Tests for complete, conservative by-election historical eligibility."""

from election_extractor.by_election_historical_reference import build_by_election_historical_reference_audit


def test_every_catalogued_by_election_has_a_reproducible_decision() -> None:
    audit = build_by_election_historical_reference_audit()
    assert audit["summary"] == {
        "approved_same_statutory_division": 5,
        "no_prior_event_in_project_scope": 1,
        "not_comparable": 2,
        "requires_official_boundary_evidence": 7,
    }
    assert len(audit["division_references"]) == 5
    assert len(audit["party_history_references"]) == 21
