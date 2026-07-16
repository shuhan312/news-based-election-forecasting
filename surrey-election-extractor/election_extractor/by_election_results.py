"""Load evidence-backed Surrey County Council by-election candidate results.

The official archive catalogue and the candidate-result evidence are separate
inputs.  An archive-listed event with no verified official candidate-result source remains
an event with zero *known* candidate records, rather than becoming a guessed
zero-candidate contest.  This module has no network access and does not alter
the completed principal-election extraction pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from election_extractor.extraction import (
    CandidateResultRecord,
    EvidenceSourceType,
    ExtractionStatus,
    FieldEvidence,
    REQUIRED_RECORD_FIELDS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOGUE_PATH = PROJECT_ROOT / "config/by_election_event_catalogue.json"
DEFAULT_RESULTS_PATH = PROJECT_ROOT / "config/by_election_official_results.json"


@dataclass(frozen=True)
class ByElectionEvent:
    """Retain one official-archive event independently of result availability."""

    election_id: str
    election_name: str
    election_date: str
    election_type: str
    authority: str
    division_name: str
    archive_source_url: str
    archive_evidence_text: str


@dataclass(frozen=True)
class ByElectionResultEvidence:
    """Store one published official source used to create candidate records."""

    election_id: str
    source_url: str
    source_title: str
    source_publisher: str
    source_format: str
    evidence_text: str
    records: tuple[CandidateResultRecord, ...]


def _required_text(value: object, field_name: str) -> str:
    """Reject blank source fields rather than supplying a default value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"By-election input requires non-empty {field_name}.")
    return value.strip()


def _optional_int(value: object) -> int | None:
    """Keep missing numeric source values null and reject non-integer values."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("By-election numeric values must be integers or null.")
    return value


def _optional_float(value: object) -> float | None:
    """Keep missing percentage source values null and reject non-numeric values."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("By-election percentage values must be numeric or null.")
    return float(value)


def _official_public_url(value: object) -> str:
    """Accept a public HTTP(S) evidence URL without credentials or fragments."""

    url = _required_text(value, "source_url")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("By-election official evidence requires a public HTTP(S) source_url.")
    return url


