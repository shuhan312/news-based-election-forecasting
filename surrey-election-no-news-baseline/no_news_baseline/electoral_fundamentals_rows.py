"""Build the basic rows of the electoral-fundamentals feature table.

Read the party-contest records produced by the election extractor and create
one row for each election, electoral area and standardised party.  When several
source records belong to the same election-area-party combination, keep their
record IDs together so the combined row can be traced back to its sources.
Historical election predictors will be added to these rows in later steps.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from no_news_baseline.electoral_fundamentals_schema import (
    IDENTIFIER_COLUMNS,
    validate_unique_row_keys,
)


# These fields are the minimum predictor-side information needed to define the
# requested observation unit.  Outcome values are intentionally absent.
REQUIRED_PARTY_CONTEST_FIELDS = (
    "party_contest_id",
    "election_id",
    "election_date",
    "division_id",
    "division_name",
    "standard_party_name",
)


def load_party_feature_rows(path: Path) -> tuple[dict[str, object], ...]:
    """Read and validate the extractor-owned predictor JSON contract."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Party-feature JSON must contain a rows list of objects.")
    for row in rows:
        missing = [
            field
            for field in REQUIRED_PARTY_CONTEST_FIELDS
            if row.get(field) is None or row.get(field) == ""
        ]
        if missing:
            raise ValueError(f"Party-feature row is missing required fields: {missing!r}.")
    return tuple(rows)


def build_fundamentals_row_index(
    party_features: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return one row per election, area and standardised party.

    The extractor can retain candidate-specific political identities, most
    notably multiple Independent candidates.  The supervisor's requested table
    is party-level, so records with the same standardised party key are grouped
    here.  Only identifiers are grouped at this stage: candidate vote shares or
    other numerical values are never summed or averaged.
    """

    grouped: dict[
        tuple[str, str, str], list[Mapping[str, object]]
    ] = defaultdict(list)
    seen_contest_ids: set[str] = set()

    for feature in party_features:
        _require_fields(feature)
        contest_id = str(feature["party_contest_id"])
        if contest_id in seen_contest_ids:
            raise ValueError(f"Duplicate source party_contest_id: {contest_id!r}.")
        seen_contest_ids.add(contest_id)
        grouped[
            (
                str(feature["election_id"]),
                str(feature["division_id"]),
                str(feature["standard_party_name"]),
            )
        ].append(feature)

    rows: list[dict[str, object]] = []
    for (election_id, area_id, party_name), source_rows in sorted(grouped.items()):
        # Values that describe the same election-area-party row must agree.
        # A conflict is treated as an upstream data-contract error rather than
        # being resolved by arbitrary first-row selection.
        election_date = _one_group_value(source_rows, "election_date")
        area_name = _one_group_value(source_rows, "division_name")
        source_ids = tuple(sorted(str(row["party_contest_id"]) for row in source_rows))
        rows.append(
            {
                "election_id": election_id,
                "election_date": election_date,
                "area_id": area_id,
                "area_name": area_name,
                "standard_party_name": party_name,
                # Construction metadata preserves which extractor rows were
                # consolidated. It is not part of the future predictor matrix.
                "source_party_contest_ids": source_ids,
                "source_party_contest_count": len(source_ids),
            }
        )

    validate_unique_row_keys(rows)
    _assert_identifier_columns_present(rows)
    return tuple(rows)


def _require_fields(row: Mapping[str, object]) -> None:
    """Check that one source record contains every field needed to build its key."""

    # Both None and an empty string mean that the record cannot be assigned to
    # a reliable election-area-party row.
    missing = [
        field
        for field in REQUIRED_PARTY_CONTEST_FIELDS
        if row.get(field) is None or row.get(field) == ""
    ]
    if missing:
        raise ValueError(f"Party-feature row is missing required fields: {missing!r}.")


def _one_group_value(rows: Sequence[Mapping[str, object]], field: str) -> object:
    """Return a field value only when all source records in the group agree."""

    # A set leaves one value when every grouped record is consistent. More than
    # one value indicates an upstream conflict that should be reviewed.
    values = {row.get(field) for row in rows}
    if len(values) != 1:
        raise ValueError(f"Grouped party records disagree on {field}: {values!r}.")
    return values.pop()


def _assert_identifier_columns_present(rows: Sequence[Mapping[str, object]]) -> None:
    """Check that every completed row follows the identifier schema."""

    for row in rows:
        # IDENTIFIER_COLUMNS is defined centrally in the schema module so this
        # construction step cannot silently produce a different table layout.
        missing = [column for column in IDENTIFIER_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"Fundamentals index is missing identifier columns: {missing!r}.")
