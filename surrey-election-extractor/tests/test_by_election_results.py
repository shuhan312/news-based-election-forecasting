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
from election_extractor.by_election_source_recovery import (
    load_by_election_source_recovery_audit,
    unresolved_source_recovery_ids,
)


def test_catalogue_and_official_result_evidence_remain_separate() -> None:
    """All events remain visible while only verified result pages create rows."""

    catalogue = load_by_election_catalogue()
    evidence = load_by_election_result_evidence(catalogue=catalogue)

    assert len(catalogue) == 15
    assert len(evidence) == 12
    assert sum(len(item.records) for item in evidence) == 60
    assert len(unavailable_by_election_ids(catalogue, evidence)) == 3
    # Surrey is the primary source. Epsom West is the documented exception:
    # its complete declaration is published by the relevant local authority.
    assert all(
        item.source_url.startswith(
            ("https://mycouncil.surreycc.gov.uk/", "https://www.epsom-ewell.gov.uk/")
        )
        for item in evidence
    )


def test_epsom_west_uses_the_official_declaration_without_calculating_vote_share() -> None:
    """A complete official declaration supplies values but not derived percentages."""

    records = by_election_records_by_id()[
        "surrey-county-council-by-election-epsom-west-2015-11-19"
    ]
    winner = next(record for record in records if record.outcome == "Elected")

    assert len(records) == 6
    assert winner.candidate_name == "PERSAND, Karandeo"
    assert winner.votes_received == 612
    assert winner.vote_share is None
    assert winner.number_of_seats == 1
    assert winner.source_url.endswith("SCCDeclarationofResults19Nov2015.pdf")


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
    assert len(by_election_rows) == 60
    assert all(row["final_position"] is None for row in by_election_rows)
    assert any(
        row["division_id"].startswith(
            "surrey-county-council-by-election-epsom-west-2015-11-19:official-document:"
        )
        for row in by_election_rows
    )


def test_event_audit_keeps_archive_only_events_explicitly_unavailable() -> None:
    """The provenance audit must not encode unavailable records as zero rows."""

    rows = evidence_audit_rows()
    missing = [row for row in rows if row["candidate_record_count"] is None]

    assert len(rows) == 15
    assert len(missing) == 3
    assert all(row["result_source_url"] is None for row in missing)
    assert all(row["provenance"] == "official_archive_catalogue_only" for row in missing)


def test_source_recovery_audit_distinguishes_complete_and_winner_only_evidence() -> None:
    """Winner-only Council minutes cannot be converted into candidate records."""

    recovery = {item.election_id: item for item in load_by_election_source_recovery_audit()}
    epsom = recovery["surrey-county-council-by-election-epsom-west-2015-11-19"]
    unresolved = unresolved_source_recovery_ids(tuple(recovery.values()))

    assert epsom.candidate_results_integrated is True
    assert epsom.result_evidence_status == "complete_official_declaration_integrated"
    assert len(unresolved) == 3
    assert "surrey-county-council-by-election-weybridge-2015-05-07" in unresolved
    assert recovery["surrey-county-council-by-election-weybridge-2015-05-07"].candidate_results_integrated is False
