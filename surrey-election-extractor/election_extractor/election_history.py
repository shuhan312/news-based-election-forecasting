"""Create an evidence-gated Surrey election-event timeline and enrichment layer.

This module only reads completed official extraction audits, the reviewed
by-election catalogue, the party lookup, and the completed geographic decision
output.  It never calls discovery or extraction and never alters a raw record.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from election_extractor.election_config import ElectionConfiguration, load_election_config
from election_extractor.by_election_results import (
    DEFAULT_RESULTS_PATH as BY_ELECTION_RESULTS_PATH,
    by_election_records_by_id,
)
from election_extractor.extraction import CandidateResultRecord
from election_extractor.master_database import AUDITED_ELECTION_INPUTS
from election_extractor.party_lookup import PartyLookupEntry, load_party_lookup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BY_ELECTION_CATALOGUE_PATH = PROJECT_ROOT / "config/by_election_event_catalogue.json"
DEFAULT_DIRECT_MAPPING_PATH = (
    PROJECT_ROOT / "outputs/geographic_crosswalk_resolution/final_direct_mapping_dataset.json"
)

REQUIRED_CANDIDATE_FIELDS = (
    "candidate_name",
    "original_party_name",
    "votes_received",
    "vote_share",
    "outcome",
)
BLOCKED_COMPARISON_FIELDS = (
    "previous_winner",
    "previous_party_vote_share",
    "vote_share_change",
    "party_swing",
    "gain_hold_loss",
    "incumbency",
    "predecessor_councillor_transfer",
)


@dataclass(frozen=True)
class ElectionEventArea:
    """Represent one election event in one published division or ward."""

    election_id: str
    election_name: str
    election_type: str
    election_date: str
    authority: str | None
    area_id: str
    area_name: str
    geographic_identity_key: str | None
    geographic_identity_basis: str
    candidate_row_count: int | None
    source_url: str
    source_coverage: str
    provenance: str
    evidence_text: str | None


def _required_text(value: object, field_name: str) -> str:
    """Reject missing catalogue text rather than inventing event metadata."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Election history requires non-empty {field_name}.")
    return value.strip()


def _optional_text(value: object) -> str | None:
    """Keep an unavailable source value as null rather than an empty string."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _present(value: object) -> bool:
    """Treat null and blank values as unavailable without substituting zero."""

    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _normalise_area_name(name: str) -> str:
    """Apply only display normalisation, never fuzzy geographic matching."""

    collapsed = " ".join(name.casefold().split())
    # The GIS review labels historic units as "ED" and 2026 units as "Ward".
    # Removing only these terminal display suffixes does not equate different
    # place names or resolve a boundary change.
    return re.sub(r"\s+(?:ed|ward)$", "", collapsed)


def _area_id(election_id: str, source_url: str, area_name: str) -> str:
    """Create a deterministic technical ID while retaining the official URL."""

    identifier = parse_qs(urlsplit(source_url).query).get("ID", [None])[0]
    if identifier and identifier.isdigit():
        return f"{election_id}:official-area:{identifier}"
    slug = re.sub(r"[^a-z0-9]+", "-", _normalise_area_name(area_name)).strip("-")
    return f"{election_id}:catalogued-area:{slug}"


def _parse_official_date(value: object) -> str:
    """Convert an already published date into ISO form without inferring a date."""

    text = _required_text(value, "election_date")
    for pattern in ("%d %B %Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return date.strptime(text, pattern).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported published election date: {text}")


def _consensus(values: Iterable[object]) -> object | None:
    """Return one shared source value, or null if records disagree or omit it."""

    observed = []
    for value in values:
        if _present(value) and value not in observed:
            observed.append(value)
    return observed[0] if len(observed) == 1 else None


def load_by_election_catalogue(
    path: str | Path = DEFAULT_BY_ELECTION_CATALOGUE_PATH,
) -> tuple[dict[str, object], ...]:
    """Load official-archive event evidence without creating candidate rows."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("By-election catalogue must be a JSON object.")
    archive_url = _required_text(payload.get("official_archive_url"), "official_archive_url")
    authority = _required_text(payload.get("authority"), "authority")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("By-election catalogue requires a non-empty events list.")
    parsed = []
    for item in events:
        if not isinstance(item, Mapping):
            raise ValueError("Each by-election catalogue entry must be an object.")
        event = {
            "election_id": _required_text(item.get("election_id"), "election_id"),
            "election_name": _required_text(item.get("election_name"), "election_name"),
            "election_type": _required_text(item.get("election_type"), "election_type"),
            "election_date": _parse_official_date(item.get("election_date")),
            "authority": authority,
            "area_name": _required_text(item.get("area_name"), "area_name"),
            "source_url": archive_url,
            "evidence_text": _required_text(item.get("evidence_text"), "evidence_text"),
        }
        if event["election_type"] != "by-election":
            raise ValueError("By-election catalogue entries must have election_type=by-election.")
        parsed.append(event)
    identifiers = [str(item["election_id"]) for item in parsed]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("By-election catalogue contains duplicate election_id values.")
    return tuple(sorted(parsed, key=lambda item: (str(item["election_date"]), str(item["election_id"]))))


