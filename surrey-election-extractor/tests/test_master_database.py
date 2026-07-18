"""Tests for the source-preserving multi-election master database payload."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.master_database import (
    AuditedElectionInput,
    _supervisor_incumbency_fields,
    build_master_database,
    load_audited_elections,
)
from election_extractor.candidate_continuity_evidence import (
    CandidateContinuityEvidence,
    OfficialEvidenceSource,
    PriorOfficialElection,
    candidate_evidence_key,
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


def test_reviewed_geographic_mapping_rows_are_exported_without_reclassification() -> None:
    """A supplied approval row is preserved as evidence, not recalculated here."""

    mapping = {
        "mapping_id": "review:001",
        "analytical_comparability": "accepted_direct",
        "historical_reference_status": "approved_for_historical_reference",
        "previous_winner_allowed": True,
        "candidate_history_allowed": False,
        "incumbency_allowed": False,
        "party_vote_share_change_allowed": False,
    }
    payload = build_master_database(
        (audited_input(2017, (record(2017, "Candidate One", "Conservative"),)),),
        geographic_mapping=(mapping,),
    )

    assert payload.geographic_mapping == (mapping,)
    assert payload.audit_summary["geographic_mapping_rows"] == 1


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


def test_verified_2013_issued_ballots_are_supplementary_only() -> None:
    """Keep verified local-authority values outside official Surrey fields.

    Woking and Epsom & Ewell publish named official local-authority results,
    while the Surrey result pages leave ballot papers issued blank. The exact
    values are exported as evidence only and cannot change official completeness.
    """

    payload = build_master_database(load_audited_elections())
    ballot_rows = [
        row
        for row in payload.supplementary_metadata
        if row["field_name"] == "secondary_division_ballot_papers_issued"
    ]

    assert len(ballot_rows) == 12
    assert {row["value"] for row in ballot_rows} == {
        2796, 2813, 2945, 3060, 3198, 3282, 3336, 3466, 3642, 3728, 3733, 4062,
    }
    divisions = {
        row["division_name"]: row
        for row in payload.divisions_and_wards
        if row["election_id"] == "surrey-county-council-2013"
    }
    assert divisions["Woking North"]["ballot_papers_issued"] is None
    assert divisions["The Byfleets"]["ballot_papers_issued"] is None
    # Supplementary rows link through the stable official result-page ID rather
    # than duplicating a display name, so a renamed division cannot misattach
    # source evidence.
    byfleets_evidence = next(
        row
        for row in ballot_rows
        if row["division_id"] == "surrey-county-council-2013:result:152"
    )
    assert byfleets_evidence["value"] == 2945
    assert "10,016" in byfleets_evidence["notes"]


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


def test_official_outcome_summary_keeps_all_multi_member_elected_candidates() -> None:
    """Multi-member outcomes retain every official Elected row without ranking votes."""

    elected_one = record(2026, "Candidate One", "Conservative")
    elected_two = record(2026, "Candidate Two", "Labour")
    not_elected = replace(
        record(2026, "Candidate Three", "Green Party"), outcome="Not elected"
    )
    payload = build_master_database(
        (audited_input(2026, (elected_one, elected_two, not_elected)),)
    )

    division = payload.divisions_and_wards[0]
    assert division["official_elected_candidate_names"] == "Candidate One; Candidate Two"
    assert division["official_elected_party_names"] == "Conservative; Labour"
    assert division["official_elected_candidate_count"] == 2
    assert division["winning_candidate_name"] is None
    assert division["winning_party_name"] is None
    assert division["outcome_summary_status"] == "multiple_official_elected_candidates"
    assert division["winning_margin"] is None
    assert (
        division["winning_margin_status"]
        == "analysis_last_seat_margin_available"
    )


def test_approved_history_is_materialised_only_for_exact_permitted_ward() -> None:
    """Historical values require both the approved reference and exact ward key."""

    approved_reference = {
        "historical_reference_status": "approved_for_historical_reference",
        "previous_election_event_id": "surrey-county-council-2021",
        "previous_election_date": "6 May 2021",
        "previous_area_name": "Earlier Example Division",
        "previous_winning_candidate_name": "Earlier Winner",
        "previous_winning_party": "Conservative",
        "previous_winning_candidate_vote_share": 52.0,
        "previous_turnout": 44.0,
        "previous_electorate": 1000,
        "source_result_url": "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=1",
        "geographic_mapping_id": "review:001",
        "permission_evidence": "Explicit official boundary permission.",
        "permission_source_urls": ("https://www.legislation.gov.uk/example",),
    }
    approved_party_history = {
        "provenance": "deterministically_derived",
        "party_previously_contested": True,
        "first_observed_appearance": False,
    }
    payload = build_master_database(
        (audited_input(2026, (record(2026, "Candidate One", "Conservative"),)),),
        historical_division_references={
            ("surrey-county-council-2026", "Example Division"): approved_reference
        },
        party_history_references={
            (
                "surrey-county-council-2026",
                "Example Division",
                "Conservative",
            ): approved_party_history
        },
    )

    division = payload.divisions_and_wards[0]
    candidate = payload.candidate_results[0]
    assert division["previous_winning_party"] == "Conservative"
    assert division["previous_winning_candidate_vote_share"] == 52.0
    assert division["previous_party_vote_share"] is None
    assert division["previous_party_vote_share_status"] == (
        "not_materialised_without_published_party_total"
    )
    assert candidate["party_previously_contested"] is True
    assert candidate["first_appearance_of_party_in_area"] is False

    unmatched = build_master_database(
        (audited_input(2026, (record(2026, "Candidate One", "Conservative"),)),),
        historical_division_references={
            ("surrey-county-council-2026", "A Different Division"): approved_reference
        },
    )
    assert unmatched.divisions_and_wards[0]["previous_winning_party"] is None
    assert unmatched.divisions_and_wards[0]["historical_reference_status"] == (
        "not_approved_or_not_applicable"
    )


def test_pre_2024_legal_continuity_is_an_explicit_second_approval_path() -> None:
    """Pre-2024 continuity must be audited, not accepted from a name alone."""

    legal_continuity_reference = {
        "historical_reference_status": "approved_pre_2024_legal_continuity",
        "previous_election_event_id": "surrey-county-council-2013",
        "previous_election_date": "2 May 2013",
        "previous_area_name": "Example Division",
        "previous_winning_candidate_name": "Earlier Winner",
        "previous_winning_party": "Conservative",
        "previous_winning_candidate_vote_share": 52.0,
        "previous_turnout": None,
        "previous_electorate": 1000,
        "source_result_url": "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=1",
        "geographic_mapping_id": "surrey-principal-2013-to-2017:Example Division",
        "permission_evidence": "Configured statutory continuity evidence.",
        "permission_source_urls": ("https://www.legislation.gov.uk/example",),
    }
    payload = build_master_database(
        (audited_input(2017, (record(2017, "Candidate One", "Conservative"),)),),
        historical_division_references={
            ("surrey-county-council-2017", "Example Division"): legal_continuity_reference
        },
    )

    division = payload.divisions_and_wards[0]
    assert division["historical_reference_status"] == (
        "approved_pre_2024_legal_continuity"
    )
    assert division["previous_winning_party"] == "Conservative"
    assert division["previous_party_vote_share"] is None


def test_identity_incumbency_and_unapproved_vote_change_are_explicitly_unresolved() -> None:
    """The materialised schema must not convert missing personal evidence into a claim."""

    incomplete = replace(
        record(2017, "Candidate One", "Conservative"),
        missing_fields=("final_position",),
    )
    payload = build_master_database((audited_input(2017, (incomplete,)),))
    candidate = payload.candidate_results[0]

    assert candidate["notes"] == "Recorded missing fields: final_position"
    assert candidate["candidate_previously_stood"] is None
    assert candidate["candidate_history_status"] == "unresolved_no_explicit_identifier"
    assert candidate["incumbent_candidate"] is None
    assert candidate["incumbent_candidate_yes_no"] == "Unknown"
    assert candidate["incumbent_party_yes_no"] == "Unknown"
    assert candidate["incumbent_party_name"] is None
    assert candidate["incumbency_status"] == "unresolved_no_authoritative_linkage"
    assert candidate["change_in_vote_share"] is None
    assert candidate["change_in_vote_share_status"] == (
        "not_calculated_no_approved_exact_label_previous_share"
    )
    assert candidate["change_in_vote_share_provenance"] == "unavailable"
    assert candidate["change_in_vote_share_model_role"] == (
        "post_election_outcome_diagnostic_not_baseline_predictor"
    )


def test_verified_member_profile_can_add_positive_person_level_fields() -> None:
    """An exact official profile link can support True without name matching."""

    source = (
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017&RPID=1"
    )
    evidence = CandidateContinuityEvidence(
        evidence_id="example:verified-profile",
        election_id="surrey-county-council-2017",
        candidate_name="Candidate One",
        division_name="Example Division",
        candidate_source_url=(
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017"
        ),
        member_profile_url="https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192",
        member_uid="192",
        term_start=date(2013, 5, 3),
        profile_linked_result_urls=(
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2013",
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017",
        ),
        prior_official_elections=(
            PriorOfficialElection(
                election_id="surrey-county-council-2013",
                election_date=date(2013, 5, 2),
                source_url=(
                    "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2013"
                ),
            ),
        ),
        candidate_previously_stood=True,
        incumbent_candidate=True,
        incumbent_party="Conservative",
        evidence_text="Official profile directly links both official result pages.",
        retrieval_date="2026-07-17",
        confidence="High",
        notes=None,
    )
    payload = build_master_database(
        (audited_input(2017, (record(2017, "Candidate One", "Conservative"),)),),
        candidate_continuity_evidence={
            candidate_evidence_key("surrey-county-council-2017", source, "Candidate One"): evidence
        },
    )
    candidate = payload.candidate_results[0]

    assert candidate["candidate_previously_stood"] is True
    assert candidate["incumbent_candidate"] is True
    assert candidate["incumbent_candidate_yes_no"] == "Yes"
    assert candidate["candidate_history_status"] == "verified_official_member_profile"
    assert candidate["candidate_continuity_evidence_id"] == "example:verified-profile"


def test_supervisor_party_incumbency_is_yes_or_no_only_with_approved_comparison() -> None:
    """Party incumbency uses prior official outcomes, not personal identity evidence."""

    approved_history = {
        "historical_reference_status": "approved_pre_2024_legal_continuity",
        "previous_winning_party": "Conservative",
    }
    incumbent_party = _supervisor_incumbency_fields(
        incumbent_candidate=None,
        incumbent_candidate_status="unresolved_no_authoritative_linkage",
        current_party_name="Conservative",
        current_number_of_seats=1,
        historical_reference_fields=approved_history,
    )
    challenging_party = _supervisor_incumbency_fields(
        incumbent_candidate=None,
        incumbent_candidate_status="unresolved_no_authoritative_linkage",
        current_party_name="Liberal Democrats",
        current_number_of_seats=1,
        historical_reference_fields=approved_history,
    )
    changed_structure = _supervisor_incumbency_fields(
        incumbent_candidate=True,
        incumbent_candidate_status="verified_official_member_profile",
        current_party_name="Conservative",
        current_number_of_seats=2,
        historical_reference_fields=approved_history,
    )

    assert incumbent_party["incumbent_candidate_yes_no"] == "Unknown"
    assert incumbent_party["incumbent_party_yes_no"] == "Yes"
    assert incumbent_party["incumbent_party_name"] == "Conservative"
    assert challenging_party["incumbent_party_yes_no"] == "No"
    assert changed_structure["incumbent_candidate_yes_no"] == "Yes"
    assert changed_structure["incumbent_party_yes_no"] == "Unknown"
    assert changed_structure["incumbent_party_name"] is None


def test_verified_multi_source_evidence_adds_history_without_name_matching() -> None:
    """A manual three-source review may be used when profile links are absent."""

    source = (
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017&RPID=1"
    )
    profile_url = "https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192"
    evidence = CandidateContinuityEvidence(
        evidence_id="example:verified-multi-source",
        election_id="surrey-county-council-2017",
        candidate_name="Candidate One",
        division_name="Example Division",
        candidate_source_url=(
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017"
        ),
        member_profile_url=profile_url,
        member_uid="192",
        term_start=date(2013, 5, 3),
        profile_linked_result_urls=(),
        prior_official_elections=(
            PriorOfficialElection(
                election_id="surrey-county-council-2013",
                election_date=date(2013, 5, 2),
                source_url=(
                    "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2013"
                ),
            ),
        ),
        candidate_previously_stood=True,
        incumbent_candidate=True,
        incumbent_party="Conservative",
        evidence_text="Three public official sources were manually reviewed.",
        retrieval_date="2026-07-18",
        confidence="High",
        notes=None,
        evidence_method="official_multi_source_match",
        supporting_sources=(
            OfficialEvidenceSource(
                source_url=profile_url,
                source_type="official_member_profile",
                source_authority="Surrey County Council",
                published_candidate_name="Candidate One",
                evidence_text="Official profile uses the candidate name and term.",
            ),
            OfficialEvidenceSource(
                source_url=(
                    "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017"
                ),
                source_type="official_result_page",
                source_authority="Surrey County Council",
                published_candidate_name="Candidate One",
                evidence_text="Official target result uses the candidate name.",
            ),
            OfficialEvidenceSource(
                source_url=(
                    "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2013"
                ),
                source_type="official_result_page",
                source_authority="Surrey County Council",
                published_candidate_name="Candidate One",
                evidence_text="Official earlier result uses the candidate name.",
            ),
        ),
    )
    payload = build_master_database(
        (audited_input(2017, (record(2017, "Candidate One", "Conservative"),)),),
        candidate_continuity_evidence={
            candidate_evidence_key("surrey-county-council-2017", source, "Candidate One"): evidence
        },
    )
    candidate = payload.candidate_results[0]

    assert candidate["candidate_previously_stood"] is True
    assert candidate["incumbent_candidate"] is True
    assert candidate["candidate_history_status"] == "verified_multi_source_official_evidence"
    assert candidate["candidate_continuity_evidence_method"] == "official_multi_source_match"
    assert "ID=2013" in candidate["candidate_continuity_source_urls"]


def test_unmatched_profile_evidence_is_rejected_not_name_matched() -> None:
    """A register entry for another published name cannot be silently reused."""

    evidence = CandidateContinuityEvidence(
        evidence_id="example:wrong-name",
        election_id="surrey-county-council-2017",
        candidate_name="Different Candidate",
        division_name="Example Division",
        candidate_source_url=(
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017"
        ),
        member_profile_url="https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192",
        member_uid="192",
        term_start=date(2013, 5, 3),
        profile_linked_result_urls=(
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2013",
            "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=2017",
        ),
        prior_official_elections=(),
        candidate_previously_stood=True,
        incumbent_candidate=True,
        incumbent_party="Conservative",
        evidence_text="This object is intentionally unmatched.",
        retrieval_date="2026-07-17",
        confidence="High",
        notes=None,
    )
    evidence_key = candidate_evidence_key(
        "surrey-county-council-2017",
        evidence.candidate_source_url,
        evidence.candidate_name,
    )

    with pytest.raises(ValueError, match="does not match an exact audited candidate row"):
        build_master_database(
            (audited_input(2017, (record(2017, "Candidate One", "Conservative"),)),),
            candidate_continuity_evidence={evidence_key: evidence},
        )
