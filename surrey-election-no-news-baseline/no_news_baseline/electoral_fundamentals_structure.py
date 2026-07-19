"""Add pre-election contest structure to the fundamentals table.

The extractor publishes the election type, approved seat count and number of
candidates before any target outcome is joined.  This module carries those
three values to the election-area-party row and checks that every party record
within the same contest describes the same structure.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from no_news_baseline.electoral_fundamentals_schema import validate_unique_row_keys


def add_contest_structure_features(
    fundamentals_rows: Iterable[Mapping[str, object]],
    party_features: Iterable[Mapping[str, object]],
    candidate_results: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Add election type, seats and candidate count without using outcomes."""

    rows = tuple(fundamentals_rows)
    features_by_area = _group_party_features_by_area(party_features)
    candidate_counts = _count_candidates_by_area(candidate_results)

    completed: list[dict[str, object]] = []
    for row in rows:
        area_key = (str(row["election_id"]), str(row["area_id"]))
        area_features = features_by_area.get(area_key)
        if not area_features:
            raise ValueError(f"Fundamentals area has no party features: {area_key!r}.")

        # Election type and seats describe the whole contest, so disagreement
        # between parties is an upstream data error rather than something that
        # should be resolved by choosing the first record.
        election_type = _one_area_value(area_features, "election_type")
        number_of_seats = _positive_int(
            _one_area_value(area_features, "analysis_number_of_seats"),
            "analysis_number_of_seats",
        )

        # Candidate count is calculated from the complete target candidate
        # table, then reconciled against the sum declared by all party records.
        # It is the ballot size known before polling, not a result-derived value.
        number_of_candidates = candidate_counts.get(area_key)
        if number_of_candidates is None:
            raise ValueError(f"Fundamentals area has no candidate rows: {area_key!r}.")
        declared_count = sum(
            _positive_int(feature.get("candidate_count_for_party"), "candidate_count_for_party")
            for feature in area_features
        )
        if number_of_candidates != declared_count:
            raise ValueError(
                "Candidate Results and party-feature candidate counts disagree "
                f"for {area_key!r}: {number_of_candidates} != {declared_count}."
            )

        enriched = dict(row)
        enriched.update(
            {
                "election_type": _required_text(election_type, "election_type"),
                "number_of_seats": number_of_seats,
                "number_of_candidates": number_of_candidates,
            }
        )
        completed.append(enriched)

    # Adding shared contest metadata must preserve exactly one row for every
    # election, area and standardised party.
    validate_unique_row_keys(completed)
    return tuple(completed)


def _group_party_features_by_area(
    party_features: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], tuple[Mapping[str, object], ...]]:
    """Group predictor-side party records by their target contest."""

    grouped: defaultdict[
        tuple[str, str], list[Mapping[str, object]]
    ] = defaultdict(list)
    seen_ids: set[str] = set()
    for feature in party_features:
        contest_id = _required_text(feature.get("party_contest_id"), "party_contest_id")
        if contest_id in seen_ids:
            raise ValueError(f"Duplicate party_contest_id: {contest_id!r}.")
        seen_ids.add(contest_id)
        key = (
            _required_text(feature.get("election_id"), "election_id"),
            _required_text(feature.get("division_id"), "division_id"),
        )
        grouped[key].append(feature)
    return {key: tuple(values) for key, values in grouped.items()}


def _count_candidates_by_area(
    candidates: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], int]:
    """Count complete target candidate rows for each election and area."""

    counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    # Candidate identifiers are stable within an election area but are not
    # globally unique across all historical elections in the master payload.
    seen_keys: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        candidate_id = _required_text(candidate.get("candidate_id"), "candidate_id")
        key = (
            _required_text(candidate.get("election_id"), "election_id"),
            _required_text(candidate.get("division_id"), "division_id"),
        )
        candidate_key = (*key, candidate_id)
        if candidate_key in seen_keys:
            raise ValueError(f"Duplicate election-area-candidate row: {candidate_key!r}.")
        seen_keys.add(candidate_key)
        counts[key] += 1
    return dict(counts)


def _one_area_value(
    rows: Sequence[Mapping[str, object]], field: str
) -> object:
    """Return a contest-level field only when all party records agree."""

    values = {row.get(field) for row in rows}
    if len(values) != 1:
        raise ValueError(f"Party records disagree on {field}: {values!r}.")
    return values.pop()


def _required_text(value: object, field: str) -> str:
    """Return a non-empty text identifier or description."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text.")
    return value.strip()


def _positive_int(value: object, field: str) -> int:
    """Return a positive integer count without accepting booleans."""

    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field} must be a positive integer.")
    return value