def _load_audit(path: Path) -> Mapping[str, object]:
    """Load one completed official extraction audit without modifying it."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Election audit must be an object: {path}")
    return payload


def _configuration_by_id() -> dict[str, ElectionConfiguration]:
    """Use configured election-level metadata rather than page-local omissions."""

    return {item.election_id: item for item in load_election_config()}


def _direct_mapping_index(path: str | Path = DEFAULT_DIRECT_MAPPING_PATH) -> dict[tuple[str, str], str]:
    """Return only reviewed accepted-direct 2026-to-historic identity links."""

    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Direct mapping dataset must be a JSON list.")
    candidates: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if not isinstance(row, Mapping) or row.get("analytical_status") != "accepted_direct":
            continue
        key = (
            _required_text(row.get("current_election_id"), "current_election_id"),
            _normalise_area_name(_required_text(row.get("current_area_name"), "current_area_name")),
        )
        candidates[key].add(
            _normalise_area_name(_required_text(row.get("previous_area_name"), "previous_area_name"))
        )
    # A conflicting direct mapping is not silently resolved. Omitting the key
    # makes chronology unavailable rather than choosing one predecessor.
    return {key: value.pop() for key, value in candidates.items() if len(value) == 1}


def _principal_event_areas(
    configuration: ElectionConfiguration,
    audit: Mapping[str, object],
    direct_mappings: Mapping[tuple[str, str], str],
) -> tuple[tuple[ElectionEventArea, ...], tuple[dict[str, object], ...]]:
    """Convert completed official candidate rows into area-level event records."""

    extraction = audit.get("extraction")
    if not isinstance(extraction, Mapping) or not isinstance(extraction.get("records"), list):
        raise ValueError(f"Audit for {configuration.election_id} has no extraction records.")
    by_area: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for record in extraction["records"]:
        if not isinstance(record, Mapping):
            raise ValueError("Extraction records must be objects.")
        source_url = _required_text(record.get("source_url"), "source_url")
        by_area[source_url].append(record)

    event_areas = []
    candidate_rows = []
    for source_url, records in sorted(by_area.items()):
        area_name = _consensus(record.get("division_ward_name") for record in records)
        if not isinstance(area_name, str):
            raise ValueError(f"Official records disagree on area name: {source_url}")
        published_date = _consensus(record.get("election_date") for record in records)
        if published_date is None:
            raise ValueError(f"Official records do not provide an election date: {source_url}")
        event_date = _parse_official_date(published_date)
        authority = _consensus(record.get("authority") for record in records)
        area_id = _area_id(configuration.election_id, source_url, area_name)
        normalised_name = _normalise_area_name(area_name)
        if configuration.election_year <= 2021:
            identity_key = f"historical:{normalised_name}"
            identity_basis = "direct_historical_published_area_name"
        else:
            previous_name = direct_mappings.get((configuration.election_id, normalised_name))
            identity_key = f"historical:{previous_name}" if previous_name else None
            identity_basis = (
                "accepted_direct_geographic_mapping"
                if previous_name
                else "unavailable_geographic_mapping"
            )
        event_areas.append(
            ElectionEventArea(
                election_id=configuration.election_id,
                election_name=configuration.election_name,
                election_type="principal_election",
                election_date=event_date,
                authority=authority if isinstance(authority, str) else None,
                area_id=area_id,
                area_name=area_name,
                geographic_identity_key=identity_key,
                geographic_identity_basis=identity_basis,
                candidate_row_count=len(records),
                source_url=source_url,
                source_coverage="official_result_page",
                provenance="source_reported",
                evidence_text=None,
            )
        )
        for index, record in enumerate(records, start=1):
            candidate_rows.append(
                {
                    "candidate_result_id": f"{area_id}:candidate:{index:02d}",
                    "election_id": configuration.election_id,
                    "election_type": "principal_election",
                    "election_date": event_date,
                    "authority": authority if isinstance(authority, str) else None,
                    "area_id": area_id,
                    "area_name": area_name,
                    "seats": record.get("number_of_seats"),
                    "candidate_name": record.get("candidate_name"),
                    "original_party_name": record.get("original_party_name"),
                    "votes": record.get("votes_received"),
                    "vote_share": record.get("vote_share"),
                    "elected_status": record.get("outcome"),
                    # Retain official division-summary values alongside every
                    # candidate row.  They are used only to audit whether a
                    # value was published; no candidate-level value is derived.
                    "total_votes": record.get("total_votes"),
                    "electorate": record.get("electorate"),
                    "ballot_papers_issued": record.get("ballot_papers_issued"),
                    "ballot_papers_rejected": record.get("ballot_papers_rejected"),
                    "turnout": record.get("turnout"),
                    "source_url": source_url,
                    "provenance": "source_reported",
                    "source_missing_fields": list(record.get("missing_fields", ())),
                }
            )
    return tuple(event_areas), tuple(candidate_rows)


def _by_election_areas(
    catalogue: Sequence[Mapping[str, object]],
    records_by_event: Mapping[str, Sequence[CandidateResultRecord]],
) -> tuple[tuple[ElectionEventArea, ...], tuple[dict[str, object], ...]]:
    """Add verified by-election rows while keeping absent result sources unavailable.

    The archive catalogue establishes that an event occurred. Candidate rows
    are added only when the separate evidence register names published official
    candidate-result evidence for that event; this function never infers candidates from the event
    title, later elections, or a candidate name appearing elsewhere.
    """

    events = []
    candidates = []
    for item in catalogue:
        area_name = _required_text(item.get("area_name"), "area_name")
        election_id = _required_text(item.get("election_id"), "election_id")
        archive_url = _required_text(item.get("source_url"), "source_url")
        records = tuple(records_by_event.get(election_id, ()))
        source_url = records[0].source_url if records else archive_url
        area_id = _area_id(election_id, source_url, area_name)
        events.append(
            ElectionEventArea(
                election_id=election_id,
                election_name=_required_text(item.get("election_name"), "election_name"),
                election_type="by-election",
                election_date=_required_text(item.get("election_date"), "election_date"),
                authority=_optional_text(item.get("authority")),
                area_id=area_id,
                area_name=area_name,
                geographic_identity_key=f"historical:{_normalise_area_name(area_name)}",
                geographic_identity_basis="direct_historical_published_area_name",
                candidate_row_count=len(records) if records else None,
                source_url=source_url,
                source_coverage=(
                    "official_candidate_result_evidence"
                    if records
                    else "official_archive_indexed_listing; complete_candidate_results_not_available"
                ),
                provenance="source_reported",
                evidence_text=_optional_text(item.get("evidence_text")),
            )
        )
        for index, record in enumerate(records, start=1):
            candidates.append(
                {
                    "candidate_result_id": f"{area_id}:candidate:{index:02d}",
                    "election_id": election_id,
                    "election_type": "by-election",
                    "election_date": _required_text(item.get("election_date"), "election_date"),
                    "authority": _optional_text(item.get("authority")),
                    "area_id": area_id,
                    "area_name": area_name,
                    "seats": record.number_of_seats,
                    "candidate_name": record.candidate_name,
                    "original_party_name": record.original_party_name,
                    "votes": record.votes_received,
                    "vote_share": record.vote_share,
                    "elected_status": record.outcome,
                    "total_votes": record.total_votes,
                    "electorate": record.electorate,
                    "ballot_papers_issued": record.ballot_papers_issued,
                    "ballot_papers_rejected": record.ballot_papers_rejected,
                    "turnout": record.turnout,
                    "source_url": record.source_url,
                    "provenance": "source_reported",
                    "source_missing_fields": list(record.missing_fields),
                }
            )
    return tuple(events), tuple(candidates)


def _standardise_party_rows(
    candidate_rows: Sequence[Mapping[str, object]],
    lookup: Mapping[str, PartyLookupEntry],
) -> tuple[dict[str, object], ...]:
    """Add a reviewed party field without changing published party wording."""

    enriched = []
    for row in candidate_rows:
        original = _optional_text(row.get("original_party_name"))
        entry = lookup.get(original) if original is not None else None
        enriched.append(
            {
                **row,
                "standardised_party_name": entry.standard_party_name if entry else None,
                "party_category": entry.party_category if entry else None,
                "party_standardisation_provenance": "manually_confirmed" if entry else "unavailable",
                # Published names alone are not an identity key. The layer
                # therefore exposes the required history fields as unavailable.
                "candidate_identity_status": "unresolved_no_explicit_identifier",
                "candidate_appeared_before": None,
                "previous_election_events_contested": None,
                "previous_parties_contested": None,
                "candidate_history_provenance": "unavailable",
            }
        )
    return tuple(enriched)


def build_chronology(events: Sequence[ElectionEventArea]) -> tuple[dict[str, object], ...]:
    """Link only direct identities and preserve any same-date ordering ambiguity."""

    groups: defaultdict[str, list[ElectionEventArea]] = defaultdict(list)
    unavailable = []
    for event in events:
        if event.geographic_identity_key is None:
            unavailable.append(event)
        else:
            groups[event.geographic_identity_key].append(event)

    timeline = []
    for identity_key, group in sorted(groups.items()):
        ordered = sorted(group, key=lambda item: (item.election_date, item.election_id))
        for index, event in enumerate(ordered):
            previous_candidates = [item for item in ordered[:index] if item.election_date < event.election_date]
            next_candidates = [item for item in ordered[index + 1 :] if item.election_date > event.election_date]
            previous_date = previous_candidates[-1].election_date if previous_candidates else None
            next_date = next_candidates[0].election_date if next_candidates else None
            previous_same_date = [item for item in ordered if item.election_date == previous_date] if previous_date else []
            next_same_date = [item for item in ordered if item.election_date == next_date] if next_date else []
            # A tied date cannot be ordered from the published date alone. The
            # unique link stays null and the competing events remain visible.
            previous_id = previous_same_date[0].election_id if len(previous_same_date) == 1 else None
            next_id = next_same_date[0].election_id if len(next_same_date) == 1 else None
            chronology_status = "available_direct_identity"
            if len(previous_same_date) > 1 or len(next_same_date) > 1:
                chronology_status = "available_with_same_date_ambiguity"
            timeline.append(
                {
                    "area_id": event.area_id,
                    "area_name": event.area_name,
                    "geographic_identity_key": identity_key,
                    "geographic_identity_basis": event.geographic_identity_basis,
                    "election_id": event.election_id,
                    "election_date": event.election_date,
                    "election_type": event.election_type,
                    "previous_election_event_id": previous_id,
                    "next_election_event_id": next_id,
                    "same_date_previous_event_ids": [item.election_id for item in previous_same_date] if len(previous_same_date) > 1 else [],
                    "same_date_next_event_ids": [item.election_id for item in next_same_date] if len(next_same_date) > 1 else [],
                    "provenance": "deterministically_derived",
                    "chronology_status": chronology_status,
                }
            )
    for event in unavailable:
        timeline.append(
            {
                "area_id": event.area_id,
                "area_name": event.area_name,
                "geographic_identity_key": None,
                "geographic_identity_basis": event.geographic_identity_basis,
                "election_id": event.election_id,
                "election_date": event.election_date,
                "election_type": event.election_type,
                "previous_election_event_id": None,
                "next_election_event_id": None,
                "same_date_previous_event_ids": [],
                "same_date_next_event_ids": [],
                "provenance": "unavailable",
                "chronology_status": "unavailable_geographic_mapping",
            }
        )
    return tuple(sorted(timeline, key=lambda item: (str(item["election_date"]), str(item["election_id"]), str(item["area_id"]))))


def _availability(records: Sequence[Mapping[str, object]], field_name: str) -> bool:
    """Report availability only when the official area records agree on a value."""

    return _consensus(record.get(field_name) for record in records) is not None


def _area_enrichment(
    events: Sequence[ElectionEventArea],
    candidates: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Create factual event summaries while leaving comparison features blocked."""

    by_area: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for candidate in candidates:
        by_area[str(candidate["area_id"])].append(candidate)
    rows = []
    for event in events:
        records = by_area[event.area_id]
        published_parties = {
            str(record["original_party_name"])
            for record in records
            if _present(record.get("original_party_name"))
        }
        rows.append(
            {
                "area_id": event.area_id,
                "election_id": event.election_id,
                "election_date": event.election_date,
                "election_type": event.election_type,
                "number_of_candidates": len(records) if event.candidate_row_count is not None else None,
                "number_of_candidates_provenance": "deterministically_derived" if records else "unavailable",
                "number_of_published_parties": len(published_parties) if records else None,
                "number_of_seats": _consensus(record.get("seats") for record in records),
                "turnout_available": _availability(records, "turnout") if records else None,
                "electorate_available": _availability(records, "electorate") if records else None,
                "rejected_ballot_available": _availability(records, "ballot_papers_rejected") if records else None,
                "contest_has_multiple_candidates": len(records) > 1 if records else None,
                "source_provenance": "deterministically_derived" if records else "unavailable",
                "blocked_comparison_features": {
                    field_name: {"value": None, "provenance": "unavailable"}
                    for field_name in BLOCKED_COMPARISON_FIELDS
                },
            }
        )
    return tuple(rows)


