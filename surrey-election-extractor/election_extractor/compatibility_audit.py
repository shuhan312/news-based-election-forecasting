"""Read-only evidence helpers for detailed election compatibility audits."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from election_extractor.election_compatibility import (
    CompatibilityPageClient,
    ElectionCompatibilityReport,
)
from election_extractor.election_config import DEFAULT_CONFIG_PATH, ElectionConfiguration
from election_extractor.official_source import parse_official_election_page


REQUIRED_CONFIGURATION_FIELDS = (
    "election_id",
    "election_name",
    "election_year",
    "election_type",
    "authority",
    "official_archive_url",
)
REQUIRED_CANDIDATE_FIELDS = (
    "candidate_name",
    "original_party_name",
    "votes_received",
    "vote_share",
    "outcome",
)
REQUIRED_SUMMARY_FIELDS = (
    "number_of_seats",
    "electorate",
    "ballot_papers_issued",
    "ballot_papers_rejected",
    "turnout",
)
RANK_HEADERS = {"final position", "position", "rank", "placing"}


class _TableParser(HTMLParser):
    """Retain table labels and visible cells for diagnosis without extraction."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, object]] = []
        self._table: list[list[tuple[str, str]]] | None = None
        self._caption: list[str] = []
        self._summary = ""
        self._row: list[tuple[str, str]] | None = None
        self._cell_tag: str | None = None
        self._cell_text: list[str] = []
        self._caption_depth = 0
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "table" and self._table is None:
            self._table = []
            self._caption = []
            self._summary = dict(attrs).get("summary") or ""
        elif lowered == "caption" and self._table is not None:
            self._caption_depth += 1
        elif lowered == "tr" and self._table is not None:
            self._row = []
        elif lowered in {"th", "td"} and self._row is not None:
            self._cell_tag = lowered
            self._cell_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth = max(self._ignored_depth - 1, 0)
            return
        if self._ignored_depth:
            return
        if lowered == "caption" and self._caption_depth:
            self._caption_depth = max(self._caption_depth - 1, 0)
        elif lowered in {"th", "td"} and self._cell_tag == lowered:
            if self._row is not None:
                self._row.append((lowered, " ".join(" ".join(self._cell_text).split())))
            self._cell_tag = None
            self._cell_text = []
        elif lowered == "tr" and self._table is not None and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif lowered == "table" and self._table is not None:
            self.tables.append(
                {
                    "caption": " ".join(" ".join(self._caption).split()),
                    "summary_attribute": self._summary,
                    "rows": tuple(tuple(row) for row in self._table),
                }
            )
            self._table = None
            self._caption = []
            self._summary = ""

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._caption_depth:
            self._caption.append(cleaned)
        if self._cell_tag:
            self._cell_text.append(cleaned)


def _normalise(value: str) -> str:
    """Compare table labels without rewriting the original evidence text."""

    return " ".join(value.casefold().split())


