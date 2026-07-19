"""Add a separate previous-UKIP context feature for Reform UK rows.

Reform UK and UKIP remain different standardised parties throughout the
fundamentals table.  For a Reform UK target row, this module records UKIP's
vote share in the already approved previous comparable area as a separate
historical context field.  It never changes Reform UK's own previous share.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime

from no_news_baseline.electoral_fundamentals_schema import validate_unique_row_keys


# These reviewed standard names represent UKIP records in the existing Surrey
# extractor. Reform UK is deliberately absent from this allow-list.
UKIP_STANDARD_PARTY_NAMES = frozenset(
    {
        "UK Independence Party",
        "UK Independence Party (UKIP)",
        "UKIP",
    }
)


def add_previous_ukip_feature(
    fundamentals_rows: Iterable[Mapping[str, object]],
    elections: Iterable[Mapping[str, object]],
    candidate_results: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Add previous_ukip_vote_share_in_area without altering party history."""

    rows = tuple(fundamentals_rows)
    election_dates = _index_election_dates(elections)
    candidates_by_area = _group_candidates_by_area(candidate_results)

    completed: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        enriched["previous_ukip_vote_share_in_area"] = _ukip_share_for_row(
            row=row,
            election_dates=election_dates,
            candidates_by_area=candidates_by_area,
        )
        completed.append(enriched)

    # Adding one contextual column must preserve the original party-level row
    # count and the unique election-area-standardised-party key.
    validate_unique_row_keys(completed)
    return tuple(completed)


def _ukip_share_for_row(
    *,
    row: Mapping[str, object],
    election_dates: Mapping[str, date],
    candidates_by_area: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
) -> float | int | None:
    """Return UKIP's share in Reform UK's approved previous comparable area."""

    # The field is an explicitly Reform-focused historical context feature.
    # Other parties keep NULL rather than receiving a repeated area-level value.
    if row.get("standard_party_name") != "Reform UK":
        return None

    previous_election_id = row.get("previous_election_id")
    previous_area_id = row.get("previous_area_id")
    if previous_election_id is None and previous_area_id is None:
        # No approved previous-area relationship means there is no defensible
        # place from which to retrieve earlier UKIP support.
        return None
    if not isinstance(previous_election_id, str) or not isinstance(
        previous_area_id, str
    ):
        raise ValueError("Reform UK row has an incomplete previous-area reference.")

    target_election_id = str(row.get("election_id", ""))
    target_date = _known_election_date(election_dates, target_election_id)
    previous_date = _known_election_date(election_dates, previous_election_id)
    if previous_date >= target_date:
        raise ValueError("UKIP source election must precede Reform UK target election.")

    area_key = (previous_election_id, previous_area_id)
    previous_candidates = candidates_by_area.get(area_key)
    if not previous_candidates:
        raise ValueError(f"Approved previous area has no candidate rows: {area_key!r}.")

    ukip_candidates = [
        candidate
        for candidate in previous_candidates
        if candidate.get("standard_party_name") in UKIP_STANDARD_PARTY_NAMES
    ]
    if not ukip_candidates:
        # The complete earlier candidate table proves that UKIP did not contest
        # this approved area, so zero is observed rather than imputed.
        return 0.0
    if len(ukip_candidates) != 1:
        # Summing or selecting one of several UKIP candidates would introduce a
        # new party-total rule, so an unexpected ambiguous result is rejected.
        raise ValueError("Previous area contains multiple UKIP candidate records.")

    share = ukip_candidates[0].get("analysis_vote_share")
    if not isinstance(share, (int, float)) or isinstance(share, bool):
        raise ValueError("Previous UKIP candidate has no analysis vote share.")
    if not 0 <= share <= 100:
        raise ValueError("Previous UKIP vote share is outside 0-100.")
    return share


def _index_election_dates(
    elections: Iterable[Mapping[str, object]],
) -> dict[str, date]:
    """Index parsed dates so every historical lookup can check time order."""

    indexed: dict[str, date] = {}
    for election in elections:
        election_id = str(election.get("election_id", ""))
        if not election_id or election_id in indexed:
            raise ValueError(f"Missing or duplicate election_id: {election_id!r}.")
        indexed[election_id] = _parse_date(election.get("election_date"))
    return indexed


def _group_candidates_by_area(
    candidates: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], tuple[Mapping[str, object], ...]]:
    """Group complete official candidate results by election and area."""

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


def _known_election_date(election_dates: Mapping[str, date], election_id: str) -> date:
    """Return the date for a known election ID."""

    try:
        return election_dates[election_id]
    except KeyError as error:
        raise ValueError(f"Unknown election_id: {election_id!r}.") from error


def _parse_date(value: object) -> date:
    """Parse the written extractor date or an ISO-formatted contract date."""

    if not isinstance(value, str):
        raise ValueError(f"Election date is missing or invalid: {value!r}.")
    for date_format in ("%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported election date format: {value!r}.")
