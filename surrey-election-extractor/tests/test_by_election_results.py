"""Tests for evidence-backed Surrey County Council by-election integration."""

from __future__ import annotations

import json

import pytest

import election_extractor.master_database as master_database
from election_extractor.by_election_results import (
    DEFAULT_RESULTS_PATH,
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
    assert len(evidence) == 15
    assert sum(len(item.records) for item in evidence) == 73
    assert len(unavailable_by_election_ids(catalogue, evidence)) == 0
    # Surrey is the primary source. Epsom West and Haslemere are documented
    # local-authority publication routes for Surrey County Council contests.
    assert all(
        item.source_url.startswith(
            (
                "https://mycouncil.surreycc.gov.uk/",
                "https://www.epsom-ewell.gov.uk/",
                "https://modgov.waverley.gov.uk/",
            )
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
    assert all(
        field.evidence_source == "Epsom & Ewell Borough Council official declaration"
        for field in winner.field_evidence
    )


def test_weybridge_2015_result_page_keeps_unpublished_summary_fields_null() -> None:
    """A complete candidate table does not justify filling absent Voting Summary values."""

    records = by_election_records_by_id()[
        "surrey-county-council-by-election-weybridge-2015-05-07"
    ]
    winner = next(record for record in records if record.outcome == "Elected")

    assert len(records) == 4
    assert winner.candidate_name == "Ramon Gray"
    assert winner.votes_received == 4190
    assert winner.total_votes == 7678
    assert winner.electorate == 11460
    assert winner.ballot_papers_issued is None
    assert winner.ballot_papers_rejected is None
    assert winner.turnout is None
    assert winner.source_url.endswith("mgElectionAreaResults.aspx?ID=169&RPID=0")


def test_surrey_by_election_evidence_uses_canonical_division_result_pages() -> None:
    """Keep record provenance on the page that publishes each division result.

    Some older Surrey archive links lead to an event-level results route that
    happens to render the same data.  The candidate records instead retain the
    canonical ``mgElectionAreaResults`` URLs so a reviewer can reach the exact
    official division page without relying on that route's redirect behaviour.
    """

    expected_urls = {
        "surrey-county-council-by-election-the-byfleets-2018-12-06": (
            "mgElectionAreaResults.aspx?ID=255&RPID=0"
        ),
        "surrey-county-council-by-election-haslemere-2019-05-02": (
            "mgElectionAreaResults.aspx?ID=257&RPID=0"
        ),
        "surrey-county-council-by-election-warlingham-2026-05-07": (
            "mgElectionAreaResults.aspx?ID=443&RPID=0"
        ),
    }

    records_by_event = by_election_records_by_id()
    for election_id, url_suffix in expected_urls.items():
        assert records_by_event[election_id]
        assert all(record.source_url.endswith(url_suffix) for record in records_by_event[election_id])


def test_result_evidence_rejects_a_non_public_source_url(tmp_path) -> None:
    """Evidence inputs cannot introduce a local path or credential-bearing URL."""

    payload = json.loads(DEFAULT_RESULTS_PATH.read_text(encoding="utf-8"))
    payload["results"][0]["source_url"] = "file:///private/election-result.pdf"
    path = tmp_path / "invalid_source.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="public HTTP\\(S\\)"):
        load_by_election_result_evidence(path=path)


def test_result_evidence_rejects_a_publisher_domain_mismatch(tmp_path) -> None:
    """A recognised publisher cannot be paired with an unrelated public host."""

    payload = json.loads(DEFAULT_RESULTS_PATH.read_text(encoding="utf-8"))
    payload["results"][0]["source_url"] = "https://example.com/result.pdf"
    path = tmp_path / "mismatched_source.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its reviewed publisher"):
        load_by_election_result_evidence(path=path)


def test_haslemere_2026_official_waverley_result_page_is_integrated() -> None:
    """The recovered County result page supplies all published result fields."""

    records = by_election_records_by_id()[
        "surrey-county-council-by-election-haslemere-2026-07-07"
    ]
    winner = next(record for record in records if record.outcome == "Elected")

    assert len(records) == 4
    assert winner.candidate_name == "Terry Weldon"
    assert winner.votes_received == 1181
    assert winner.vote_share == 47.8
    assert winner.total_votes == 2471
    assert winner.turnout == 24.8
    assert winner.source_url.startswith("https://modgov.waverley.gov.uk/")


def test_farnham_south_2016_official_waverley_result_page_is_integrated() -> None:
    """The recovered County result page supplies all published result fields."""

    records = by_election_records_by_id()[
        "surrey-county-council-by-election-farnham-south-2016-08-18"
    ]
    winner = next(record for record in records if record.outcome == "Elected")

    assert len(records) == 5
    assert winner.candidate_name == "Robert Wyatt Ramsdale"
    assert winner.votes_received == 932
    assert winner.vote_share == 61.9
    assert winner.total_votes == 1506
    assert winner.turnout == 22.8
    assert winner.source_url.startswith("https://modgov.waverley.gov.uk/")


def test_staines_official_page_publishes_clarke_candidate_values() -> None:
    """Correct a configuration omission only when the official table states the values."""

    records = by_election_records_by_id()[
        "surrey-county-council-by-election-staines-south-ashford-west-2016-05-05"
    ]
    clarke = next(record for record in records if record.candidate_name == "Clarke Matthew David")

    assert clarke.original_party_name == "Trade Unionist and Socialist Coalition"
    assert clarke.votes_received == 33
    assert clarke.vote_share == 1
    assert clarke.final_position is None
    assert clarke.elected == "No"  # Explicit official Outcome, not a vote-rank inference.
    assert clarke.source_url.endswith("mgElectionAreaResults.aspx?ID=171&RPID=0")


def test_by_election_division_metadata_requires_verified_result_evidence(
    tmp_path, monkeypatch
) -> None:
    """A division claim cannot attach to an archive-only by-election event."""

    election_id = "surrey-county-council-by-election-weybridge-2015-05-07"
    path = tmp_path / "supplementary_metadata.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "metadata_id": f"{election_id}:result:169:test",
                        "election_id": election_id,
                        "division_id": f"{election_id}:result:169",
                        "field_name": "secondary_division_turnout",
                        "value": 67.0,
                        "geographic_level": "division",
                        "source_type": "Test official publication",
                        "source_name": "Test source",
                        "source_url": "https://example.org/result",
                        "evidence_text": "A directly published test value.",
                        "retrieval_date": "2026-07-16",
                        "confidence": "High",
                        "notes": "Test only.",
                        "validation_status": "verified",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(master_database, "SUPPLEMENTARY_METADATA_PATH", path)
    monkeypatch.setattr(master_database, "by_election_records_by_id", lambda: {})

    with pytest.raises(ValueError, match="requires verified official result evidence"):
        master_database.load_audited_elections()


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
    assert len(by_election_rows) == 73
    assert all(row["final_position"] is None for row in by_election_rows)
    assert any(
        row["division_id"].startswith(
            "surrey-county-council-by-election-epsom-west-2015-11-19:official-document:"
        )
        for row in by_election_rows
    )


def test_addlestone_secondary_turnout_is_separate_from_official_turnout() -> None:
    """A verified local-authority turnout claim cannot repair the official field."""

    database = build_master_database(load_audited_elections())
    election_id = "surrey-county-council-by-election-addlestone-2025-08-21"
    metadata = next(
        row
        for row in database.supplementary_metadata
        if row["election_id"] == election_id
        and row["field_name"] == "secondary_division_turnout"
    )
    division = next(
        row
        for row in database.divisions_and_wards
        if row["election_id"] == election_id
    )

    assert metadata["value"] == 24.0
    assert metadata["division_id"] == division["division_id"]
    assert division["turnout"] is None


def test_event_audit_reports_complete_candidate_source_coverage() -> None:
    """Every catalogued event now has a verified official candidate-result source."""

    rows = evidence_audit_rows()
    missing = [row for row in rows if row["candidate_record_count"] is None]

    assert len(rows) == 15
    assert missing == []
    assert all(row["result_source_url"] for row in rows)
    assert all(row["provenance"] == "published_official_candidate_result" for row in rows)


def test_source_recovery_audit_distinguishes_complete_and_winner_only_evidence() -> None:
    """Winner-only Council minutes cannot be converted into candidate records."""

    recovery = {item.election_id: item for item in load_by_election_source_recovery_audit()}
    epsom = recovery["surrey-county-council-by-election-epsom-west-2015-11-19"]
    weybridge = recovery["surrey-county-council-by-election-weybridge-2015-05-07"]
    unresolved = unresolved_source_recovery_ids(tuple(recovery.values()))

    assert epsom.candidate_results_integrated is True
    assert epsom.result_evidence_status == "official_declaration_integrated"
    haslemere = recovery["surrey-county-council-by-election-haslemere-2026-07-07"]
    farnham = recovery["surrey-county-council-by-election-farnham-south-2016-08-18"]
    assert haslemere.result_evidence_status == "official_result_page_integrated"
    assert haslemere.candidate_results_integrated is True
    assert haslemere.missing_official_information == ()
    assert farnham.result_evidence_status == "official_result_page_integrated"
    assert farnham.candidate_results_integrated is True
    assert farnham.missing_official_information == ()
    assert weybridge.result_evidence_status == "official_result_page_integrated"
    assert weybridge.candidate_results_integrated is True
    assert weybridge.missing_official_information == (
        "published ballot papers issued",
        "published rejected ballots",
        "published turnout",
    )
    assert unresolved == ()