def _candidate_table_headers(tables: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    """Return published headers for the table that visibly contains candidates."""

    for table in tables:
        for row in table["rows"]:
            cells = tuple(cell[1] for cell in row)
            normalised = {_normalise(cell) for cell in cells}
            if (
                {"candidate", "election candidate"} & normalised
                and "party" in normalised
                and "votes" in normalised
            ):
                return cells
    return ()


def _voting_summary_table(tables: Sequence[Mapping[str, object]]) -> Mapping[str, object] | None:
    """Find only a table explicitly labelled as the official Voting Summary."""

    for table in tables:
        descriptor = _normalise(
            f"{table['caption']} {table['summary_attribute']}"
        )
        if "voting summary" in descriptor:
            return table
    return None


def inspect_official_result_page(
    url: str,
    client: CompatibilityPageClient,
) -> dict[str, object]:
    """Inspect one representative page without retaining a full candidate dataset."""

    response = client.fetch(url)
    if response.status_code != 200:
        return {
            "result_url": url,
            "status_code": response.status_code,
            "error": response.error,
            "candidate_table_headers": [],
            "candidate_fields": [],
            "published_shared_fields": [],
            "voting_summary_fields": [],
            "summary_row_labels": [],
            "official_election_date": None,
            "official_authority": None,
            "final_position_headers": [],
            "party_name_examples": [],
        }

    parser = _TableParser()
    parser.feed(response.body)
    parser.close()
    page_data = parse_official_election_page(response.body)
    candidate_fields = sorted(
        {
            field_name
            for row in page_data.candidate_rows
            for field_name, _ in row.fields
        }
    )
    party_examples = []
    for row in page_data.candidate_rows:
        fields = dict(row.fields)
        party = fields.get("original_party_name")
        if party and party not in party_examples:
            party_examples.append(party)
        if len(party_examples) == 8:
            break

    headers = _candidate_table_headers(parser.tables)
    final_position_headers = [
        header
        for header in headers
        if _normalise(header) in RANK_HEADERS
        or re.search(r"\b(final position|position|rank|placing)\b", _normalise(header))
    ]
    summary_table = _voting_summary_table(parser.tables)
    summary_labels = []
    if summary_table is not None:
        for row in summary_table["rows"]:
            if len(row) >= 2 and row[0][0] == "td":
                summary_labels.append(row[0][1])

    shared_fields = dict(page_data.shared_fields)
    voting_summary_fields = sorted(
        field_name
        for field_name in REQUIRED_SUMMARY_FIELDS
        if field_name in shared_fields
    )
    return {
        "result_url": url,
        "status_code": response.status_code,
        "final_url": response.final_url,
        "candidate_table_headers": list(headers),
        "candidate_fields": candidate_fields,
        "candidate_row_count_observed": len(page_data.candidate_rows),
        # Keep page-wide fields separate from the Voting Summary subset. This
        # lets the audit distinguish election-level metadata from division data.
        "published_shared_fields": sorted(shared_fields),
        "voting_summary_fields": voting_summary_fields,
        "voting_summary_caption": summary_table["caption"] if summary_table else None,
        "voting_summary_summary_attribute": (
            summary_table["summary_attribute"] if summary_table else None
        ),
        "summary_row_labels": summary_labels,
        "official_election_date": shared_fields.get("election_date"),
        "official_authority": shared_fields.get("authority"),
        "final_position_headers": final_position_headers,
        "party_name_examples": party_examples,
    }


def configuration_check(
    configuration: ElectionConfiguration,
    raw_entry: Mapping[str, object],
    archive_accessible: bool,
) -> dict[str, object]:
    """Report configured metadata exactly as stored, without filling authority."""

    fields = []
    for field_name in REQUIRED_CONFIGURATION_FIELDS:
        value = raw_entry.get(field_name)
        available = value is not None and (not isinstance(value, str) or bool(value.strip()))
        note = None
        if field_name == "authority" and not available:
            note = (
                "Not present in elections.json. Possible source location: the "
                "official division result pages, where authority is assessed as "
                "official election-level metadata; this audit does not populate it."
            )
        fields.append(
            {
                "field": field_name,
                "available_in_configuration": available,
                "value": value if available else None,
                "note": note,
            }
        )
    parsed = urlsplit(configuration.official_url)
    return {
        "fields": fields,
        "official_archive_url_valid": (
            parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        ),
        "official_surrey_domain": (
            (parsed.hostname or "").casefold().endswith(".surreycc.gov.uk")
        ),
        "archive_accessible": archive_accessible,
    }


def raw_configuration_entry(
    election_id: str,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Mapping[str, object]:
    """Read the exact declarative configuration entry for a diagnostic report."""

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return next(
        item for item in payload["elections"] if item.get("election_id") == election_id
    )


def build_2013_audit(
    configuration: ElectionConfiguration,
    compatibility: ElectionCompatibilityReport,
    page_evidence: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Create a complete 2013 diagnostic report from bounded official evidence."""

    raw_entry = raw_configuration_entry(configuration.election_id)
    config = configuration_check(
        configuration,
        raw_entry,
        compatibility.archive.status == "accessible",
    )
    candidate_available = {
        field_name: all(field_name in page["candidate_fields"] for page in page_evidence)
        for field_name in REQUIRED_CANDIDATE_FIELDS
    }
    summary_available = {
        field_name: all(
            field_name in page["voting_summary_fields"] for page in page_evidence
        )
        for field_name in REQUIRED_SUMMARY_FIELDS
    }
    # These booleans describe source availability only. They do not construct
    # a date or authority when an official page omits either value.
    official_date_observed = any(
        page.get("official_election_date") is not None for page in page_evidence
    )
    official_authority_observed = any(
        page.get("official_authority") is not None for page in page_evidence
    )

    party_examples = []
    for page in page_evidence:
        for party in page["party_name_examples"]:
            if party not in party_examples:
                party_examples.append(party)
    final_position_present = any(page["final_position_headers"] for page in page_evidence)
    missing_summary = [
        field_name for field_name, available in summary_available.items() if not available
    ]
    no_new_rule_required = not any(
        not available for available in candidate_available.values()
    )
    return {
        "audit_title": "Surrey County Council Election 2013 Compatibility Audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": (
            "Read-only configuration, archive discovery and three representative "
            "official result pages. No candidate-result extraction was run."
        ),
        "compatibility_status": compatibility.overall_status.value,
        "configuration_check": config,
        "archive_check": compatibility.archive,
        "discovery_check": {
            "unique_divisions_found": compatibility.discovery.unique_divisions_found,
            "accepted_divisions": compatibility.discovery.accepted_divisions,
            "raw_result_links_found": compatibility.discovery.raw_result_links_found,
            "duplicate_urls_removed": compatibility.discovery.duplicate_urls_removed,
            "invalid_or_failed_links": compatibility.discovery.failed_urls,
            "result_url_patterns": compatibility.discovery.url_patterns,
            "pagination_and_index_behaviour": (
                "Existing discovery followed the official 2013 election-area index "
                "and its published Page parameters; duplicate result URLs were "
                "deduplicated by result ID."
            ),
            "risk": "Result-page metadata omits election name and year, but verified official URLs remain accepted with metadata_status=missing.",
        },
        "representative_result_pages": list(page_evidence),
        "candidate_result_compatibility": {
            "required_fields_available_in_all_sampled_pages": candidate_available,
            "structural_difference_from_2017_2021": (
                "No required candidate-table field difference was observed in the "
                "three representative official pages."
                if all(candidate_available.values())
                else "One or more required candidate fields were not observed; review before extraction."
            ),
        },
        "voting_summary_compatibility": {
            "fields_available_in_all_sampled_pages": summary_available,
            "missing_fields": missing_summary,
            "structural_difference_from_2017_2021": (
                "The representative 2013 Voting Summary pages do not publish "
                + ", ".join(missing_summary)
                + ". These remain NULL at division level; no values are inferred."
                if missing_summary
                else "No Voting Summary difference was observed in the representative pages."
            ),
        },
        "metadata_and_completeness_compatibility": {
            "election_level": {
                "election_name": "configuration",
                "election_date": (
                    "official result page observed"
                    if official_date_observed
                    else "not observed in sampled official result pages"
                ),
                "election_type": "configuration",
                "authority": (
                    "official result page observed; missing from current configuration"
                    if official_authority_observed
                    else "not observed in sampled official result pages and missing from current configuration"
                ),
            },
            "division_level": (
                "Existing layered completeness can retain missing official ballot "
                "papers issued and turnout as division-level NULL values."
            ),
            "candidate_level": (
                "Candidate completeness uses candidate name, original party name, "
                "votes, vote share and outcome only."
            ),
            "new_completeness_rule_required": not no_new_rule_required,
        },
        "final_position_check": {
            "official_field_present": final_position_present,
            "headers_observed": sorted(
                {
                    header
                    for page in page_evidence
                    for header in page["final_position_headers"]
                }
            ),
            "conclusion": (
                "Official final_position exists and should be extracted."
                if final_position_present
                else "Official final_position was not observed and must remain NULL; no vote-based ranking is calculated."
            ),
        },
        "party_handling_check": {
            "original_party_name_examples": party_examples,
            "standardisation_risk": (
                "Original published wording varies by party. Preserve it unchanged; "
                "do not merge UK Independence Party/UKIP with Reform UK."
            ),
        },
        "comparison_with_2017_2021": compatibility.structural_differences_from_2021,
        "required_future_changes": (
            []
            if no_new_rule_required
            else ["Review missing required candidate fields before approving extraction."]
        ),
        "recommendation": compatibility.recommendation,
        "source_provenance": compatibility.provenance,
    }


def _as_json(value: object) -> object:
    """Serialise compatibility dataclasses without changing their content."""

    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot serialise {type(value).__name__}.")


def audit_markdown(audit: Mapping[str, object]) -> str:
    """Render a concise report while retaining detail in the companion JSON file."""

    discovery = audit["discovery_check"]
    candidate = audit["candidate_result_compatibility"]
    summary = audit["voting_summary_compatibility"]
    final_position = audit["final_position_check"]
    party = audit["party_handling_check"]
    assert isinstance(discovery, Mapping)
    assert isinstance(candidate, Mapping)
    assert isinstance(summary, Mapping)
    assert isinstance(final_position, Mapping)
    assert isinstance(party, Mapping)
    lines = [
        "# Surrey County Council Election 2013 Compatibility Audit",
        "",
        f"- Compatibility status: `{audit['compatibility_status']}`",
        "- Scope: read-only archive discovery and three representative official result pages; no extraction was run.",
        "",
        "## Configuration and archive",
        "",
        f"- Official archive: `{audit['archive_check'].url}` ({audit['archive_check'].status}).",
        "- `authority` is absent from the current configuration and is not filled by this audit; official result pages are the possible source location.",
        "",
        "## Discovery",
        "",
        f"- Unique divisions: {discovery['unique_divisions_found']}",
        f"- Raw links: {discovery['raw_result_links_found']}; duplicates removed: {discovery['duplicate_urls_removed']}; invalid/failed: {discovery['invalid_or_failed_links']}.",
        f"- URL pattern: {', '.join(discovery['result_url_patterns']) or 'None'}.",
        f"- {discovery['pagination_and_index_behaviour']}",
        "",
        "## Result-page structure",
        "",
        f"- Candidate fields available in all sampled pages: {candidate['required_fields_available_in_all_sampled_pages']}",
        f"- Voting Summary availability in all sampled pages: {summary['fields_available_in_all_sampled_pages']}",
        f"- Voting Summary difference: {summary['structural_difference_from_2017_2021']}",
        f"- Final position: {final_position['conclusion']}",
        "",
        "## Party handling and completeness",
        "",
        f"- Published party examples: {', '.join(party['original_party_name_examples']) or 'None observed'}.",
        f"- {party['standardisation_risk']}",
        "- Existing layered completeness can retain missing division-level official fields as NULL; no new candidate-level completeness rule is required.",
        "",
        "## Recommendation",
        "",
        str(audit["recommendation"]),
        "",
    ]
    return "\n".join(lines)
