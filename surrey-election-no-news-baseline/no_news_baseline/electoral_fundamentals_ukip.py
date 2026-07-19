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
import re

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

# The latest completed county-wide result before the 2026 target election is
# the 2021 Surrey County Council election. Naming it explicitly prevents the
# crosswalk route from silently choosing another election type or a later date.
PREVIOUS_COUNTY_ELECTION_ID = "surrey-county-council-2021"

# The official-boundary overlay covers every old and new area. Its smallest
# target coverage is 99.858614%; the tiny remainder is caused by differences
# between boundary file versions. This guard rejects materially incomplete
# crosswalks while accepting the audited Surrey release.
MIN_COMPLETE_CROSSWALK_COVERAGE_PERCENT = 99.8


def add_previous_ukip_feature(
    fundamentals_rows: Iterable[Mapping[str, object]],
    elections: Iterable[Mapping[str, object]],
    candidate_results: Iterable[Mapping[str, object]],
    geographic_overlap_audit: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    """Add previous_ukip_vote_share_in_area without altering party history."""

    rows = tuple(fundamentals_rows)
    candidates = tuple(candidate_results)
    election_dates = _index_election_dates(elections)
    candidates_by_area = _group_candidates_by_area(candidates)
    candidates_by_area_name = _group_candidates_by_area_name(candidates)

    completed: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        # Return the value and its evidence description together.  A numeric
        # zero is a real observation only when a complete approved previous
        # result contains no UKIP candidate; it must not be confused with an
        # area for which no comparable historical geography exists.
        enriched.update(_ukip_evidence_for_row(
            row=row,
            election_dates=election_dates,
            candidates_by_area=candidates_by_area,
            candidates_by_area_name=candidates_by_area_name,
            geographic_overlap_audit=geographic_overlap_audit,
        ))
        completed.append(enriched)

    # Adding one contextual column must preserve the original party-level row
    # count and the unique election-area-standardised-party key.
    validate_unique_row_keys(completed)
    return tuple(completed)


def _ukip_evidence_for_row(
    *,
    row: Mapping[str, object],
    election_dates: Mapping[str, date],
    candidates_by_area: Mapping[tuple[str, str], Sequence[Mapping[str, object]]],
    candidates_by_area_name: Mapping[
        tuple[str, str], Sequence[Mapping[str, object]]
    ],
    geographic_overlap_audit: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return UKIP's historical value together with auditable provenance.

    The official earlier result is published for the earlier electoral area,
    not for polling districts.  Consequently this function releases a value
    only when the extractor has approved a comparable previous area.  It does
    not use polygon area to redistribute votes across changed 2026 boundaries.
    """

    # The field is an explicitly Reform-focused historical context feature.
    # Other parties keep NULL rather than receiving a repeated area-level value.
    if row.get("standard_party_name") != "Reform UK":
        return _ukip_evidence(
            value=None,
            status="not_applicable_non_reform_party",
            method=None,
        )

    previous_election_id = row.get("previous_election_id")
    previous_area_id = row.get("previous_area_id")
    if previous_election_id is None and previous_area_id is None:
        # A complete many-area crosswalk can still prove zero when every
        # contributing old division has a complete result and none contains a
        # UKIP candidate. This proof does not redistribute votes or estimate a
        # positive share.
        crosswalk_zero = _crosswalk_zero_evidence(
            row=row,
            election_dates=election_dates,
            candidates_by_area_name=candidates_by_area_name,
            geographic_overlap_audit=geographic_overlap_audit,
        )
        if crosswalk_zero is not None:
            return crosswalk_zero
        return _ukip_evidence(
            value=None,
            status="unavailable_no_approved_previous_area",
            method=None,
        )
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
        return _ukip_evidence(
            value=0.0,
            status="observed_zero_in_complete_previous_result",
            method="direct_approved_previous_area_result",
            source_election_id=previous_election_id,
            source_area_id=previous_area_id,
            source_area_ids=(previous_area_id,),
            geographic_coverage_percent=100.0,
        )
    if len(ukip_candidates) != 1:
        # Summing or selecting one of several UKIP candidates would introduce a
        # new party-total rule, so an unexpected ambiguous result is rejected.
        raise ValueError("Previous area contains multiple UKIP candidate records.")

    share = ukip_candidates[0].get("analysis_vote_share")
    if not isinstance(share, (int, float)) or isinstance(share, bool):
        raise ValueError("Previous UKIP candidate has no analysis vote share.")
    if not 0 <= share <= 100:
        raise ValueError("Previous UKIP vote share is outside 0-100.")
    return _ukip_evidence(
        value=share,
        status="observed_share_in_complete_previous_result",
        method="direct_approved_previous_area_result",
        source_election_id=previous_election_id,
        source_area_id=previous_area_id,
        source_area_ids=(previous_area_id,),
        geographic_coverage_percent=100.0,
    )


def _crosswalk_zero_evidence(
    *,
    row: Mapping[str, object],
    election_dates: Mapping[str, date],
    candidates_by_area_name: Mapping[
        tuple[str, str], Sequence[Mapping[str, object]]
    ],
    geographic_overlap_audit: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Prove UKIP absence across all old areas contributing to a new ward.

    This function is deliberately one-sided: it can establish an exact zero
    from complete candidate lists, but it never turns area overlap into an
    estimated positive vote share. If any contributing old division contains
    UKIP, polling-district votes would be needed and the value remains NULL.
    """

    if geographic_overlap_audit is None:
        return None
    target_election_id = str(row.get("election_id", ""))
    if target_election_id not in {
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }:
        return None

    source_date = _known_election_date(election_dates, PREVIOUS_COUNTY_ELECTION_ID)
    target_date = _known_election_date(election_dates, target_election_id)
    if source_date >= target_date:
        raise ValueError("Crosswalk UKIP source election must precede target election.")

    overlap_rows = geographic_overlap_audit.get("candidate_overlap_rows")
    if not isinstance(overlap_rows, list):
        raise ValueError("Geographic overlap audit has no candidate-overlap rows.")

    target_name = _normalise_area_name(str(row.get("area_name", "")))
    matches = [
        overlap
        for overlap in overlap_rows
        if isinstance(overlap, dict)
        and overlap.get("current_election_id") == target_election_id
        and _normalise_area_name(str(overlap.get("current_area_name", "")))
        == target_name
    ]
    if not matches:
        raise ValueError("2026 Reform row has no official GIS crosswalk rows.")

    coverage = sum(
        _percentage(overlap.get("current_area_overlap_percent"), "target overlap")
        for overlap in matches
    )
    if coverage < MIN_COMPLETE_CROSSWALK_COVERAGE_PERCENT:
        # An incomplete crosswalk cannot rule out an omitted fragment from a
        # UKIP-contested division, so it cannot support an observed zero.
        return None

    source_names = sorted(
        {
            _normalise_area_name(str(overlap.get("previous_area_name", "")))
            for overlap in matches
        }
    )
    if not all(source_names):
        raise ValueError("GIS crosswalk contains an unnamed previous area.")

    source_candidates: list[Mapping[str, object]] = []
    for source_name in source_names:
        candidates = candidates_by_area_name.get(
            (PREVIOUS_COUNTY_ELECTION_ID, source_name)
        )
        if not candidates:
            raise ValueError(
                f"Crosswalk source has no complete 2021 candidate result: {source_name!r}."
            )
        source_candidates.extend(candidates)

    if any(
        candidate.get("standard_party_name") in UKIP_STANDARD_PARTY_NAMES
        for candidate in source_candidates
    ):
        # UKIP support is known somewhere in an intersecting old division, but
        # the official result does not locate those votes inside that division.
        return None

    return _ukip_evidence(
        value=0.0,
        status="observed_zero_across_complete_previous_crosswalk",
        method="complete_official_results_across_official_gis_crosswalk",
        source_election_id=PREVIOUS_COUNTY_ELECTION_ID,
        source_area_ids=tuple(source_names),
        geographic_coverage_percent=round(coverage, 6),
    )


def _ukip_evidence(
    *,
    value: float | int | None,
    status: str,
    method: str | None,
    source_election_id: str | None = None,
    source_area_id: str | None = None,
    source_area_ids: tuple[str, ...] | None = None,
    geographic_coverage_percent: float | None = None,
) -> dict[str, object]:
    """Create one consistent value-and-provenance block for the output row."""

    # Source identifiers remain NULL when no value is released.  This prevents
    # a changed-boundary relationship from looking like a direct observation.
    if value is None and any(
        item is not None
        for item in (
            method,
            source_election_id,
            source_area_id,
            source_area_ids,
            geographic_coverage_percent,
        )
    ):
        raise ValueError("Unavailable UKIP history cannot claim a direct source.")
    return {
        "previous_ukip_vote_share_in_area": value,
        "previous_ukip_vote_share_status": status,
        "previous_ukip_vote_share_method": method,
        "previous_ukip_source_election_id": source_election_id,
        "previous_ukip_source_area_id": source_area_id,
        "previous_ukip_source_area_ids": source_area_ids,
        "previous_ukip_geographic_coverage_percent": geographic_coverage_percent,
    }


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


def _group_candidates_by_area_name(
    candidates: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], tuple[Mapping[str, object], ...]]:
    """Group official candidates by the area labels used in the GIS audit."""

    grouped: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for candidate in candidates:
        election_id = str(candidate.get("election_id", ""))
        area_name = _normalise_area_name(str(candidate.get("division_name", "")))
        if not election_id or not area_name:
            raise ValueError("Candidate row has an incomplete election-area name key.")
        grouped[(election_id, area_name)].append(candidate)
    return {key: tuple(rows) for key, rows in grouped.items()}


def _normalise_area_name(value: str) -> str:
    """Align reviewed master/GIS suffix and conjunction differences exactly."""

    # The official result and GIS exports differ in typographic hyphenation
    # (for example, "South-East" versus "South East").
    name = re.sub(r"[-–—]", " ", value.strip())
    name = " ".join(name.split())
    for suffix in (" Ward", " ED"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    # This deterministic formatting adjustment is used only after the official
    # GIS overlay has identified a relationship; it does not approve geography
    # merely because two names happen to look alike.
    return name.replace(" and ", " & ").casefold()


def _percentage(value: object, field: str) -> float:
    """Validate a percentage read from the generated official GIS audit."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"GIS {field} is missing or invalid: {value!r}.")
    number = float(value)
    if not 0 <= number <= 100:
        raise ValueError(f"GIS {field} is outside 0-100: {number!r}.")
    return number


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
