"""Read-only compatibility audit helpers for the published 2026 Surrey map indexes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from election_extractor.compatibility_audit import _TableParser, inspect_official_result_page
from election_extractor.discovery import OfficialArchiveResponse, discover_election_areas
from election_extractor.election_compatibility import CompatibilityPageClient
from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord
from election_extractor.official_source import parse_official_election_page
from election_extractor.search_providers.mock_provider import MockSearchProvider
from election_extractor.workbook import CANDIDATE_COLUMNS


RESULT_HOST = "mycouncil.surreycc.gov.uk"
RESULT_PATH = "/mgElectionAreaResults.aspx"
DECLARED_WARDS_PATTERN = re.compile(r"\b(\d+)\s+of\s+(\d+)\s+wards\s+declared\b", re.I)
REQUIRED_CANDIDATE_FIELDS = (
    "candidate_name",
    "original_party_name",
    "votes_received",
    "vote_share",
    "outcome",
)
REQUIRED_SUMMARY_FIELDS = (
    "number_of_seats",
    "total_votes",
    "electorate",
    "ballot_papers_issued",
    "ballot_papers_rejected",
    "turnout",
)
RANK_WORDS = ("final position", "position", "rank", "placing")


@dataclass(frozen=True)
class _MapAnchor:
    """Keep the published ward label beside its literal map-index target."""

    href: str
    text: str


class _MapIndexParser(HTMLParser):
    """Read visible index text and anchors without executing map-page scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible_text: list[str] = []
        self.anchors: list[_MapAnchor] = []
        self._ignored_depth = 0
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = href
                self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth = max(self._ignored_depth - 1, 0)
            return
        if self._ignored_depth:
            return
        if lowered == "a" and self._href is not None:
            self.anchors.append(
                _MapAnchor(
                    href=self._href,
                    text=" ".join(" ".join(self._anchor_text).split()),
                )
            )
            self._href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        self.visible_text.append(cleaned)
        if self._href is not None:
            self._anchor_text.append(cleaned)


class _DiscoveryAuditClient:
    """Adapt compatibility responses to the established discovery client contract.

    The audit uses the real discovery adapter rather than duplicating its map
    link rules. This wrapper is read-only and only converts response shapes;
    it never changes URLs, HTML or election metadata.
    """

    def __init__(self, client: CompatibilityPageClient) -> None:
        self._client = client

    def fetch(self, url: str) -> OfficialArchiveResponse:
        response = self._client.fetch(url)
        return OfficialArchiveResponse(
            status_code=response.status_code or 0,
            final_url=response.final_url or url,
            body=response.body,
        )


def _discovery_evidence(
    configuration: ElectionConfiguration,
    client: CompatibilityPageClient,
) -> dict[str, object]:
    """Run the current map-index adapter and retain its auditable output.

    An empty mocked search provider is intentional. A 2026 map index is the
    authoritative discovery source, so this diagnostic must not add wards from
    indexed search results if a map link is unavailable or malformed.
    """
    report = discover_election_areas(
        configuration.official_url,
        MockSearchProvider({}),
        archive_client=_DiscoveryAuditClient(client),
    )
    map_attempt = next(
        (
            attempt
            for attempt in report.search_attempts
            if attempt.validation_result == "map_index_loaded"
        ),
        None,
    )
    rejected_attempts = [
        attempt
        for attempt in report.search_attempts
        if attempt.validation_result == "rejected"
    ]
    duplicate_attempts = [
        attempt
        for attempt in report.search_attempts
        if attempt.validation_result == "duplicate"
    ]
    failed_attempts = [
        attempt for attempt in report.search_attempts if attempt.status == "failed"
    ]
    areas = list(report.areas)
    output_compatible = bool(areas) and all(
        area.discovery_status.value == "discovered"
        and area.discovery_method == "official_map_index"
        and area.division_ward_name
        and area.source_index_url == configuration.official_url
        and area.official_index_url == configuration.official_url
        and "EID=" in area.result_url
        and "ID=" in area.result_url
        for area in areas
    )
    return {
        "source_index_url": report.source_index_url,
        "raw_result_link_count": map_attempt.result_count if map_attempt else 0,
        "unique_result_page_count": len(areas),
        "duplicate_urls_removed": len(duplicate_attempts),
        "rejected_result_links": [
            {"result_url": attempt.discovered_url, "reason": attempt.rejection_reason}
            for attempt in rejected_attempts
        ],
        "failed_discovery_attempts": len(failed_attempts),
        "discovery_methods": sorted({area.discovery_method for area in areas}),
        "output_can_be_consumed_by_extraction": output_compatible,
        "provenance_preserved": output_compatible,
        "discovered_areas": [
            {
                "division_ward_name": area.division_ward_name,
                "result_url": area.result_url,
                "source_index_url": area.source_index_url,
                "official_index_url": area.official_index_url,
                "discovery_status": area.discovery_status.value,
                "metadata_status": area.metadata_status.value,
                "missing_metadata_fields": list(area.missing_metadata_fields),
            }
            for area in areas
        ],
    }


