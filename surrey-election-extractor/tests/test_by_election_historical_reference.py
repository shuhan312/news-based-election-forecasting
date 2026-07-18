"""Tests for complete, conservative by-election historical eligibility."""

from election_extractor.by_election_historical_reference import build_by_election_historical_reference_audit


def test_every_catalogued_by_election_has_a_reproducible_decision() -> None:
    audit = build_by_election_historical_reference_audit()
    assert audit["summary"] == {"approved_same_statutory_division": 15}
    assert len(audit["division_references"]) == 15
    assert len(audit["party_history_references"]) == 73


def test_duplicate_prior_label_blocks_only_that_exact_label() -> None:
    """Two prior Independents must not suppress unrelated Farnham labels."""

    audit = build_by_election_historical_reference_audit()
    rows = [
        row for row in audit["party_history_references"]
        if row["current_election_id"]
        == "surrey-county-council-by-election-farnham-south-2016-08-18"
    ]
    independent = next(row for row in rows if row["original_party_name"] == "Independent")
    conservative = next(row for row in rows if row["original_party_name"] == "The Conservative Party")
    assert independent["previous_party_vote_share"] is None
    assert independent["previous_party_vote_share_status"] == "not_derived_prior_exact_label_not_unique"
    assert conservative["previous_party_vote_share"] == 0.0
