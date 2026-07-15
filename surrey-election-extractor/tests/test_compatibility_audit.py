"""Tests for the bounded, read-only 2013 compatibility audit helpers."""

from election_extractor.compatibility_audit import (
    audit_markdown,
    build_2013_audit,
    configuration_check,
    inspect_official_result_page,
    raw_configuration_entry,
)
from election_extractor.election_compatibility import (
    ArchiveCompatibility,
    CompatibilityPageResponse,
    CompatibilityStatus,
    DiscoveryCompatibility,
    ElectionCompatibilityReport,
    MetadataCompatibility,
    ResultStructureCompatibility,
)
from election_extractor.election_config import load_election_config


RESULT_URL = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=87"


class MockPageClient:
    """Return fixed official-style HTML without making a public HTTP request."""

    def fetch(self, url: str) -> CompatibilityPageResponse:
        return CompatibilityPageResponse(200, url, representative_result_page())


def representative_result_page() -> str:
    """Model the published labels needed for compatibility-only inspection."""

    return """
    <html><head><title>Election results for Addlestone, 2 May 2013</title></head>
    <body>
      <p>Surrey County Council</p>
      <table>
        <tr><th>Election Candidate</th><th>Party</th><th>Votes</th><th>Vote Share</th><th>Outcome</th></tr>
        <tr><td>Example Candidate</td><td>UK Independence Party</td><td>100</td><td>50%</td><td>Elected</td></tr>
      </table>
      <table summary="Voting summary table">
        <caption>Voting Summary</caption>
        <tr><th>Details</th><th>Number</th></tr>
        <tr><td>Seats</td><td>1</td></tr>
        <tr><td>Total votes</td><td>100</td></tr>
        <tr><td>Electorate</td><td>200</td></tr>
        <tr><td>Number of ballot papers rejected</td><td>0</td></tr>
      </table>
    </body></html>
    """


def configured_2013():
    """Load the declared 2013 entry used by the audit."""

    return next(
        item
        for item in load_election_config()
        if item.election_id == "surrey-county-council-2013"
    )


def compatible_report() -> ElectionCompatibilityReport:
    """Build a minimal compatible report to test report rendering only."""

    configuration = configured_2013()
    return ElectionCompatibilityReport(
        election_id=configuration.election_id,
        election_year=configuration.election_year,
        election_name=configuration.election_name,
        election_type=configuration.election_type,
        archive_url=configuration.official_url,
        overall_status=CompatibilityStatus.COMPATIBLE,
        archive=ArchiveCompatibility("accessible", configuration.official_url, True, "HTTP 200"),
        discovery=DiscoveryCompatibility(81, 243, 162, 0, ("/mgElectionAreaResults.aspx",), (), 81, 81),
        result_structure=ResultStructureCompatibility(1, {}, {}, (), (), ()),
        metadata=MetadataCompatibility("official_result_page", False, "Seats observed."),
        risks=(),
        recommendation="A later, separately approved extraction run can use the existing pipeline.",
        provenance={"representative_result_page_urls": (RESULT_URL,)},
    )


def test_page_inspection_keeps_published_labels_and_does_not_create_rank() -> None:
    """The inspector records visible HTML labels without deriving missing values."""

    evidence = inspect_official_result_page(RESULT_URL, MockPageClient())

    assert evidence["candidate_table_headers"] == [
        "Election Candidate", "Party", "Votes", "Vote Share", "Outcome"
    ]
    assert "number_of_seats" in evidence["voting_summary_fields"]
    assert "ballot_papers_issued" not in evidence["voting_summary_fields"]
    assert evidence["final_position_headers"] == []
    assert evidence["party_name_examples"] == ["UK Independence Party"]


def test_configuration_audit_reports_missing_authority_without_filling_it() -> None:
    """Missing configuration data remains explicitly missing in the audit."""

    configuration = configured_2013()
    check = configuration_check(
        configuration,
        raw_configuration_entry(configuration.election_id),
        archive_accessible=True,
    )
    authority = next(item for item in check["fields"] if item["field"] == "authority")

    assert authority["available_in_configuration"] is False
    assert authority["value"] is None
    assert "does not populate" in authority["note"]


def test_audit_reports_division_missing_values_without_changing_candidate_rules() -> None:
    """Missing summary fields stay division-level and final position remains NULL."""

    evidence = inspect_official_result_page(RESULT_URL, MockPageClient())
    audit = build_2013_audit(configured_2013(), compatible_report(), (evidence,))

    assert audit["voting_summary_compatibility"]["fields_available_in_all_sampled_pages"]["ballot_papers_issued"] is False
    assert audit["metadata_and_completeness_compatibility"]["new_completeness_rule_required"] is False
    assert "must remain NULL" in audit["final_position_check"]["conclusion"]
    assert "Compatibility status" in audit_markdown(audit)