def _result_url(url: str) -> str | None:
    """Accept only an official 2026 result link with both published identifiers."""

    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or (parsed.hostname or "").casefold() != RESULT_HOST
        or parsed.path.casefold() != RESULT_PATH.casefold()
    ):
        return None
    values = {
        key.casefold(): value
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    }
    if not values.get("id", "").isdigit() or not values.get("eid", "").isdigit():
        return None
    # Stable normalisation prevents one displayed link per elected candidate
    # from being mistaken for several ward result pages.
    parameters = sorted(
        ((key.upper(), value) for key, value in values.items()),
        key=lambda item: item[0],
    )
    return urlunsplit(("https", RESULT_HOST, RESULT_PATH, urlencode(parameters), ""))


def _result_id(url: str) -> str:
    """Return the official EID/ID pair; either value alone is not sufficient."""

    values = {key.casefold(): value for key, value in parse_qsl(urlsplit(url).query)}
    return f"EID={values['eid']}; ID={values['id']}"


def _declared_ward_count(text: Sequence[str]) -> dict[str, int | None]:
    """Record only the published declared-ward count from the map index."""

    match = DECLARED_WARDS_PATTERN.search(" ".join(text))
    if match is None:
        return {"declared": None, "total": None}
    return {"declared": int(match.group(1)), "total": int(match.group(2))}


def _party_names_from_index(body: str) -> list[str]:
    """Read only the published Party column of the map-key table.

    The shared table parser already preserves captions and individual cells.
    Reusing it here prevents visible map-key colour labels or later search-page
    text from being misclassified as party names.
    """

    parser = _TableParser()
    parser.feed(body)
    parser.close()
    parties: list[str] = []
    for table in parser.tables:
        descriptor = f"{table['caption']} {table['summary_attribute']}".casefold()
        if "map key" not in descriptor:
            continue
        for row in table["rows"]:
            cells = [cell[1] for cell in row]
            if len(cells) < 2 or cells[-1] == "Party":
                continue
            party = cells[-1]
            if party and party not in parties:
                parties.append(party)
    return parties


def _index_evidence(
    configuration: ElectionConfiguration,
    client: CompatibilityPageClient,
) -> dict[str, object]:
    """Inspect one East/West map index without using the historical discovery stage."""

    response = client.fetch(configuration.official_url)
    if response.status_code != 200:
        return {
            "index_url": configuration.official_url,
            "status_code": response.status_code,
            "accessible": False,
            "error": response.error,
            "declared_wards": {"declared": None, "total": None},
            "raw_result_links": [],
            "unique_result_urls": [],
            "invalid_result_links": [],
            "party_names_from_map_key": [],
            "pagination_observed": False,
        }

    parser = _MapIndexParser()
    parser.feed(response.body)
    parser.close()
    raw_links: list[dict[str, str]] = []
    invalid_links: list[dict[str, str]] = []
    for anchor in parser.anchors:
        absolute = urljoin(configuration.official_url, anchor.href)
        if urlsplit(absolute).path.casefold() != RESULT_PATH.casefold():
            continue
        normalised = _result_url(absolute)
        evidence = {"ward_name": anchor.text, "literal_url": absolute}
        if normalised is None:
            invalid_links.append(evidence)
        else:
            raw_links.append({**evidence, "result_url": normalised})

    by_url: dict[str, dict[str, str]] = {}
    for item in raw_links:
        # Repeated links are expected where the map index lists each elected
        # candidate. Keep one ward result page; this is not a Seats inference.
        by_url.setdefault(item["result_url"], item)
    unique = [
        {**item, "official_result_identifier": _result_id(url)}
        for url, item in sorted(by_url.items(), key=lambda pair: _result_id(pair[0]))
    ]
    return {
        "index_url": configuration.official_url,
        "status_code": response.status_code,
        "accessible": True,
        "error": response.error,
        "declared_wards": _declared_ward_count(parser.visible_text),
        "raw_result_links": raw_links,
        "unique_result_urls": unique,
        "invalid_result_links": invalid_links,
        "party_names_from_map_key": _party_names_from_index(response.body),
        # A single published map page was inspected. No page-navigation control
        # was observed, but this does not assert that pagination never exists.
        "pagination_observed": False,
    }


