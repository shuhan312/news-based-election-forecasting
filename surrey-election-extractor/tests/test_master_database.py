"""Tests for the source-preserving multi-election master database payload."""

from dataclasses import replace
from pathlib import Path

from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.master_database import AuditedElectionInput, build_master_database
from election_extractor.models import ElectionStructureMetadata, SupplementaryMetadataRecord


def configuration(year: int) -> ElectionConfiguration:
    """Create a minimal configured election without embedding seat assumptions."""

    return ElectionConfiguration(
        election_id=f"surrey-county-council-{year}",
        election_name=f"Surrey County Council Election {year}",
        election_year=year,
        election_type="County Council election",
        official_url=f"https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID={year}",
        official_url_field="official_archive_url",
    )


def record(
    year: int,
    candidate_name: str,
    party_name: str,
    *,
    seats: int | None = 1,
    rejected_ballots: int | None = 3,
    final_position: int | None = None,
) -> CandidateResultRecord:
    """Build audited source data with only published fields populated."""

    return CandidateResultRecord(
        election_name=f"Surrey County Council Election {year}",
        election_date=f"6 May {year}",
        authority="Surrey County Council",
        division_ward_name="Example Division",
        number_of_seats=seats,
        candidate_name=candidate_name,
        original_party_name=party_name,
        votes_received=100,
        vote_share=50.0,
        outcome="Elected",
        electorate=1000,
        ballot_papers_issued=503,
        ballot_papers_rejected=rejected_ballots,
        turnout=50.3,
        source_url=(
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx"
            f"?ID={year}&RPID=1"
        ),
        extraction_status=ExtractionStatus.COMPLETE,
        missing_fields=(),
        final_position=final_position,
    )


def audited_input(
    year: int,
    records: tuple[CandidateResultRecord, ...],
    metadata: tuple[ElectionStructureMetadata, ...] = (),
    supplementary_metadata: tuple[SupplementaryMetadataRecord, ...] = (),
) -> AuditedElectionInput:
    """Create a local audited-input object without accessing a real website."""

    return AuditedElectionInput(
        configuration=configuration(year),
        audit_path=Path(__file__),
        records=records,
        election_structure_metadata=metadata,
        supplementary_metadata=supplementary_metadata,
    )


def audited_input_with_configuration(
    configuration_value: ElectionConfiguration,
    records: tuple[CandidateResultRecord, ...],
) -> AuditedElectionInput:
    """Create an audited input for one separately configured 2026 region."""

    return AuditedElectionInput(
        configuration=configuration_value,
        audit_path=Path(__file__),
        records=records,
        election_structure_metadata=(),
    )


def configuration_2026(region: str) -> ElectionConfiguration:
    """Model one official 2026 map-index source without merging regions."""

    return ElectionConfiguration(
        election_id=f"surrey-county-council-2026-{region}-surrey",
        election_name="Surrey County Council Election 2026",
        election_year=2026,
        election_type="County Council election",
        official_url=f"https://www10.surreycc.gov.uk/electionmap/{region}Surrey/",
        official_url_field="official_url",
    )


def record_2026(
    region: str,
    result_id: int,
    candidate_name: str,
    party_name: str,
    ward_name: str,
) -> CandidateResultRecord:
    """Model a published two-seat result without deriving its seat value."""

    return CandidateResultRecord(
        election_name=None,
        election_date="7 May 2026",
        authority="Surrey County Council",
        division_ward_name=ward_name,
        number_of_seats=2,
        candidate_name=candidate_name,
        original_party_name=party_name,
        votes_received=100,
        vote_share=50.0,
        outcome="Elected",
        electorate=1000,
        ballot_papers_issued=500,
        ballot_papers_rejected=2,
        turnout=50.0,
        source_url=(
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx"
            f"?EID={'2037' if region == 'east' else '2007'}&ID={result_id}"
        ),
        extraction_status=ExtractionStatus.INCOMPLETE,
        missing_fields=("election_name",),
        final_position=None,
    )


def test_candidate_results_have_one_row_per_candidate() -> None:
    payload = build_master_database(
        (
            audited_input(
                2017,
                (
                    record(2017, "Candidate One", "Conservative"),
                    record(2017, "Candidate Two", "Labour"),
                ),
            ),
        )
    )

    assert len(payload.candidate_results) == 2
    assert {row["candidate_name"] for row in payload.candidate_results} == {
        "Candidate One",
        "Candidate Two",
    }


def test_original_party_names_are_preserved_without_merging() -> None:
    payload = build_master_database(
        (
            audited_input(
                2021,
                (
                    record(2021, "Candidate UKIP", "UK Independence Party"),
                    record(2021, "Candidate Reform", "Reform UK"),
                ),
            ),
        )
    )

    party_names = {row["original_party_name"] for row in payload.candidate_results}
    assert party_names == {"UK Independence Party", "Reform UK"}
    assert {row["standard_party_name"] for row in payload.political_parties} == party_names


def test_official_and_secondary_seats_remain_separate() -> None:
    metadata = ElectionStructureMetadata(
        election_year=2021,
        election_name="Surrey County Council Election 2021",
        authority="Surrey County Council",
        division_or_ward_name="Example Division",
        official_number_of_seats=None,
        secondary_number_of_seats=1,
        seat_source_type="UK statutory instrument",
        seat_source_url="https://www.legislation.gov.uk/uksi/2012/1872/contents/made",
        seat_evidence_text="The division elects one councillor.",
        confidence="High",
    )
    payload = build_master_database(
        (
            audited_input(
                2021,
                (record(2021, "Candidate One", "Conservative", seats=None),),
                (metadata,),
            ),
        )
    )

    division = payload.divisions_and_wards[0]
    assert division["official_number_of_seats"] is None
    assert division["secondary_number_of_seats"] == 1


