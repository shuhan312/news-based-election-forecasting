"""Assemble a source-preserving multi-election analytical database payload."""

from __future__ import annotations

import json
from hashlib import sha256
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
from election_extractor.by_election_results import (
    DEFAULT_RESULTS_PATH as BY_ELECTION_RESULTS_PATH,
    by_election_records_by_id,
    load_by_election_catalogue,
)
from election_extractor.division_supplementary_audit import (
    audit_2013_division_evidence,
)
from election_extractor.derived_metadata import (
    load_derived_metadata,
    records_as_rows as derived_records_as_rows,
    validate_derived_metadata,
)
from election_extractor.election_config import ElectionConfiguration, load_election_config
from election_extractor.election_structure_metadata import load_secondary_seats_audit
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.models import (
    DerivedMetadataRecord,
    ElectionStructureMetadata,
    SupplementaryMetadataRecord,
)
from election_extractor.party_lookup import PartyLookupEntry, load_party_lookup
from election_extractor.supplementary_metadata import (
    load_supplementary_metadata,
    records_as_rows,
    structure_metadata_as_records,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENTARY_METADATA_PATH = PROJECT_ROOT / "config/supplementary_metadata.json"
DERIVED_METADATA_PATH = PROJECT_ROOT / "config/derived_metadata.json"
# This is the date on which the existing statutory Seats audit was reviewed
# into the generic metadata layer. It does not claim a date for the statute.
SECONDARY_SEATS_AUDIT_RETRIEVAL_DATE = "2026-07-15"
AUDITED_ELECTION_INPUTS = {
    "surrey-county-council-2013": {
        "audit_path": PROJECT_ROOT / "outputs/2013_full_extraction/2013_extraction_audit.json",
        "secondary_seats_audit": None,
        # This small reviewed register contains only named Council turnout
        # statements. It is additive evidence, not input to official extraction
        # or layered completeness.
        "division_turnout_evidence": PROJECT_ROOT
        / "config/2013_division_turnout_evidence.json",
    },
    "surrey-county-council-2017": {
        "audit_path": PROJECT_ROOT / "outputs/2017_full_extraction/2017_extraction_audit.json",
        "secondary_seats_audit": None,
        "division_turnout_evidence": None,
    },
    "surrey-county-council-2021": {
        "audit_path": PROJECT_ROOT
        / "outputs/2021_archive_discovery_pilot/2021_archive_discovery_pilot_audit.json",
        "secondary_seats_audit": PROJECT_ROOT
        / "outputs/2021_secondary_seats_audit/2021_secondary_seats_audit.json",
        "division_turnout_evidence": None,
    },
    # East and West are separate configured 2026 election inputs.  They share
    # an election year and title, but their map-index sources and new ward IDs
    # must remain distinct until a separate evidence-based boundary mapping is
    # approved.
    "surrey-county-council-2026-east-surrey": {
        "audit_path": PROJECT_ROOT
        / "outputs/2026_east_full_extraction/2026_extraction_audit.json",
        "secondary_seats_audit": None,
        "division_turnout_evidence": None,
    },
    "surrey-county-council-2026-west-surrey": {
        "audit_path": PROJECT_ROOT
        / "outputs/2026_west_full_extraction/2026_extraction_audit.json",
        "secondary_seats_audit": None,
        "division_turnout_evidence": None,
    },
}


@dataclass(frozen=True)
class AuditedElectionInput:
    """Keep one completed audit and separate supplementary evidence records."""

    configuration: ElectionConfiguration
    audit_path: Path
    records: tuple[CandidateResultRecord, ...]
    election_structure_metadata: tuple[ElectionStructureMetadata, ...]
    supplementary_metadata: tuple[SupplementaryMetadataRecord, ...] = ()
    # Calculated records are distinct from both official values and external
    # supplementary evidence. They never enter extraction or completeness.
    derived_metadata: tuple[DerivedMetadataRecord, ...] = ()
    # Archive-catalogue values describe an event even where no official result
    # page has been verified. They remain distinct from candidate-page fields.
    event_date: str | None = None
    event_authority: str | None = None
    event_source_url: str | None = None


@dataclass(frozen=True)
class MasterDatabasePayload:
    """Contain tables and documentation without changing any source record."""

    elections: tuple[dict[str, object], ...]
    candidate_results: tuple[dict[str, object], ...]
    divisions_and_wards: tuple[dict[str, object], ...]
    candidates: tuple[dict[str, object], ...]
    political_parties: tuple[dict[str, object], ...]
    party_history_and_new_entrants: tuple[dict[str, object], ...]
    party_standardisation_issues: tuple[dict[str, object], ...]
    geographic_mapping: tuple[dict[str, object], ...]
    supplementary_metadata: tuple[dict[str, object], ...]
    derived_metadata: tuple[dict[str, object], ...]
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
    """Load audited principal elections and catalogued by-election events.

    This function deliberately has no network access and never calls discovery
    or extraction. It makes the master workbook reproducible from the audited
    local inputs named in ``AUDITED_ELECTION_INPUTS``.
    """

    configurations = {item.election_id: item for item in load_election_config()}
    # By-elections are archive-catalogued events rather than entries in
    # ``elections.json``.  Their identifiers are nevertheless valid targets
    # for supplementary evidence, provided that the evidence remains in the
    # separate metadata table and is tied to the event's official result URL.
    by_election_catalogue = load_by_election_catalogue()
    permitted_metadata_election_ids = set(configurations) | {
        event.election_id for event in by_election_catalogue
    }
    registered_metadata: defaultdict[str, list[SupplementaryMetadataRecord]] = defaultdict(list)
    for item in load_supplementary_metadata(
        SUPPLEMENTARY_METADATA_PATH,
        permitted_election_ids=permitted_metadata_election_ids,
    ):
        registered_metadata[item.election_id].append(item)
    registered_derived: defaultdict[str, list[DerivedMetadataRecord]] = defaultdict(list)
    for item in load_derived_metadata(
        DERIVED_METADATA_PATH,
        permitted_election_ids=permitted_metadata_election_ids,
    ):
        registered_derived[item.election_id].append(item)
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
        # A generic metadata record receives an official division ID only when
        # the audited official result URL identifies that same published name.
        # The conversion is additive: the specialised Seats fields remain as
        # they were and no generic record is passed into completeness logic.
        division_ids_by_name = {
            record.division_ward_name.casefold(): _division_id(
                configuration.election_id, record.source_url
            )
            for record in records
            if record.division_ward_name is not None
        }
        supplementary_metadata = list(registered_metadata[configuration.election_id])
        supplementary_metadata.extend(
            structure_metadata_as_records(
                election_id=configuration.election_id,
                metadata=metadata,
                division_ids_by_name=division_ids_by_name,
                retrieval_date=SECONDARY_SEATS_AUDIT_RETRIEVAL_DATE,
            )
        )
        division_turnout_evidence = paths.get("division_turnout_evidence")
        if division_turnout_evidence is not None:
            # The audit requires exact official division-name matching. Its
            # records stay in Supplementary Metadata and are never supplied to
            # ``assess_layered_completeness`` below.
            supplementary_metadata.extend(
                audit_2013_division_evidence(
                    records,
                    Path(division_turnout_evidence),
                ).supplementary_records
            )
        loaded.append(
            AuditedElectionInput(
                configuration=configuration,
                audit_path=audit_path,
                records=records,
                election_structure_metadata=metadata,
                supplementary_metadata=tuple(supplementary_metadata),
                derived_metadata=tuple(registered_derived[configuration.election_id]),
            )
        )
    # Candidate rows for by-elections are available only where the existing
    # archive catalogue has separately verified official candidate-result evidence.
    # Every catalogued event is still included in Elections, so absence of a
    # result source is visible rather than becoming an invented zero-row result.
    records_by_event = by_election_records_by_id()
    for event in by_election_catalogue:
        event_records = records_by_event.get(event.election_id, ())
        source_url = event_records[0].source_url if event_records else event.archive_source_url
        event_metadata = tuple(registered_metadata[event.election_id])
        division_metadata = tuple(
            item for item in event_metadata if item.division_id is not None
        )
        if division_metadata and not event_records:
            # A division-level claim needs a verified official result source
            # from which its deterministic division ID can be checked. Without
            # that anchor, even a plausible-looking event ID could attach
            # external evidence to the wrong place, so reject the claim rather
            # than exporting unverified metadata.
            raise ValueError(
                "By-election division-level supplementary metadata requires "
                f"verified official result evidence for {event.election_id}."
            )
        if event_records:
            # A division-level external claim is acceptable only when its
            # identifier is the same deterministic identifier used for the
            # verified official result source.  This prevents a nearby ward,
            # borough contest or similarly named event from being attached to
            # the County Council by-election by mistake.
            official_division_id = _division_id(event.election_id, source_url)
            for item in division_metadata:
                if item.division_id != official_division_id:
                    raise ValueError(
                        "By-election supplementary metadata does not match the "
                        f"official result division ID for {event.election_id}."
                    )
        loaded.append(
            AuditedElectionInput(
                configuration=ElectionConfiguration(
                    election_id=event.election_id,
                    election_name=event.election_name,
                    election_year=int(event.election_date[:4]),
                    election_type=event.election_type,
                    official_url=source_url,
                    official_url_field="official_url",
                ),
                audit_path=BY_ELECTION_RESULTS_PATH,
                records=event_records,
                election_structure_metadata=(),
                supplementary_metadata=event_metadata,
                derived_metadata=tuple(registered_derived[event.election_id]),
                event_date=event.election_date,
                event_authority=event.authority,
                event_source_url=source_url,
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
    """Create a stable identifier from an official result ID or source URL.

    Surrey result pages normally expose an ``ID`` query parameter. An official
    declaration PDF may not, so it receives a deterministic URL digest instead.
    The digest identifies the source document only; it does not assert a new
    division, a geographic relationship, or any candidate identity.
    """

    result_id = parse_qs(urlsplit(source_url).query).get("ID", [None])[0]
    if result_id:
        return f"{election_id}:result:{result_id}"
    source_digest = sha256(source_url.encode("utf-8")).hexdigest()[:12]
    return f"{election_id}:official-document:{source_digest}"


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


def _validate_election_derived_metadata(election: AuditedElectionInput) -> None:
    """Check derived records against one election's untouched official values.

    Candidate records repeat their division summary fields.  Consensus first
    confirms that the official page supplied one unambiguous value before that
    value is allowed to be used as a derivation input.
    """

    official_values_by_division: dict[str, dict[str, object]] = {}
    official_source_urls_by_division: dict[str, str] = {}
    records_by_source: defaultdict[str, list[CandidateResultRecord]] = defaultdict(list)
    for record in election.records:
        records_by_source[record.source_url].append(record)

    for source_url, division_records in records_by_source.items():
        division_id = _division_id(election.configuration.election_id, source_url)
        official_source_urls_by_division[division_id] = source_url
        official_values_by_division[division_id] = {
            "ballot_papers_issued": _consensus(
                record.ballot_papers_issued for record in division_records
            ),
            "total_votes": _consensus(
                record.total_votes for record in division_records
            ),
            "rejected_ballots": _consensus(
                record.ballot_papers_rejected for record in division_records
            ),
        }

    validate_derived_metadata(
        election.derived_metadata,
        official_values_by_division=official_values_by_division,
        official_source_urls_by_division=official_source_urls_by_division,
    )


def _party_lookup_fields(
    original_party_name: str | None,
    party_lookup: Mapping[str, PartyLookupEntry],
) -> dict[str, object]:
    """Return reviewed party fields without changing the published party label.

    A missing or unlisted source label stays unstandardised.  This makes any
    later review visible in the workbook rather than applying a name-based
    guess to Residents groups, Independent candidates, or new parties.
    """

    if original_party_name is None:
        return {
            "standard_party_name": None,
            "party_category": None,
            "party_lookup_status": "missing_published_party_name",
            "party_lookup_notes": "Official candidate result did not publish a party name.",
        }
    entry = party_lookup.get(original_party_name)
    if entry is None:
        return {
            "standard_party_name": None,
            "party_category": None,
            "party_lookup_status": "unmapped",
            "party_lookup_notes": "No reviewed exact-label lookup entry exists; no mapping was applied.",
        }
    return {
        "standard_party_name": entry.standard_party_name,
        "party_category": entry.party_category,
        "party_lookup_status": "reviewed_exact_label",
        "party_lookup_notes": entry.notes,
    }


def build_master_database(
    elections: Sequence[AuditedElectionInput],
    party_lookup: Mapping[str, PartyLookupEntry] | None = None,
) -> MasterDatabasePayload:
    """Build all required tables from audited values and separate provenance layers.

    ``party_lookup`` is optional so tests can inject a small reviewed register.
    Normal production runs load the committed exact-label configuration.  It
    controls only added lookup fields, never the original published party name.

    The final Geographic Mapping table deliberately remains empty here.  GIS
    overlap candidates are exported to a separate review dataset and cannot
    enter this database until a future, evidence-backed approval process is
    explicitly implemented.
    """

    if party_lookup is None:
        party_lookup = load_party_lookup()
    candidate_ids = _candidate_ids(
        tuple(record for election in elections for record in election.records)
    )
    election_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    division_rows: list[dict[str, object]] = []
    supplementary_rows: list[dict[str, object]] = []
    derived_rows: list[dict[str, object]] = []
    party_years: defaultdict[str, set[int]] = defaultdict(set)
    layered_reports: dict[str, LayeredCompletenessReport] = {}

    for election in elections:
        configuration = election.configuration
        # Supplementary evidence is exported as its own table. It is never an
        # input to candidate or division completeness assessment below.
        supplementary_rows.extend(records_as_rows(election.supplementary_metadata))
        # A derived record must be reproducible from the same immutable official
        # result page. Validation occurs before exporting any calculated value,
        # and does not write into the candidate or division record collections.
        _validate_election_derived_metadata(election)
        derived_rows.extend(derived_records_as_rows(election.derived_metadata))
        # Layered completeness is read-only: it selects metadata sources for
        # assessment but never writes configuration or supplementary values
        # back into official candidate records.
        layered = assess_layered_completeness(
            configuration,
            election.records,
            election_structure_metadata=election.election_structure_metadata,
        )
        layered_reports[configuration.election_id] = layered
        # Fall back only to the existing official archive catalogue for an
        # event-level date and authority. This does not populate individual
        # candidate records and does not substitute a Voting Summary value.
        election_date = _consensus(record.election_date for record in election.records)
        if election_date is None:
            election_date = election.event_date
        authority = _consensus(record.authority for record in election.records)
        if authority is None:
            authority = election.event_authority
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
                    f"{('config/by_election_event_catalogue.json' if configuration.election_type == 'by-election' else 'config/elections.json')}#{configuration.election_id}; "
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
            party_fields = _party_lookup_fields(record.original_party_name, party_lookup)
            candidate_rows.append(
                {
                    "election_id": configuration.election_id,
                    "election_year": configuration.election_year,
                    "division_id": division_id,
                    "division_name": record.division_ward_name,
                    "candidate_id": candidate_ids[record.candidate_name],
                    "candidate_name": record.candidate_name,
                    "original_party_name": record.original_party_name,
                    **party_fields,
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

        # Candidate-level supplementary evidence is allowed only when it names
        # an exact row from the same official result source. This guards against
        # accidental identity matching across divisions or elections while
        # keeping the evidence outside the official candidate fields.
        published_candidate_scopes = {
            (_division_id(configuration.election_id, record.source_url), record.candidate_name)
            for record in election.records
        }
        for item in election.supplementary_metadata:
            if item.geographic_level.value != "candidate":
                continue
            if (item.division_id, item.candidate_name) not in published_candidate_scopes:
                raise ValueError(
                    "Candidate-level supplementary metadata does not match an "
                    "exact published candidate row for "
                    f"{configuration.election_id}."
                )

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
            **_party_lookup_fields(party_name, party_lookup),
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
    # Only labels with no published wording or no exact reviewed entry appear
    # as issues.  A row asks for review; it is not a proposed party merger.
    party_standardisation_issues = tuple(
        {
            "issue_id": f"party-issue:{index:03d}",
            "election_id": None,
            "original_party_name": party_name,
            "issue_type": issue_type,
            "proposed_standard_party_name": None,
            "status": "requires_review",
            "evidence_source": source,
            "notes": notes,
        }
        for index, (party_name, issue_type, source, notes) in enumerate(
            _party_standardisation_issues(candidate_rows), start=1
        )
    )
    summary = _audit_summary(
        elections=elections,
        candidate_rows=candidate_rows,
        division_rows=division_rows,
        supplementary_rows=supplementary_rows,
        derived_rows=derived_rows,
        layered_reports=layered_reports,
        party_standardisation_issues=party_standardisation_issues,
    )
    return MasterDatabasePayload(
        elections=tuple(election_rows),
        candidate_results=tuple(candidate_rows),
        divisions_and_wards=tuple(division_rows),
        candidates=candidates,
        political_parties=parties,
        party_history_and_new_entrants=party_history,
        party_standardisation_issues=party_standardisation_issues,
        geographic_mapping=(),
        supplementary_metadata=tuple(
            sorted(supplementary_rows, key=lambda row: str(row["metadata_id"]))
        ),
        derived_metadata=tuple(
            sorted(derived_rows, key=lambda row: str(row["metadata_id"]))
        ),
        data_dictionary=tuple(_data_dictionary_rows()),
        audit_summary=summary,
    )


def _party_standardisation_issues(
    candidate_rows: Sequence[Mapping[str, object]],
) -> tuple[tuple[str | None, str, str, str], ...]:
    """Create review rows only for party labels that no lookup safely resolves.

    The source evidence is the already-audited candidate table.  This function
    never suggests a replacement name, because deriving aliases from similar
    wording would violate the requirement to preserve uncertainty.
    """

    evidence_by_label: defaultdict[str | None, set[str]] = defaultdict(set)
    status_by_label: dict[str | None, str] = {}
    for row in candidate_rows:
        party_name = row["original_party_name"]
        if party_name is not None and not isinstance(party_name, str):
            raise ValueError("original_party_name must be text or null.")
        status = str(row["party_lookup_status"])
        if status == "reviewed_exact_label":
            continue
        evidence_by_label[party_name].add(str(row["election_id"]))
        status_by_label[party_name] = status

    issues = []
    for party_name in sorted(
        evidence_by_label,
        key=lambda value: (value is None, "" if value is None else value.casefold()),
    ):
        status = status_by_label[party_name]
        if status == "missing_published_party_name":
            issue_type = "missing_published_party_name"
            notes = "No original party wording was published; no standard party name was created."
        else:
            issue_type = "unmapped_published_party_name"
            notes = "No exact reviewed lookup entry exists; no standard party name was created."
        elections = ", ".join(sorted(evidence_by_label[party_name]))
        issues.append(
            (
                party_name,
                issue_type,
                f"Audited Candidate Results for {elections}.",
                notes,
            )
        )
    return tuple(issues)


def _audit_summary(
    *,
    elections: Sequence[AuditedElectionInput],
    candidate_rows: Sequence[Mapping[str, object]],
    division_rows: Sequence[Mapping[str, object]],
    supplementary_rows: Sequence[Mapping[str, object]],
    derived_rows: Sequence[Mapping[str, object]],
    layered_reports: Mapping[str, LayeredCompletenessReport],
    party_standardisation_issues: Sequence[Mapping[str, object]],
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
        "supplementary_metadata_records": len(supplementary_rows),
        "supplementary_metadata_by_field": dict(
            sorted(Counter(str(row["field_name"]) for row in supplementary_rows).items())
        ),
        "derived_metadata_records": len(derived_rows),
        "derived_metadata_by_field": dict(
            sorted(Counter(str(row["field_name"]) for row in derived_rows).items())
        ),
        "geographic_mapping_rows": 0,
        "party_standardisation_issue_rows": len(party_standardisation_issues),
        "official_division_field_missing_counts": missing_division_values,
        "per_election": per_election,
        "data_integrity_note": (
            "Null values preserve unavailable official information. Supplementary "
            "evidence and documented calculations are stored separately and do not "
            "replace official fields or change layered completeness. No final boundary mappings have been "
            "approved, so no historical comparisons are calculated."
        ),
    }


def _data_dictionary_rows() -> list[dict[str, object]]:
    """Document every exported field and its explicit missing-value policy."""

    definitions = {
        "Elections": [
            ("election_id", "Stable configured election identifier.", "configuration", "configuration", "Never blank for configured elections."),
            ("election_name", "Configured election title.", "configuration", "configuration", "Never blank for configured elections."),
            ("election_date", "Published polling date from official result records or the official archive event catalogue.", "official result pages or official archive catalogue", "official", "NULL if the applicable official source is unavailable or conflicting."),
            ("election_year", "Configured calendar year.", "configuration", "configuration", "Never blank for configured elections."),
            ("election_type", "Configured election type.", "configuration", "configuration", "Never blank for configured elections."),
            ("authority", "Published authority from official result records or the official archive event catalogue.", "official result pages or official archive catalogue", "official", "NULL if the applicable official source is unavailable or conflicting."),
            ("source_type", "Source layers used by the election row.", "configuration and official", "derived", "Never used to replace field-level values."),
            ("source_reference", "Configuration key and audited input location.", "configuration and audit", "derived", "Never blank for loaded elections."),
        ],
        "Candidate Results": [
            ("election_id", "Configured election identifier.", "configuration", "configuration", "Never blank."),
            ("election_year", "Configured calendar year.", "configuration", "configuration", "Never blank."),
            ("division_id", "Derived stable identifier from an official result-page ID, or from the official source URL when no result ID is published.", "official URL", "derived", "Never blank for verified official sources; does not claim geographic identity."),
            ("division_name", "Published division or ward name.", "official result page", "official", "NULL only if not published."),
            ("candidate_id", "Identifier for an exact published name; not identity matching.", "candidate name", "derived", "Never blank for a candidate row."),
            ("candidate_name", "Published candidate name.", "official result page", "official", "Never blank for extracted candidate rows."),
            ("original_party_name", "Published party wording without normalisation.", "official result page", "official", "NULL if not published."),
            ("standard_party_name", "Reviewed standard name for an exact published party label.", "party standardisation lookup", "derived", "NULL when no approved exact-label mapping exists; never replaces original_party_name."),
            ("party_category", "Reviewed project grouping: established, emerging, local or independent.", "party standardisation lookup", "derived", "NULL when no approved exact-label mapping exists."),
            ("party_lookup_status", "Whether a reviewed exact-label party mapping was available.", "party standardisation lookup", "derived", "Never changes original_party_name or candidate completeness."),
            ("party_lookup_notes", "Non-merger and scope note for the reviewed party mapping.", "party standardisation lookup", "derived", "NULL when no lookup note is available."),
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
            ("division_id", "Derived stable identifier from an official result-page ID, or from the official source URL when no result ID is published.", "official URL", "derived", "Never blank for verified official sources; does not claim geographic identity."),
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
            ("standard_party_name", "Reviewed standard name for an exact published party label.", "party standardisation lookup", "derived", "NULL when no approved exact-label mapping exists; never merges parties automatically."),
            ("party_category", "Reviewed project grouping: established, emerging, local or independent.", "party standardisation lookup", "derived", "NULL when no approved exact-label mapping exists."),
            ("party_lookup_status", "Whether a reviewed exact-label party mapping was available.", "party standardisation lookup", "derived", "Never changes original_party_name."),
            ("party_lookup_notes", "Non-merger and scope note for the reviewed party mapping.", "party standardisation lookup", "derived", "NULL when no lookup note is available."),
        ],
        "Party Standardisation Issues": [
            ("issue_id", "Stable identifier for one reviewed party-standardisation issue.", "party standardisation review", "derived", "No rows until a documented review identifies an issue."),
            ("election_id", "Configured election identifier in which the published party wording was observed.", "configuration", "configuration", "NULL only for a future cross-election issue."),
            ("original_party_name", "Exact published party wording requiring review.", "official result page", "official", "NULL only when the official candidate record published no party wording."),
            ("issue_type", "Reason an exact-label mapping could not be applied.", "party standardisation review", "derived", "Never proposes a party merge."),
            ("proposed_standard_party_name", "Potential standardised name pending documented approval.", "party standardisation review", "derived", "NULL until a documented mapping is approved; does not alter original_party_name."),
            ("status", "Review status of the unresolved party label.", "party standardisation review", "derived", "Never changes candidate or division completeness."),
            ("evidence_source", "Audited Candidate Results in which the issue was observed.", "candidate results", "derived", "Never asserts a party relationship."),
            ("notes", "Reason no standardisation was applied.", "party standardisation review", "derived", "Never fills an unpublished party name."),
        ],
        "Geographic Mapping": [
            ("mapping_id", "Stable identifier for an approved geographic mapping decision.", "geographic mapping decision framework", "derived", "No rows until direct boundary evidence and reviewer approval exist."),
            ("previous_election_id", "Configured identifier for the earlier election geography.", "geographic mapping decision framework", "derived", "No value is inferred from an area name or overlap."),
            ("previous_area_name", "Published earlier division or ward name.", "official result page", "official", "No value is inferred from a later ward name."),
            ("previous_area_id", "Stable earlier result-page identifier.", "official URL", "derived", "No rows until an evidence-supported mapping is reviewed."),
            ("current_election_id", "Configured identifier for the later election geography.", "geographic mapping decision framework", "derived", "No value is inferred from an area name or overlap."),
            ("current_area_name", "Published later division or ward name.", "official result page", "official", "No value is inferred from an earlier division name."),
            ("current_area_id", "Stable later result-page identifier.", "official URL", "derived", "No rows until an evidence-supported mapping is reviewed."),
            ("relationship_type", "GIS-derived relationship type: exact, near_exact, split, merged or uncertain.", "geographic mapping review", "derived", "Never implies administrative identity or final comparability by itself."),
            ("administrative_identity", "Legal identity status: confirmed, not_confirmed or uncertain.", "official legal boundary evidence", "derived", "GIS cannot confirm this field."),
            ("analytical_comparability", "Decision status for historical analysis: accepted_direct, requires_review or not_comparable.", "geographic mapping decision framework", "derived", "Only accepted_direct may enter a future separately authorised enrichment stage."),
            ("confidence", "Confidence in the analytical comparability decision.", "geographic mapping decision framework", "derived", "Never substitutes for evidence or legal identity."),
            ("decision", "Explicit reviewer decision: accepted, rejected or requires_review.", "geographic mapping decision framework", "derived", "No final row is written unless decision is accepted."),
            ("overlap_area_m2", "GIS intersection area in square metres.", "official GIS", "derived", "Required for an accepted_direct mapping."),
            ("previous_area_overlap_percentage", "Percentage of the historic area represented by the intersection.", "official GIS", "derived", "Required for an accepted_direct mapping."),
            ("current_area_overlap_percentage", "Percentage of the 2026 ward represented by the intersection.", "official GIS", "derived", "Required for an accepted_direct mapping."),
            ("largest_previous_area_competitor_percentage", "Largest competing 2026 ward overlap for the historic area.", "geographic mapping decision framework", "derived", "Must remain below the configured direct-match threshold."),
            ("largest_current_area_competitor_percentage", "Largest competing historic overlap for the 2026 ward.", "geographic mapping decision framework", "derived", "Must remain below the configured direct-match threshold."),
            ("geometry_valid", "Whether both source geometries passed official GIS validation.", "official GIS", "derived", "Required true for accepted_direct."),
            ("boundary_sources_consistent", "Whether the configured official GIS sources were processed in the common review framework.", "official GIS", "derived", "Required true for accepted_direct."),
            ("GIS_source", "Official GIS source URLs supporting the pair.", "official GIS", "derived", "Required for an accepted_direct mapping."),
            ("boundary_source", "Legal boundary source retained for provenance.", "official legislation or boundary document", "derived", "Does not alone claim historical-to-2026 legal identity."),
            ("evidence_notes", "Evidence limitation or boundary-change qualification.", "geographic mapping decision framework", "derived", "Required for an accepted_direct mapping."),
            ("reviewer_reason", "Why the relationship passed or failed direct analytical criteria.", "geographic mapping decision framework", "derived", "Never uses a name match as evidence."),
            ("evidence_summary", "Recorded overlap, competitor, geometry and source-consistency evidence.", "geographic mapping decision framework", "derived", "Required for every decision row."),
        ],
        "Party History and New Entrants": [
            ("party_name", "Observed published party name.", "Candidate Results", "derived", "Never blank for observed parties."),
            ("first_observed_year", "First year present in the loaded audited dataset only.", "Candidate Results", "derived", "NULL only if no loaded observation exists."),
            ("party_status", "Current dataset status only.", "Candidate Results", "derived", "Does not assert historical party origin."),
            ("notes", "Scope limitation for party-history enrichment.", "project documentation", "derived", "Never used as electoral evidence."),
            ("source", "Dataset source used for this observation.", "Candidate Results", "derived", "Never blank for observed parties."),
        ],
        "Supplementary Metadata": [
            ("metadata_id", "Stable identifier for one reviewed external evidence record.", "supplementary metadata register", "supplementary", "Never blank; duplicate identifiers are rejected."),
            ("election_id", "Configured election identifier for the evidence claim.", "configuration", "supplementary", "Never blank for a supplementary record."),
            ("division_id", "Official derived division identifier when evidence is division- or candidate-level.", "official URL", "supplementary", "NULL for election-level metadata; required for division- and candidate-level metadata."),
            ("candidate_name", "Exact published candidate name that anchors candidate-level evidence.", "official result page", "supplementary", "NULL for election- or division-level metadata; required for candidate-level metadata and never used for cross-election identity matching."),
            ("field_name", "Name of the separate supplementary field supported by the source.", "supplementary metadata register", "supplementary", "Never blank; does not map automatically to an official field."),
            ("value", "Reviewed external value retained only in this evidence layer.", "supplementary source", "supplementary", "Never copied into official candidate or division fields."),
            ("geographic_level", "Scope of the evidence: election, division or candidate.", "supplementary metadata register", "supplementary", "Never blank; prevents election-wide values being treated as division data."),
            ("source_type", "Type of external or separate official source.", "supplementary source", "supplementary", "Never blank for a supplementary value."),
            ("source_name", "Named publication or document that supports the claim.", "supplementary source", "supplementary", "Never blank for a supplementary value."),
            ("source_url", "Direct URL for the supporting source.", "supplementary source", "supplementary", "Never blank; HTTP(S) URL required."),
            ("evidence_text", "Supporting passage or precise evidence summary.", "supplementary source", "supplementary", "Never blank for a supplementary value."),
            ("retrieval_date", "Date on which the source evidence was retrieved or reviewed.", "supplementary metadata register", "supplementary", "Never blank; ISO YYYY-MM-DD format required."),
            ("confidence", "Recorded assessment of the evidence reliability.", "supplementary metadata register", "supplementary", "Never blank for a supplementary value."),
            ("notes", "Scope restriction or handling note for the external evidence.", "supplementary metadata register", "supplementary", "NULL when no additional note is required."),
            ("validation_status", "Review decision for the evidence record.", "supplementary metadata register", "supplementary", "Never blank; does not alter official completeness."),
        ],
        "Derived Metadata": [
            ("metadata_id", "Stable identifier for one approved calculation.", "derived metadata register", "derived", "Never blank; duplicate identifiers are rejected."),
            ("election_id", "Configured election identifier for the calculation.", "configuration", "derived", "Never blank."),
            ("division_id", "Identifier of the exact official result page supplying all inputs.", "official URL", "derived", "Never blank; must match the source URL."),
            ("field_name", "Separate calculated field name.", "derived metadata register", "derived", "Never maps automatically into an official field."),
            ("value", "Calculated value after official-input validation.", "documented formula", "derived", "Never copied into the official target field."),
            ("target_official_field", "Official field intentionally left unchanged by the calculation.", "derived metadata register", "derived", "Must remain NULL for this calculation to be accepted."),
            ("formula", "Allow-listed calculation formula.", "derived metadata register", "derived", "Must reproduce value exactly from named official inputs."),
            ("official_inputs", "Published official values used by the formula.", "official result page", "derived", "Every value must match the same official source URL."),
            ("source_url", "Single official result page containing all calculation inputs.", "official result page", "official", "Never blank; must match the audited division source URL."),
            ("evidence_text", "Precise description of the published inputs and missing target field.", "derived metadata register", "derived", "Never blank."),
            ("retrieval_date", "Date the official inputs were reviewed.", "derived metadata register", "derived", "ISO YYYY-MM-DD required."),
            ("confidence", "Confidence in the calculation after source validation.", "derived metadata register", "derived", "Never blank."),
            ("notes", "Scope and non-overwrite restriction.", "derived metadata register", "derived", "NULL when no note is required."),
            ("validation_status", "Result of formula and official-source validation.", "derived metadata register", "derived", "Never changes official or completeness values."),
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
        "Party Standardisation Issues": list(payload.party_standardisation_issues),
        "Geographic Mapping": list(payload.geographic_mapping),
        "Supplementary Metadata": list(payload.supplementary_metadata),
        "Derived Metadata": list(payload.derived_metadata),
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
        f"- Supplementary metadata records: {summary['supplementary_metadata_records']}",
        f"- Supplementary metadata by field: {summary['supplementary_metadata_by_field']}",
        f"- Derived metadata records: {summary['derived_metadata_records']}",
        f"- Derived metadata by field: {summary['derived_metadata_by_field']}",
        f"- Geographic Mapping rows: {summary['geographic_mapping_rows']}",
        f"- Party Standardisation Issues rows: {summary['party_standardisation_issue_rows']}",
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