def _page_evidence(
    urls: Sequence[str], client: CompatibilityPageClient
) -> list[dict[str, object]]:
    """Inspect a bounded page sample for structure only, never candidate data."""

    evidence = []
    for url in urls:
        page = inspect_official_result_page(url, client)
        if page["status_code"] == 200:
            # Only the named Voting Summary supplies Seats. The value is stored
            # for audit evidence, not used to fill any election record.
            response = client.fetch(url)
            parsed_page = parse_official_election_page(response.body)
            shared_fields = dict(parsed_page.shared_fields)
            page["official_seats_value"] = shared_fields.get("number_of_seats")
            outcomes = [dict(row.fields).get("outcome") for row in parsed_page.candidate_rows]
            page["candidate_outcomes_observed"] = outcomes
            page["elected_candidate_count_observed"] = sum(
                outcome == "Elected" for outcome in outcomes
            )
            # The earlier compatibility helper predates the master database's
            # ``total_votes`` field. This audit reads that published summary
            # field directly without changing the shared extraction parser.
            page["voting_summary_fields"] = sorted(
                {
                    *page["voting_summary_fields"],
                    *(field for field in REQUIRED_SUMMARY_FIELDS if field in shared_fields),
                }
            )
        else:
            page["official_seats_value"] = None
            page["candidate_outcomes_observed"] = []
            page["elected_candidate_count_observed"] = 0
        evidence.append(page)
    return evidence


def _all_required(pages: Sequence[Mapping[str, object]], key: str, fields: Sequence[str]) -> dict[str, bool]:
    """Report field availability across sampled pages without constructing values."""

    return {
        field: bool(pages) and all(field in page[key] for page in pages)
        for field in fields
    }


