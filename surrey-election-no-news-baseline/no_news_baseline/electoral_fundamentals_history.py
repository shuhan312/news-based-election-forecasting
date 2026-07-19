"""Add approved previous-election features to the fundamentals row index.

The election extractor decides which earlier election and area are comparable
with each target contest.  This module uses those approved links to retrieve
the complete earlier official result and add historical predictors to each
election-area-party row.  Every historical date is checked against the target
date before a value is released.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime

from no_news_baseline.electoral_fundamentals_schema import validate_unique_row_keys


APPROVED_GEOGRAPHIC_REFERENCE = "approved_historical_reference"


def add_previous_election_features(
    row_index: Iterable[Mapping[str, object]],
    party_features: Iterable[Mapping[str, object]],
    master_payload: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    """Return the row index with six leakage-safe historical predictors.

    The added predictors are previous party vote share, party rank, winner
    status, winning margin, turnout and days since the approved comparable
    election.  The master payload is consulted only after the extractor's
    predictor record has supplied an approved earlier-election reference.
    """

    index_rows = tuple(row_index)
    # Prepare lookup dictionaries once so every fundamentals row can retrieve
    # its source record, election, previous area, candidates and margin by ID.
    # This is both clearer and faster than repeatedly scanning the full tables.
    source_by_id = _index_party_features(party_features)
    elections = _index_elections(_payload_table(master_payload, "Elections"))
    previous_areas = _index_areas_by_name(
        _payload_table(master_payload, "Divisions and Wards")
    )
    candidates_by_area = _group_candidates_by_area(
        _payload_table(master_payload, "Candidate Results")
    )
    margins = _index_analysis_margins(
        _payload_table(master_payload, "Analysis Voting Summary")
    )

    completed: list[dict[str, object]] = []
    for row in index_rows:
        # The row index keeps every extractor record ID that contributed to a
        # party-level row. Reusing those IDs avoids a second, looser data join.
        source_rows = _source_rows_for_index_row(row, source_by_id)
        enriched = dict(row)
        enriched.update(
            _previous_features_for_row(
                row=row,
                source_rows=source_rows,
                elections=elections,
                previous_areas=previous_areas,
                candidates_by_area=candidates_by_area,
                margins=margins,
            )
        )
        completed.append(enriched)

    validate_unique_row_keys(completed)
    return tuple(completed)


def _previous_features_for_row(
    *,
    row: Mapping[str, object],
    source_rows: Sequence[Mapping[str, object]],
    elections: Mapping[str, Mapping[str, object]],
    previous_areas: Mapping[tuple[str, str], Mapping[str, object]],
    candidates_by_area: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
    margins: Mapping[tuple[str, str], object],
) -> dict[str, object]:
    """Build the historical fields for one election-area-party row."""

    reference_status = _shared_value(source_rows, "historical_reference_status")
    geographic_status = _shared_value(
        source_rows, "geographic_reference_eligibility"
    )
    previous_election_id = _shared_value(source_rows, "previous_election_id")
    previous_area_name = _shared_value(source_rows, "previous_division_name")

    # Rows without an approved predecessor remain in the table with explicit
    # provenance, while their historical predictors stay unknown.
    if geographic_status != APPROVED_GEOGRAPHIC_REFERENCE:
        if previous_election_id is not None or previous_area_name is not None:
            raise ValueError("Unapproved row contains a previous-area reference.")
        return _empty_previous_features(reference_status)

    if not isinstance(previous_election_id, str) or not isinstance(
        previous_area_name, str
    ):
        raise ValueError("Approved historical reference is incomplete.")

    target_election_id = str(row["election_id"])
    target_date = _election_date(elections, target_election_id)
    previous_date = _election_date(elections, previous_election_id)
    if previous_date >= target_date:
        raise ValueError("Historical source election must precede target election.")

    # Area-name resolution happens only inside an already approved election
    # link. The index requires the name to identify exactly one official area.
    area_key = (previous_election_id, previous_area_name)
    previous_area = previous_areas.get(area_key)
    if previous_area is None:
        raise ValueError(f"Approved previous area cannot be resolved: {area_key!r}.")
    previous_area_id = str(previous_area["division_id"])
    previous_candidates = candidates_by_area.get(
        (previous_election_id, previous_area_id), ()
    )
    if not previous_candidates:
        raise ValueError(f"Approved previous area has no candidate rows: {area_key!r}.")

    previous_turnout = _shared_value(source_rows, "analysis_previous_turnout")
    # Share, rank and winner are read from the same matched prior-party record
    # so these three fields cannot describe different parties by accident.
    previous_share, previous_rank, previous_winner = _previous_party_result(
        standard_party_name=str(row["standard_party_name"]),
        previous_candidates=previous_candidates,
    )
    # Winning margin is an area-level historical predictor, so every party in
    # the same target area receives the same approved previous-area value.
    previous_margin = margins.get((previous_election_id, previous_area_id))

    # The predictor values and their source identifiers are returned together.
    # This allows every populated value to be traced to its previous election
    # and area in the full feature table.
    return {
        "previous_party_vote_share": previous_share,
        "previous_party_rank": previous_rank,
        "previous_party_was_winner": previous_winner,
        "previous_winning_margin": previous_margin,
        "previous_turnout": previous_turnout,
        "days_since_previous_comparable_election": (target_date - previous_date).days,
        "previous_election_id": previous_election_id,
        "previous_election_date": previous_date.isoformat(),
        "previous_area_id": previous_area_id,
        "previous_area_name": previous_area_name,
        "historical_reference_status": reference_status,
        "historical_source_url": _shared_value(source_rows, "historical_source_url"),
    }


def _previous_party_result(
    *,
    standard_party_name: str,
    previous_candidates: Sequence[Mapping[str, object]],
) -> tuple[float | int | None, int | None, bool | None]:
    """Return share, rank and winner status for one standardised prior party."""

    # Independent is a generic ballot label rather than a continuing party
    # identity, so it cannot carry candidate-specific history across elections.
    if standard_party_name == "Independent":
        return None, None, None

    # The table's observation unit is standardised party. Matching therefore
    # uses the extractor's reviewed standard name, while Reform UK and UKIP
    # remain distinct because they have different standardised names.
    matches = [
        candidate
        for candidate in previous_candidates
        if candidate.get("standard_party_name") == standard_party_name
    ]
    if not matches:
        # Absence from a complete previous candidate table is an observed zero,
        # not missing data. A party that did not contest has no previous rank.
        return 0.0, None, False
    if len(matches) != 1:
        raise ValueError("Standardised party matches multiple previous candidates.")

    # The matched candidate supplies all three party-level historical values.
    # The share and rank are already governed analysis fields in the extractor;
    # elected_yes_no retains the official published outcome.
    matched_share = matches[0].get("analysis_vote_share")
    if not isinstance(matched_share, (int, float)) or isinstance(matched_share, bool):
        raise ValueError("Matched previous candidate has no analysis vote share.")

    rank = matches[0].get("derived_final_position")
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
        raise ValueError("Matched previous candidate has no valid derived rank.")
    outcome = matches[0].get("elected_yes_no")
    if outcome not in {"Yes", "No"}:
        raise ValueError("Matched previous candidate has no valid elected outcome.")
    return matched_share, rank, outcome == "Yes"


def _empty_previous_features(reference_status: object) -> dict[str, object]:
    """Create a consistent historical-field block for a row without a predecessor."""

    # Keeping these rows preserves the complete target-election population.
    # NULL states that no approved historical comparison exists; it does not
    # claim that the party had zero support in an unknown previous area.
    return {
        "previous_party_vote_share": None,
        "previous_party_rank": None,
        "previous_party_was_winner": None,
        "previous_winning_margin": None,
        "previous_turnout": None,
        "days_since_previous_comparable_election": None,
        "previous_election_id": None,
        "previous_election_date": None,
        "previous_area_id": None,
        "previous_area_name": None,
        "historical_reference_status": reference_status,
        "historical_source_url": None,
    }


def _index_party_features(
    party_features: Iterable[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    """Index extractor records by their stable party-contest ID."""

    indexed: dict[str, Mapping[str, object]] = {}
    for feature in party_features:
        contest_id = str(feature.get("party_contest_id", ""))
        if not contest_id:
            raise ValueError("Party-feature record has no party_contest_id.")
        if contest_id in indexed:
            raise ValueError(f"Duplicate party_contest_id: {contest_id!r}.")
        indexed[contest_id] = feature
    return indexed


def _source_rows_for_index_row(
    row: Mapping[str, object],
    source_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Recover the extractor records listed by one fundamentals index row."""

    source_ids = row.get("source_party_contest_ids")
    if not isinstance(source_ids, (tuple, list)) or not source_ids:
        raise ValueError("Fundamentals row has no source party-contest IDs.")
    try:
        # The order stored by the row-index stage is retained, making the join
        # deterministic and easy to reproduce.
        return tuple(source_by_id[str(source_id)] for source_id in source_ids)
    except KeyError as error:
        raise ValueError(f"Fundamentals row refers to an unknown source ID: {error}.") from error


