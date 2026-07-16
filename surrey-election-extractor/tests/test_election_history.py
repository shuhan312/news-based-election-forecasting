"""Tests for the evidence-gated election event timeline layer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from election_extractor.election_history import (
    ElectionEventArea,
    build_chronology,
    build_election_history,
    load_by_election_catalogue,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _event(event_id: str, election_date: str) -> ElectionEventArea:
    """Build a direct-identity fixture without assuming electoral values."""

    return ElectionEventArea(
        election_id=event_id,
        election_name=event_id,
        election_type="by-election",
        election_date=election_date,
        authority="Surrey County Council",
        area_id=f"area:{event_id}",
        area_name="Example Division",
        geographic_identity_key="historical:example division",
        geographic_identity_basis="direct_historical_published_area_name",
        candidate_row_count=None,
        source_url="https://mycouncil.surreycc.gov.uk/mgManageElectionResults.aspx?bcr=1",
        source_coverage="official_archive_indexed_listing",
        provenance="source_reported",
        evidence_text="Official archive evidence.",
    )


def test_by_elections_use_only_verified_official_candidate_result_pages() -> None:
    """Archive events receive rows only where separate official evidence exists."""

    history = build_election_history()
    by_elections = [
        row for row in history["election_events"] if row["election_type"] == "by-election"
    ]

    assert len(load_by_election_catalogue()) == 15
    assert len(by_elections) == 15
    assert len({row["election_id"] for row in by_elections}) == 15
    assert sum(row["candidate_row_count"] is not None for row in by_elections) == 11
    assert sum(row["candidate_row_count"] is None for row in by_elections) == 4
    assert sum(row["candidate_row_count"] or 0 for row in by_elections) == 54
    assert all(row["evidence_text"] for row in by_elections)


def test_chronology_orders_only_distinct_published_dates() -> None:
    """Direct identity supports chronology, while tied dates remain ambiguous."""

    chronology = {
        row["election_id"]: row
        for row in build_chronology(
            (
                _event("event-2017", "2017-05-04"),
                _event("event-2019", "2019-01-31"),
                _event("event-2021-a", "2021-05-06"),
                _event("event-2021-b", "2021-05-06"),
            )
        )
    }

    assert chronology["event-2019"]["previous_election_event_id"] == "event-2017"
    assert chronology["event-2019"]["next_election_event_id"] is None
    assert chronology["event-2019"]["same_date_next_event_ids"] == [
        "event-2021-a",
        "event-2021-b",
    ]


def test_missing_by_election_values_remain_null_and_comparison_features_blocked() -> None:
    """Unavailable archive detail must not become a zero or a comparison value."""

    history = build_election_history()
    row = next(
        item
        for item in history["safe_enrichment"]["area_event_enrichment"]
        if item["election_id"] == "surrey-county-council-by-election-weybridge-2015-05-07"
    )

    assert row["number_of_candidates"] is None
    assert row["number_of_seats"] is None
    assert row["contest_has_multiple_candidates"] is None
    assert all(feature["value"] is None for feature in row["blocked_comparison_features"].values())


def test_ukip_and_reform_uk_remain_distinct_standardised_parties() -> None:
    """The approved lookup cannot merge the two supervisor-specified parties."""

    history = build_election_history()
    pairs = {
        (row["original_party_name"], row["standardised_party_name"])
        for row in history["canonical_candidate_results"]
        if row["original_party_name"] in {"UK Independence Party", "Reform UK"}
    }

    assert ("UK Independence Party", "UK Independence Party") in pairs
    assert ("Reform UK", "Reform UK") in pairs


def test_name_only_candidate_matches_are_not_created() -> None:
    """Published candidate names alone never produce personal history claims."""

    history = build_election_history()
    candidate_history = history["safe_enrichment"]["candidate_appearance_history"]

    assert candidate_history
    assert all(
        row["candidate_identity_status"] == "unresolved_no_explicit_identifier"
        and row["candidate_appeared_before"] is None
        and row["previous_election_events_contested"] is None
        for row in candidate_history
    )


def test_partial_crosswalk_area_cannot_create_history_or_previous_winner() -> None:
    """A reviewed partial relationship remains unavailable to electoral history."""

    history = build_election_history()
    addlestone = next(
        row
        for row in history["election_chronology"]
        if row["election_id"] == "surrey-county-council-2026-west-surrey"
        and row["area_name"] == "Addlestone Ward"
    )
    enrichment = next(
        row
        for row in history["safe_enrichment"]["area_event_enrichment"]
        if row["area_id"] == addlestone["area_id"]
    )

    assert addlestone["chronology_status"] == "unavailable_geographic_mapping"
    assert addlestone["previous_election_event_id"] is None
    assert enrichment["blocked_comparison_features"]["previous_winner"]["value"] is None
    assert enrichment["blocked_comparison_features"]["incumbency"]["value"] is None


def test_history_build_does_not_change_raw_official_audit_file() -> None:
    """The layer is read-only over previously completed official extraction data."""

    audit_path = PROJECT_ROOT / "outputs/2017_full_extraction/2017_extraction_audit.json"
    before = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    history = build_election_history()
    after = hashlib.sha256(audit_path.read_bytes()).hexdigest()

    assert before == after
    # The history layer preserves the 1,898 principal-election rows and adds
    # only the 54 separately verified official by-election candidate rows.
    assert history["coverage_report"]["summary"]["raw_candidate_rows_preserved"] == 1952


def test_coverage_reports_integrated_and_unavailable_by_election_results() -> None:
    """Coverage distinguishes verified rows from archive-only event metadata."""

    history = build_election_history()
    report = history["coverage_report"]
    encoded = json.dumps(report)

    assert report["summary"]["events_required"] == 20
    assert report["summary"]["events_represented"] == 20
    assert report["summary"]["by_elections_with_candidate_rows"] == 11
    assert "official_candidate_results_not_retrieved" in encoded
