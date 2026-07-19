"""Add pre-election participation and incumbency fields to fundamentals rows.

The election extractor has already classified candidate history, incumbency
and approved local party history.  This module converts those audited records
to the election-area-party unit used by the fundamentals table and preserves
Unknown whenever the available evidence cannot support Yes or No.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from no_news_baseline.electoral_fundamentals_schema import validate_unique_row_keys


def add_participation_features(
    fundamentals_rows: Iterable[Mapping[str, object]],
    party_features: Iterable[Mapping[str, object]],
    candidate_results: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Add six pre-election candidate, party and incumbency predictors.

    Candidate-level evidence is aggregated within each target
    election-area-party row. Party-level history continues to use the
    extractor records linked to that row, so this stage does not create a new
    historical-area matching rule.
    """

    rows = tuple(fundamentals_rows)
    # Stable source IDs reconnect each fundamentals row to the exact extractor
    # records used to build it. Candidate grouping supplies the people who are
    # standing for that party in the target contest.
    source_by_id = _index_party_features(party_features)
    candidates_by_party = _group_candidates_by_target_party(candidate_results)

    completed: list[dict[str, object]] = []
    for row in rows:
        source_rows = _source_rows_for_index_row(row, source_by_id)
        candidate_key = (
            str(row["election_id"]),
            str(row["area_id"]),
            str(row["standard_party_name"]),
        )
        candidates = candidates_by_party.get(candidate_key, ())
        if not candidates:
            raise ValueError(f"Fundamentals row has no target candidates: {candidate_key!r}.")

        # The row index may consolidate several Independent party-contest
        # records. Summing their declared counts gives the expected number of
        # people represented by the final standardised-party row.
        expected_candidate_count = sum(
            _positive_int(source.get("candidate_count_for_party"))
            for source in source_rows
        )
        if len(candidates) != expected_candidate_count:
            raise ValueError("Target candidate count disagrees with party features.")

        enriched = dict(row)
        enriched.update(
            _participation_features_for_row(
                row=row,
                source_rows=source_rows,
                candidates=candidates,
            )
        )
        completed.append(enriched)

    # Adding predictors must not change the declared observation unit or create
    # a second row for the same election, area and standardised party.
    validate_unique_row_keys(completed)
    return tuple(completed)