def load_by_election_catalogue(
    path: str | Path = DEFAULT_CATALOGUE_PATH,
) -> tuple[ByElectionEvent, ...]:
    """Load existing archive-listed events without adding a second event list."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("By-election catalogue must be a JSON object.")
    authority = _required_text(payload.get("authority"), "authority")
    archive_url = _required_text(payload.get("official_archive_url"), "official_archive_url")
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("By-election catalogue requires an events list.")
    events = []
    for raw in raw_events:
        if not isinstance(raw, Mapping):
            raise ValueError("Each by-election catalogue event must be an object.")
        event = ByElectionEvent(
            election_id=_required_text(raw.get("election_id"), "election_id"),
            election_name=_required_text(raw.get("election_name"), "election_name"),
            election_date=_required_text(raw.get("election_date"), "election_date"),
            election_type=_required_text(raw.get("election_type"), "election_type"),
            authority=authority,
            division_name=_required_text(raw.get("area_name"), "area_name"),
            archive_source_url=archive_url,
            archive_evidence_text=_required_text(raw.get("evidence_text"), "evidence_text"),
        )
        if event.election_type != "by-election":
            raise ValueError("By-election catalogue events must have election_type=by-election.")
        events.append(event)
    identifiers = [event.election_id for event in events]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("By-election catalogue contains duplicate election IDs.")
    return tuple(sorted(events, key=lambda event: (event.election_date, event.election_id)))


def _missing_fields(record: Mapping[str, object]) -> tuple[str, ...]:
    """Use the existing extraction completeness field list without filling values."""

    attributes = {
        "election_name": record["election_name"],
        "election_date": record["election_date"],
        "authority": record["authority"],
        "division_ward_name": record["division_ward_name"],
        "number_of_seats": record["number_of_seats"],
        "candidate_name": record["candidate_name"],
        "original_party_name": record["original_party_name"],
        "votes_received": record["votes_received"],
        "vote_share": record["vote_share"],
        "outcome": record["outcome"],
        "electorate": record["electorate"],
        "ballot_papers_issued": record["ballot_papers_issued"],
        "ballot_papers_rejected": record["ballot_papers_rejected"],
        "turnout": record["turnout"],
    }
    return tuple(field for field in REQUIRED_RECORD_FIELDS if attributes[field] is None)


def _field_evidence(
    *,
    source_url: str,
    source_title: str,
    source_publisher: str,
    source_format: str,
    evidence_text: str,
    values: Mapping[str, object],
) -> tuple[FieldEvidence, ...]:
    """Attach source-specific official provenance to every non-null field."""

    return tuple(
        FieldEvidence(
            field_name=name,
            published_value=str(value),
            source_url=source_url,
            search_query="Official published election-result evidence",
            search_result_title=source_title,
            search_result_snippet=evidence_text,
            evidence_source=f"{source_publisher} {source_format.replace('_', ' ')}",
            source_type=EvidenceSourceType.OFFICIAL,
        )
        for name, value in values.items()
        if value is not None
    )


def load_by_election_result_evidence(
    *,
    catalogue: Sequence[ByElectionEvent] | None = None,
    path: str | Path = DEFAULT_RESULTS_PATH,
) -> tuple[ByElectionResultEvidence, ...]:
    """Load only event results with identified published official evidence."""

    events = catalogue if catalogue is not None else load_by_election_catalogue()
    events_by_id = {event.election_id: event for event in events}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
        raise ValueError("By-election official-results input requires a results list.")
    evidence = []
    for raw_result in payload["results"]:
        if not isinstance(raw_result, Mapping):
            raise ValueError("Each by-election official result must be an object.")
        election_id = _required_text(raw_result.get("election_id"), "election_id")
        if election_id not in events_by_id:
            raise ValueError("By-election result evidence references an event outside the catalogue.")
        event = events_by_id[election_id]
        source_url = _official_public_url(raw_result.get("source_url"))
        source_title = _required_text(raw_result.get("source_title"), "source_title")
        source_publisher = _required_text(raw_result.get("source_publisher"), "source_publisher")
        source_format = _required_text(raw_result.get("source_format"), "source_format")
        if source_format not in {"official_result_page", "official_declaration"}:
            raise ValueError("By-election result evidence has an unsupported source_format.")
        evidence_text = _required_text(raw_result.get("evidence_text"), "evidence_text")
        summary = raw_result.get("voting_summary")
        candidates = raw_result.get("candidates")
        if not isinstance(summary, Mapping) or not isinstance(candidates, list) or not candidates:
            raise ValueError("Official by-election evidence requires a summary and non-empty candidates list.")
        shared = {
            "election_name": event.election_name,
            "election_date": event.election_date,
            "authority": event.authority,
            "division_ward_name": event.division_name,
            "number_of_seats": _optional_int(summary.get("seats")),
            "electorate": _optional_int(summary.get("electorate")),
            "ballot_papers_issued": _optional_int(summary.get("ballot_papers_issued")),
            "ballot_papers_rejected": _optional_int(summary.get("rejected_ballots")),
            "turnout": _optional_float(summary.get("turnout")),
            "total_votes": _optional_int(summary.get("total_votes")),
        }
        records = []
        for raw_candidate in candidates:
            if not isinstance(raw_candidate, Mapping):
                raise ValueError("By-election candidate evidence must be an object.")
            candidate_values = {
                **shared,
                "candidate_name": _required_text(raw_candidate.get("candidate_name"), "candidate_name"),
                "original_party_name": raw_candidate.get("original_party_name"),
                "votes_received": _optional_int(raw_candidate.get("votes")),
                "vote_share": _optional_float(raw_candidate.get("vote_share")),
                "outcome": raw_candidate.get("elected_status"),
            }
            if candidate_values["original_party_name"] is not None:
                candidate_values["original_party_name"] = _required_text(
                    candidate_values["original_party_name"], "original_party_name"
                )
            if candidate_values["outcome"] is not None:
                candidate_values["outcome"] = _required_text(candidate_values["outcome"], "elected_status")
            missing = _missing_fields(candidate_values)
            records.append(
                CandidateResultRecord(
                    election_name=event.election_name,
                    election_date=event.election_date,
                    authority=event.authority,
                    division_ward_name=event.division_name,
                    number_of_seats=candidate_values["number_of_seats"],
                    candidate_name=candidate_values["candidate_name"],
                    original_party_name=candidate_values["original_party_name"],
                    votes_received=candidate_values["votes_received"],
                    vote_share=candidate_values["vote_share"],
                    outcome=candidate_values["outcome"],
                    electorate=candidate_values["electorate"],
                    ballot_papers_issued=candidate_values["ballot_papers_issued"],
                    ballot_papers_rejected=candidate_values["ballot_papers_rejected"],
                    turnout=candidate_values["turnout"],
                    source_url=source_url,
                    extraction_status=(ExtractionStatus.COMPLETE if not missing else ExtractionStatus.INCOMPLETE),
                    missing_fields=missing,
                    field_evidence=_field_evidence(
                        source_url=source_url,
                        source_title=source_title,
                        source_publisher=source_publisher,
                        source_format=source_format,
                        evidence_text=evidence_text,
                        values=candidate_values,
                    ),
                    source_type=EvidenceSourceType.OFFICIAL,
                    extraction_timestamp=None,
                    election_type=event.election_type,
                    final_position=None,
                    elected=("Yes" if candidate_values["outcome"] == "Elected" else "No" if candidate_values["outcome"] == "Not elected" else None),
                    total_votes=candidate_values["total_votes"],
                )
            )
        evidence.append(
            ByElectionResultEvidence(
                election_id=election_id,
                source_url=source_url,
                source_title=source_title,
                source_publisher=source_publisher,
                source_format=source_format,
                evidence_text=evidence_text,
                records=tuple(records),
            )
        )
    identifiers = [item.election_id for item in evidence]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("By-election official-results input contains duplicate election IDs.")
    return tuple(sorted(evidence, key=lambda item: item.election_id))


def by_election_records_by_id(
    evidence: Sequence[ByElectionResultEvidence] | None = None,
) -> dict[str, tuple[CandidateResultRecord, ...]]:
    """Return records keyed by event ID, leaving no-evidence events absent."""

    items = evidence if evidence is not None else load_by_election_result_evidence()
    return {item.election_id: item.records for item in items}


def unavailable_by_election_ids(
    catalogue: Sequence[ByElectionEvent] | None = None,
    evidence: Sequence[ByElectionResultEvidence] | None = None,
) -> tuple[str, ...]:
    """Expose catalogued events lacking verified candidate-result evidence for audit."""

    events = catalogue if catalogue is not None else load_by_election_catalogue()
    records = evidence if evidence is not None else load_by_election_result_evidence(catalogue=events)
    extracted_ids = {item.election_id for item in records}
    return tuple(event.election_id for event in events if event.election_id not in extracted_ids)


def evidence_audit_rows(
    *,
    catalogue: Sequence[ByElectionEvent] | None = None,
    evidence: Sequence[ByElectionResultEvidence] | None = None,
) -> tuple[dict[str, object], ...]:
    """Produce event-level provenance rows without pretending missing results exist."""

    events = catalogue if catalogue is not None else load_by_election_catalogue()
    results = evidence if evidence is not None else load_by_election_result_evidence(catalogue=events)
    results_by_id = {item.election_id: item for item in results}
    return tuple(
        {
            "election_id": event.election_id,
            "election_name": event.election_name,
            "election_date": event.election_date,
            "division_name": event.division_name,
            "archive_source_url": event.archive_source_url,
            "result_source_url": results_by_id[event.election_id].source_url if event.election_id in results_by_id else None,
            "result_source_publisher": results_by_id[event.election_id].source_publisher if event.election_id in results_by_id else None,
            "result_source_format": results_by_id[event.election_id].source_format if event.election_id in results_by_id else None,
            "candidate_record_count": len(results_by_id[event.election_id].records) if event.election_id in results_by_id else None,
            "extraction_status": "official_result_evidence_available" if event.election_id in results_by_id else "official_result_evidence_not_retrieved",
            "provenance": "official_indexed_page" if event.election_id in results_by_id else "official_archive_catalogue_only",
            "notes": None if event.election_id in results_by_id else "No verified official candidate-result evidence was available to this run; no candidate rows were created.",
        }
        for event in events
    )
