"""Derive transparent single-seat winning margins from official result rows.

The supervisor requests a winning-margin field, but Surrey's result pages do
not publish a dedicated margin column. This module therefore creates a
*separate* derived record only where the official result page itself supplies
all evidence required to quantify the margin without guessing a winner:

* the official Voting Summary publishes exactly one available seat;
* exactly one candidate is explicitly marked ``Elected``;
* every listed candidate has an official vote total and explicit outcome; and
* the elected candidate's total is not lower than any non-elected total.

The calculation is deliberately unavailable for multi-member contests. There
is no single universally unambiguous ``winning margin`` in that setting, and
this project will not create one merely by choosing a vote-order convention.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from election_extractor.extraction import CandidateResultRecord

# This date identifies the reviewed policy version, rather than the date an
# individual official result was published. Keeping it fixed makes rebuilt
# workbooks traceable to the same governed derivation rule.
MARGIN_RULE_REVIEW_DATE = "2026-07-17"


@dataclass(frozen=True)
class DerivedWinningMargin:
    """One auditable, separate winning-margin calculation for a division.

    ``value`` never replaces the absent official ``winning_margin`` field. The
    named candidate totals are retained so the calculation is inspectable.
    """

    metadata_id: str
    election_id: str
    division_id: str
    field_name: str
    target_official_field: str
    value: int
    elected_candidate_name: str
    elected_candidate_votes: int
    runner_up_candidate_name: str
    runner_up_candidate_votes: int
    source_url: str
    formula: str
    evidence_text: str
    retrieval_date: str
    notes: str


def derive_single_member_winning_margins(
    *,
    election_id: str,
    records: Iterable[CandidateResultRecord],
    division_id_for_source_url: Callable[[str], str],
) -> tuple[DerivedWinningMargin, ...]:
    """Return margins only for fully evidenced, official single-seat contests.

    Records are grouped by their exact source URL. This ensures the elected
    outcome and every candidate vote used by a calculation originate on one
    official page, rather than from a cross-page comparison. A missing or
    inconsistent field makes the contest ineligible rather than estimated.
    """

    by_source: defaultdict[str, list[CandidateResultRecord]] = defaultdict(list)
    for record in records:
        by_source[record.source_url].append(record)

    calculated: list[DerivedWinningMargin] = []
    for source_url, contest_records in sorted(by_source.items()):
        margin = _margin_from_official_contest(
            election_id=election_id,
            division_id=division_id_for_source_url(source_url),
            source_url=source_url,
            records=contest_records,
        )
        if margin is not None:
            calculated.append(margin)
    return tuple(calculated)


def _margin_from_official_contest(
    *,
    election_id: str,
    division_id: str,
    source_url: str,
    records: list[CandidateResultRecord],
) -> DerivedWinningMargin | None:
    """Validate one official page before calculating its single-seat margin."""

    # A directly published margin is official data already, so a derived
    # duplicate would obscure the provenance split.
    if {record.winning_margin for record in records} != {None}:
        return None
    if {record.number_of_seats for record in records} != {1}:
        return None

    # Explicit outcome text identifies the winner. Votes quantify only the
    # gap to the highest *officially non-elected* candidate; they never choose
    # or replace the official winner.
    elected = [record for record in records if record.outcome == "Elected"]
    not_elected = [record for record in records if record.outcome == "Not elected"]
    if len(elected) != 1 or not not_elected or len(elected) + len(not_elected) != len(records):
        return None
    if any(record.votes_received is None for record in records):
        return None

    winner = elected[0]
    # The preceding null check guarantees that all comparison inputs are
    # published integers. This key therefore cannot silently substitute a
    # missing value for zero.
    runner_up = max(not_elected, key=lambda record: record.votes_received)
    assert winner.votes_received is not None
    assert runner_up.votes_received is not None
    if winner.votes_received < runner_up.votes_received:
        # An outcome/vote contradiction needs source review, not a negative
        # result or a silently corrected winner.
        return None

    value = winner.votes_received - runner_up.votes_received
    return DerivedWinningMargin(
        metadata_id=f"{division_id}:derived_winning_margin",
        election_id=election_id,
        division_id=division_id,
        field_name="derived_winning_margin",
        target_official_field="winning_margin",
        value=value,
        elected_candidate_name=winner.candidate_name,
        elected_candidate_votes=winner.votes_received,
        runner_up_candidate_name=runner_up.candidate_name,
        runner_up_candidate_votes=runner_up.votes_received,
        source_url=source_url,
        formula="officially_elected_candidate_votes - highest_officially_not_elected_candidate_votes",
        evidence_text=(
            "The same official single-seat result page marks "
            f"{winner.candidate_name} Elected with {winner.votes_received:,} votes "
            f"and {runner_up.candidate_name} Not elected with "
            f"{runner_up.votes_received:,} votes."
        ),
        retrieval_date=MARGIN_RULE_REVIEW_DATE,
        notes=(
            "Derived only from explicit official outcomes and votes on one "
            "single-seat result page. It remains separate from the official "
            "winning_margin field."
        ),
    )


def records_as_rows(
    records: Iterable[DerivedWinningMargin],
) -> tuple[dict[str, object], ...]:
    """Convert audited calculations to the existing Derived Metadata table."""

    return tuple(
        {
            "metadata_id": record.metadata_id,
            "election_id": record.election_id,
            "division_id": record.division_id,
            "field_name": record.field_name,
            "value": record.value,
            "target_official_field": record.target_official_field,
            "formula": record.formula,
            "official_inputs": (
                f"officially_elected_candidate_votes={record.elected_candidate_votes}; "
                f"highest_officially_not_elected_candidate_votes={record.runner_up_candidate_votes}"
            ),
            "source_url": record.source_url,
            "evidence_text": record.evidence_text,
            "retrieval_date": record.retrieval_date,
            "confidence": "High",
            "notes": record.notes,
            "validation_status": "verified",
        }
        for record in sorted(records, key=lambda item: item.metadata_id)
    )
