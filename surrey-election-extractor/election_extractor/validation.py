"""Read-only validation for extracted Surrey election result records."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from election_extractor.extraction import CandidateResultRecord, ExtractionStatus


class ValidationStatus(str, Enum):
    """Describe the outcome of a validation result or event."""

    PASSED = "Passed"
    WARNING = "Warning"
    FAILED = "Failed"
    INCOMPLETE = "Incomplete"


@dataclass(frozen=True)
class PublishedVotingSummary:
    """Store published totals used only as validation evidence."""

    # These values are comparison inputs. Validation never copies them into or
    # uses them to repair CandidateResultRecord source fields.
    source_url: str
    total_votes: int | None = None
    valid_votes: int | None = None


@dataclass(frozen=True)
class ValidationEvent:
    """Record one auditable validation rule outcome."""

    division_ward_name: str | None
    validation_rule: str
    result: ValidationStatus
    warning_message: str | None
    failed_fields: tuple[str, ...]
    source_url: str


@dataclass(frozen=True)
class ValidationResult:
    """Summarise validation for all candidate records from one result URL."""

    # One result represents one official ward/division URL, while events retain
    # the outcome of each individual validation rule for audit purposes.
    election_name: str | None
    election_year: int | None
    division_ward_name: str | None
    source_url: str
    validation_status: ValidationStatus
    fields_reviewed: tuple[str, ...]
    failed_checks: tuple[str, ...]
    warnings: tuple[str, ...]
    validation_notes: tuple[str, ...]
    missing_fields: tuple[str, ...]
    validation_timestamp: datetime
    events: tuple[ValidationEvent, ...]


FIELDS_REVIEWED = (
    "election_name",
    "election_date",
    "authority",
    "division_ward_name",
    "number_of_seats",
    "candidate_name",
    "original_party_name",
    "votes_received",
    "vote_share",
    "outcome",
    "total_votes",
    "valid_votes",
    "electorate",
    "ballot_papers_issued",
    "ballot_papers_rejected",
    "turnout",
    "extraction_status",
    "source_url",
)

# A half-percentage-point tolerance accepts whole-number published percentages
# such as 45% when the validation calculation is 44.8%.
VOTE_SHARE_TOLERANCE_PERCENTAGE_POINTS = 0.5
TURNOUT_TOLERANCE_PERCENTAGE_POINTS = 0.5


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _distinct(values: Iterable[object]) -> tuple[object, ...]:
    """Return distinct non-missing values without changing source values."""
    distinct: dict[tuple[type[object], str], object] = {}
    for value in values:
        if _is_missing(value):
            continue
        # Type is part of the key so text "40" is not silently treated as the
        # same published value as numeric 40.
        key = (type(value), str(value).casefold())
        distinct.setdefault(key, value)
    return tuple(distinct.values())


def _consensus(values: Iterable[object]) -> object | None:
    """Return a value only when all available evidence agrees."""
    distinct = _distinct(values)
    return distinct[0] if len(distinct) == 1 else None


def _year_from_metadata(election_name: str | None, election_date: str | None) -> int | None:
    # A year is returned only when the available election name and date agree.
    # Conflicting years remain unresolved rather than selecting the first one.
    years = {
        int(match.group(0))
        for value in (election_name, election_date)
        if value
        for match in re.finditer(r"\b(?:19|20)\d{2}\b", value)
    }
    return next(iter(years)) if len(years) == 1 else None


def _conflict_note(field_name: str, values: Sequence[object]) -> str:
    published = ", ".join(repr(value) for value in values)
    return f"Conflicting published values for {field_name}: {published}."


def _event(
    ward: str | None,
    rule: str,
    result: ValidationStatus,
    source_url: str,
    message: str | None = None,
    failed_fields: Sequence[str] = (),
) -> ValidationEvent:
    return ValidationEvent(
        division_ward_name=ward,
        validation_rule=rule,
        result=result,
        warning_message=message,
        failed_fields=tuple(failed_fields),
        source_url=source_url,
    )


def _group_by_source_url(
    records: Sequence[CandidateResultRecord],
) -> dict[str, list[CandidateResultRecord]]:
    # Exact source-URL grouping prevents candidates from different official
    # ward/division result pages from being validated together.
    groups: dict[str, list[CandidateResultRecord]] = {}
    for record in records:
        groups.setdefault(record.source_url, []).append(record)
    return groups


def _summaries_by_source_url(
    summaries: Sequence[PublishedVotingSummary],
) -> dict[str, list[PublishedVotingSummary]]:
    groups: dict[str, list[PublishedVotingSummary]] = {}
    for summary in summaries:
        groups.setdefault(summary.source_url, []).append(summary)
    return groups


def _candidate_missing_fields(
    records: Sequence[CandidateResultRecord],
) -> set[str]:
    missing = set()
    candidate_fields = {
        "candidate_name": "candidate_name",
        "original_party_name": "party",
        "votes_received": "votes",
        "vote_share": "vote_share",
        "outcome": "outcome",
    }
    for index, record in enumerate(records, start=1):
        for attribute, label in candidate_fields.items():
            if _is_missing(getattr(record, attribute)):
                missing.add(f"candidate[{index}].{label}")
        # Respect missing fields already recorded by extraction, even if a
        # caller provides a record whose values and extraction audit disagree.
        for field_name in record.missing_fields:
            missing.add(f"extraction[{index}].{field_name}")
    return missing


def _summary_missing_fields(
    records: Sequence[CandidateResultRecord],
    summaries: Sequence[PublishedVotingSummary],
) -> set[str]:
    missing = set()
    # Election-summary fields are repeated across candidate rows by extraction.
    # They are missing at area level only when no candidate row supplies a value.
    record_fields = (
        "number_of_seats",
        "electorate",
        "ballot_papers_issued",
        "ballot_papers_rejected",
        "turnout",
    )
    for field_name in record_fields:
        if not any(not _is_missing(getattr(record, field_name)) for record in records):
            missing.add(f"summary.{field_name}")
    if not any(not _is_missing(summary.total_votes) for summary in summaries):
        missing.add("summary.total_votes")
    return missing


def _conflict_events(
    records: Sequence[CandidateResultRecord],
    summaries: Sequence[PublishedVotingSummary],
    ward: str | None,
    source_url: str,
) -> tuple[list[ValidationEvent], list[str]]:
    events = []
    notes = []
    # Shared values should agree across every candidate from the same source URL.
    # Every conflicting published value is kept in the note for later review.
    record_fields = (
        "election_name",
        "election_date",
        "authority",
        "division_ward_name",
        "number_of_seats",
        "electorate",
        "ballot_papers_issued",
        "ballot_papers_rejected",
        "turnout",
    )
    for field_name in record_fields:
        values = _distinct(getattr(record, field_name) for record in records)
        if len(values) <= 1:
            continue
        note = _conflict_note(field_name, values)
        notes.append(note)
        events.append(
            _event(
                ward,
                "conflict_check",
                ValidationStatus.WARNING,
                source_url,
                note,
                (field_name,),
            )
        )

    for field_name in ("total_votes", "valid_votes"):
        values = _distinct(getattr(summary, field_name) for summary in summaries)
        if len(values) <= 1:
            continue
        note = _conflict_note(field_name, values)
        notes.append(note)
        events.append(
            _event(
                ward,
                "conflict_check",
                ValidationStatus.WARNING,
                source_url,
                note,
                (field_name,),
            )
        )
    return events, notes


def _indexed_evidence_conflict_events(
    records: Sequence[CandidateResultRecord],
    ward: str | None,
    source_url: str,
) -> tuple[list[ValidationEvent], list[str]]:
    """Expose extraction conflicts as validation warnings without repairing data."""
    events = []
    notes = []
    seen = set()
    for index, record in enumerate(records, start=1):
        for conflict in record.conflicts:
            key = (index, conflict.field_name, conflict.published_values)
            if key in seen:
                continue
            seen.add(key)
            values = ", ".join(repr(value) for value in conflict.published_values)
            sources = ", ".join(
                dict.fromkeys(item.source_url for item in conflict.evidence)
            )
            note = (
                f"Conflicting indexed evidence for candidate {index} "
                f"{conflict.field_name}: {values}. Sources: {sources}."
            )
            notes.append(note)
            events.append(
                _event(
                    ward,
                    "indexed_evidence_conflict",
                    ValidationStatus.WARNING,
                    source_url,
                    note,
                    (f"candidate[{index}].{conflict.field_name}",),
                )
            )
    return events, notes


def _candidate_vote_total_event(
    records: Sequence[CandidateResultRecord],
    summaries: Sequence[PublishedVotingSummary],
    ward: str | None,
    source_url: str,
) -> tuple[ValidationEvent, str | None]:
    votes = [record.votes_received for record in records]
    valid_vote_values = _distinct(summary.valid_votes for summary in summaries)
    total_vote_values = _distinct(summary.total_votes for summary in summaries)
    if len(valid_vote_values) > 1 or len(total_vote_values) > 1:
        message = "Candidate vote total was not calculated because published voting totals conflict."
        return (
            _event(
                ward,
                "candidate_vote_total",
                ValidationStatus.WARNING,
                source_url,
                message,
                ("total_votes", "valid_votes"),
            ),
            message,
        )
    # Candidate votes normally sum to valid votes. When valid votes are not
    # published, total votes are used as the available comparison value.
    valid_votes = _consensus(summary.valid_votes for summary in summaries)
    total_votes = _consensus(summary.total_votes for summary in summaries)
    published_total = valid_votes if valid_votes is not None else total_votes
    published_label = "valid votes" if valid_votes is not None else "total votes"

    if not records or any(value is None for value in votes) or published_total is None:
        message = "Candidate vote total could not be checked because required values are missing or conflicting."
        return (
            _event(
                ward,
                "candidate_vote_total",
                ValidationStatus.INCOMPLETE,
                source_url,
                message,
                ("votes_received", published_label.replace(" ", "_")),
            ),
            message,
        )

    # This calculated total is validation-only and never replaces any published
    # candidate or summary value.
    candidate_total = sum(value for value in votes if value is not None)
    note = f"Candidate vote total {candidate_total} compared with published {published_label} {published_total}."
    if candidate_total == published_total:
        return (
            _event(
                ward,
                "candidate_vote_total",
                ValidationStatus.PASSED,
                source_url,
            ),
            note,
        )

    message = "Candidate vote totals do not match the published voting summary."
    return (
        _event(
            ward,
            "candidate_vote_total",
            ValidationStatus.WARNING,
            source_url,
            message,
            ("votes_received", published_label.replace(" ", "_")),
        ),
        f"{note} {message}",
    )


def _vote_share_events(
    records: Sequence[CandidateResultRecord],
    summaries: Sequence[PublishedVotingSummary],
    ward: str | None,
    source_url: str,
) -> tuple[list[ValidationEvent], list[str]]:
    events = []
    notes = []
    valid_vote_values = _distinct(summary.valid_votes for summary in summaries)
    total_vote_values = _distinct(summary.total_votes for summary in summaries)
    totals_conflict = len(valid_vote_values) > 1 or len(total_vote_values) > 1
    valid_votes = _consensus(summary.valid_votes for summary in summaries)
    total_votes = _consensus(summary.total_votes for summary in summaries)
    denominator = valid_votes if valid_votes is not None else total_votes

    for index, record in enumerate(records, start=1):
        field = f"candidate[{index}].vote_share"
        if totals_conflict:
            message = f"Vote share was not calculated for candidate {index} because published voting totals conflict."
            events.append(
                _event(
                    ward,
                    "vote_share",
                    ValidationStatus.WARNING,
                    source_url,
                    message,
                    (field, "total_votes", "valid_votes"),
                )
            )
            notes.append(message)
            continue
        if record.votes_received is None or record.vote_share is None or not denominator:
            message = f"Vote share could not be checked for candidate {index} because required values are missing or conflicting."
            events.append(
                _event(
                    ward,
                    "vote_share",
                    ValidationStatus.INCOMPLETE,
                    source_url,
                    message,
                    (field,),
                )
            )
            notes.append(message)
            continue

        # Preserve the published percentage on the record; calculated is used
        # only to measure whether the difference is within rounding tolerance.
        calculated = record.votes_received / denominator * 100
        difference = abs(record.vote_share - calculated)
        note = (
            f"Candidate {index} published vote share {record.vote_share}% compared with "
            f"calculated {calculated:.4f}% for validation only."
        )
        notes.append(note)
        if difference <= VOTE_SHARE_TOLERANCE_PERCENTAGE_POINTS:
            events.append(
                _event(
                    ward,
                    "vote_share",
                    ValidationStatus.PASSED,
                    source_url,
                )
            )
        else:
            events.append(
                _event(
                    ward,
                    "vote_share",
                    ValidationStatus.FAILED,
                    source_url,
                    "Published vote share is inconsistent with candidate votes and the published total.",
                    (field,),
                )
            )
    return events, notes


def _turnout_event(
    records: Sequence[CandidateResultRecord],
    ward: str | None,
    source_url: str,
) -> tuple[ValidationEvent, str | None]:
    turnout_values = _distinct(record.turnout for record in records)
    electorate_values = _distinct(record.electorate for record in records)
    issued_values = _distinct(record.ballot_papers_issued for record in records)
    if any(len(values) > 1 for values in (turnout_values, electorate_values, issued_values)):
        message = "Turnout was not calculated because published turnout values conflict."
        return (
            _event(
                ward,
                "turnout",
                ValidationStatus.WARNING,
                source_url,
                message,
                ("turnout", "electorate", "ballot_papers_issued"),
            ),
            message,
        )
    turnout = _consensus(record.turnout for record in records)
    electorate = _consensus(record.electorate for record in records)
    issued = _consensus(record.ballot_papers_issued for record in records)
    if turnout is None or electorate is None or issued is None or not electorate:
        message = "Turnout could not be checked because required values are missing or conflicting."
        return (
            _event(
                ward,
                "turnout",
                ValidationStatus.INCOMPLETE,
                source_url,
                message,
                ("turnout", "electorate", "ballot_papers_issued"),
            ),
            message,
        )

    # Turnout is checked against issued ballots divided by electorate, but the
    # calculated value is recorded only in notes and never written to the record.
    calculated = issued / electorate * 100
    difference = abs(float(turnout) - calculated)
    note = (
        f"Published turnout {turnout}% compared with calculated {calculated:.4f}% "
        "for validation only."
    )
    if difference <= TURNOUT_TOLERANCE_PERCENTAGE_POINTS:
        return (
            _event(ward, "turnout", ValidationStatus.PASSED, source_url),
            note,
        )
    return (
        _event(
            ward,
            "turnout",
            ValidationStatus.FAILED,
            source_url,
            "Published turnout is inconsistent with ballot papers issued and electorate.",
            ("turnout",),
        ),
        note,
    )


def _extraction_status_event(
    records: Sequence[CandidateResultRecord],
    ward: str | None,
    source_url: str,
) -> ValidationEvent:
    statuses = {record.extraction_status for record in records}
    # Validation adds evidence about reliability; it is not allowed to upgrade
    # an extraction that was already incomplete or failed.
    if ExtractionStatus.SEARCH_FAILED in statuses:
        return _event(
            ward,
            "extraction_status",
            ValidationStatus.FAILED,
            source_url,
            "A failed extraction cannot be upgraded by validation.",
            ("extraction_status",),
        )
    if statuses & {ExtractionStatus.INCOMPLETE, ExtractionStatus.NO_EVIDENCE}:
        return _event(
            ward,
            "extraction_status",
            ValidationStatus.INCOMPLETE,
            source_url,
            "An incomplete extraction remains incomplete after validation.",
            ("extraction_status",),
        )
    return _event(ward, "extraction_status", ValidationStatus.PASSED, source_url)


def _overall_status(
    events: Sequence[ValidationEvent],
    missing_fields: Sequence[str],
) -> ValidationStatus:
    results = {event.result for event in events}
    # Precedence is deliberate: a failed consistency check is strongest, missing
    # required data remains incomplete, and non-blocking conflicts are warnings.
    if ValidationStatus.FAILED in results:
        return ValidationStatus.FAILED
    if missing_fields or ValidationStatus.INCOMPLETE in results:
        return ValidationStatus.INCOMPLETE
    if ValidationStatus.WARNING in results:
        return ValidationStatus.WARNING
    return ValidationStatus.PASSED


def validate_election_results(
    records: Sequence[CandidateResultRecord],
    summaries: Sequence[PublishedVotingSummary] = (),
    *,
    validation_timestamp: datetime | None = None,
) -> tuple[ValidationResult, ...]:
    """Validate records by exact result URL without modifying source values."""
    timestamp = validation_timestamp or datetime.now(timezone.utc)
    record_groups = _group_by_source_url(records)
    summary_groups = _summaries_by_source_url(summaries)
    source_urls = sorted(set(record_groups) | set(summary_groups))
    results = []

    for source_url in source_urls:
        # All calculations below use local variables and immutable input records.
        # The original extraction output is never mutated or replaced.
        area_records = record_groups.get(source_url, [])
        area_summaries = summary_groups.get(source_url, [])
        election_name = _consensus(record.election_name for record in area_records)
        election_date = _consensus(record.election_date for record in area_records)
        ward = _consensus(record.division_ward_name for record in area_records)
        election_name_text = election_name if isinstance(election_name, str) else None
        election_date_text = election_date if isinstance(election_date, str) else None
        ward_text = ward if isinstance(ward, str) else None

        missing = _candidate_missing_fields(area_records)
        missing.update(_summary_missing_fields(area_records, area_summaries))
        events, notes = _conflict_events(
            area_records,
            area_summaries,
            ward_text,
            source_url,
        )
        indexed_conflict_events, indexed_conflict_notes = (
            _indexed_evidence_conflict_events(
                area_records,
                ward_text,
                source_url,
            )
        )
        events.extend(indexed_conflict_events)
        notes.extend(indexed_conflict_notes)

        missing_message = None
        if missing:
            missing_message = "Required candidate or voting-summary fields are missing."
            events.append(
                _event(
                    ward_text,
                    "missing_data",
                    ValidationStatus.INCOMPLETE,
                    source_url,
                    missing_message,
                    sorted(missing),
                )
            )
        else:
            events.append(
                _event(
                    ward_text,
                    "missing_data",
                    ValidationStatus.PASSED,
                    source_url,
                )
            )

        vote_total_event, vote_total_note = _candidate_vote_total_event(
            area_records,
            area_summaries,
            ward_text,
            source_url,
        )
        events.append(vote_total_event)
        if vote_total_note:
            notes.append(vote_total_note)

        vote_share_events, vote_share_notes = _vote_share_events(
            area_records,
            area_summaries,
            ward_text,
            source_url,
        )
        events.extend(vote_share_events)
        notes.extend(vote_share_notes)

        turnout_event, turnout_note = _turnout_event(
            area_records,
            ward_text,
            source_url,
        )
        events.append(turnout_event)
        if turnout_note:
            notes.append(turnout_note)

        extraction_event = _extraction_status_event(
            area_records,
            ward_text,
            source_url,
        )
        events.append(extraction_event)

        # Keep human-readable summaries and structured events together so the
        # same result supports both review and machine-readable audit.
        warnings = tuple(
            event.warning_message
            for event in events
            if event.result is ValidationStatus.WARNING and event.warning_message
        )
        failed_checks = tuple(
            dict.fromkeys(
                event.validation_rule
                for event in events
                if event.result is ValidationStatus.FAILED
            )
        )
        results.append(
            ValidationResult(
                election_name=election_name_text,
                election_year=_year_from_metadata(
                    election_name_text,
                    election_date_text,
                ),
                division_ward_name=ward_text,
                source_url=source_url,
                validation_status=_overall_status(events, sorted(missing)),
                fields_reviewed=FIELDS_REVIEWED,
                failed_checks=failed_checks,
                warnings=warnings,
                validation_notes=tuple(notes),
                missing_fields=tuple(sorted(missing)),
                validation_timestamp=timestamp,
                events=tuple(events),
            )
        )

    return tuple(results)