def test_missing_values_remain_null() -> None:
    payload = build_master_database(
        (
            audited_input(
                2017,
                (record(2017, "Candidate One", "Conservative", rejected_ballots=None),),
            ),
        )
    )

    assert payload.divisions_and_wards[0]["rejected_ballots"] is None


def test_final_position_is_not_calculated_from_votes() -> None:
    payload = build_master_database(
        (
            audited_input(
                2021,
                (record(2021, "Candidate One", "Conservative", final_position=None),),
            ),
        )
    )

    assert payload.candidate_results[0]["final_position"] is None


def test_2017_and_2021_can_coexist_in_one_database() -> None:
    payload = build_master_database(
        (
            audited_input(2017, (record(2017, "Candidate 2017", "Conservative"),)),
            audited_input(2021, (record(2021, "Candidate 2021", "Reform UK"),)),
        )
    )

    assert [row["election_year"] for row in payload.elections] == [2017, 2021]
    assert {row["election_year"] for row in payload.candidate_results} == {2017, 2021}


def test_2013_can_join_existing_years_without_filling_division_values() -> None:
    """2013 enters the shared database without receiving county-wide turnout."""

    incomplete_2013 = replace(
        record(2013, "Candidate 2013", "UK Independence Party"),
        ballot_papers_issued=None,
        turnout=None,
        final_position=None,
        missing_fields=("ballot_papers_issued", "turnout"),
        extraction_status=ExtractionStatus.INCOMPLETE,
    )
    payload = build_master_database(
        (
            audited_input(2013, (incomplete_2013,)),
            audited_input(2017, (record(2017, "Candidate 2017", "Conservative"),)),
            audited_input(2021, (record(2021, "Candidate 2021", "Reform UK"),)),
        )
    )

    division = next(
        row for row in payload.divisions_and_wards if row["election_id"] == "surrey-county-council-2013"
    )
    assert [row["election_year"] for row in payload.elections] == [2013, 2017, 2021]
    assert division["ballot_papers_issued"] is None
    assert division["turnout"] is None
    assert division["official_number_of_seats"] == 1


def test_2026_east_and_west_candidate_rows_stay_separate_and_complete() -> None:
    """Two 2026 map-index regions retain their own IDs and every candidate row."""

    east = configuration_2026("east")
    west = configuration_2026("west")
    east_records = (
        record_2026(
            "east",
            352,
            "East Candidate One",
            "Ashtead Independent, working with Ashtead Residents",
            "Ashtead Ward",
        ),
        record_2026("east", 352, "East Candidate Two", "Reform UK", "Ashtead Ward"),
    )
    west_records = (
        record_2026("west", 388, "West Candidate One", "Independent", "Addlestone Ward"),
        record_2026("west", 388, "West Candidate Two", "Reform UK", "Addlestone Ward"),
    )

    payload = build_master_database(
        (
            audited_input_with_configuration(east, east_records),
            audited_input_with_configuration(west, west_records),
        )
    )

    assert [row["election_id"] for row in payload.elections] == [east.election_id, west.election_id]
    assert len(payload.candidate_results) == len(east_records) + len(west_records)
    assert {row["division_id"] for row in payload.candidate_results} == {
        f"{east.election_id}:result:352",
        f"{west.election_id}:result:388",
    }
    assert {
        row["original_party_name"] for row in payload.candidate_results
    } == {
        "Ashtead Independent, working with Ashtead Residents",
        "Reform UK",
        "Independent",
    }
    assert {row["candidate_completeness_status"] for row in payload.candidate_results} == {
        "complete"
    }


def test_2026_integration_creates_empty_mapping_and_enrichment_frameworks() -> None:
    """No boundary equivalence, swing, incumbency or party merge is invented."""

    configuration_value = configuration_2026("east")
    payload = build_master_database(
        (
            audited_input_with_configuration(
                configuration_value,
                (
                    record_2026(
                        "east",
                        352,
                        "Candidate One",
                        "UK Independence Party",
                        "Ashtead Ward",
                    ),
                    record_2026(
                        "east",
                        352,
                        "Candidate Two",
                        "Reform UK",
                        "Ashtead Ward",
                    ),
                ),
            ),
        )
    )

    assert payload.geographic_mapping == ()
    assert payload.party_standardisation_issues == ()
    assert {row["original_party_name"] for row in payload.political_parties} == {
        "UK Independence Party",
        "Reform UK",
    }
    assert not {"vote_change", "incumbent_status", "previous_winner"}.intersection(
        payload.candidate_results[0]
    )
    dictionary_tables = {row["table"] for row in payload.data_dictionary}
    assert {"Geographic Mapping", "Party Standardisation Issues"}.issubset(
        dictionary_tables
    )


def test_2026_integration_does_not_change_historical_source_records() -> None:
    """Adding a 2026 input leaves immutable historical values exactly as supplied."""

    historical = record(
        2021,
        "Historical Candidate",
        "Conservative",
        seats=None,
        rejected_ballots=None,
    )
    before = replace(historical)
    payload = build_master_database(
        (
            audited_input(2021, (historical,)),
            audited_input_with_configuration(
                configuration_2026("east"),
                (
                    record_2026(
                        "east",
                        352,
                        "2026 Candidate",
                        "Reform UK",
                        "Ashtead Ward",
                    ),
                ),
            ),
        )
    )

    historical_row = next(
        row
        for row in payload.candidate_results
        if row["candidate_name"] == "Historical Candidate"
    )
    assert historical == before
    assert historical_row["original_party_name"] == "Conservative"
    assert historical_row["final_position"] is None