def _payload_table(
    payload: Mapping[str, object], table_name: str
) -> tuple[Mapping[str, object], ...]:
    """Return one named master-payload table after checking its basic shape."""

    table = payload.get(table_name)
    if not isinstance(table, list) or not all(isinstance(row, dict) for row in table):
        raise ValueError(f"Master payload table is missing or invalid: {table_name!r}.")
    return tuple(table)


def _index_elections(
    elections: Iterable[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    """Index election metadata and reject duplicate election IDs."""

    indexed: dict[str, Mapping[str, object]] = {}
    for election in elections:
        election_id = str(election.get("election_id", ""))
        if not election_id or election_id in indexed:
            raise ValueError(f"Missing or duplicate election_id: {election_id!r}.")
        indexed[election_id] = election
    return indexed


def _index_areas_by_name(
    areas: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], Mapping[str, object]]:
    """Index official areas by election and published area name."""

    indexed: dict[tuple[str, str], Mapping[str, object]] = {}
    for area in areas:
        key = (str(area.get("election_id", "")), str(area.get("division_name", "")))
        if not all(key) or key in indexed:
            raise ValueError(f"Missing or duplicate election-area name: {key!r}.")
        indexed[key] = area
    return indexed


def _group_candidates_by_area(
    candidates: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], tuple[Mapping[str, object], ...]]:
    """Group the complete official candidate table by election and area ID."""

    grouped: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for candidate in candidates:
        key = (
            str(candidate.get("election_id", "")),
            str(candidate.get("division_id", "")),
        )
        if not all(key):
            raise ValueError("Candidate row has an incomplete election-area key.")
        grouped[key].append(candidate)
    return {key: tuple(rows) for key, rows in grouped.items()}


