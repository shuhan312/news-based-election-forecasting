"""Release tests for the complete one-row-per-2026-ward geographic lookup."""

from collections import Counter

from scripts.generate_master_election_database import reviewed_geographic_mapping_rows


def test_geographic_lookup_contains_every_2026_ward_once() -> None:
    """A blocked ward must be visible rather than disappearing from the workbook."""

    rows = reviewed_geographic_mapping_rows()
    keys = {
        (row["current_election_id"], row["current_area_id"])
        for row in rows
    }

    assert len(rows) == 81
    assert len(keys) == 81


def test_geographic_lookup_keeps_direct_and_changed_boundaries_separate() -> None:
    """Full lookup coverage must not upgrade the 57 non-direct wards."""

    rows = reviewed_geographic_mapping_rows()
    statuses = Counter(str(row["ward_lookup_status"]) for row in rows)

    assert statuses == {
        "accepted_direct": 24,
        "changed_boundary_not_directly_comparable": 36,
        "insufficient_weighted_crosswalk_evidence": 21,
    }
    blocked = [row for row in rows if row["ward_lookup_status"] != "accepted_direct"]
    assert all(row["historical_vote_share_status"] == "unavailable_after_gis_review" for row in blocked)
    assert all(row["previous_winner_allowed"] is False for row in blocked)
    assert all(row["candidate_history_allowed"] is False for row in blocked)
    assert all(row["incumbency_allowed"] is False for row in blocked)
    assert all(row["party_vote_share_change_allowed"] is False for row in blocked)


def test_only_permission_approved_direct_wards_expose_history() -> None:
    """A complete lookup table is not permission to manufacture historical data."""

    rows = reviewed_geographic_mapping_rows()
    authorised = [
        row
        for row in rows
        if row["historical_vote_share_status"]
        == "available_from_approved_direct_mapping"
    ]

    assert len(authorised) == 24
    assert all(row["ward_lookup_status"] == "accepted_direct" for row in authorised)
    assert all(
        row["historical_reference_status"] == "approved_for_historical_reference"
        for row in authorised
    )
