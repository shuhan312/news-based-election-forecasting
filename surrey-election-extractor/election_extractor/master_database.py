"""Assemble a source-preserving multi-election analytical database payload."""

from __future__ import annotations

import json
import re
import unicodedata
from hashlib import sha256
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
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
from election_extractor.candidate_continuity_evidence import (
    CandidateContinuityEvidence,
    candidate_evidence_key,
)
from election_extractor.division_supplementary_audit import (
    audit_2013_division_evidence,
)
from election_extractor.derived_metadata import (
    DerivedMetadataRule,
    derive_records_from_rules,
    load_derived_metadata,
    load_derived_metadata_rules,
    records_as_rows as derived_records_as_rows,
    validate_derived_metadata,
)
from election_extractor.derived_winning_margin import (
    derive_single_member_winning_margins,
    records_as_rows as derived_winning_margin_rows,
)
from election_extractor.derived_final_position import (
    derive_final_positions,
    validate_final_positions_against_official_outcomes,
)
from election_extractor.analysis_voting_summary import build_analysis_voting_summary
from election_extractor.analysis_vote_share import build_analysis_vote_share_rows
from election_extractor.change_in_vote_share import change_in_vote_share_fields
from election_extractor.candidate_name_standardisation import (
    standardise_candidate_name,
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
# The 2021-to-2026 GIS permissions and pre-2024 statutory-continuity audit
# are deliberately distinct evidence paths. Both are allowed only after their
# own audit has created an explicit reference row; a matching name alone is
# never enough.
APPROVED_HISTORICAL_REFERENCE_STATUSES = frozenset(
    {
        "approved_for_historical_reference",
        "approved_pre_2024_legal_continuity",
        # A separately audited by-election may use the same limited history
        # only after exact statutory-division and single-member checks.
        "approved_same_statutory_division",
    }
)
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
    analysis_voting_summary: tuple[dict[str, object], ...]
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
    registered_derived_rules: defaultdict[str, list[DerivedMetadataRule]] = defaultdict(list)
    for rule in load_derived_metadata_rules(
        DERIVED_METADATA_PATH,
        permitted_election_ids=permitted_metadata_election_ids,
    ):
        registered_derived_rules[rule.election_id].append(rule)
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
        # Rules are evaluated only from this election's audited official
        # values.  They never use configuration or supplementary evidence as
        # calculation inputs, and their output remains in Derived Metadata.
        official_values, official_urls = _official_derived_context(
            configuration.election_id,
            records,
        )
        generated_derived = derive_records_from_rules(
            registered_derived_rules[configuration.election_id],
            official_values_by_division=official_values,
            official_source_urls_by_division=official_urls,
        )
        derived_metadata = (
            tuple(registered_derived[configuration.election_id]) + generated_derived
        )
        _validate_unique_derived_metadata(derived_metadata)
        loaded.append(
            AuditedElectionInput(
                configuration=configuration,
                audit_path=audit_path,
                records=records,
                election_structure_metadata=metadata,
                supplementary_metadata=tuple(supplementary_metadata),
                derived_metadata=derived_metadata,
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
        # By-election derivations use exactly the same safeguards as principal
        # elections: inputs must be published on the one official result page,
        # the target official field must remain missing, and the result stays
        # in Derived Metadata.  This is intentionally evaluated per event,
        # because an archive listing alone never supplies calculation inputs.
        official_values, official_urls = _official_derived_context(
            event.election_id,
            event_records,
        )
        generated_derived = derive_records_from_rules(
            registered_derived_rules[event.election_id],
            official_values_by_division=official_values,
            official_source_urls_by_division=official_urls,
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
                derived_metadata=(
                    tuple(registered_derived[event.election_id]) + generated_derived
                ),
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


def _candidate_standardisation_fields(published_name: str) -> dict[str, str]:
    """Return source and analytical names without linking candidate identities."""

    standardised = standardise_candidate_name(published_name)
    return {
        "candidate_name_as_published": published_name,
        "standard_candidate_name": standardised.value,
        "candidate_name_standardisation_status": standardised.status,
    }


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

    official_values_by_division, official_source_urls_by_division = _official_derived_context(
        election.configuration.election_id,
        election.records,
    )

    validate_derived_metadata(
        election.derived_metadata,
        official_values_by_division=official_values_by_division,
        official_source_urls_by_division=official_source_urls_by_division,
    )


def _validate_unique_derived_metadata(
    records: Sequence[DerivedMetadataRecord],
) -> None:
    """Reject an explicit record that collides with a rule-generated record."""

    identifiers = [record.metadata_id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Derived metadata contains duplicate metadata_id values.")


def _official_derived_context(
    election_id: str,
    records: Sequence[CandidateResultRecord],
) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """Collect one consensus Voting Summary and URL per official division page."""

    official_values_by_division: dict[str, dict[str, object]] = {}
    official_source_urls_by_division: dict[str, str] = {}
    records_by_source: defaultdict[str, list[CandidateResultRecord]] = defaultdict(list)
    for record in records:
        records_by_source[record.source_url].append(record)

    for source_url, division_records in records_by_source.items():
        division_id = _division_id(election_id, source_url)
        official_source_urls_by_division[division_id] = source_url
        official_values_by_division[division_id] = {
            "number_of_seats": _consensus(
                record.number_of_seats for record in division_records
            ),
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

    return official_values_by_division, official_source_urls_by_division


def _party_lookup_fields(
    original_party_name: str | None,
    party_lookup: Mapping[str, PartyLookupEntry],
) -> dict[str, object]:
    """Return reviewed party fields without changing the published party label.

    An unlisted published label stays unstandardised. A genuinely blank label
    receives a separate analytical name while the original field remains
    NULL. Electoral Commission nomination guidance permits a non-party
    candidate to leave the description blank, so this is an unaffiliated
    category rather than an invented published party name.
    """

    if original_party_name is None:
        return {
            "standard_party_name": "No published party label",
            "party_category": "independent",
            "party_lookup_status": "reviewed_blank_as_unaffiliated",
            "party_lookup_notes": (
                "Original official party label remains NULL. Standard analytical "
                "label follows Electoral Commission guidance that a non-party "
                "candidate may leave the ballot description blank."
            ),
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


def _joined_unique_text(values: Iterable[object]) -> str | None:
    """Preserve the source order while representing multiple official winners.

    A multi-member ward can have more than one official elected candidate.  This
    helper creates a display value only from explicit published strings; it
    never uses vote order to select, rank, or remove a candidate.
    """

    observed: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        if value not in observed:
            observed.append(value)
    return "; ".join(observed) if observed else None


def _official_outcome_summary(
    records: Sequence[CandidateResultRecord],
) -> dict[str, object]:
    """Summarise explicit official elected outcomes without constructing a rank.

    The supervisor's requested winner field is singular, but 2026 wards may
    elect multiple candidates.  Singular winner fields are therefore populated
    only where one candidate is explicitly marked Elected.  The complete list
    of source-reported elected candidates remains available in separate plural
    fields for multi-member wards.
    """

    elected_records = [
        record for record in records if _elected_yes_no(record.outcome) == "Yes"
    ]
    elected_names = _joined_unique_text(record.candidate_name for record in elected_records)
    elected_parties = _joined_unique_text(
        record.original_party_name for record in elected_records
    )
    if len(elected_records) == 1:
        return {
            "official_elected_candidate_names": elected_names,
            "official_elected_party_names": elected_parties,
            "official_elected_candidate_count": 1,
            "winning_candidate_name": elected_records[0].candidate_name,
            "winning_party_name": elected_records[0].original_party_name,
            "outcome_summary_status": "single_official_elected_candidate",
        }
    if elected_records:
        return {
            "official_elected_candidate_names": elected_names,
            "official_elected_party_names": elected_parties,
            "official_elected_candidate_count": len(elected_records),
            "winning_candidate_name": None,
            "winning_party_name": None,
            "outcome_summary_status": "multiple_official_elected_candidates",
        }
    return {
        "official_elected_candidate_names": None,
        "official_elected_party_names": None,
        "official_elected_candidate_count": 0,
        "winning_candidate_name": None,
        "winning_party_name": None,
        "outcome_summary_status": "no_explicit_official_elected_candidate",
    }


def _source_notes(record: CandidateResultRecord) -> str | None:
    """Expose audited source-page gaps as Notes without changing source values."""

    if not record.missing_fields:
        return None
    return "Recorded missing fields: " + ", ".join(record.missing_fields)


def _unavailable_historical_reference() -> dict[str, object]:
    """Return the explicit NULL state for a relationship without permission."""

    return {
        "historical_reference_status": "not_approved_or_not_applicable",
        "previous_election_id": None,
        "previous_election_date": None,
        "previous_division_name": None,
        "previous_winning_candidate_name": None,
        "previous_winning_party": None,
        # Candidate vote share is intentionally distinct from a party total.
        # The project does not reconstruct a party total from candidate rows.
        "previous_winning_candidate_vote_share": None,
        "previous_party_vote_share": None,
        "previous_party_vote_share_status": "not_materialised_without_published_party_total",
        "previous_turnout": None,
        "previous_electorate": None,
        "historical_source_url": None,
        "historical_mapping_id": None,
        "historical_reference_notes": None,
    }


def _historical_reference_fields(
    election_id: str,
    division_name: str | None,
    references: Mapping[tuple[str, str], Mapping[str, object]],
) -> dict[str, object]:
    """Expose only an explicitly approved historical division reference.

    The caller supplies rows from the existing permission-audited baseline.
    Exact election ID and exact published ward name are required.  A missing
    match is a deliberate NULL result, not an opportunity to use fuzzy names
    or a GIS overlap to create an unapproved comparison.
    """

    if division_name is None:
        return _unavailable_historical_reference()
    reference = references.get((election_id, division_name))
    if reference is None:
        return _unavailable_historical_reference()
    status = reference.get("historical_reference_status")
    if status not in APPROVED_HISTORICAL_REFERENCE_STATUSES:
        raise ValueError("Historical references must have explicit approval.")
    source_urls = reference.get("permission_source_urls")
    if isinstance(source_urls, (tuple, list)):
        source_urls = "; ".join(str(url) for url in source_urls)
    return {
        "historical_reference_status": status,
        "previous_election_id": reference.get("previous_election_event_id"),
        "previous_election_date": reference.get("previous_election_date"),
        "previous_division_name": reference.get("previous_area_name"),
        "previous_winning_candidate_name": reference.get(
            "previous_winning_candidate_name"
        ),
        "previous_winning_party": reference.get("previous_winning_party"),
        "previous_winning_candidate_vote_share": reference.get(
            "previous_winning_candidate_vote_share"
        ),
        "previous_party_vote_share": None,
        "previous_party_vote_share_status": "not_materialised_without_published_party_total",
        "previous_turnout": reference.get("previous_turnout"),
        "previous_electorate": reference.get("previous_electorate"),
        "historical_source_url": reference.get("source_result_url"),
        "historical_mapping_id": reference.get("geographic_mapping_id"),
        "historical_reference_notes": reference.get("permission_evidence"),
        "historical_permission_source_urls": source_urls,
    }


def _party_history_fields(
    election_id: str,
    division_name: str | None,
    original_party_name: str | None,
    references: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> dict[str, object]:
    """Attach exact-label party history only from an approved direct lineage."""

    unavailable = {
        "party_previously_contested": None,
        "first_appearance_of_party_in_area": None,
        "party_history_status": "not_approved_or_not_applicable",
        # This candidate-level feature is the supervisor's Previous party
        # vote share. It stays separate from the division-level placeholder,
        # which has no current-party label and therefore cannot be meaningful.
        "previous_party_vote_share": None,
        "previous_party_vote_share_status": "not_derived_no_approved_exact_label_reference",
    }
    if division_name is None or original_party_name is None:
        return unavailable
    reference = references.get((election_id, division_name, original_party_name))
    if reference is None:
        return unavailable
    if reference.get("provenance") != "deterministically_derived":
        raise ValueError("Party-history fields require an approved direct lineage.")
    return {
        "party_previously_contested": reference.get("party_previously_contested"),
        "first_appearance_of_party_in_area": reference.get(
            "first_observed_appearance"
        ),
        "party_history_status": "approved_direct_exact_label",
        "previous_party_vote_share": reference.get("previous_party_vote_share"),
        "previous_party_vote_share_status": reference.get(
            "previous_party_vote_share_status",
            "not_derived_not_single_member_or_exact_label",
        ),
    }


def _candidate_continuity_fields(
    *,
    election_id: str,
    record: CandidateResultRecord,
    evidence_by_key: Mapping[
        tuple[str, str, str], CandidateContinuityEvidence
    ],
) -> tuple[dict[str, object], tuple[str, str, str] | None]:
    """Expose only a manually verified candidate-history or incumbency claim.

    A candidate name alone never enters this function as a lookup key.  The
    reviewed evidence register must first bind that exact published name and
    result-page ID through either a direct official profile link or a manually
    checked set of three official sources (profile, target result and prior
    result).  This allows auditable corroboration without silently treating
    repeated names as the same person.
    """

    unavailable = {
        "candidate_previously_stood": None,
        "candidate_history_status": "unresolved_no_explicit_identifier",
        "incumbent_candidate": None,
        "incumbency_status": "unresolved_no_authoritative_linkage",
        "candidate_continuity_evidence_id": None,
        "candidate_continuity_profile_url": None,
        "candidate_continuity_evidence_method": None,
        "candidate_continuity_source_urls": None,
    }
    try:
        key = candidate_evidence_key(
            election_id,
            record.source_url,
            record.candidate_name,
        )
    except ValueError:
        return unavailable, None
    evidence = evidence_by_key.get(key)
    if evidence is None:
        return unavailable, None
    if record.division_ward_name != evidence.division_name:
        raise ValueError("Candidate continuity evidence has a different published division.")
    if evidence.incumbent_candidate is True and record.original_party_name != evidence.incumbent_party:
        raise ValueError(
            "Candidate continuity evidence must retain the exact published party label."
        )
    # Keep the reviewed route visible in the database.  This is provenance,
    # not a confidence score: every route has already passed its own strict
    # validation in candidate_continuity_evidence.py.
    status_by_method = {
        "official_member_profile": "verified_official_member_profile",
        "official_multi_source_match": "verified_multi_source_official_evidence",
        "official_council_record_match": "verified_official_council_record_evidence",
    }
    status = status_by_method[evidence.evidence_method]
    return {
        "candidate_previously_stood": True,
        "candidate_history_status": status,
        "incumbent_candidate": evidence.incumbent_candidate,
        "incumbency_status": status if evidence.incumbent_candidate else "unknown_no_incumbency_claim",
        "candidate_continuity_evidence_id": evidence.evidence_id,
        # A stable profile is retained when available. The separate
        # Council-record route deliberately keeps this NULL rather than
        # fabricating a member UID or profile URL.
        "candidate_continuity_profile_url": evidence.member_profile_url,
        "candidate_continuity_evidence_method": evidence.evidence_method,
        "candidate_continuity_source_urls": "; ".join(
            source.source_url for source in evidence.supporting_sources
        ) or evidence.member_profile_url,
    }, key


def _supervisor_incumbency_fields(
    *,
    incumbent_candidate: object,
    incumbent_candidate_status: object,
    roster_fields: Mapping[str, object],
    current_candidate_name: str | None,
    current_source_url: str | None,
    current_party_name: str | None,
    current_number_of_seats: int | None,
    historical_reference_fields: Mapping[str, object],
) -> dict[str, object]:
    """Materialise the supervisor's two incumbency questions as tri-state fields.

    Candidate incumbency is a person-identity claim, so only reviewed official
    continuity evidence can produce ``Yes``.  Missing evidence remains
    ``Unknown``; it is never converted to ``No`` merely because a profile was
    not found.

    Party incumbency is a different, area-level question.  For an approved
    comparable single-member contest, the prior official winning party is the
    incumbent party and an exact published-label comparison can therefore
    produce ``Yes`` or ``No`` for every current candidate row.  Changed or
    multi-member geography remains ``Unknown`` because that comparison would
    otherwise transfer incumbency across a structure the project has not
    authorised.
    """

    prior_winning_candidate = historical_reference_fields.get(
        "previous_winning_candidate_name"
    )
    prior_source_url = historical_reference_fields.get("historical_source_url")
    prior_winning_party = historical_reference_fields.get("previous_winning_party")
    historical_status = historical_reference_fields.get("historical_reference_status")

    if incumbent_candidate is True:
        candidate_yes_no = "Yes"
        candidate_status = incumbent_candidate_status
        candidate_sources = None
    elif roster_fields.get("incumbent_candidate_roster_yes_no") in {"Yes", "No"}:
        # A complete election-date roster can prove both presence and absence.
        # This is stronger and more scalable than treating an unsuccessful
        # individual profile search as evidence of No.
        candidate_yes_no = str(
            roster_fields["incumbent_candidate_roster_yes_no"]
        )
        candidate_status = roster_fields["incumbent_candidate_roster_status"]
        candidate_sources = roster_fields[
            "incumbent_candidate_roster_source_urls"
        ]
    elif (
        historical_status in APPROVED_HISTORICAL_REFERENCE_STATUSES
        and isinstance(current_candidate_name, str)
        and isinstance(prior_winning_candidate, str)
        and _canonical_official_candidate_name(current_candidate_name)
        == _canonical_official_candidate_name(prior_winning_candidate)
        and isinstance(current_source_url, str)
        and isinstance(prior_source_url, str)
        and current_source_url != prior_source_url
    ):
        # This is more than a database-wide name match: two distinct official
        # result pages identify the same complete published name, the earlier
        # page explicitly marks that person Elected, and a separate statutory
        # audit approves the area continuity.  The narrow route can support a
        # positive incumbency claim, but never a negative one.
        candidate_yes_no = "Yes"
        candidate_status = (
            "verified_consecutive_official_results_approved_area_continuity"
        )
        candidate_sources = f"{prior_source_url}; {current_source_url}"
    else:
        candidate_yes_no = "Unknown"
        candidate_status = incumbent_candidate_status
        candidate_sources = None

    if historical_status not in APPROVED_HISTORICAL_REFERENCE_STATUSES:
        party_yes_no = "Unknown"
        party_name = None
        party_status = "unknown_no_approved_historical_reference"
    elif current_number_of_seats != 1:
        party_yes_no = "Unknown"
        party_name = None
        party_status = "unknown_not_comparable_single_member_contest"
    elif not isinstance(prior_winning_party, str) or not prior_winning_party.strip():
        party_yes_no = "Unknown"
        party_name = None
        party_status = "unknown_previous_winning_party_unavailable"
    elif not isinstance(current_party_name, str) or not current_party_name.strip():
        party_yes_no = "Unknown"
        party_name = prior_winning_party
        party_status = "unknown_current_published_party_unavailable"
    else:
        # Exact published labels are intentional: party standardisation must
        # not silently turn a renamed or related party into an incumbent.
        party_yes_no = "Yes" if current_party_name == prior_winning_party else "No"
        party_name = prior_winning_party
        party_status = "derived_from_approved_previous_official_winner_exact_label"

    return {
        "incumbent_candidate_yes_no": candidate_yes_no,
        "incumbent_candidate_yes_no_status": candidate_status,
        "incumbent_candidate_yes_no_source_urls": candidate_sources,
        "incumbent_candidate_roster_event_ids": roster_fields.get(
            "incumbent_candidate_roster_event_ids"
        ),
        "incumbent_party_yes_no": party_yes_no,
        "incumbent_party_name": party_name,
        "incumbent_party_yes_no_status": party_status,
    }


def _canonical_official_candidate_name(value: str) -> str:
    """Normalise only presentation differences in a complete official name.

    The 2013 result pages publish names as ``Surname, Given names`` whereas
    later pages publish ``Given names Surname``.  This function reverses that
    explicit comma format and normalises case, accents and punctuation.  It
    does not drop initials, titles or name tokens and therefore cannot turn a
    partial or similar name into an identity match.
    """

    compact = " ".join(value.split())
    if compact.count(",") == 1:
        surname, given_names = compact.split(",", 1)
        compact = f"{given_names.strip()} {surname.strip()}"
    ascii_name = unicodedata.normalize("NFKD", compact).encode(
        "ascii", "ignore"
    ).decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", ascii_name.casefold()))


def _event_date_text(election: AuditedElectionInput) -> str:
    """Return one audited ISO event date for chronological roster updates."""

    values = {
        _normalise_event_date(
            value.isoformat() if hasattr(value, "isoformat") else str(value)
        )
        for value in (record.election_date for record in election.records)
        if value is not None
    }
    if election.event_date is not None:
        values.add(_normalise_event_date(str(election.event_date)))
    if len(values) != 1:
        raise ValueError(
            f"Election {election.configuration.election_id} requires one event date "
            "before an incumbency roster can be reconstructed."
        )
    return next(iter(values))


def _normalise_event_date(value: str) -> str:
    """Canonicalise the two official date presentations before sorting."""

    for pattern in ("%Y-%m-%d", "%d %B %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported audited election date: {value!r}.")


def _canonical_area_name(value: str) -> str:
    """Normalise only published ``and``/ampersand and punctuation variants."""

    return " ".join(
        re.findall(r"[a-z0-9]+", value.casefold().replace("&", " and "))
    )


def _pre_election_incumbency_roster_fields(
    elections: Sequence[AuditedElectionInput],
) -> dict[tuple[str, str, str], dict[str, object]]:
    """Reconstruct the complete official councillor roster before each event.

    The 2013, 2017 and 2021 principal results each elect the complete 81-seat
    Surrey County Council. Every audited by-election then replaces exactly one
    vacant division. Processing those official outcomes chronologically creates
    an election-date roster without relying on retrospective biographies.

    A by-election's vacant division is removed before its candidates are
    classified. Elections held on the same date all use the same opening
    snapshot, preventing one simultaneous result from influencing another.
    The 2026 East/West shadow-authority elections read the continuing Surrey
    roster but never replace it. No roster is asserted for 2013 because the
    project does not contain a complete audited 2009 result set.
    """

    principal_ids = {
        "surrey-county-council-2013",
        "surrey-county-council-2017",
        "surrey-county-council-2021",
    }
    events_by_date: defaultdict[str, list[AuditedElectionInput]] = defaultdict(list)
    for election in elections:
        events_by_date[_event_date_text(election)].append(election)

    # area key -> (canonical candidate name, published name, official URL)
    roster: dict[str, tuple[str, str, str]] = {}
    roster_known = False
    output: dict[tuple[str, str, str], dict[str, object]] = {}
    contributing_event_ids: list[str] = []

    for event_date in sorted(events_by_date):
        same_day = events_by_date[event_date]
        for election in same_day:
            configuration = election.configuration
            event_roster = dict(roster)
            if configuration.election_type == "by-election" and roster_known:
                contested_areas = {
                    _canonical_area_name(record.division_ward_name)
                    for record in election.records
                    if record.division_ward_name
                }
                for area_key in contested_areas:
                    # The official archive's by-election event establishes a
                    # vacancy. Remove that office before testing its candidates.
                    event_roster.pop(area_key, None)

            active_by_name: defaultdict[
                str, list[tuple[str, str, str]]
            ] = defaultdict(list)
            for member in event_roster.values():
                active_by_name[member[0]].append(member)

            for record in election.records:
                key = (
                    configuration.election_id,
                    record.source_url,
                    record.candidate_name,
                )
                if not roster_known:
                    output[key] = {
                        "incumbent_candidate_roster_yes_no": "Unknown",
                        "incumbent_candidate_roster_status": (
                            "unknown_no_complete_pre_2013_official_roster"
                        ),
                        "incumbent_candidate_roster_source_urls": None,
                        "incumbent_candidate_roster_event_ids": None,
                    }
                    continue

                matches = active_by_name[
                    _canonical_official_candidate_name(record.candidate_name)
                ]
                if len(matches) > 1:
                    value = "Unknown"
                    status = "unknown_duplicate_complete_name_in_official_roster"
                    source_urls = None
                elif len(matches) == 1:
                    value = "Yes"
                    status = "verified_in_complete_pre_election_official_roster"
                    source_urls = f"{matches[0][2]}; {record.source_url}"
                else:
                    value = "No"
                    status = "verified_absent_from_complete_pre_election_official_roster"
                    source_urls = record.source_url
                output[key] = {
                    "incumbent_candidate_roster_yes_no": value,
                    "incumbent_candidate_roster_status": status,
                    "incumbent_candidate_roster_source_urls": source_urls,
                    "incumbent_candidate_roster_event_ids": "; ".join(
                        contributing_event_ids
                    ),
                }

        # Apply all same-day outcomes only after every same-day snapshot has
        # been classified.
        for election in same_day:
            configuration = election.configuration
            elected = [
                record for record in election.records if record.outcome == "Elected"
            ]
            if configuration.election_id in principal_ids:
                # Small unit-test or direct-page payloads deliberately do not
                # pretend to be a complete roster. Production inputs contain
                # all 81 official divisions and therefore enter this branch.
                if len(elected) != 81:
                    continue
                roster = {
                    _canonical_area_name(record.division_ward_name): (
                        _canonical_official_candidate_name(record.candidate_name),
                        record.candidate_name,
                        record.source_url,
                    )
                    for record in elected
                    if record.division_ward_name
                }
                roster_known = True
                contributing_event_ids = [configuration.election_id]
            elif configuration.election_type == "by-election":
                if len(elected) != 1:
                    continue
                winner = elected[0]
                if roster_known and winner.division_ward_name:
                    roster[_canonical_area_name(winner.division_ward_name)] = (
                        _canonical_official_candidate_name(winner.candidate_name),
                        winner.candidate_name,
                        winner.source_url,
                    )
                    contributing_event_ids.append(configuration.election_id)

    return output


def _pre_election_candidate_history_fields(
    elections: Sequence[AuditedElectionInput],
) -> dict[tuple[str, str, str], dict[str, object]]:
    """Classify prior candidature against the complete earlier result universe.

    This is a deterministic record-linkage layer, not fuzzy person matching.
    It compares the complete published name after only the documented 2013
    surname-first presentation normalisation.  It never removes initials or
    name tokens and never uses similarity scores.

    Once the complete 2013 principal result has established the observation
    window, absence from *all* earlier audited candidate tables can support No
    within the project's 2013--2026 scope.  A repeated exact identifier can
    support Yes unless the identifier represented multiple candidates on the
    same earlier election date.  Such a collision remains Unknown unless the
    separate manually reviewed evidence register resolves it.  Same-day events
    share an opening history snapshot, preventing outcome leakage.
    """

    principal_ids = {
        "surrey-county-council-2013",
        "surrey-county-council-2017",
        "surrey-county-council-2021",
    }
    events_by_date: defaultdict[str, list[AuditedElectionInput]] = defaultdict(list)
    for election in elections:
        events_by_date[_event_date_text(election)].append(election)

    # canonical complete name -> prior official appearances
    history: defaultdict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    history_known = False
    contributing_event_ids: list[str] = []
    ambiguous_names: set[str] = set()
    output: dict[tuple[str, str, str], dict[str, object]] = {}

    for event_date in sorted(events_by_date):
        same_day = events_by_date[event_date]
        for election in same_day:
            election_id = election.configuration.election_id
            for record in election.records:
                row_key = (election_id, record.source_url, record.candidate_name)
                if not history_known:
                    output[row_key] = {
                        "candidate_previously_stood": None,
                        "candidate_history_status": (
                            "unknown_no_complete_pre_2013_candidate_history"
                        ),
                        "candidate_history_source_urls": None,
                        "candidate_history_event_ids": None,
                    }
                    continue

                name_key = _canonical_official_candidate_name(record.candidate_name)
                matches = history[name_key]
                if name_key in ambiguous_names:
                    value = None
                    status = "unknown_ambiguous_complete_name_in_prior_official_results"
                    source_urls = "; ".join(sorted({item[2] for item in matches})) or None
                elif matches:
                    value = True
                    status = "verified_in_prior_complete_official_candidate_results"
                    source_urls = "; ".join(sorted({item[2] for item in matches}))
                else:
                    value = False
                    status = "verified_absent_from_prior_complete_official_candidate_results"
                    source_urls = record.source_url
                output[row_key] = {
                    "candidate_previously_stood": value,
                    "candidate_history_status": status,
                    "candidate_history_source_urls": source_urls,
                    "candidate_history_event_ids": "; ".join(contributing_event_ids),
                }

        # Add current candidates only after every simultaneous event has been
        # classified. Record exact-name collisions within the same date so a
        # later row cannot silently treat two people as one identity.
        names_on_date: defaultdict[str, set[str]] = defaultdict(set)
        for election in same_day:
            election_id = election.configuration.election_id
            for record in election.records:
                name_key = _canonical_official_candidate_name(record.candidate_name)
                names_on_date[name_key].add(record.source_url)
                history[name_key].append(
                    (election_id, record.candidate_name, record.source_url, event_date)
                )
        ambiguous_names.update(
            name_key for name_key, source_urls in names_on_date.items()
            if len(source_urls) > 1
        )

        for election in same_day:
            election_id = election.configuration.election_id
            if election_id not in contributing_event_ids:
                contributing_event_ids.append(election_id)
            if election_id in principal_ids:
                elected_count = sum(
                    record.outcome == "Elected" for record in election.records
                )
                # A small unit-test fixture must not claim that it constitutes
                # the complete historical search universe. Production
                # principal elections contain all 81 official elected rows.
                if elected_count == 81:
                    history_known = True

    return output


def build_master_database(
    elections: Sequence[AuditedElectionInput],
    party_lookup: Mapping[str, PartyLookupEntry] | None = None,
    geographic_mapping: Sequence[Mapping[str, object]] = (),
    historical_division_references: Mapping[
        tuple[str, str], Mapping[str, object]
    ] | None = None,
    party_history_references: Mapping[
        tuple[str, str, str], Mapping[str, object]
    ] | None = None,
    candidate_continuity_evidence: Mapping[
        tuple[str, str, str], CandidateContinuityEvidence
    ] | None = None,
) -> MasterDatabasePayload:
    """Build all required tables from audited values and separate provenance layers.

    ``party_lookup`` is optional so tests can inject a small reviewed register.
    Normal production runs load the committed exact-label configuration.  It
    controls only added lookup fields, never the original published party name.

    ``geographic_mapping`` is optional and accepts only already-reviewed
    mapping rows.  It is intentionally supplied by the reporting layer rather
    than calculated here: this election-data builder must not reclassify GIS
    relationships or promote a name match into a historical comparison.

    The two historical-reference inputs are also optional, read-only products
    of the existing permission-audited baseline.  They can expose limited
    source-backed history for approved 2026 wards, but they never permit
    candidate identity, incumbency, cross-boundary swing or vote redistribution.
    A same-lineage single-member outcome diagnostic is governed separately.

    ``candidate_continuity_evidence`` is a separately reviewed official
    member-profile register. It can add only a positive, source-linked claim
    for an exact candidate row; it never searches names, turns unknown into
    False, or transfers a person across an unapproved geographic relationship.
    """

    if party_lookup is None:
        party_lookup = load_party_lookup()
    geographic_rows = tuple(dict(row) for row in geographic_mapping)
    historical_division_references = historical_division_references or {}
    party_history_references = party_history_references or {}
    candidate_continuity_evidence = candidate_continuity_evidence or {}
    used_candidate_continuity_evidence: set[tuple[str, str, str]] = set()
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
    # Reconstruct once from the complete audited event sequence. Candidate
    # rows then receive a pre-election value without querying a later profile
    # or allowing the current result to change its own predictor.
    incumbency_roster_by_row = _pre_election_incumbency_roster_fields(elections)
    candidate_history_by_row = _pre_election_candidate_history_fields(elections)

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
        # A single-seat winning margin needs explicit official candidate
        # outcomes as well as candidate votes, so it uses a specialised audited
        # derivation. It remains a separate Derived Metadata row and never
        # changes the official winning_margin column below.
        derived_margin_records = derive_single_member_winning_margins(
            election_id=configuration.election_id,
            records=election.records,
            division_id_for_source_url=lambda source_url: _division_id(
                configuration.election_id, source_url
            ),
        )
        derived_rows.extend(derived_winning_margin_rows(derived_margin_records))
        derived_margin_division_ids = {
            record.division_id for record in derived_margin_records
        }
        # Candidate rank uses a narrower, candidate-page-only rule than the
        # division-level margin calculation.  It needs neither a winner nor a
        # Seats value: complete official candidate votes are sufficient to
        # describe vote order, while official Final Position remains untouched.
        # A vote rank is a distinct analytical calculation, not a claim that
        # the official page omitted a rank.  Complete official candidate votes
        # on the same page are sufficient for this calculation; if an official
        # rank was extracted, derive_final_positions deliberately yields no
        # duplicate and final_position remains the authoritative field.
        derived_positions = derive_final_positions(
            election_id=configuration.election_id,
            records=election.records,
        )
        # This is an independent consistency check, not a ranking input.  It
        # fails the build if published Elected/Not elected outcomes contradict
        # the vote ordering, so a source-row mismatch cannot silently enter the
        # analytical database as a plausible-looking rank.
        validate_final_positions_against_official_outcomes(
            records=election.records,
            positions=derived_positions,
        )
        derived_position_by_row = {
            (position.source_url, position.candidate_name): position
            for position in derived_positions
        }
        # Vote share has its own candidate-level publication layer. Published
        # percentages pass through unchanged; a missing value is calculated
        # only from a complete single-member candidate table on the same
        # official source page. The official vote_share field remains NULL.
        analysis_vote_share_by_row = build_analysis_vote_share_rows(election.records)
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
            party_history_fields = _party_history_fields(
                configuration.election_id,
                record.division_ward_name,
                record.original_party_name,
                party_history_references,
            )
            historical_reference_fields = _historical_reference_fields(
                configuration.election_id,
                record.division_ward_name,
                historical_division_references,
            )
            continuity_fields, continuity_key = _candidate_continuity_fields(
                election_id=configuration.election_id,
                record=record,
                evidence_by_key=candidate_continuity_evidence,
            )
            if continuity_key is not None:
                used_candidate_continuity_evidence.add(continuity_key)
            candidate_history_fields = dict(
                candidate_history_by_row[
                    (
                        configuration.election_id,
                        record.source_url,
                        record.candidate_name,
                    )
                ]
            )
            if continuity_fields["candidate_previously_stood"] is True:
                # Manually reviewed person-level evidence outranks deterministic
                # record linkage, particularly if a complete published name is
                # shared by more than one earlier candidate.
                evidence = candidate_continuity_evidence[continuity_key]
                candidate_history_fields.update(
                    {
                        "candidate_previously_stood": True,
                        "candidate_history_status": continuity_fields[
                            "candidate_history_status"
                        ],
                        "candidate_history_source_urls": continuity_fields[
                            "candidate_continuity_source_urls"
                        ],
                        "candidate_history_event_ids": "; ".join(
                            prior.election_id
                            for prior in evidence.prior_official_elections
                        ),
                    }
                )
            roster_fields = incumbency_roster_by_row[
                (
                    configuration.election_id,
                    record.source_url,
                    record.candidate_name,
                )
            ]
            if (
                candidate_history_fields["candidate_previously_stood"] is None
                and candidate_history_fields["candidate_history_status"]
                == "unknown_ambiguous_complete_name_in_prior_official_results"
                and roster_fields.get("incumbent_candidate_roster_yes_no") == "Yes"
            ):
                # A complete chronological officeholder roster can resolve an
                # otherwise ambiguous historical full name. In the production
                # data this handles the two 2021 David John Lewis winners: the
                # 2025 Camberley West by-election removes one officeholder, so
                # only the Cobham result remains in the 2026 opening roster.
                candidate_history_fields.update(
                    {
                        "candidate_previously_stood": True,
                        "candidate_history_status": (
                            "verified_in_unique_pre_election_official_roster"
                        ),
                        "candidate_history_source_urls": roster_fields[
                            "incumbent_candidate_roster_source_urls"
                        ],
                        "candidate_history_event_ids": roster_fields[
                            "incumbent_candidate_roster_event_ids"
                        ],
                    }
                )
            position = derived_position_by_row.get(
                (record.source_url, record.candidate_name)
            )
            analysis_vote_share = analysis_vote_share_by_row[
                (record.source_url, record.candidate_name)
            ]
            secondary_structure = (
                secondary_by_name.get(record.division_ward_name.casefold())
                if record.division_ward_name is not None
                else None
            )
            # Use the same governed Seats precedence as the analysis layer.
            # Supplementary statutory Seats can establish that a 2021 contest
            # was single-member without filling the official Seats field.
            analysis_number_of_seats = (
                record.number_of_seats
                if record.number_of_seats is not None
                else (
                    secondary_structure.secondary_number_of_seats
                    if secondary_structure is not None
                    else None
                )
            )
            supervisor_incumbency_fields = _supervisor_incumbency_fields(
                incumbent_candidate=continuity_fields["incumbent_candidate"],
                incumbent_candidate_status=continuity_fields["incumbency_status"],
                roster_fields=roster_fields,
                current_candidate_name=record.candidate_name,
                current_source_url=record.source_url,
                current_party_name=record.original_party_name,
                current_number_of_seats=analysis_number_of_seats,
                historical_reference_fields=historical_reference_fields,
            )
            vote_share_change = change_in_vote_share_fields(
                current_vote_share=analysis_vote_share["analysis_vote_share"],
                current_vote_share_provenance=analysis_vote_share[
                    "analysis_vote_share_provenance"
                ],
                current_number_of_seats=analysis_number_of_seats,
                previous_party_vote_share=party_history_fields[
                    "previous_party_vote_share"
                ],
                previous_party_vote_share_status=party_history_fields[
                    "previous_party_vote_share_status"
                ],
            )
            candidate_rows.append(
                {
                    "election_id": configuration.election_id,
                    "election_year": configuration.election_year,
                    "division_id": division_id,
                    "division_name": record.division_ward_name,
                    "candidate_id": candidate_ids[record.candidate_name],
                    # Preserve the source wording and add a separate display
                    # standardisation. The legacy candidate_name remains for
                    # compatibility and is still the published value.
                    "candidate_name": record.candidate_name,
                    **_candidate_standardisation_fields(record.candidate_name),
                    "original_party_name": record.original_party_name,
                    **party_fields,
                    "votes": record.votes_received,
                    "vote_share": record.vote_share,
                    **analysis_vote_share,
                    "outcome": record.outcome,
                    # This is a transparent recoding of an explicit official
                    # Outcome, not a rank or a prediction from vote totals.
                    "elected_yes_no": _elected_yes_no(record.outcome),
                    "final_position": record.final_position,
                    # This is deliberately a new field.  It is present only
                    # when the complete official candidate table permits an
                    # auditable vote ordering; it never fills final_position.
                    "derived_final_position": position.value if position else None,
                    "derived_final_position_tied": position.tied if position else None,
                    "derived_final_position_status": (
                        "derived_competition_rank_from_complete_official_votes"
                        if position
                        else "not_derived_missing_votes_duplicate_name_or_official_rank"
                    ),
                    "source_url": record.source_url,
                    "source_type": _source_type(record.source_type),
                    "notes": _source_notes(record),
                    # Retain the narrow manually reviewed person-evidence
                    # fields. The broader supervisor candidature-history
                    # classification is applied immediately afterwards.
                    **continuity_fields,
                    # The supervisor-facing candidature-history value uses the
                    # complete prior official candidate universe. The original
                    # manual evidence fields remain alongside it as a stronger
                    # person-identity provenance route where available.
                    **candidate_history_fields,
                    # The supervisor asks two Yes/No questions. They are kept
                    # separate because person identity and prior winning-party
                    # status require different official evidence chains.
                    **supervisor_incumbency_fields,
                    # This is a post-election diagnostic outcome. It must never
                    # enter the no-news predictor because it contains the
                    # current election's vote share.
                    **vote_share_change,
                    **party_history_fields,
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
            historical_reference_fields = _historical_reference_fields(
                configuration.election_id,
                division_name,
                historical_division_references,
            )
            outcome_summary = _official_outcome_summary(division_records)
            division_id = _division_id(configuration.election_id, source_url)
            official_winning_margin = _consensus(
                record.winning_margin for record in division_records
            )
            division_rows.append(
                {
                    "election_id": configuration.election_id,
                    "division_id": division_id,
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
                    **outcome_summary,
                    # Preserve a published official margin if a future source
                    # supplies one. Current audited pages supply none, so the
                    # present release remains NULL in the official field.
                    "winning_margin": official_winning_margin,
                    "winning_margin_status": (
                        "official_winning_margin_retained"
                        if official_winning_margin is not None
                        else (
                            "derived_single_member_margin_available"
                            if division_id in derived_margin_division_ids
                            else "analysis_last_seat_margin_available"
                        )
                    ),
                    **historical_reference_fields,
                    "division_completeness_status": assessment.status.value,
                }
            )

    unused_continuity_evidence = set(candidate_continuity_evidence) - used_candidate_continuity_evidence
    if unused_continuity_evidence:
        raise ValueError(
            "Candidate continuity evidence does not match an exact audited candidate row: "
            f"{sorted(unused_continuity_evidence)!r}."
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
            **_candidate_standardisation_fields(name),
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
    analysis_voting_summary = build_analysis_voting_summary(
        division_rows, supplementary_rows, derived_rows, candidate_rows
    )
    summary = _audit_summary(
        elections=elections,
        candidate_rows=candidate_rows,
        division_rows=division_rows,
        supplementary_rows=supplementary_rows,
        derived_rows=derived_rows,
        layered_reports=layered_reports,
        party_standardisation_issues=party_standardisation_issues,
        geographic_mapping_rows=geographic_rows,
    )
    analysis_margin_rows = tuple(
        row
        for row in analysis_voting_summary
        if row["field_name"] == "analysis_winning_margin"
    )
    # Report analysis-facing closure separately from official and same-page
    # derived fields. Multi-member values are final-seat cutoff margins, not
    # claims that an official margin was published.
    summary["divisions_with_analysis_winning_margin"] = sum(
        row["value"] is not None for row in analysis_margin_rows
    )
    summary["divisions_without_unambiguous_analysis_winning_margin"] = sum(
        row["value"] is None for row in analysis_margin_rows
    )
    return MasterDatabasePayload(
        elections=tuple(election_rows),
        candidate_results=tuple(candidate_rows),
        divisions_and_wards=tuple(division_rows),
        candidates=candidates,
        political_parties=parties,
        party_history_and_new_entrants=party_history,
        party_standardisation_issues=party_standardisation_issues,
        # These rows are read-only audit decisions.  They do not alter election
        # result fields, approve vote redistribution, or identify candidates.
        geographic_mapping=geographic_rows,
        supplementary_metadata=tuple(
            sorted(supplementary_rows, key=lambda row: str(row["metadata_id"]))
        ),
        derived_metadata=tuple(
            sorted(derived_rows, key=lambda row: str(row["metadata_id"]))
        ),
        # This publication layer is analysis-facing only. It never writes into
        # the official fields above and every selected value reports its layer.
        analysis_voting_summary=analysis_voting_summary,
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
    geographic_mapping_rows: Sequence[Mapping[str, object]],
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
        # Keep official absence and analytical availability side by side.  A
        # complete derived count must never be read as a claim that an official
        # ranking column was published by the Returning Officer.
        "candidate_rows_with_derived_final_position": sum(
            row["derived_final_position"] is not None for row in candidate_rows
        ),
        "candidate_rows_with_tied_derived_final_position": sum(
            row["derived_final_position_tied"] is True for row in candidate_rows
        ),
        "candidate_rows_with_official_vote_share": sum(
            row["vote_share"] is not None for row in candidate_rows
        ),
        "candidate_rows_with_analysis_vote_share": sum(
            row["analysis_vote_share"] is not None for row in candidate_rows
        ),
        "candidate_rows_with_derived_analysis_vote_share": sum(
            row["analysis_vote_share_provenance"]
            == "governed_derived_from_official_candidate_votes"
            for row in candidate_rows
        ),
        "candidate_rows_with_change_in_vote_share": sum(
            row["change_in_vote_share"] is not None for row in candidate_rows
        ),
        "candidate_rows_with_previous_party_vote_share": sum(
            row["previous_party_vote_share"] is not None for row in candidate_rows
        ),
        "candidate_previously_stood_true": sum(
            row["candidate_previously_stood"] is True for row in candidate_rows
        ),
        "candidate_previously_stood_false": sum(
            row["candidate_previously_stood"] is False for row in candidate_rows
        ),
        "candidate_previously_stood_unknown": sum(
            row["candidate_previously_stood"] is None for row in candidate_rows
        ),
        "incumbent_candidate_yes": sum(
            row["incumbent_candidate_yes_no"] == "Yes" for row in candidate_rows
        ),
        "incumbent_candidate_no": sum(
            row["incumbent_candidate_yes_no"] == "No" for row in candidate_rows
        ),
        "incumbent_candidate_unknown": sum(
            row["incumbent_candidate_yes_no"] == "Unknown" for row in candidate_rows
        ),
        "incumbent_party_yes": sum(
            row["incumbent_party_yes_no"] == "Yes" for row in candidate_rows
        ),
        "incumbent_party_no": sum(
            row["incumbent_party_yes_no"] == "No" for row in candidate_rows
        ),
        "incumbent_party_unknown": sum(
            row["incumbent_party_yes_no"] == "Unknown" for row in candidate_rows
        ),
        "candidate_rows_change_blocked_multi_member": sum(
            row["change_in_vote_share_status"]
            == "not_calculated_current_contest_not_single_member"
            for row in candidate_rows
        ),
        "candidate_rows_change_without_approved_previous_share": sum(
            row["change_in_vote_share_status"]
            == "not_calculated_no_approved_exact_label_previous_share"
            for row in candidate_rows
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
        "geographic_mapping_rows": len(geographic_mapping_rows),
        "divisions_with_single_official_winner": sum(
            row["outcome_summary_status"] == "single_official_elected_candidate"
            for row in division_rows
        ),
        "divisions_with_multiple_official_winners": sum(
            row["outcome_summary_status"] == "multiple_official_elected_candidates"
            for row in division_rows
        ),
        "approved_historical_reference_rows": sum(
            row["historical_reference_status"]
            in APPROVED_HISTORICAL_REFERENCE_STATUSES
            for row in division_rows
        ),
        "candidate_rows_with_approved_party_history": sum(
            row["party_history_status"] == "approved_direct_exact_label"
            for row in candidate_rows
        ),
        "party_standardisation_issue_rows": len(party_standardisation_issues),
        "official_division_field_missing_counts": missing_division_values,
        "per_election": per_election,
        "data_integrity_note": (
            "Null values preserve unavailable official information. Supplementary "
            "evidence and documented calculations are stored separately and do not "
            "replace official fields or change layered completeness. Geographic "
            "mapping rows, when supplied, are read-only reviewed evidence and do "
            "not change source extraction fields. Official elected outcomes and "
            "explicitly approved historical references are materialised separately "
            "without unsupported candidate identity, incumbency, margin or cross-boundary swing inference."
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
            ("candidate_name_as_published", "Exact candidate wording retained from the official result row.", "official result page", "official", "Never blank; never overwritten by standardisation."),
            ("standard_candidate_name", "Display-standard candidate name produced only from explicit punctuation, Unicode and whitespace rules.", "candidate-name standardisation policy", "derived", "Never used to assert that two records are the same person."),
            ("candidate_name_standardisation_status", "Deterministic rule used for standard_candidate_name.", "candidate-name standardisation policy", "derived", "Records whether published order was retained or an explicit surname-comma format was reformatted."),
            ("original_party_name", "Published party wording without normalisation.", "official result page", "official", "NULL if not published."),
            ("standard_party_name", "Reviewed standard name for an exact published party label.", "party standardisation lookup", "derived", "NULL when no approved exact-label mapping exists; never replaces original_party_name."),
            ("party_category", "Reviewed project grouping: established, emerging, local or independent.", "party standardisation lookup", "derived", "NULL when no approved exact-label mapping exists."),
            ("party_lookup_status", "Whether a reviewed exact-label party mapping was available.", "party standardisation lookup", "derived", "Never changes original_party_name or candidate completeness."),
            ("party_lookup_notes", "Non-merger and scope note for the reviewed party mapping.", "party standardisation lookup", "derived", "NULL when no lookup note is available."),
            ("votes", "Published votes received.", "official result page", "official", "NULL if not published."),
            ("vote_share", "Published candidate vote share percentage.", "official result page", "official", "NULL if not published."),
            ("analysis_vote_share", "Analysis-ready candidate vote share percentage.", "official vote share or governed calculation from one complete official candidate table", "analysis", "Uses the official percentage when published. Otherwise available only for a complete, positive-total, single-member official candidate table; never overwrites vote_share."),
            ("analysis_vote_share_provenance", "Evidence layer selected for analysis_vote_share.", "analysis vote-share policy", "derived", "Either official_result_page, governed_derived_from_official_candidate_votes or unavailable."),
            ("analysis_vote_share_status", "Reason analysis_vote_share is available or unavailable.", "analysis vote-share policy", "derived", "A derived value requires complete non-negative candidate votes, one seat, a positive total and a unique candidate name on one source page."),
            ("outcome", "Published candidate outcome text.", "official result page", "official", "NULL if not published."),
            ("elected_yes_no", "Yes/No recoding of explicit published Outcome only.", "official outcome", "derived", "NULL unless Outcome is exactly Elected or Not elected."),
            ("final_position", "Official candidate rank or placing if published.", "official result page", "official", "NULL when not published; never calculated from votes."),
            ("derived_final_position", "Competition rank calculated from all published candidate vote totals on the same official result page.", "official candidate votes on one result page", "derived", "NULL unless every candidate vote is published and no official Final Position is extracted. Never overwrites final_position."),
            ("derived_final_position_tied", "Whether the candidate shares the derived vote total with another candidate on the same result page.", "official candidate votes on one result page", "derived", "NULL when derived_final_position is unavailable; TRUE preserves a tie rather than imposing page-order tie-breaking."),
            ("derived_final_position_status", "Reason a separate candidate vote rank is available or unavailable.", "derived-final-position policy", "derived", "A rank is created only from a complete single-page official candidate table; it is not an official placement or outcome."),
            ("source_url", "Official result page for the candidate row.", "official result page", "official", "Never blank for extracted records."),
            ("source_type", "Evidence tier recorded by extraction.", "extraction audit", "official", "Preserved from the audited record."),
            ("notes", "Recorded source-page limitation for this candidate row.", "extraction audit", "derived", "NULL where no record-specific source limitation was recorded; never used to fill a source field."),
            ("candidate_previously_stood", "Whether the candidate appeared in an earlier audited Surrey County Council election within the project observation window.", "complete chronological official candidate-result universe, pre-election officeholder roster and reviewed person-level evidence", "derived", "TRUE requires a deterministic complete-name link across separate earlier official results, a unique roster resolution, or stronger reviewed person evidence. FALSE means absent from every earlier complete in-scope candidate table. NULL is retained before the 2013 observation boundary or for an unresolved exact-name collision; no fuzzy matching is used."),
            ("candidate_history_status", "Why candidate_previously_stood is True, False or unresolved.", "chronological official candidate-result universe, officeholder roster and candidate-history evidence register", "derived", "Distinguishes prior exact-result presence, absence from a complete prior search universe, unique-roster collision resolution, stronger reviewed person evidence, the first-period boundary and ambiguous exact-name collisions."),
            ("candidate_history_source_urls", "Official result or reviewed evidence URLs supporting the candidature-history classification.", "prior and current official candidate results or reviewed continuity evidence", "official provenance", "TRUE retains earlier supporting result URLs. FALSE retains the current result URL and is interpreted with candidate_history_event_ids, which defines the complete searched universe."),
            ("candidate_history_event_ids", "Earlier audited election events searched for candidate_previously_stood.", "chronological master event sequence", "derived provenance", "NULL before a complete prior observation window exists. Same-day events are excluded from one another to prevent temporal leakage."),
            ("incumbent_candidate", "Machine-readable person-level incumbency evidence value.", "reviewed official continuity evidence", "derived", "TRUE only when reviewed official evidence gives an eligible term start before the election; otherwise NULL. This evidence value underlies the supervisor-facing tri-state field."),
            ("incumbent_candidate_yes_no", "Supervisor-facing answer to whether this candidate held Surrey County Council office immediately before the election.", "chronological official election-result roster plus reviewed person-level evidence", "derived", "Yes/No follows the complete pre-election roster reconstructed from full principal results and every audited intervening by-election. The 2013 rows remain Unknown because no complete audited 2009 roster is in scope."),
            ("incumbent_candidate_yes_no_status", "Evidence status supporting incumbent_candidate_yes_no.", "pre-election incumbency roster and candidate continuity evidence register", "derived", "Distinguishes roster presence, roster absence, reviewed profile/Council evidence and a genuinely unavailable prior roster; an unsuccessful profile search is never treated as No."),
            ("incumbent_candidate_yes_no_source_urls", "Official source URLs supporting the candidate incumbency decision.", "prior official winning result and current official candidate result", "official provenance", "Yes retains the prior officeholder and current candidate URLs. No retains the current candidate URL and is supported by the complete roster event IDs. Profile and Council-record URLs remain in candidate_continuity_source_urls."),
            ("incumbent_candidate_roster_event_ids", "Chronological official events contributing to the pre-election councillor roster.", "complete principal results and audited by-election results", "derived provenance", "NULL only where no complete prior roster exists. Same-day events cannot influence one another; 2026 shadow-authority results do not overwrite the continuing Surrey County Council roster."),
            ("incumbent_party_yes_no", "Whether this candidate's exact published party was the approved prior winning party in the area.", "approved historical reference and prior official result", "derived", "Yes or No only for a comparable single-member contest with an approved historical reference and published prior winner; otherwise Unknown."),
            ("incumbent_party_name", "Exact published name of the prior winning party used for incumbent_party_yes_no.", "approved historical reference and prior official result", "derived", "Retained for both Yes and No comparisons; NULL when party incumbency is not decidable. This is not the party name of a person inferred to be an incumbent."),
            ("incumbent_party_yes_no_status", "Reason incumbent_party_yes_no is decidable or Unknown.", "historical-reference incumbency policy", "derived", "Exact-label comparison is allowed only within an approved comparable single-member lineage; no fuzzy party mapping or boundary transfer."),
            ("incumbency_status", "Why incumbency is available or unresolved.", "incumbency evidence register", "derived", "verified_official_member_profile, verified_multi_source_official_evidence and verified_official_council_record_evidence mean the reviewed register supports TRUE. unresolved_no_authoritative_linkage is not evidence of no incumbency."),
            ("candidate_continuity_evidence_id", "Identifier for the reviewed person-level continuity record.", "candidate continuity evidence register", "derived", "NULL when no person-level evidence is approved; never generated from a name."),
            ("candidate_continuity_profile_url", "Public official member-profile URL supporting an approved continuity record.", "Surrey County Council member profile", "official", "NULL when a Council-record route is used or when no person-level evidence is approved; no profile URL or member UID is fabricated."),
            ("candidate_continuity_evidence_method", "Reviewed method used for a person-level continuity claim.", "candidate continuity evidence register", "derived", "official_member_profile requires direct profile links. official_multi_source_match requires a reviewed profile, exact target result and earlier official result page. official_council_record_match requires exact target and prior results plus a dated Council record naming the person and office."),
            ("candidate_continuity_source_urls", "Public source URLs reviewed for the continuity claim.", "candidate continuity evidence register", "derived", "Retained only for an approved record so reviewers can reproduce the decision; no source is selected by name matching."),
            ("change_in_vote_share", "Current minus previous exact-label vote share in percentage points.", "analysis vote share and approved historical exact-label reference", "outcome diagnostic", "Available only for comparable single-member contests; never reconstructed across changed boundaries or multi-member ballots."),
            ("change_in_vote_share_status", "Reason a post-election share change is available or unavailable.", "vote-share-change policy", "derived", "Requires an approved exact-label previous share, one current seat and a current analysis share."),
            ("change_in_vote_share_provenance", "Evidence layers used by the share-change calculation.", "vote-share-change policy", "derived", "Identifies whether the current share was official or governed-derived; unavailable rows remain explicit."),
            ("change_in_vote_share_model_role", "Permitted modelling role of change_in_vote_share.", "target-leakage policy", "governance", "Always post_election_outcome_diagnostic_not_baseline_predictor because the value contains the current-election outcome."),
            ("party_previously_contested", "Whether the exact original party label was present in an approved prior direct lineage.", "historical baseline feature layer", "derived", "NULL where no explicit geographic permission exists; never uses party-name similarity."),
            ("first_appearance_of_party_in_area", "Whether the exact original party label has no earlier recorded contest in an approved direct lineage.", "historical baseline feature layer", "derived", "NULL where geography is unresolved; this is not a claim about a party's overall origin."),
            ("party_history_status", "Permission status for area-specific party history.", "historical reference audit", "derived", "Only an explicit approved exact-label lineage permits an area-specific value."),
            ("previous_party_vote_share", "Prior vote share for this candidate's exact published party label.", "official prior candidate share under approved continuity policy", "derived", "Available only for an approved exact-name single-member contest with one candidate per label, including reviewed same-statutory-division by-elections. A zero means the exact label is absent from a complete prior official candidate table; never aggregates candidates or maps labels across parties."),
            ("previous_party_vote_share_status", "Reason the candidate-level prior party share is available or blocked.", "principal and by-election historical-reference audits", "derived", "Supports a separate outcome-diagnostic change only when the current contest is also single-member; never authorises candidate identity transfer, multi-member swing or an unapproved boundary comparison."),
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
            ("official_elected_candidate_names", "All candidates explicitly marked Elected on the official result page.", "official candidate outcomes", "derived", "Preserves every official elected candidate; never selected from vote order."),
            ("official_elected_party_names", "Published party labels of all candidates explicitly marked Elected.", "official candidate outcomes", "derived", "Preserves exact original party labels and supports multi-member wards."),
            ("official_elected_candidate_count", "Count of candidates explicitly marked Elected.", "official candidate outcomes", "derived", "Counted only from explicit official outcomes; never inferred from seats."),
            ("winning_candidate_name", "Single official winning candidate where exactly one candidate is marked Elected.", "official candidate outcomes", "derived", "NULL for multi-member wards; use official_elected_candidate_names instead."),
            ("winning_party_name", "Published party of the single official winning candidate.", "official candidate outcomes", "derived", "NULL for multi-member wards; use official_elected_party_names instead."),
            ("outcome_summary_status", "Whether the official page reports one, multiple or no elected candidates.", "official candidate outcomes", "derived", "Never ranks candidates or predicts a winner."),
            ("winning_margin", "Official winning margin, when a source publishes it.", "official result page", "official", "NULL when an official page does not publish a margin; a separate derived value never overwrites it."),
            ("winning_margin_status", "Evidence state for an official or separate derived/analysis winning margin.", "official outcomes and audited winning-margin policies", "derived", "Official values take precedence. Same-page single-seat calculations remain in Derived Metadata; the analysis table additionally publishes a labelled final-seat cutoff margin for every eligible contest."),
            ("historical_reference_status", "Whether limited prior-election values may be shown for this ward.", "historical reference audit", "derived", "Only approved_for_historical_reference or approved_pre_2024_legal_continuity exposes prior values."),
            ("previous_election_id", "Identifier of the permitted earlier principal election.", "historical reference audit", "derived", "NULL without explicit geographic or legal-continuity permission."),
            ("previous_election_date", "Published date of the permitted earlier principal election.", "historical reference audit", "derived", "NULL without explicit geographic or legal-continuity permission."),
            ("previous_division_name", "Published historical division name in the permitted direct relationship.", "historical reference audit", "derived", "NULL without explicit geographic or legal-continuity permission."),
            ("previous_winning_candidate_name", "Single source-reported elected candidate in the permitted prior event.", "official historical candidate outcome", "derived", "NULL where the prior event has multiple elected candidates or geography is not approved."),
            ("previous_winning_party", "Original published party label of the single source-reported prior winner.", "official historical candidate outcome", "derived", "NULL where winner evidence or geography is ambiguous."),
            ("previous_winning_candidate_vote_share", "Published vote share of the single source-reported prior winner.", "official historical candidate result", "derived", "Not a party-total vote share and never used to calculate swing."),
            ("previous_party_vote_share", "Division-level placeholder retained for backward schema compatibility; the meaningful exact-label value is candidate-level.", "candidate-level historical baseline policy", "not applicable at division level", "Always NULL in Divisions and Wards because a division row has no current party label. Use Candidate Results.previous_party_vote_share, available for approved exact-label references; no party-total reconstruction is permitted."),
            ("previous_party_vote_share_status", "Reason the division-level placeholder is not used.", "historical baseline policy", "derived", "Directs users to the governed candidate-level field and prevents a NULL division placeholder from being misreported as zero project-wide coverage."),
            ("previous_turnout", "Official turnout of the permitted previous event.", "official historical Voting Summary", "derived", "NULL when unavailable in the historical source."),
            ("previous_electorate", "Official electorate of the permitted previous event.", "official historical Voting Summary", "derived", "NULL when unavailable in the historical source."),
            ("historical_source_url", "Official historical result page used for the permitted prior values.", "official historical result page", "official", "NULL without explicit geographic permission."),
            ("historical_mapping_id", "Reviewed geographic mapping or legal-continuity ID that permits the historical reference.", "historical reference audit", "derived", "NULL without explicit permission; does not establish person-level succession."),
            ("historical_reference_notes", "Boundary or statutory-continuity explanation for the permitted reference.", "historical reference audit", "derived", "NULL without explicit permission."),
            ("historical_permission_source_urls", "Official legal and GIS sources authorising the limited historical reference.", "historical reference audit", "derived", "NULL without explicit permission."),
            ("division_completeness_status", "Read-only division-level completeness result.", "layered completeness", "derived", "Does not fill official missing values."),
        ],
        "Candidates": [
            ("candidate_id", "Identifier for an exact published name; not identity matching.", "candidate name", "derived", "Never blank."),
            ("candidate_name", "Exact published candidate name.", "official result pages", "official", "Never blank."),
            ("candidate_name_as_published", "Exact candidate wording retained from the official result row.", "official result pages", "official", "Never blank; never overwritten by standardisation."),
            ("standard_candidate_name", "Display-standard candidate name produced only from explicit punctuation, Unicode and whitespace rules.", "candidate-name standardisation policy", "derived", "Never used as evidence of person identity."),
            ("candidate_name_standardisation_status", "Deterministic rule used for standard_candidate_name.", "candidate-name standardisation policy", "derived", "Never changes candidate_id or candidate-history evidence."),
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
            ("historical_reference_status", "Whether this reviewed direct relationship is explicitly approved for limited historical reference.", "official boundary permission audit", "derived", "Never transfers candidate identity, incumbency, swing or redistributed votes."),
            ("previous_winner_allowed", "Whether the source-reported previous winner may be exposed as a limited historical reference.", "official boundary permission audit", "derived", "True only for an explicitly approved direct relationship."),
            ("candidate_history_allowed", "Whether personal candidate history can be transferred across the boundary relationship.", "official boundary permission audit", "derived", "Always false without an explicit person-level identifier."),
            ("incumbency_allowed", "Whether incumbency may be transferred across the boundary relationship.", "official boundary permission audit", "derived", "Always false in the current project."),
            ("party_vote_share_change_allowed", "Whether party vote-share change may be calculated across the relationship.", "official boundary permission audit", "derived", "Always false in the current project."),
            ("permission_source_urls", "Official legal and GIS sources used by the permission audit.", "official boundary permission audit", "derived", "Blank when no explicit permission record exists."),
            ("permission_uncertainty", "Scope limitation recorded by the permission audit.", "official boundary permission audit", "derived", "Never interpreted as legal succession."),
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
        "Analysis Voting Summary": [
            ("election_id", "Configured election identifier.", "configuration", "configuration", "Never blank."),
            ("division_id", "Stable identifier of the analysed division or ward.", "official result URL", "derived", "Never blank for an audited area."),
            ("division_name", "Exact published division or ward name.", "official result page", "official", "Never blank for an audited area."),
            ("field_name", "Name of the analysis-facing voting-summary field.", "analysis selection policy", "analysis", "Never blank."),
            ("value", "Strongest permitted analysis value with its source layer retained.", "official, supplementary or governed-derived evidence", "analysis", "NULL where the evidence does not support one unambiguous value."),
            ("provenance_layer", "Layer and rule that supplied the analysis value.", "analysis selection policy", "derived", "For analysis_winning_margin, distinguishes official Seats from supplementary statutory Seats. Multi-member values use the documented final-seat cutoff definition."),
            ("source_metadata_id", "Identifier of supplementary or derived evidence used by the selection.", "supplementary or derived metadata", "derived", "NULL when the official result page alone supplies the analysis value."),
            ("official_field_name", "Official field preserved alongside the analysis value.", "analysis selection policy", "derived", "Never blank."),
            ("official_value", "Unchanged value extracted from the official result field.", "official result page", "official", "NULL remains visible even when a separate analysis value is available."),
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
        "Analysis Voting Summary": list(payload.analysis_voting_summary),
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
        f"- Candidate rows with separate derived_final_position: {summary['candidate_rows_with_derived_final_position']}",
        f"- Candidate rows tied on derived_final_position: {summary['candidate_rows_with_tied_derived_final_position']}",
        f"- Candidate rows with official vote_share: {summary['candidate_rows_with_official_vote_share']}",
        f"- Candidate rows with analysis_vote_share: {summary['candidate_rows_with_analysis_vote_share']}",
        f"- Candidate rows with governed-derived analysis_vote_share: {summary['candidate_rows_with_derived_analysis_vote_share']}",
        f"- Candidate rows with previous_party_vote_share: {summary['candidate_rows_with_previous_party_vote_share']}",
        f"- Candidate rows with post-election change_in_vote_share: {summary['candidate_rows_with_change_in_vote_share']}",
        f"- Candidate rows with change blocked for a multi-member current contest: {summary['candidate_rows_change_blocked_multi_member']}",
        f"- Candidate rows with no approved previous exact-label share: {summary['candidate_rows_change_without_approved_previous_share']}",
        f"- Candidate previously stood: True={summary['candidate_previously_stood_true']}; False={summary['candidate_previously_stood_false']}; Unknown={summary['candidate_previously_stood_unknown']}",
        f"- Incumbent candidate: Yes={summary['incumbent_candidate_yes']}; No={summary['incumbent_candidate_no']}; Unknown={summary['incumbent_candidate_unknown']}",
        f"- Incumbent party: Yes={summary['incumbent_party_yes']}; No={summary['incumbent_party_no']}; Unknown={summary['incumbent_party_unknown']}",
        f"- Divisions with analysis_winning_margin: {summary['divisions_with_analysis_winning_margin']}",
        f"- Divisions without an unambiguous analysis_winning_margin: {summary['divisions_without_unambiguous_analysis_winning_margin']}",
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