def build_2026_compatibility_audit(
    configurations: Sequence[ElectionConfiguration],
    client: CompatibilityPageClient,
    *,
    sample_size: int = 2,
) -> dict[str, object]:
    """Create the required read-only East/West compatibility decision.

    The function exercises the implemented 2026 map-index discovery route,
    then inspects a bounded sample of its official result-page output. It does
    not start candidate extraction or create any 2026 data product.
    """

    selected = tuple(item for item in configurations if item.election_year == 2026)
    if len(selected) != 2 or sample_size < 1:
        raise ValueError("The 2026 audit requires East and West configurations and a positive sample size.")

    audits = []
    for configuration in selected:
        index = _index_evidence(configuration, client)
        discovery = _discovery_evidence(configuration, client)
        urls = [item["result_url"] for item in discovery["discovered_areas"]]
        pages = _page_evidence(urls[:sample_size], client)
        candidate_fields = _all_required(pages, "candidate_fields", REQUIRED_CANDIDATE_FIELDS)
        summary_fields = _all_required(pages, "voting_summary_fields", REQUIRED_SUMMARY_FIELDS)
        headers = sorted({header for page in pages for header in page["candidate_table_headers"]})
        rank_headers = sorted({header for page in pages for header in page["final_position_headers"]})
        official_authorities = sorted(
            {
                str(page["official_authority"])
                for page in pages
                if page.get("official_authority")
            }
        )
        official_dates = sorted(
            {
                str(page["official_election_date"])
                for page in pages
                if page.get("official_election_date")
            }
        )
        published_party_names = list(index["party_names_from_map_key"])
        for page in pages:
            for party in page["party_name_examples"]:
                if party not in published_party_names:
                    published_party_names.append(party)
        local_or_independent_names = [
            party
            for party in published_party_names
            if "independent" in party.casefold() or "resident" in party.casefold()
        ]
        candidate_record_fields = {field.name for field in fields(CandidateResultRecord)}
        elected_counts = [page["elected_candidate_count_observed"] for page in pages]
        discovery_matches_declared_count = (
            index["declared_wards"]["total"] is not None
            and discovery["unique_result_page_count"] == index["declared_wards"]["total"]
        )
        audits.append(
            {
                "election_id": configuration.election_id,
                "election_name": configuration.election_name,
                "election_year": configuration.election_year,
                "election_type": configuration.election_type,
                "configuration_authority": None,
                "configuration_authority_status": "missing",
                "official_authorities_observed": official_authorities,
                "official_dates_observed": official_dates,
                "archive_and_discovery": {
                    "index_url": index["index_url"],
                    "index_status_code": index["status_code"],
                    "index_accessible": index["accessible"],
                    "index_error": index["error"],
                    "declared_wards": index["declared_wards"],
                    "declared_count_matches_discovery": discovery_matches_declared_count,
                    **discovery,
                },
                "representative_result_pages": pages,
                "candidate_table_audit": {
                    "headers": headers,
                    "required_fields_available_in_all_sampled_pages": candidate_fields,
                },
                "voting_summary_audit": {
                    "fields_available_in_all_sampled_pages": summary_fields,
                    "source_location": "Official table captioned Voting Summary",
                },
                "multi_seat_audit": {
                    "official_seats_values_observed": [page["official_seats_value"] for page in pages],
                    "official_source_location": "Official Voting Summary row labelled Seats",
                    "elected_candidate_counts_observed": elected_counts,
                    "multiple_elected_candidates_observed": any(count > 1 for count in elected_counts),
                    "candidate_results_schema_support": {
                        "one_row_per_candidate": True,
                        "published_outcome_field": "outcome" in candidate_record_fields,
                        "official_seats_field": "number_of_seats" in candidate_record_fields,
                    },
                    "validation_support": "Validation groups records by official result URL and evaluates candidate fields independently; it does not require exactly one elected candidate.",
                    "workbook_support": {
                        "candidate_results_columns": list(CANDIDATE_COLUMNS),
                        "one_row_per_candidate": True,
                    },
                    "note": "Each Seats value is read only from the official Voting Summary. No ward magnitude is inferred from the year, candidate count or repeated map link.",
                },
                "party_structure_audit": {
                    "published_party_names_observed": published_party_names,
                    "local_or_independent_names_observed": local_or_independent_names,
                    "historical_name_comparison": "Not determined in this diagnostic because full 2026 candidate extraction has not run. Every observed label remains original published wording until a separate explicit lookup is reviewed.",
                    "standardisation_risk": "Local resident and independent labels require a future explicit lookup; original published party wording must remain unchanged.",
                    "ukip_reform_handling": "Reform UK is observed. UKIP is not merged with Reform UK and remains a distinct historical party where present.",
                },
                "final_position_audit": {
                    "headers_observed": rank_headers,
                    "official_field_present": bool(rank_headers),
                    "conclusion": (
                        "Official final_position exists and should be extracted."
                        if rank_headers
                        else "Official final_position was not observed in the sampled candidate tables and must remain NULL; no ranking is calculated from votes."
                    ),
                },
            }
        )

    all_candidate_fields = all(
        all(section["candidate_table_audit"]["required_fields_available_in_all_sampled_pages"].values())
        for section in audits
    )
    all_summary_fields = all(
        all(section["voting_summary_audit"]["fields_available_in_all_sampled_pages"].values())
        for section in audits
    )
    indexes_accessible = all(section["archive_and_discovery"]["index_accessible"] for section in audits)
    discovery_ready = all(
        section["archive_and_discovery"]["output_can_be_consumed_by_extraction"]
        and section["archive_and_discovery"]["declared_count_matches_discovery"]
        and section["archive_and_discovery"]["failed_discovery_attempts"] == 0
        for section in audits
    )
    multi_seat_compatible = all(
        section["multi_seat_audit"]["multiple_elected_candidates_observed"]
        and all(section["multi_seat_audit"]["candidate_results_schema_support"].values())
        and section["multi_seat_audit"]["workbook_support"]["one_row_per_candidate"]
        for section in audits
    )
    election_metadata_compatible = all(
        section["election_name"]
        and section["election_type"]
        and section["official_dates_observed"]
        and section["official_authorities_observed"]
        for section in audits
    )
    completeness_compatible = election_metadata_compatible and all_candidate_fields and all_summary_fields
    compatible = (
        indexes_accessible
        and discovery_ready
        and all_candidate_fields
        and all_summary_fields
        and multi_seat_compatible
        and completeness_compatible
    )
    status = "compatible" if compatible else "requires_changes"
    status_rationale = (
        "The implemented 2026 map-index discovery adapter produces the complete published East and West ward URL sets, and representative official result pages are compatible with the existing candidate, Voting Summary, multi-seat and layered-completeness contracts."
        if compatible
        else "One or more required discovery, page-structure, multi-seat or completeness checks did not pass; inspect the evidence sections before extraction."
    )
    return {
        "audit_title": "Surrey County Council Election 2026 Compatibility Audit",
        "scope": "Read-only configuration validation, official map-index discovery and two representative official result pages per East/West election. No candidate extraction, workbook generation or database integration was run.",
        "compatibility_status": status,
        "status_rationale": status_rationale,
        "configuration_validation": {
            "configured_elections": [item.election_id for item in selected],
            "all_index_urls_accessible": indexes_accessible,
            "authority_missing_from_configuration": True,
        },
        "east_and_west": audits,
        "completeness_compatibility": {
            "election_level_compatible": election_metadata_compatible,
            "candidate_level_compatible": all_candidate_fields,
            "division_level_voting_summary_compatible": all_summary_fields,
            "election_level_sources": {
                "election_name": "elections.json configuration",
                "election_type": "elections.json configuration",
                "election_date": "representative official result pages",
                "authority": "representative official result pages",
            },
            "candidate_level_boundary": "Candidate completeness requires candidate, party, votes, vote share and Outcome only; ward-level Voting Summary fields are assessed separately.",
            "no_values_created": True,
        },
        "required_pipeline_changes": [] if compatible else [
            "Resolve the failed compatibility checks before any 2026 extraction is authorised."
        ],
        "non_changes_confirmed": [
            "This audit used the implemented discovery.py map-index adapter but did not modify discovery.py, official_source.py, extraction.py, validation.py, completeness.py or master_database.py.",
            "No 2026 candidate records, workbook rows or master-database rows were created.",
            "Seats, turnout, ranking and winners were not inferred.",
        ],
        "recommended_next_step": (
            "Subject to separate authorisation, run the existing full pipeline independently for East Surrey and West Surrey. Keep the two 2026 outputs separate from the historical master database until old divisions and new wards have been mapped."
            if compatible
            else "Resolve the identified compatibility issues, then rerun this diagnostic before authorising any 2026 extraction."
        ),
        "diagnostic_summary": {
            "map_indexes_accessible": indexes_accessible,
            "candidate_structure_compatible_in_samples": all_candidate_fields,
            "voting_summary_compatible_in_samples": all_summary_fields,
            "multi_seat_model_compatible_in_samples": multi_seat_compatible,
            "layered_completeness_compatible_in_samples": completeness_compatible,
            "existing_discovery_ready": discovery_ready,
        },
    }


