"""Tests for the final Independent historical-share NULL review."""

from __future__ import annotations

from no_news_baseline.independent_previous_share_audit import (
    audit_independent_previous_share_nulls,
)


def _feature(area: str, previous_area: str) -> dict[str, object]:
    """Create one later Independent feature row with approved history."""

    return {
        "election_id": "target",
        "election_date": "2021-05-06",
        "area_id": area,
        "area_name": area,
        "standard_party_name": "Independent",
        "previous_party_vote_share": None,
        "previous_party_vote_share_status": "unavailable_no_direct_or_zero_proof",
        "previous_election_id": "previous",
        "previous_area_id": previous_area,
        "previous_area_name": previous_area,
    }


def _candidate(
    election: str,
    area: str,
    name: str,
    *,
    stood: bool | None = None,
    events: str | None = None,
) -> dict[str, object]:
    """Create the candidate evidence fields consumed by the audit."""

    return {
        "election_id": election,
        "division_id": area,
        "candidate_name": name,
        "standard_party_name": "Independent",
        "candidate_previously_stood": stood,
        "candidate_history_event_ids": events,
    }


def test_verified_candidate_history_is_not_relabelled_as_party_share() -> None:
    """A continuing person remains candidate evidence, not party evidence."""

    audit = audit_independent_previous_share_nulls(
        (_feature("A", "Old A"),),
        (
            _candidate("target", "A", "Alex", stood=True, events="previous"),
            _candidate("previous", "Old A", "Alex"),
        ),
    )
    decision = audit["decisions"][0]
    assert decision["decision"] == "candidate_history_available_not_party_history"
    assert decision["final_previous_party_vote_share"] is None
    assert audit["methodological_decision"]["candidate_history_predictor_retained"] is True


def test_different_independent_candidate_remains_unmatched() -> None:
    """Sharing the Independent label cannot link two different people."""

    audit = audit_independent_previous_share_nulls(
        (_feature("A", "Old A"),),
        (
            _candidate("target", "A", "New Person", stood=False),
            _candidate("previous", "Old A", "Earlier Person"),
        ),
    )
    assert audit["decisions"][0]["decision"] == (
        "different_or_ambiguous_independent_identity"
    )


def test_absent_independent_label_is_not_forced_to_zero() -> None:
    """No previous Independent is not evidence of zero for a continuing party."""

    other_party = _candidate("previous", "Old A", "Party Candidate")
    other_party["standard_party_name"] = "Conservative"
    audit = audit_independent_previous_share_nulls(
        (_feature("A", "Old A"),),
        (_candidate("target", "A", "New Person", stood=False), other_party),
    )
    assert audit["decisions"][0]["decision"] == (
        "generic_independent_label_not_continuing_entity"
    )
    assert audit["methodological_decision"]["zero_assigned_from_label_absence"] is False


def test_name_match_without_verified_history_is_not_accepted() -> None:
    """Exact names alone are insufficient identity evidence."""

    audit = audit_independent_previous_share_nulls(
        (_feature("A", "Old A"),),
        (
            _candidate("target", "A", "Same Name", stood=None),
            _candidate("previous", "Old A", "Same Name"),
        ),
    )
    assert audit["decisions"][0]["verified_same_candidate_names"] == ()
    assert audit["decisions"][0]["decision"] == (
        "different_or_ambiguous_independent_identity"
    )
