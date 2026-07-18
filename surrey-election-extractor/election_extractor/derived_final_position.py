"""Derive transparent candidate vote ranks without altering official rank data.

Surrey's audited result pages publish candidate vote totals but do not publish a
``Final position`` column.  The supervisor nevertheless requests a final-
position field.  This module therefore creates a *separate analytical rank*
only when every candidate on one official result page has a published integer
vote total and that page has no official rank at all.

The rank is a competition rank: 100, 80, 80, 50 votes become ranks 1, 2, 2,
4.  This is preferable to silently breaking a tie alphabetically or by page
order.  It is a descriptive ordering of official votes, not an official
placing, an outcome, or a substitute for the source field.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from election_extractor.extraction import CandidateResultRecord


@dataclass(frozen=True)
class DerivedFinalPosition:
    """One candidate-level rank calculated from a complete official page."""

    election_id: str
    source_url: str
    candidate_name: str
    value: int
    tied: bool


def derive_final_positions(
    *,
    election_id: str,
    records: Iterable[CandidateResultRecord],
) -> tuple[DerivedFinalPosition, ...]:
    """Return ranks only for official pages that meet every evidence condition.

    Keeping pages separate is essential: a rank must never compare candidates
    from different divisions or from two URLs for the same event.  If one vote
    is absent, or an official rank appears anywhere on the page, the complete
    page is skipped rather than creating a mixture of official and derived
    values.
    """

    records_by_url: defaultdict[str, list[CandidateResultRecord]] = defaultdict(list)
    for record in records:
        records_by_url[record.source_url].append(record)

    derived: list[DerivedFinalPosition] = []
    for source_url, contest_records in sorted(records_by_url.items()):
        derived.extend(
            _positions_from_complete_official_contest(
                election_id=election_id,
                source_url=source_url,
                records=contest_records,
            )
        )
    return tuple(derived)


def _positions_from_complete_official_contest(
    *,
    election_id: str,
    source_url: str,
    records: list[CandidateResultRecord],
) -> tuple[DerivedFinalPosition, ...]:
    """Calculate competition ranks for one fully published candidate table."""

    if not records:
        return ()
    # Official rank, when it exists, takes precedence.  Do not create a
    # derived duplicate or attempt to reconcile a partially ranked table.
    if any(record.final_position is not None for record in records):
        return ()
    if any(record.votes_received is None for record in records):
        return ()

    # ``votes_received`` is known to be an int after the null guard above.
    votes_by_name = {record.candidate_name: record.votes_received for record in records}
    # Duplicate names on one source page would make a candidate-level rank
    # ambiguous.  Reject rather than silently overwrite one row in the dict.
    if len(votes_by_name) != len(records):
        return ()

    distinct_totals = sorted(set(votes_by_name.values()), reverse=True)
    # Competition rank is one plus the number of candidates strictly ahead.
    # It makes ties visible (1, 2, 2, 4), unlike dense ranking (1, 2, 2, 3).
    rank_by_votes = {
        votes: 1 + sum(other_votes > votes for other_votes in votes_by_name.values())
        for votes in distinct_totals
    }
    tied_vote_totals = {
        votes
        for votes in distinct_totals
        if sum(other_votes == votes for other_votes in votes_by_name.values()) > 1
    }
    return tuple(
        DerivedFinalPosition(
            election_id=election_id,
            source_url=source_url,
            candidate_name=record.candidate_name,
            value=rank_by_votes[votes_by_name[record.candidate_name]],
            tied=votes_by_name[record.candidate_name] in tied_vote_totals,
        )
        for record in records
    )
