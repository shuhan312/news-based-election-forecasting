"""Assemble a source-preserving multi-election analytical database payload."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from election_extractor.completeness import (
    CompletenessStatus,
    LayeredCompletenessReport,
    assess_layered_completeness,
)
from election_extractor.election_config import ElectionConfiguration, load_election_config
from election_extractor.election_structure_metadata import load_secondary_seats_audit
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.models import ElectionStructureMetadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDITED_ELECTION_INPUTS = {
    "surrey-county-council-2013": {
        "audit_path": PROJECT_ROOT / "outputs/2013_full_extraction/2013_extraction_audit.json",
        "secondary_seats_audit": None,
    },
    "surrey-county-council-2017": {
        "audit_path": PROJECT_ROOT / "outputs/2017_full_extraction/2017_extraction_audit.json",
        "secondary_seats_audit": None,
    },
    "surrey-county-council-2021": {
        "audit_path": PROJECT_ROOT
        / "outputs/2021_archive_discovery_pilot/2021_archive_discovery_pilot_audit.json",
        "secondary_seats_audit": PROJECT_ROOT
        / "outputs/2021_secondary_seats_audit/2021_secondary_seats_audit.json",
    },
}


@dataclass(frozen=True)
class AuditedElectionInput:
    """Keep one completed election audit and its optional secondary Seats audit."""

    configuration: ElectionConfiguration
    audit_path: Path
    records: tuple[CandidateResultRecord, ...]
    election_structure_metadata: tuple[ElectionStructureMetadata, ...]


@dataclass(frozen=True)
class MasterDatabasePayload:
    """Contain tables and documentation without changing any source record."""

    elections: tuple[dict[str, object], ...]
    candidate_results: tuple[dict[str, object], ...]
    divisions_and_wards: tuple[dict[str, object], ...]
    candidates: tuple[dict[str, object], ...]
    political_parties: tuple[dict[str, object], ...]
    party_history_and_new_entrants: tuple[dict[str, object], ...]
    data_dictionary: tuple[dict[str, object], ...]
    audit_summary: dict[str, object]


def _record_from_audit(payload: Mapping[str, object]) -> CandidateResultRecord:
    """Rebuild a record from a completed audit without copying field evidence.

    The master database only needs published values and record-level provenance.
    Detailed per-field evidence remains in the existing audit file referenced by
    the source URL and generated audit summary.
    """

    return CandidateResultRecord(
        election_name=_optional_text(payload.get("election_name")),
        election_date=_optional_text(payload.get("election_date")),
        authority=_optional_text(payload.get("authority")),
        division_ward_name=_optional_text(payload.get("division_ward_name")),
        number_of_seats=_optional_int(payload.get("number_of_seats")),
        candidate_name=str(payload["candidate_name"]),
        original_party_name=_optional_text(payload.get("original_party_name")),
        votes_received=_optional_int(payload.get("votes_received")),
        vote_share=_optional_float(payload.get("vote_share")),
        outcome=_optional_text(payload.get("outcome")),
        electorate=_optional_int(payload.get("electorate")),
        ballot_papers_issued=_optional_int(payload.get("ballot_papers_issued")),
        ballot_papers_rejected=_optional_int(payload.get("ballot_papers_rejected")),
        turnout=_optional_float(payload.get("turnout")),
        source_url=str(payload["source_url"]),
        extraction_status=ExtractionStatus(str(payload["extraction_status"])),
        missing_fields=tuple(str(item) for item in payload.get("missing_fields", ())),
        election_type=_optional_text(payload.get("election_type")),
        final_position=_optional_int(payload.get("final_position")),
        elected=_optional_text(payload.get("elected")),
        winning_candidate=_optional_text(payload.get("winning_candidate")),
        winning_party=_optional_text(payload.get("winning_party")),
        winning_margin=_optional_int(payload.get("winning_margin")),
        total_votes=_optional_int(payload.get("total_votes")),
        valid_votes=_optional_int(payload.get("valid_votes")),
    )


def _optional_text(value: object) -> str | None:
    """Return a clean text value while preserving unavailable values as null."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    """Keep integer values null when an audited source did not publish them."""

    if value is None:
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    """Keep decimal values null when an audited source did not publish them."""

    if value is None:
        return None
    return float(value)


def load_audited_elections(
    inputs: Mapping[str, Mapping[str, Path | None]] = AUDITED_ELECTION_INPUTS,
) -> tuple[AuditedElectionInput, ...]:
    """Load only the completed audited 2013, 2017 and 2021 source outputs.

    This function deliberately has no network access and never calls discovery
    or extraction. It makes the master workbook reproducible from the audited
    local inputs named in ``AUDITED_ELECTION_INPUTS``.
    """

    configurations = {item.election_id: item for item in load_election_config()}
    loaded = []
    for election_id, paths in inputs.items():
        configuration = configurations[election_id]
        audit_path = Path(paths["audit_path"])
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        records = tuple(
            _record_from_audit(item) for item in audit["extraction"]["records"]
        )
        secondary_path = paths.get("secondary_seats_audit")
        metadata: tuple[ElectionStructureMetadata, ...] = ()
        if secondary_path is not None:
            authority = _consensus(record.authority for record in records)
            metadata = load_secondary_seats_audit(
                Path(secondary_path),
                election_year=configuration.election_year,
                election_name=configuration.election_name,
                authority=authority if isinstance(authority, str) else None,
            )
        loaded.append(
            AuditedElectionInput(
                configuration=configuration,
                audit_path=audit_path,
                records=records,
                election_structure_metadata=metadata,
            )
        )
    return tuple(loaded)


def _present(value: object | None) -> bool:
    """Treat null and blank values as missing without converting them."""

    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _consensus(values: Iterable[object | None]) -> object | None:
    """Return a shared value, or null when source records disagree or omit it."""

    distinct: list[object] = []
    for value in values:
        if _present(value) and value not in distinct:
            distinct.append(value)
    return distinct[0] if len(distinct) == 1 else None


def _division_id(election_id: str, source_url: str) -> str:
    """Create a stable derived identifier from the official result-page ID."""

    result_id = parse_qs(urlsplit(source_url).query).get("ID", [None])[0]
    if not result_id:
        raise ValueError(f"Official result URL has no ID parameter: {source_url}")
    return f"{election_id}:result:{result_id}"


def _elected_yes_no(outcome: str | None) -> str | None:
    """Translate only explicit published outcomes; unknown values remain null."""

    if outcome == "Elected":
        return "Yes"
    if outcome == "Not elected":
        return "No"
    return None


def _candidate_ids(records: Sequence[CandidateResultRecord]) -> dict[str, str]:
    """Assign IDs to exact published names without asserting real-world identity."""

    names = sorted({record.candidate_name for record in records}, key=lambda name: (name.casefold(), name))
    return {name: f"candidate-{index:04d}" for index, name in enumerate(names, start=1)}


def _source_type(value: object) -> str:
    """Normalise enum-like audited source values to readable workbook text."""

    return str(getattr(value, "value", value))


def _division_assessments(
    report: LayeredCompletenessReport,
) -> dict[str, object]:
    """Index read-only division assessments by their official result URL."""

    return {division.source_url: division for division in report.divisions}


def _secondary_metadata_by_division(
    metadata: Sequence[ElectionStructureMetadata],
) -> dict[str, ElectionStructureMetadata]:
    """Match supplementary evidence only by the audited published division name."""

    return {item.division_or_ward_name.casefold(): item for item in metadata}


def build_master_database(
    elections: Sequence[AuditedElectionInput],
) -> MasterDatabasePayload:
    """Build all required tables from audited values and separate provenance layers."""

    candidate_ids = _candidate_ids(
        tuple(record for election in elections for record in election.records)
    )
    election_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    division_rows: list[dict[str, object]] = []
    party_years: defaultdict[str, set[int]] = defaultdict(set)
    layered_reports: dict[str, LayeredCompletenessReport] = {}

    for election in elections:
        configuration = election.configuration
        # Layered completeness is read-only: it selects metadata sources for
        # assessment but never writes configuration or supplementary values
        # back into official candidate records.
        layered = assess_layered_completeness(
            configuration,
            election.records,
            election_structure_metadata=election.election_structure_metadata,
        )
        layered_reports[configuration.election_id] = layered
        election_date = _consensus(record.election_date for record in election.records)
        authority = _consensus(record.authority for record in election.records)
        election_rows.append(
            {
                "election_id": configuration.election_id,
                "election_name": configuration.election_name,
                "election_date": election_date,
                "election_year": configuration.election_year,
                "election_type": configuration.election_type,
                "authority": authority,
                "source_type": "configuration; official",
                "source_reference": (
                    f"config/elections.json#{configuration.election_id}; "
                    f"{election.audit_path.relative_to(PROJECT_ROOT)}"
                ),
            }
        )

        division_assessments = _division_assessments(layered)
        secondary_by_name = _secondary_metadata_by_division(
            election.election_structure_metadata
        )
        records_by_url: defaultdict[str, list[CandidateResultRecord]] = defaultdict(list)
        for record, assessment in zip(election.records, layered.candidates, strict=True):
            division_id = _division_id(configuration.election_id, record.source_url)
            candidate_rows.append(
                {
                    "election_id": configuration.election_id,
                    "election_year": configuration.election_year,
                    "division_id": division_id,
                    "division_name": record.division_ward_name,
                    "candidate_id": candidate_ids[record.candidate_name],
                    "candidate_name": record.candidate_name,
                    "original_party_name": record.original_party_name,
                    "votes": record.votes_received,
                    "vote_share": record.vote_share,
                    "outcome": record.outcome,
                    # This is a transparent recoding of an explicit official
                    # Outcome, not a rank or a prediction from vote totals.
                    "elected_yes_no": _elected_yes_no(record.outcome),
                    "final_position": record.final_position,
                    "source_url": record.source_url,
                    "source_type": _source_type(record.source_type),
                    "election_completeness_status": layered.election.status.value,
                    "division_completeness_status": division_assessments[
                        record.source_url
                    ].status.value,
                    "candidate_completeness_status": assessment.status.value,
                }
            )
            records_by_url[record.source_url].append(record)
            if record.original_party_name:
                party_years[record.original_party_name].add(configuration.election_year)

        for source_url, division_records in sorted(records_by_url.items()):
            representative = division_records[0]
            division_name = representative.division_ward_name
            if division_name is None:
                raise ValueError(f"No published division name for {source_url}")
            assessment = division_assessments[source_url]
            secondary = secondary_by_name.get(division_name.casefold())
            division_rows.append(
                {
                    "election_id": configuration.election_id,
                    "division_id": _division_id(configuration.election_id, source_url),
                    "division_name": division_name,
                    "official_number_of_seats": _consensus(
                        record.number_of_seats for record in division_records
                    ),
                    "secondary_number_of_seats": (
                        secondary.secondary_number_of_seats if secondary else None
                    ),
                    "electorate": _consensus(record.electorate for record in division_records),
                    "ballot_papers_issued": _consensus(
                        record.ballot_papers_issued for record in division_records
                    ),
                    "rejected_ballots": _consensus(
                        record.ballot_papers_rejected for record in division_records
                    ),
                    "turnout": _consensus(record.turnout for record in division_records),
                    "total_votes": _consensus(record.total_votes for record in division_records),
                    "official_source_url": source_url,
                    "official_source_type": _source_type(representative.source_type),
                    "secondary_seats_source": secondary.seat_source_type if secondary else None,
                    "secondary_seats_source_url": secondary.seat_source_url if secondary else None,
                    "secondary_seats_evidence": secondary.seat_evidence_text if secondary else None,
                    "secondary_seats_confidence": secondary.confidence if secondary else None,
                    "division_completeness_status": assessment.status.value,
                }
            )

    candidate_rows.sort(
        key=lambda row: (
            str(row["election_id"]),
            str(row["division_name"]),
            str(row["candidate_name"]),
        )
    )
    division_rows.sort(key=lambda row: (str(row["election_id"]), str(row["division_name"])))
    candidates = tuple(
        {
            "candidate_id": candidate_ids[name],
            "candidate_name": name,
        }
        for name in sorted(candidate_ids, key=lambda value: (value.casefold(), value))
    )
    parties = tuple(
        {
            "original_party_name": party_name,
            # No party-name mapping is available yet, so this exact copy avoids
            # unsupported merging while leaving a standardisation field ready.
            "standard_party_name": party_name,
            "party_category": None,
        }
        for party_name in sorted(party_years, key=lambda value: (value.casefold(), value))
    )
    loaded_years = ", ".join(
        str(election.configuration.election_year) for election in elections
    )
    party_history = tuple(
        {
            "party_name": party_name,
            "first_observed_year": min(years),
            "party_status": "observed",
            "notes": (
                "First observed in the loaded audited dataset only; this is not "
                "a claim about the party's historical origin or entry."
            ),
            "source": f"Derived from audited Candidate Results for {loaded_years}.",
        }
        for party_name, years in sorted(
            party_years.items(), key=lambda item: (item[0].casefold(), item[0])
        )
    )
    summary = _audit_summary(
        elections=elections,
        candidate_rows=candidate_rows,
        division_rows=division_rows,
        layered_reports=layered_reports,
    )
    return MasterDatabasePayload(
        elections=tuple(election_rows),
        candidate_results=tuple(candidate_rows),
        divisions_and_wards=tuple(division_rows),
        candidates=candidates,
        political_parties=parties,
        party_history_and_new_entrants=party_history,
        data_dictionary=tuple(_data_dictionary_rows()),
        audit_summary=summary,
    )


def _audit_summary(
    *,
    elections: Sequence[AuditedElectionInput],
    candidate_rows: Sequence[Mapping[str, object]],
    division_rows: Sequence[Mapping[str, object]],
    layered_reports: Mapping[str, LayeredCompletenessReport],
) -> dict[str, object]:
    """Summarise coverage and missingness without presenting it as a repair."""

    per_election = []
    for election in elections:
        report = layered_reports[election.configuration.election_id]
        per_election.append(
            {
                "election_id": election.configuration.election_id,
                "candidate_rows": len(election.records),
                "division_rows": len(report.divisions),
                "election_completeness": report.election.status.value,
                "candidate_complete": sum(
                    candidate.status is CompletenessStatus.COMPLETE
                    for candidate in report.candidates
                ),
                "division_incomplete": sum(
                    division.status is CompletenessStatus.INCOMPLETE
                    for division in report.divisions
                ),
            }
        )
    missing_division_values = {
        field_name: sum(row.get(field_name) is None for row in division_rows)
        for field_name in (
            "official_number_of_seats",
            "electorate",
            "ballot_papers_issued",
            "rejected_ballots",
            "turnout",
        )
    }
    return {
        "elections_loaded": len(elections),
        "candidate_rows": len(candidate_rows),
        "division_rows": len(division_rows),
        "candidate_rows_with_null_final_position": sum(
            row["final_position"] is None for row in candidate_rows
        ),
        "divisions_with_secondary_seats": sum(
            row["secondary_number_of_seats"] is not None for row in division_rows
        ),
        "official_division_field_missing_counts": missing_division_values,
        "per_election": per_election,
        "data_integrity_note": (
            "Null values preserve unavailable official information. Supplementary "
            "Seats evidence is stored separately and does not replace official Seats."
        ),
    }


def _data_dictionary_rows() -> list[dict[str, object]]:
    """Document every exported field and its explicit missing-value policy."""

    definitions = {
        "Elections": [
            ("election_id", "Stable configured election identifier.", "configuration", "configuration", "Never blank for configured elections."),
            ("election_name", "Configured election title.", "configuration", "configuration", "Never blank for configured elections."),
            ("election_date", "Consensus published polling date in audited records.", "official result pages", "official", "NULL if the audited official pages disagree or omit it."),
            ("election_year", "Configured calendar year.", "configuration", "configuration", "Never blank for configured elections."),
            ("election_type", "Configured election type.", "configuration", "configuration", "Never blank for configured elections."),
            ("authority", "Consensus published authority in audited records.", "official result pages", "official", "NULL if unavailable or conflicting."),
            ("source_type", "Source layers used by the election row.", "configuration and official", "derived", "Never used to replace field-level values."),
            ("source_reference", "Configuration key and audited input location.", "configuration and audit", "derived", "Never blank for loaded elections."),
        ],
        "Candidate Results": [
            ("election_id", "Configured election identifier.", "configuration", "configuration", "Never blank."),
            ("election_year", "Configured calendar year.", "configuration", "configuration", "Never blank."),
            ("division_id", "Derived stable identifier from the official result-page ID.", "official URL", "derived", "Never blank for verified official URLs."),
            ("division_name", "Published division or ward name.", "official result page", "official", "NULL only if not published."),
            ("candidate_id", "Identifier for an exact published name; not identity matching.", "candidate name", "derived", "Never blank for a candidate row."),
            ("candidate_name", "Published candidate name.", "official result page", "official", "Never blank for extracted candidate rows."),
            ("original_party_name", "Published party wording without normalisation.", "official result page", "official", "NULL if not published."),
            ("votes", "Published votes received.", "official result page", "official", "NULL if not published."),
            ("vote_share", "Published candidate vote share percentage.", "official result page", "official", "NULL if not published."),
            ("outcome", "Published candidate outcome text.", "official result page", "official", "NULL if not published."),
            ("elected_yes_no", "Yes/No recoding of explicit published Outcome only.", "official outcome", "derived", "NULL unless Outcome is exactly Elected or Not elected."),
            ("final_position", "Official candidate rank or placing if published.", "official result page", "official", "NULL when not published; never calculated from votes."),
            ("source_url", "Official result page for the candidate row.", "official result page", "official", "Never blank for extracted records."),
            ("source_type", "Evidence tier recorded by extraction.", "extraction audit", "official", "Preserved from the audited record."),
            ("election_completeness_status", "Read-only election-level completeness result.", "layered completeness", "derived", "Does not alter source fields."),
            ("division_completeness_status", "Read-only division-level completeness result.", "layered completeness", "derived", "Does not alter source fields."),
            ("candidate_completeness_status", "Read-only candidate-level completeness result.", "layered completeness", "derived", "Does not alter source fields."),
        ],
        "Divisions and Wards": [
            ("election_id", "Configured election identifier.", "configuration", "configuration", "Never blank."),
            ("division_id", "Derived stable identifier from the official result-page ID.", "official URL", "derived", "Never blank for verified official URLs."),
            ("division_name", "Published division or ward name.", "official result page", "official", "NULL only if not published."),
            ("official_number_of_seats", "Seats explicitly published on the official result page.", "official result page", "official", "NULL when not published; never inferred."),
            ("secondary_number_of_seats", "Seats confirmed by separate supplementary evidence.", "supplementary metadata", "supplementary", "NULL unless documented secondary evidence exists; never overwrites official Seats."),
            ("electorate", "Published electorate.", "official result page", "official", "NULL if not published."),
            ("ballot_papers_issued", "Published issued ballot-paper count.", "official result page", "official", "NULL if not published."),
            ("rejected_ballots", "Published rejected ballot-paper count.", "official result page", "official", "NULL if not published."),
            ("turnout", "Published turnout percentage.", "official result page", "official", "NULL if not published."),
            ("total_votes", "Published total votes.", "official result page", "official", "NULL if not published."),
            ("official_source_url", "Official page supplying division data.", "official result page", "official", "Never blank for included divisions."),
            ("official_source_type", "Evidence tier of the official division record.", "extraction audit", "official", "Preserved from audited records."),
            ("secondary_seats_source", "Type of source supporting secondary Seats.", "supplementary metadata", "supplementary", "NULL without secondary Seats evidence."),
            ("secondary_seats_source_url", "URL for supplementary Seats source.", "supplementary metadata", "supplementary", "NULL without secondary Seats evidence."),
            ("secondary_seats_evidence", "Supporting text for supplementary Seats.", "supplementary metadata", "supplementary", "NULL without secondary Seats evidence."),
            ("secondary_seats_confidence", "Recorded confidence of supplementary Seats evidence.", "supplementary metadata", "supplementary", "NULL without secondary Seats evidence."),
            ("division_completeness_status", "Read-only division-level completeness result.", "layered completeness", "derived", "Does not fill official missing values."),
        ],
        "Candidates": [
            ("candidate_id", "Identifier for an exact published name; not identity matching.", "candidate name", "derived", "Never blank."),
            ("candidate_name", "Exact published candidate name.", "official result pages", "official", "Never blank."),
        ],
        "Political Parties": [
            ("original_party_name", "Exact published party wording.", "official result pages", "official", "Never blank for observed parties."),
            ("standard_party_name", "Current no-op standardisation retaining the exact published wording.", "original party name", "derived", "Never merges parties automatically."),
            ("party_category", "Reserved for a separately evidenced classification.", "future enrichment", "derived", "NULL until a documented classification is added."),
        ],
        "Party History and New Entrants": [
            ("party_name", "Observed published party name.", "Candidate Results", "derived", "Never blank for observed parties."),
            ("first_observed_year", "First year present in the loaded audited dataset only.", "Candidate Results", "derived", "NULL only if no loaded observation exists."),
            ("party_status", "Current dataset status only.", "Candidate Results", "derived", "Does not assert historical party origin."),
            ("notes", "Scope limitation for party-history enrichment.", "project documentation", "derived", "Never used as electoral evidence."),
            ("source", "Dataset source used for this observation.", "Candidate Results", "derived", "Never blank for observed parties."),
        ],
    }
    rows = []
    for table, fields in definitions.items():
        for field_name, definition, source_type, classification, missing_policy in fields:
            rows.append(
                {
                    "field_name": field_name,
                    "table": table,
                    "definition": definition,
                    "source_type": source_type,
                    "classification": classification,
                    "missing_value_policy": missing_policy,
                }
            )
    return rows


def payload_as_dict(payload: MasterDatabasePayload) -> dict[str, object]:
    """Convert immutable table collections into JSON-ready structures."""

    return {
        "Elections": list(payload.elections),
        "Candidate Results": list(payload.candidate_results),
        "Divisions and Wards": list(payload.divisions_and_wards),
        "Candidates": list(payload.candidates),
        "Political Parties": list(payload.political_parties),
        "Party History and New Entrants": list(payload.party_history_and_new_entrants),
        "Data Dictionary": list(payload.data_dictionary),
        "audit_summary": payload.audit_summary,
    }


def audit_summary_markdown(payload: MasterDatabasePayload) -> str:
    """Render a compact, human-readable audit summary from the master payload."""

    summary = payload.audit_summary
    lines = [
        "# Surrey Master Election Database Audit Summary",
        "",
        f"- Elections loaded: {summary['elections_loaded']}",
        f"- Candidate-result rows: {summary['candidate_rows']}",
        f"- Division rows: {summary['division_rows']}",
        f"- Candidate rows with NULL final_position: {summary['candidate_rows_with_null_final_position']}",
        f"- Divisions with supplementary Seats evidence: {summary['divisions_with_secondary_seats']}",
        f"- Official division-field missing counts: {summary['official_division_field_missing_counts']}",
        "",
        "## Election coverage",
        "",
    ]
    for election in summary["per_election"]:
        assert isinstance(election, Mapping)
        lines.append(
            "- {election_id}: {candidate_rows} candidates; {division_rows} divisions; "
            "election completeness={election_completeness}; division incomplete="
            "{division_incomplete}.".format(**election)
        )
    lines.extend(["", "## Data integrity", "", str(summary["data_integrity_note"]), ""])
    return "\n".join(lines)


def schema_documentation_markdown(payload: MasterDatabasePayload) -> str:
    """Provide schema documentation outside Excel for repository readers."""

    grouped: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in payload.data_dictionary:
        grouped[str(row["table"])].append(row)
    lines = ["# Surrey Master Election Database Schema", ""]
    for table, rows in grouped.items():
        lines.extend([f"## {table}", "", "| Field | Definition | Source | Classification | Missing-value policy |", "| --- | --- | --- | --- | --- |"])
        for row in rows:
            lines.append(
                "| {field_name} | {definition} | {source_type} | {classification} | {missing_value_policy} |".format(
                    **row
                )
            )
        lines.append("")
    return "\n".join(lines)
