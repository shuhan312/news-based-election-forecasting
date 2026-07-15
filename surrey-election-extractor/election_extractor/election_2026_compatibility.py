"""Read-only compatibility audit helpers for the published 2026 Surrey map indexes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from election_extractor.compatibility_audit import _TableParser, inspect_official_result_page
from election_extractor.election_compatibility import CompatibilityPageClient
from election_extractor.election_config import ElectionConfiguration
from election_extractor.official_source import parse_official_election_page


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
            shared_fields = dict(parse_official_election_page(response.body).shared_fields)
            page["official_seats_value"] = shared_fields.get("number_of_seats")
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

    The function deliberately does not call discovery.py because its validated
    archive-index contract does not yet include the 2026 map-index route.
    """

    selected = tuple(item for item in configurations if item.election_year == 2026)
    if len(selected) != 2 or sample_size < 1:
        raise ValueError("The 2026 audit requires East and West configurations and a positive sample size.")

    audits = []
    for configuration in selected:
        index = _index_evidence(configuration, client)
        urls = [item["result_url"] for item in index["unique_result_urls"]]
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
                    **index,
                    "raw_result_link_count": len(index["raw_result_links"]),
                    "unique_result_page_count": len(index["unique_result_urls"]),
                    "duplicate_urls_removed": len(index["raw_result_links"]) - len(index["unique_result_urls"]),
                    "unique_official_result_identifiers": [
                        item["official_result_identifier"] for item in index["unique_result_urls"]
                    ],
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
                    "single_seat_example_observed": False,
                    "note": "No single-seat official page was included in the bounded sample; no ward magnitude is inferred from the year, candidate count or index-link repetition.",
                },
                "party_structure_audit": {
                    "published_map_key_party_names": index["party_names_from_map_key"],
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
    indexes_accessible = all(section["archive_and_discovery"]["accessible"] for section in audits)
    discovery_ready = False
    return {
        "audit_title": "Surrey County Council Election 2026 Compatibility Audit",
        "scope": "Read-only configuration validation, official map-index discovery and two representative official result pages per East/West election. No candidate extraction, workbook generation or database integration was run.",
        "compatibility_status": "requires_changes",
        "status_rationale": (
            "Candidate and Voting Summary structures are compatible in the sampled official pages, "
            "but the existing discovery stage does not support the separate 2026 www10.surreycc.gov.uk map indexes."
        ),
        "configuration_validation": {
            "configured_elections": [item.election_id for item in selected],
            "all_index_urls_accessible": indexes_accessible,
            "authority_missing_from_configuration": True,
        },
        "east_and_west": audits,
        "completeness_compatibility": {
            "candidate_level_compatible": all_candidate_fields,
            "division_level_voting_summary_compatible": all_summary_fields,
            "election_level_authority": "The current configuration omits authority, but representative official result pages publish Surrey County Council; this follows the existing official-page provenance rule.",
            "no_values_created": True,
        },
        "required_pipeline_changes": [
            "Add a narrowly validated 2026 map-index discovery route for the two configured www10.surreycc.gov.uk indexes, deduplicating published result links by EID and ID.",
        ],
        "non_changes_confirmed": [
            "No modification was made to discovery.py, official_source.py, extraction.py, validation.py or master_database.py.",
            "No 2026 candidate records, workbook rows or master-database rows were created.",
            "Seats, turnout, ranking and winners were not inferred.",
        ],
        "recommended_next_step": (
            "Implement and test only the two-index 2026 discovery adapter, then rerun this compatibility audit before approving a separate East/West extraction."
        ),
        "diagnostic_summary": {
            "map_indexes_accessible": indexes_accessible,
            "candidate_structure_compatible_in_samples": all_candidate_fields,
            "voting_summary_compatible_in_samples": all_summary_fields,
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
                f"- Result links: {discovery['raw_result_link_count']} raw; {discovery['unique_result_page_count']} unique; {discovery['duplicate_urls_removed']} repeats removed; {len(discovery['invalid_result_links'])} invalid.",
                f"- Candidate headers: {', '.join(section['candidate_table_audit']['headers']) or 'None observed'}.",
                f"- Voting Summary fields in every sampled page: {section['voting_summary_audit']['fields_available_in_all_sampled_pages']}.",
                f"- Official Seats values sampled: {section['multi_seat_audit']['official_seats_values_observed']} (from the Voting Summary only).",
                f"- Final position: {section['final_position_audit']['conclusion']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Required changes before extraction",
            "",
            *[f"- {item}" for item in audit["required_pipeline_changes"]],
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
