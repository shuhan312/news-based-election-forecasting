"""Tests for the source-preserving multi-election master database payload."""

from dataclasses import replace
from pathlib import Path

from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.master_database import (
    AuditedElectionInput,
    build_master_database,
    load_audited_elections,
)
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


def test_geographic_mapping_schema_requires_decision_and_evidence_fields() -> None:
    """The empty final table still documents the evidence-gated mapping contract."""

    payload = build_master_database(
        (audited_input(2017, (record(2017, "Candidate One", "Conservative"),)),)
    )
    fields = {
        row["field_name"]
        for row in payload.data_dictionary
        if row["table"] == "Geographic Mapping"
    }

    assert payload.geographic_mapping == ()
    assert {
        "mapping_id",
        "previous_election_id",
        "current_election_id",
        "relationship_type",
        "administrative_identity",
        "analytical_comparability",
        "decision",
        "overlap_area_m2",
        "GIS_source",
        "boundary_source",
        "evidence_notes",
    } <= fields


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


def test_reviewed_party_lookup_adds_fields_without_changing_published_names() -> None:
    """Local labels remain separate while the lookup adds auditable grouping."""

    payload = build_master_database(
        (
            audited_input(
                2026,
                (
                    record(
                        2026,
                        "Local Candidate",
                        "Farnham Residents",
                    ),
                    record(2026, "Reform Candidate", "Reform UK"),
                ),
            ),
        )
    )

    local_row = next(
        row
        for row in payload.candidate_results
        if row["candidate_name"] == "Local Candidate"
    )
    reform_row = next(
        row
        for row in payload.candidate_results
        if row["candidate_name"] == "Reform Candidate"
    )
    assert local_row["original_party_name"] == "Farnham Residents"
    assert local_row["standard_party_name"] == "Farnham Residents"
    assert local_row["party_category"] == "local"
    assert reform_row["standard_party_name"] == "Reform UK"
    assert reform_row["standard_party_name"] != "UK Independence Party"


def test_unmapped_or_missing_party_name_remains_unstandardised() -> None:
    """Unknown and unpublished labels create review issues rather than guesses."""

    unpublished = replace(record(2021, "No Party", "Conservative"), original_party_name=None)
    payload = build_master_database(
        (
            audited_input(
                2021,
                (
                    record(2021, "Unmapped Party", "Unreviewed Future Party"),
                    unpublished,
                ),
            ),
        )
    )

    rows = {row["candidate_name"]: row for row in payload.candidate_results}
    assert rows["Unmapped Party"]["standard_party_name"] is None
    assert rows["Unmapped Party"]["party_lookup_status"] == "unmapped"
    assert rows["No Party"]["standard_party_name"] is None
    assert rows["No Party"]["party_lookup_status"] == "missing_published_party_name"
    assert {issue["issue_type"] for issue in payload.party_standardisation_issues} == {
        "unmapped_published_party_name",
        "missing_published_party_name",
    }


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


def test_current_by_election_corrections_flow_into_master_database() -> None:
    """Guard the reviewed local inputs against a stale master-database build.

    The official Staines correction and the two turnout supplements are loaded
    from configuration, but supplementary values must never fill the official
    Voting Summary fields in the division table.
    """

    payload = build_master_database(load_audited_elections())

    clarke = next(
        row
        for row in payload.candidate_results
        if row["candidate_name"] == "Clarke Matthew David"
    )
    assert clarke["original_party_name"] == "Trade Unionist and Socialist Coalition"
    assert clarke["votes"] == 33
    assert clarke["vote_share"] == 1.0
    assert clarke["source_url"].endswith("ID=171&RPID=0")

    supplement_rows = {
        (row["election_id"], row["field_name"]): row
        for row in payload.supplementary_metadata
    }
    assert supplement_rows[
        (
            "surrey-county-council-by-election-staines-south-ashford-west-2016-05-05",
            "secondary_division_turnout",
        )
    ]["value"] == 31.3
    assert supplement_rows[
        (
            "surrey-county-council-by-election-addlestone-2025-08-21",
            "secondary_division_turnout",
        )
    ]["value"] == 24.0

    official_turnout = {
        row["election_id"]: row["turnout"]
        for row in payload.divisions_and_wards
        if row["election_id"]
        in {
            "surrey-county-council-by-election-staines-south-ashford-west-2016-05-05",
            "surrey-county-council-by-election-addlestone-2025-08-21",
        }
    }
    assert official_turnout == {
        "surrey-county-council-by-election-staines-south-ashford-west-2016-05-05": None,
        "surrey-county-council-by-election-addlestone-2025-08-21": None,
    }