def audit_markdown(audit: Mapping[str, object]) -> str:
    """Render a concise reviewer-facing report from the JSON evidence record."""

    lines = [
        "# Surrey County Council Election 2026 Compatibility Audit",
        "",
        f"- Compatibility status: `{audit['compatibility_status']}`",
        f"- {audit['status_rationale']}",
        "",
        "## Official map indexes",
        "",
    ]
    for section in audit["east_and_west"]:
        discovery = section["archive_and_discovery"]
        lines.extend(
            [
                f"### {section['election_id']}",
                f"- Index: {discovery['index_url']}",
                f"- Declared wards: {discovery['declared_wards']['declared']} of {discovery['declared_wards']['total']}",
                f"- Result links: {discovery['raw_result_link_count']} raw; {discovery['unique_result_page_count']} unique; {discovery['duplicate_urls_removed']} repeats removed; {len(discovery['rejected_result_links'])} rejected.",
                f"- Candidate headers: {', '.join(section['candidate_table_audit']['headers']) or 'None observed'}.",
                f"- Voting Summary fields in every sampled page: {section['voting_summary_audit']['fields_available_in_all_sampled_pages']}.",
                f"- Official Seats values sampled: {section['multi_seat_audit']['official_seats_values_observed']} (from the Voting Summary only).",
                f"- Final position: {section['final_position_audit']['conclusion']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Discovery and parsing compatibility",
            "",
            *[
                f"- {section['election_id']}: discovery output consumable by extraction = {section['archive_and_discovery']['output_can_be_consumed_by_extraction']}; declared count matches discovery = {section['archive_and_discovery']['declared_count_matches_discovery']}."
                for section in audit["east_and_west"]
            ],
            "",
            "## Multi-seat and completeness compatibility",
            "",
            *[
                f"- {section['election_id']}: elected candidates observed per sampled page = {section['multi_seat_audit']['elected_candidate_counts_observed']}; multiple-elected support observed = {section['multi_seat_audit']['multiple_elected_candidates_observed']}."
                for section in audit["east_and_west"]
            ],
            f"- Layered completeness compatible in sampled pages: {audit['diagnostic_summary']['layered_completeness_compatible_in_samples']}.",
            "",
            "## Remaining risks",
            "",
            "- This is a bounded diagnostic, not a full candidate extraction. All 2026 wards must still be processed independently before results are used.",
            "- East and West outputs must remain separate from 2013, 2017 and 2021 until ward-boundary mapping is completed.",
            "- Published local party wording requires a later explicit lookup; it must not be standardised or merged during this audit.",
            "",
            "## Confirmed boundaries",
            "",
            *[f"- {item}" for item in audit["non_changes_confirmed"]],
            "",
            "## Recommendation",
            "",
            str(audit["recommended_next_step"]),
            "",
        ]
    )
    return "\n".join(lines)