def _party_history(candidates: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    """Record factual party-event appearance history without vote redistribution."""

    by_party: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for candidate in candidates:
        party = candidate.get("standardised_party_name")
        if isinstance(party, str):
            by_party[party].append(candidate)
    history = []
    for party, rows in sorted(by_party.items()):
        event_dates = {
            (str(row["election_id"]), str(row["election_date"])) for row in rows
        }
        ordered_events = sorted(event_dates, key=lambda item: (item[1], item[0]))
        previous: list[str] = []
        for event_id, event_date in ordered_events:
            contested = [row for row in rows if row["election_id"] == event_id]
            history.append(
                {
                    "standardised_party_name": party,
                    "election_id": event_id,
                    "election_date": event_date,
                    "first_observed_appearance": not previous,
                    "previous_election_events": list(previous),
                    "previous_contest_count": len(previous),
                    "candidate_result_rows_in_event": len(contested),
                    "provenance": "deterministically_derived",
                }
            )
            previous.append(event_id)
    return tuple(history)


def _coverage_report(
    events: Sequence[ElectionEventArea],
    candidates: Sequence[Mapping[str, object]],
    catalogue: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Audit coverage and missingness without treating unavailable rows as zero."""

    candidate_by_event = Counter(str(row["election_id"]) for row in candidates)
    missing_fields_by_event: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in candidates:
        event_id = str(row["election_id"])
        for field_name in row.get("source_missing_fields", []):
            missing_fields_by_event[event_id][str(field_name)] += 1
    event_rows = []
    for event_id, event_group in sorted(
        ((event_id, [item for item in events if item.election_id == event_id]) for event_id in {item.election_id for item in events}),
        key=lambda item: (item[1][0].election_date, item[0]),
    ):
        event = event_group[0]
        by_election = event.election_type == "by-election"
        event_rows.append(
            {
                "election_id": event_id,
                "election_type": event.election_type,
                "election_date": event.election_date,
                "area_count": len(event_group),
                "candidate_row_count": (
                    candidate_by_event.get(event_id)
                    if event.candidate_row_count is not None
                    else None
                ),
                "source_coverage": event.source_coverage,
                "missing_election": False,
                "missing_areas": [],
                "missing_candidates": (
                    ["official_candidate_results_not_retrieved"]
                    if by_election and event.candidate_row_count is None
                    else []
                ),
                "missing_fields": (
                    {"candidate_results": "unavailable"}
                    if by_election and event.candidate_row_count is None
                    else dict(sorted(missing_fields_by_event[event_id].items()))
                ),
                "source_url": event.source_url,
            }
        )
    expected_ids = set(AUDITED_ELECTION_INPUTS) | {str(row["election_id"]) for row in catalogue}
    represented_ids = {event.election_id for event in events}
    return {
        "summary": {
            "events_required": len(expected_ids),
            "events_represented": len(represented_ids),
            "principal_elections": len(
                {
                    event.election_id
                    for event in events
                    if event.election_type == "principal_election"
                }
            ),
            "by_elections_catalogued": len(catalogue),
            "by_elections_with_candidate_rows": sum(
                candidate_by_event.get(str(row["election_id"]), 0) > 0 for row in catalogue
            ),
            "missing_elections": sorted(expected_ids - represented_ids),
            "raw_candidate_rows_preserved": len(candidates),
        },
        "events": event_rows,
    }


def build_election_history(
    *,
    catalogue_path: str | Path = DEFAULT_BY_ELECTION_CATALOGUE_PATH,
    direct_mapping_path: str | Path = DEFAULT_DIRECT_MAPPING_PATH,
    party_lookup: Mapping[str, PartyLookupEntry] | None = None,
) -> dict[str, object]:
    """Build the requested event, chronology and enrichment outputs from evidence."""

    configurations = _configuration_by_id()
    direct_mappings = _direct_mapping_index(direct_mapping_path)
    event_areas: list[ElectionEventArea] = []
    raw_candidates: list[dict[str, object]] = []
    source_inputs = []
    for election_id, input_paths in AUDITED_ELECTION_INPUTS.items():
        configuration = configurations[election_id]
        audit_path = Path(input_paths["audit_path"])
        audit = _load_audit(audit_path)
        areas, candidates = _principal_event_areas(configuration, audit, direct_mappings)
        event_areas.extend(areas)
        raw_candidates.extend(candidates)
        source_inputs.append(str(audit_path))
    catalogue = load_by_election_catalogue(catalogue_path)
    by_election_areas, by_election_candidates = _by_election_areas(
        catalogue,
        by_election_records_by_id(),
    )
    event_areas.extend(by_election_areas)
    raw_candidates.extend(by_election_candidates)
    # The timeline names both by-election inputs explicitly: the archive
    # catalogue proves the event, while the results register proves only the
    # candidate rows that were actually available from an official page.
    source_inputs.extend((str(Path(catalogue_path)), str(BY_ELECTION_RESULTS_PATH)))
    standardised_candidates = _standardise_party_rows(
        raw_candidates,
        party_lookup if party_lookup is not None else load_party_lookup(),
    )
    chronology = build_chronology(event_areas)
    enrichment = {
        "area_event_enrichment": _area_enrichment(event_areas, standardised_candidates),
        "candidate_appearance_history": [
            {
                "candidate_result_id": row["candidate_result_id"],
                "candidate_name": row["candidate_name"],
                "election_id": row["election_id"],
                "candidate_identity_status": row["candidate_identity_status"],
                "candidate_appeared_before": row["candidate_appeared_before"],
                "previous_election_events_contested": row["previous_election_events_contested"],
                "previous_parties_contested": row["previous_parties_contested"],
                "provenance": row["candidate_history_provenance"],
            }
            for row in standardised_candidates
        ],
        "party_history": _party_history(standardised_candidates),
        "blocked_features": list(BLOCKED_COMPARISON_FIELDS),
        "blocked_feature_policy": (
            "No previous winner, prior vote share, vote-share change, swing, gain/loss, "
            "incumbency or predecessor transfer is calculated in this layer."
        ),
    }
    return {
        "schema_version": "1.0",
        "scope": "Election event timeline and baseline preparation only; no prediction feature generation.",
        "source_inputs": source_inputs,
        "election_events": [asdict(event) for event in sorted(event_areas, key=lambda item: (item.election_date, item.election_id, item.area_id))],
        "canonical_candidate_results": list(standardised_candidates),
        "coverage_report": _coverage_report(event_areas, standardised_candidates, catalogue),
        "election_chronology": list(chronology),
        "safe_enrichment": enrichment,
        "provenance_rules": {
            "source_reported": "Published values or official archive event evidence.",
            "deterministically_derived": "Counts, chronology and party appearance history derived without changing source values.",
            "manually_confirmed": "Approved party lookup mapping only.",
            "unavailable": "Blocked or unsupported value; retained as null rather than inferred.",
        },
    }


def event_coverage_markdown(coverage: Mapping[str, object]) -> str:
    """Render a concise event-coverage report for human audit."""

    summary = coverage["summary"]
    events = coverage["events"]
    assert isinstance(summary, Mapping) and isinstance(events, list)
    lines = [
        "# Surrey Election Event Coverage Report",
        "",
        f"- Events required: {summary['events_required']}",
        f"- Events represented: {summary['events_represented']}",
        f"- By-elections catalogued from official archive evidence: {summary['by_elections_catalogued']}",
        f"- By-elections with candidate result rows: {summary['by_elections_with_candidate_rows']}",
        f"- Missing election events: {', '.join(summary['missing_elections']) or 'None'}",
        "",
        "## Event coverage",
        "",
        "| Election ID | Type | Date | Areas | Candidate rows | Source coverage | Missing candidates | Missing fields |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for event in events:
        candidate_count = event["candidate_row_count"]
        lines.append(
            "| {id} | {type} | {date} | {areas} | {candidates} | {source} | {missing} | {fields} |".format(
                id=event["election_id"],
                type=event["election_type"],
                date=event["election_date"],
                areas=event["area_count"],
                candidates=candidate_count if candidate_count is not None else "NULL",
                source=event["source_coverage"],
                missing="yes" if event["missing_candidates"] else "no",
                fields=", ".join(event["missing_fields"]) if isinstance(event["missing_fields"], list) else "; ".join(
                    f"{field}: {value}" for field, value in event["missing_fields"].items()
                )
                or "none",
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "By-election events are separate timeline records with official archive evidence. Candidate rows are included only for events with separately verified official candidate-result evidence; other events remain NULL/unavailable and no zero-row result is created.",
            "",
        ]
    )
    return "\n".join(lines)


def data_dictionary_markdown() -> str:
    """Document source, derived and deliberately blocked history-layer fields."""

    rows = [
        ("election_events.election_id", "Canonical event identifier", "source reported / deterministically derived", "Never merged across events."),
        ("election_events.candidate_row_count", "Published candidate rows available for an event", "deterministically derived", "NULL for catalogued by-elections without verified candidate-result evidence."),
        ("canonical_candidate_results.original_party_name", "Exact published party wording", "source reported", "Never overwritten by standardisation."),
        ("canonical_candidate_results.standardised_party_name", "Reviewed lookup label", "manually confirmed", "NULL when no approved lookup exists; Reform UK and UKIP stay separate."),
        ("election_chronology.previous_election_event_id", "Prior event in the same valid geographic identity", "deterministically derived", "NULL for unavailable mappings or same-date ambiguity."),
        ("safe_enrichment.candidate_appeared_before", "Candidate appearance history", "unavailable", "No name-only matching; explicit identity evidence is required."),
        ("safe_enrichment.party_history", "Party appearance and previous contests", "deterministically derived", "Uses approved standard-party labels only."),
        ("safe_enrichment.number_of_candidates", "Candidate count in published candidate-result evidence", "deterministically derived", "NULL when candidate rows are unavailable."),
        ("safe_enrichment.previous_winner", "Prior winner", "unavailable", "Blocked pending approved geographic comparison rules."),
        ("safe_enrichment.vote_share_change", "Change in party or candidate vote share", "unavailable", "Blocked; no geographic redistribution or comparison is performed."),
        ("safe_enrichment.incumbency", "Incumbency or predecessor transfer", "unavailable", "Blocked; no candidate history crosses partial or unresolved mappings."),
    ]
    lines = [
        "# Election Event Timeline and Baseline Preparation Data Dictionary",
        "",
        "| Field | Meaning | Provenance | Missing/blocked rule |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(f"| {field} | {meaning} | {provenance} | {rule} |" for field, meaning, provenance, rule in rows)
    lines.extend(
        [
            "",
            "Official source values are never overwritten. `source_reported`, `deterministically_derived`, `manually_confirmed` and `unavailable` are distinct provenance states. Partial crosswalk, not-comparable and requires-review geographic rows cannot generate chronology links, candidate history, incumbency, previous winners or vote comparisons.",
            "",
        ]
    )
    return "\n".join(lines)
