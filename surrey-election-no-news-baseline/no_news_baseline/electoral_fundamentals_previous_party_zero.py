"""Recover exact previous-party zeros across the audited 2021-to-2026 crosswalk.

Official candidate lists can prove that a party received no votes in a new
2026 ward when that party was absent from every 2021 division contributing to
the ward.  The inference is deliberately one-sided: polygon overlap can prove
absence, but it is never used to redistribute positive votes across changed
boundaries.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from no_news_baseline.electoral_fundamentals_schema import validate_unique_row_keys
from no_news_baseline.electoral_fundamentals_ukip import (
    MIN_COMPLETE_CROSSWALK_COVERAGE_PERCENT,
    PREVIOUS_COUNTY_ELECTION_ID,
    _index_election_dates,
    _known_election_date,
    _normalise_area_name,
    _percentage,
)


TARGET_2026_ELECTION_IDS = frozenset(
    {
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }
)


def add_crosswalk_previous_party_zeros(
    fundamentals_rows: Iterable[Mapping[str, object]],
    elections: Iterable[Mapping[str, object]],
    candidate_results: Iterable[Mapping[str, object]],
    geographic_overlap_audit: Mapping[str, object] | None,
) -> tuple[dict[str, object], ...]:
    """Add direct provenance and defensible crosswalk-zero party history."""

    rows = tuple(fundamentals_rows)
    election_dates = _index_election_dates(elections)
    candidates_by_area_name = _group_candidates_by_area_name(candidate_results)

    completed: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        if row.get("previous_party_vote_share") is not None:
            # Existing values already come from an approved direct predecessor.
            # The dedicated block makes their evidence comparable with the new
            # multi-area exact-zero route without changing the original fields.
            enriched.update(_direct_evidence(row))
        else:
            zero_evidence = _crosswalk_zero_evidence(
                row=row,
                election_dates=election_dates,
                candidates_by_area_name=candidates_by_area_name,
                geographic_overlap_audit=geographic_overlap_audit,
            )
            if zero_evidence is None:
                enriched.update(_unavailable_evidence(row))
            else:
                # Absence from every complete source result establishes these
                # party-history states without estimating where votes occurred.
                enriched.update(
                    {
                        "previous_party_vote_share": 0.0,
                        "previous_party_was_winner": False,
                        "incumbent_party": False,
                        "party_previously_stood": False,
                        "first_party_appearance_in_area": True,
                        **zero_evidence,
                    }
                )
        completed.append(enriched)

    validate_unique_row_keys(completed)
    return tuple(completed)


def _crosswalk_zero_evidence(
    *,
    row: Mapping[str, object],
    election_dates: Mapping[str, date],
    candidates_by_area_name: Mapping[
        tuple[str, str], Sequence[Mapping[str, object]]
    ],
    geographic_overlap_audit: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Return evidence only when all contributing results prove party absence."""

    party = row.get("standard_party_name")
    # Generic Independent rows combine unrelated people and therefore do not
    # represent a continuing political identity whose historical absence can
    # be asserted at party level.
    if party == "Independent" or not isinstance(party, str) or not party:
        return None
    target_election_id = str(row.get("election_id", ""))
    if target_election_id not in TARGET_2026_ELECTION_IDS:
        return None
    if geographic_overlap_audit is None:
        return None

    source_date = _known_election_date(election_dates, PREVIOUS_COUNTY_ELECTION_ID)
    target_date = _known_election_date(election_dates, target_election_id)
    if source_date >= target_date:
        raise ValueError("Crosswalk party-history source must precede target election.")

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
        raise ValueError("2026 party row has no official GIS crosswalk rows.")

    coverage = sum(
        _percentage(overlap.get("current_area_overlap_percent"), "target overlap")
        for overlap in matches
    )
    if coverage < MIN_COMPLETE_CROSSWALK_COVERAGE_PERCENT:
        return None

    source_names = tuple(
        sorted(
            {
                _normalise_area_name(str(overlap.get("previous_area_name", "")))
                for overlap in matches
            }
        )
    )
    if not source_names or not all(source_names):
        raise ValueError("GIS crosswalk contains an unnamed previous area.")

    for source_name in source_names:
        candidates = candidates_by_area_name.get(
            (PREVIOUS_COUNTY_ELECTION_ID, source_name)
        )
        if not candidates:
            raise ValueError(
                f"Crosswalk source has no complete 2021 result: {source_name!r}."
            )
        if any(candidate.get("standard_party_name") == party for candidate in candidates):
            # A positive source-area result cannot be allocated to the new ward
            # without polling-district electorate weights, so it stays NULL.
            return None

    return {
        "previous_party_vote_share_status": (
            "observed_zero_across_complete_previous_crosswalk"
        ),
        "previous_party_vote_share_method": (
            "complete_official_results_across_official_gis_crosswalk"
        ),
        "previous_party_source_election_id": PREVIOUS_COUNTY_ELECTION_ID,
        "previous_party_source_area_ids": source_names,
        "previous_party_geographic_coverage_percent": round(coverage, 6),
    }


def _direct_evidence(row: Mapping[str, object]) -> dict[str, object]:
    """Describe a value already obtained from one approved predecessor."""

    source_election_id = row.get("previous_election_id")
    source_area_id = row.get("previous_area_id")
    if not isinstance(source_election_id, str) or not isinstance(source_area_id, str):
        raise ValueError("Previous party share has incomplete direct provenance.")
    return {
        "previous_party_vote_share_status": "observed_in_approved_previous_result",
        "previous_party_vote_share_method": "direct_approved_previous_area_result",
        "previous_party_source_election_id": source_election_id,
        "previous_party_source_area_ids": (source_area_id,),
        "previous_party_geographic_coverage_percent": 100.0,
    }


def _unavailable_evidence(row: Mapping[str, object]) -> dict[str, object]:
    """Distinguish generic Independent non-applicability from unknown history.

    Independent candidates do not belong to one continuing party, so their
    party-level lag is structurally not applicable. Other missing values remain
    unavailable until direct or exact-zero evidence is present.
    """

    return {
        "previous_party_vote_share_status": (
            "not_applicable_generic_independent_identity"
            if row.get("standard_party_name") == "Independent"
            else "unavailable_no_direct_or_zero_proof"
        ),
        "previous_party_vote_share_method": None,
        "previous_party_source_election_id": None,
        "previous_party_source_area_ids": None,
        "previous_party_geographic_coverage_percent": None,
    }


def _group_candidates_by_area_name(
    candidates: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], tuple[Mapping[str, object], ...]]:
    """Index complete candidate lists by the official GIS area labels."""

    grouped: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for candidate in candidates:
        election_id = str(candidate.get("election_id", ""))
        area_name = _normalise_area_name(str(candidate.get("division_name", "")))
        if not election_id or not area_name:
            raise ValueError("Candidate row has an incomplete election-area key.")
        grouped[(election_id, area_name)].append(candidate)
    return {key: tuple(values) for key, values in grouped.items()}