def _participation_features_for_row(
    *,
    row: Mapping[str, object],
    source_rows: Sequence[Mapping[str, object]],
    candidates: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build the six participation predictors for one party-level target row."""

    # These two fields describe whether at least one current candidate has the
    # relevant verified history. Unknown is retained unless all candidates have
    # sufficient evidence for a definite No.
    candidate_previously_stood = _aggregate_optional_booleans(
        candidate.get("candidate_previously_stood") for candidate in candidates
    )
    incumbent_candidate_present = _aggregate_yes_no_values(
        candidate.get("incumbent_candidate_yes_no") for candidate in candidates
    )

    # Confirm that the candidate-level aggregation agrees with the separately
    # released party-contest field. A disagreement would indicate that the two
    # extractor contracts no longer describe the same target candidates.
    released_incumbent_candidate = _aggregate_yes_no_values(
        source.get("incumbent_candidate_any_yes_no") for source in source_rows
    )
    if incumbent_candidate_present != released_incumbent_candidate:
        raise ValueError("Candidate incumbency disagrees with party-feature release.")

    standard_party_name = str(row["standard_party_name"])
    if standard_party_name == "Independent":
        # Independent is not one continuing party identity. Candidate history
        # remains usable because it refers to verified people, while party-level
        # continuity, party incumbency and new-party status are not applicable.
        incumbent_party = None
        party_previously_stood = None
        first_party_appearance = None
        new_party_indicator = None
    else:
        # Non-independent parties have a reviewed continuing standard identity,
        # so the extractor's approved party-level history can be retained.
        incumbent_party = _shared_yes_no_value(source_rows, "incumbent_party_yes_no")
        party_previously_stood = _shared_optional_boolean(
            source_rows, "party_previously_contested"
        )
        first_party_appearance = _shared_optional_boolean(
            source_rows, "first_appearance_of_party_in_area"
        )
        _validate_party_history_pair(
            party_previously_stood, first_party_appearance
        )
        new_party_indicator = _new_party_indicator(source_rows)

    return {
        "incumbent_party": incumbent_party,
        "incumbent_candidate_present": incumbent_candidate_present,
        "candidate_previously_stood": candidate_previously_stood,
        "party_previously_stood": party_previously_stood,
        "first_party_appearance_in_area": first_party_appearance,
        "new_party_indicator": new_party_indicator,
    }


def _aggregate_optional_booleans(values: Iterable[object]) -> bool | None:
    """Return True if any candidate is Yes and False only when all are No."""

    collected = tuple(values)
    if not collected:
        raise ValueError("Cannot aggregate an empty candidate group.")
    if any(value is True for value in collected):
        return True
    if all(value is False for value in collected):
        return False
    if any(value not in {True, False, None} for value in collected):
        raise ValueError("Candidate history must be True, False or NULL.")
    return None


def _aggregate_yes_no_values(values: Iterable[object]) -> bool | None:
    """Convert candidate Yes/No/Unknown evidence to a party-level tri-state."""

    collected = tuple(values)
    if not collected:
        raise ValueError("Cannot aggregate an empty Yes/No candidate group.")
    if any(value == "Yes" for value in collected):
        return True
    if all(value == "No" for value in collected):
        return False
    if any(value not in {"Yes", "No", "Unknown"} for value in collected):
        raise ValueError("Incumbency value must be Yes, No or Unknown.")
    return None


def _shared_yes_no_value(
    rows: Sequence[Mapping[str, object]], field: str
) -> bool | None:
    """Return one agreed extractor Yes/No/Unknown value as a Python tri-state."""

    value = _shared_value(rows, field)
    if value == "Yes":
        return True
    if value == "No":
        return False
    if value == "Unknown":
        return None
    raise ValueError(f"{field} must be Yes, No or Unknown.")


def _shared_optional_boolean(
    rows: Sequence[Mapping[str, object]], field: str
) -> bool | None:
    """Return one agreed True/False/NULL party-history value."""

    value = _shared_value(rows, field)
    if value not in {True, False, None}:
        raise ValueError(f"{field} must be True, False or NULL.")
    return value  # type: ignore[return-value]


def _validate_party_history_pair(
    previously_stood: bool | None, first_appearance: bool | None
) -> None:
    """Check that the two local party-history fields express opposite states."""

    if (previously_stood is None) != (first_appearance is None):
        raise ValueError("Party history fields have inconsistent missingness.")
    if previously_stood is not None and previously_stood == first_appearance:
        raise ValueError("Party history and first appearance must be opposites.")


def _new_party_indicator(
    source_rows: Sequence[Mapping[str, object]],
) -> bool | None:
    """Identify a reviewed emerging party without inferring its founding date."""

    # Do not use the first year observed in the completed dataset: that value
    # describes data coverage and is not evidence of a party's founding date.
    category = _shared_value(source_rows, "party_category")
    if category == "emerging":
        return True
    if category in {"established", "local"}:
        return False
    if category in {"independent", None}:
        return None
    raise ValueError(f"Unsupported party category: {category!r}.")


def _group_candidates_by_target_party(
    candidates: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str, str], tuple[Mapping[str, object], ...]]:
    """Group current candidates by the fundamentals election-area-party key."""

    grouped: defaultdict[
        tuple[str, str, str], list[Mapping[str, object]]
    ] = defaultdict(list)
    for candidate in candidates:
        key = (
            str(candidate.get("election_id", "")),
            str(candidate.get("division_id", "")),
            str(candidate.get("standard_party_name", "")),
        )
        if not all(key):
            raise ValueError("Candidate has an incomplete election-area-party key.")
        grouped[key].append(candidate)
    return {key: tuple(rows) for key, rows in grouped.items()}


def _index_party_features(
    party_features: Iterable[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    """Index predictor-side extractor records by stable party-contest ID."""

    indexed: dict[str, Mapping[str, object]] = {}
    for feature in party_features:
        contest_id = str(feature.get("party_contest_id", ""))
        if not contest_id or contest_id in indexed:
            raise ValueError(f"Missing or duplicate party_contest_id: {contest_id!r}.")
        indexed[contest_id] = feature
    return indexed


def _source_rows_for_index_row(
    row: Mapping[str, object],
    source_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Return the exact party-feature records listed by one fundamentals row."""

    source_ids = row.get("source_party_contest_ids")
    if not isinstance(source_ids, (tuple, list)) or not source_ids:
        raise ValueError("Fundamentals row has no source party-contest IDs.")
    try:
        return tuple(source_by_id[str(source_id)] for source_id in source_ids)
    except KeyError as error:
        raise ValueError(f"Unknown source party-contest ID: {error}.") from error


def _shared_value(rows: Sequence[Mapping[str, object]], field: str) -> object:
    """Return one field only when every source record agrees."""

    values = {row.get(field) for row in rows}
    if len(values) != 1:
        raise ValueError(f"Grouped party records disagree on {field}: {values!r}.")
    return values.pop()


def _positive_int(value: object) -> int:
    """Return a positive integer candidate count from a party-feature record."""

    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("candidate_count_for_party must be a positive integer.")
    return value
