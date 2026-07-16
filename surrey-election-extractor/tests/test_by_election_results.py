"""Tests for evidence-backed Surrey County Council by-election integration."""

from __future__ import annotations

from election_extractor.by_election_results import (
    by_election_records_by_id,
    evidence_audit_rows,
    load_by_election_catalogue,
    load_by_election_result_evidence,
    unavailable_by_election_ids,
)
from election_extractor.election_history import build_election_history
from election_extractor.master_database import build_master_database, load_audited_elections


def test_catalogue_and_official_result_evidence_remain_separate() -> None:
    """All events remain visible while only verified result pages create rows."""

    catalogue = load_by_election_catalogue()
    evidence = load_by_election_result_evidence(catalogue=catalogue)

    assert len(catalogue) == 15
    assert len(evidence) == 11
    assert sum(len(item.records) for item in evidence) == 54
    assert len(unavailable_by_election_ids(catalogue, evidence)) == 4
    assert all(item.source_url.startswith("https://mycouncil.surreycc.gov.uk/") for item in evidence)


def test_missing_source_values_stay_null_and_do_not_create_a_winner() -> None:
    """An incomplete official row remains incomplete rather than being repaired."""

    records = by_election_records_by_id()[
        "surrey-county-council-by-election-staines-south-ashford-west-2016-05-05"
    ]
    incomplete = next(record for record in records if record.candidate_name == "Clarke Matthew David")

    assert incomplete.original_party_name is None
    assert incomplete.votes_received is None
    assert incomplete.final_position is None
    assert incomplete.elected == "No"  # Explicit official Outcome, not a vote-rank inference.


def test_party_standardisation_preserves_ukip_and_reform_uk_as_distinct() -> None:
    """Exact reviewed labels retain the required non-merger rule."""

    history = build_election_history()
    labels = {
        (row["original_party_name"], row["standardised_party_name"])
        for row in history["canonical_candidate_results"]
        if row["election_type"] == "by-election"
        and row["original_party_name"] in {"UK Independence Party", "Reform UK"}
    }

    assert ("UK Independence Party", "UK Independence Party") in labels
    assert ("Reform UK", "Reform UK") in labels


def test_master_database_includes_events_and_candidate_rows_without_identity_inference() -> None:
    """Integration reuses database structures and leaves name-only identity unresolved."""

    database = build_master_database(load_audited_elections())
    by_election_ids = {
        event.election_id for event in load_by_election_catalogue()
    }
    by_election_rows = [
        row for row in database.candidate_results if row["election_id"] in by_election_ids
    ]

    assert len([row for row in database.elections if row["election_id"] in by_election_ids]) == 15
    assert len(by_election_rows) == 54
    assert all(row["final_position"] is None for row in by_election_rows)
    assert all(row["source_url"].startswith("https://mycouncil.surreycc.gov.uk/") for row in by_election_rows)


def test_event_audit_keeps_archive_only_events_explicitly_unavailable() -> None:
    """The provenance audit must not encode unavailable records as zero rows."""

    rows = evidence_audit_rows()
    missing = [row for row in rows if row["candidate_record_count"] is None]

    assert len(rows) == 15
    assert len(missing) == 4
    assert all(row["result_source_url"] is None for row in missing)
    assert all(row["provenance"] == "official_archive_catalogue_only" for row in missing)