def test_verified_woking_2013_issued_ballots_are_supplementary_only() -> None:
    """Keep six cross-checked Woking declaration values outside official fields.

    The Woking declaration is a named official local-authority source, while
    the Surrey result pages leave ballot papers issued blank. The exact values
    are exported as evidence only and cannot change official completeness.
    """

    payload = build_master_database(load_audited_elections())
    ballot_rows = [
        row
        for row in payload.supplementary_metadata
        if row["field_name"] == "secondary_division_ballot_papers_issued"
    ]

    assert len(ballot_rows) == 6
    assert {row["value"] for row in ballot_rows} == {2796, 3198, 3336, 3642, 3728, 4062}
    divisions = {
        row["division_name"]: row
        for row in payload.divisions_and_wards
        if row["election_id"] == "surrey-county-council-2013"
    }
    assert divisions["Woking North"]["ballot_papers_issued"] is None
    assert divisions["The Byfleets"]["ballot_papers_issued"] is None


def test_cross_validated_foxhills_turnout_is_supplementary_only() -> None:
    """Keep the approved Wikipedia turnout outside the official 2013 field.

    The individual Surrey result page omits its turnout number. The master
    database may expose the separately cross-validated evidence record, but
    must not make the official division field look published or complete.
    """

    payload = build_master_database(load_audited_elections())
    foxhills = next(
        row
        for row in payload.divisions_and_wards
        if row["election_id"] == "surrey-county-council-2013"
        and row["division_name"] == "Foxhills, Thorpe & Virginia Water"
    )
    supplementary = next(
        row
        for row in payload.supplementary_metadata
        if row["metadata_id"].endswith(
            "secondary_division_turnout:wikipedia-cross-validated"
        )
    )

    assert foxhills["turnout"] is None
    assert supplementary["division_id"] == foxhills["division_id"]
    assert supplementary["value"] == 27.0
    assert supplementary["source_type"] == "Wikipedia secondary election table"


def test_current_published_party_labels_have_reviewed_lookup_entries() -> None:
    """Require explicit review for every non-blank party label in current inputs.

    A future source label must become an auditable lookup decision rather than
    being categorised by a heuristic. An officially blank party remains blank
    and is intentionally outside this exact-label review.
    """

    payload = build_master_database(load_audited_elections())

    unmapped_labels = {
        row["original_party_name"]
        for row in payload.candidate_results
        if row["original_party_name"] is not None
        and row["standard_party_name"] is None
    }
    assert unmapped_labels == set()


def test_lingfield_2013_published_blank_party_remains_null() -> None:
    """Do not turn an officially blank 2013 party cell into an assumption.

    The indexed Surrey result table publishes D'Avray's name, votes, share and
    outcome but leaves its Party column empty. The separate Surrey Council
    announcement is recorded as supplementary evidence rather than changing
    this field or treating “No party affiliation” as an Independent label.
    """

    payload = build_master_database(load_audited_elections())
    candidate = next(
        row
        for row in payload.candidate_results
        if row["election_id"] == "surrey-county-council-2013"
        and row["division_name"] == "Lingfield"
        and row["candidate_name"] == "D'Avray, Christopher David"
    )

    assert candidate["original_party_name"] is None
    assert candidate["standard_party_name"] is None
    assert candidate["party_category"] is None
    affiliation = next(
        row
        for row in payload.supplementary_metadata
        if row["metadata_id"].endswith("candidate-party-affiliation:davray-christopher-david")
    )
    assert affiliation["candidate_name"] == "D'Avray, Christopher David"
    assert affiliation["value"] == "No party affiliation"