def _index_analysis_margins(
    analysis_rows: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], object]:
    """Index the extractor's governed analysis winning margin for each area."""

    margins: dict[tuple[str, str], object] = {}
    for row in analysis_rows:
        # Analysis Voting Summary also contains Seats, turnout and ballot
        # fields; only its governed winning-margin rows belong in this lookup.
        if row.get("field_name") != "analysis_winning_margin":
            continue
        key = (str(row.get("election_id", "")), str(row.get("division_id", "")))
        if not all(key) or key in margins:
            raise ValueError(f"Missing or duplicate analysis margin key: {key!r}.")
        value = row.get("value")
        if value is not None and (
            not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
        ):
            raise ValueError("Analysis winning margin must be non-negative or NULL.")
        margins[key] = value
    return margins


def _election_date(
    elections: Mapping[str, Mapping[str, object]], election_id: str
) -> date:
    """Return a parsed election date for a known election ID."""

    election = elections.get(election_id)
    if election is None:
        raise ValueError(f"Unknown election_id: {election_id!r}.")
    return _parse_date(election.get("election_date"))


def _parse_date(value: object) -> date:
    """Parse the published date format and the ISO format used by test fixtures."""

    if not isinstance(value, str):
        raise ValueError(f"Election date is missing or invalid: {value!r}.")
    # Extractor outputs use a written UK date, while compact ISO dates are also
    # accepted for generated contracts and small test fixtures.
    for date_format in ("%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported election date format: {value!r}.")


def _shared_value(rows: Sequence[Mapping[str, object]], field: str) -> object:
    """Return a field only when every extractor record in the row agrees."""

    values = {row.get(field) for row in rows}
    if len(values) != 1:
        raise ValueError(f"Grouped source records disagree on {field}: {values!r}.")
    return values.pop()
