"""Produce a read-only QA release package for derived candidate vote ranks.

The package does not alter official results or derived ranks.  It makes the
eligibility, outcome checks, ties and required second-source review visible at
the result-page level so that a reviewer can reproduce every decision.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import json
from pathlib import Path
import random
from urllib.parse import urlsplit

from election_extractor.derived_final_position import (
    derive_final_positions,
    validate_final_positions_against_official_outcomes,
)
from election_extractor.extraction import CandidateResultRecord
from election_extractor.master_database import AuditedElectionInput


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECOND_SOURCE_REVIEWS_PATH = (
    PROJECT_ROOT / "config" / "final_position_second_source_reviews.json"
)


def _source_format_family(source_url: str) -> str:
    """Return a stable publisher/endpoint family for stratified QA sampling.

    ``source_type`` describes how data were extracted, not how the publisher
    presents election results.  This family captures the latter, so distinct
    council/PDF/interactive-map formats are sampled without treating every
    by-election date as a different format.
    """

    parsed = urlsplit(source_url)
    return f"{parsed.netloc.lower()}{parsed.path.lower()}"


def load_second_source_reviews(
    path: Path = SECOND_SOURCE_REVIEWS_PATH,
) -> dict[tuple[str, str], dict[str, object]]:
    """Load recorded independent official checks keyed by primary result page.

    This explicit registry is intentionally separate from extraction inputs:
    corroboration documents are QA evidence, never a fallback source used to
    populate an official result field.
    """

    payload = json.loads(path.read_text())
    return {
        (item["election_id"], item["source_url"]): item
        for item in payload["reviews"]
    }


def build_final_position_qa(
    elections: Iterable[AuditedElectionInput],
    second_source_reviews: dict[tuple[str, str], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return result-page QA rows, tie review records and a review sample.

    The second-source fields intentionally start as ``pending``.  They are a
    review queue, not a claim that a declaration or archive page was checked.
    """

    reviews = second_source_reviews or load_second_source_reviews()
    pages: list[dict[str, object]] = []
    tie_pages: list[dict[str, object]] = []
    for election in elections:
        by_url: defaultdict[str, list[CandidateResultRecord]] = defaultdict(list)
        for record in election.records:
            by_url[record.source_url].append(record)
        positions = derive_final_positions(
            election_id=election.configuration.election_id,
            records=election.records,
        )
        # A contradiction is a release blocker, not a row-level warning.
        validate_final_positions_against_official_outcomes(
            records=election.records, positions=positions
        )
        position_by_key = {
            (item.source_url, item.candidate_name): item for item in positions
        }
        for source_url, records in sorted(by_url.items()):
            page_positions = [position_by_key.get((source_url, r.candidate_name)) for r in records]
            votes_complete = all(isinstance(r.votes_received, int) for r in records)
            elected = [r for r in records if r.outcome == "Elected"]
            not_elected = [r for r in records if r.outcome == "Not elected"]
            outcome_complete = len(elected) + len(not_elected) == len(records)
            cutoff_gap = (
                min(r.votes_received for r in elected)
                - max(r.votes_received for r in not_elected)
                if outcome_complete
                and elected
                and not_elected
                and votes_complete
                else None
            )
            seats = {r.number_of_seats for r in records}
            seats_value = next(iter(seats)) if len(seats) == 1 else None
            seats_consistent = (
                isinstance(seats_value, int)
                and outcome_complete
                and len(elected) == seats_value
            )
            seats_consistency_status = (
                "official_seats_unavailable"
                if seats_value is None
                else (
                    "outcome_unavailable"
                    if not outcome_complete
                    else (
                        "passed"
                        if seats_consistent
                        else "official_seats_outcome_inconsistent"
                    )
                )
            )
            outcome_vote_order_status = (
                "passed"
                if outcome_complete and elected and not_elected and votes_complete
                else (
                    "not_eligible_incomplete_votes"
                    if outcome_complete and elected and not_elected
                    else "not_applicable"
                )
            )
            # A vote rank does not require Seats, but the validation report
            # must not flatten a missing official Seats value into a generic
            # pass.  This preserves both the successful rank test and the
            # separate official metadata limitation in one release field.
            validation_result = (
                "not_eligible_incomplete_votes"
                if not votes_complete
                else (
                    "passed_complete_rank_and_seats_checks"
                    if seats_consistent and outcome_vote_order_status == "passed"
                    else "passed_rank_checks_official_seats_unavailable_or_inconsistent"
                )
            )
            tied = [p for p in page_positions if p is not None and p.tied]
            row = {
                "election_id": election.configuration.election_id,
                "division_or_ward": records[0].division_ward_name,
                "source_url": source_url,
                "source_format": records[0].source_type.value,
                "source_format_family": _source_format_family(source_url),
                "candidate_count": len(records),
                "votes_complete": votes_complete,
                "elected_count": len(elected),
                "not_elected_count": len(not_elected),
                "official_seats": seats_value,
                "seats_consistency_status": seats_consistency_status,
                "outcome_vote_order_status": outcome_vote_order_status,
                "outcome_cutoff_gap": cutoff_gap,
                "derived_rank_count": sum(p is not None for p in page_positions),
                "unique_vote_total_count": len({r.votes_received for r in records if r.votes_received is not None}),
                "has_tied_vote_rank": bool(tied),
                "validation_result": validation_result,
                # Retained as a compatibility alias for existing downstream
                # consumers. New analyses should use validation_result.
                "validation_status": validation_result,
                "review_reason": (
                    "tie_at_or_within_candidate_vote_ranks" if tied else None
                ),
            }
            pages.append(row)
            if tied:
                # Keep every candidate, not only tied rows: the declared
                # outcome and the seat cutoff must be reviewed in context.
                cutoff = min((r.votes_received for r in elected), default=None)
                review = reviews.get((row["election_id"], source_url), {})
                tie_pages.append(
                    {
                        **row,
                        "tied_ranks": sorted({p.value for p in tied}),
                        "lowest_elected_vote_cutoff": cutoff,
                        "candidates": [
                            {
                                "candidate_name": r.candidate_name,
                                "votes": r.votes_received,
                                "outcome": r.outcome,
                                "derived_rank": (
                                    position_by_key[(source_url, r.candidate_name)].value
                                    if (source_url, r.candidate_name) in position_by_key else None
                                ),
                            }
                            for r in records
                        ],
                        "second_official_source_url": review.get("second_official_source_url"),
                        "second_source_type": review.get("second_source_type"),
                        "second_source_review_status": review.get(
                            "review_status", "pending_manual_official_review"
                        ),
                        "second_source_reviewed_fields": review.get("reviewed_fields", []),
                        "second_source_review_notes": review.get("review_notes"),
                    }
                )

    # Every tied page is independently checked.  The remaining source review
    # is a reproducible risk sample, not an unnecessary second extraction of
    # every multi-seat result already covered by the official primary source.
    # A fixed seed makes the random selection auditable and repeatable.
    selected_reasons: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for row in tie_pages:
        selected_reasons[(row["election_id"], row["source_url"])].add("tied_vote_rank")
    for row in pages:
        # A 50-vote threshold is deliberately conservative and only applies
        # where complete official outcomes and votes make the cutoff gap
        # observable.  It flags close single-seat boundaries without creating
        # a pseudo-margin for multi-seat contests.
        if (
            row["official_seats"] == 1
            and isinstance(row["outcome_cutoff_gap"], int)
            and row["outcome_cutoff_gap"] <= 50
        ):
            selected_reasons[(row["election_id"], row["source_url"])].add(
                "low_single_seat_cutoff_gap_50_votes_or_less"
            )
    sampling_rng = random.Random("final-position-risk-sample-v1")
    # Principal elections receive one sample each; by-elections are instead
    # stratified by publisher/endpoint family.  This implements the requested
    # coverage of every by-election *source format* without needlessly
    # treating every by-election date as a separate format.
    principal_elections = sorted(
        {row["election_id"] for row in pages if "by-election" not in row["election_id"]}
    )
    strata: list[tuple[str, list[dict[str, object]]]] = []
    for election_id in principal_elections:
        strata.append((
            f"principal:{election_id}",
            [row for row in pages if row["election_id"] == election_id],
        ))
    by_election_families = sorted(
        {row["source_format_family"] for row in pages if "by-election" in row["election_id"]}
    )
    for family in by_election_families:
        strata.append((
            f"by-election-format:{family}",
            [
                row
                for row in pages
                if "by-election" in row["election_id"]
                and row["source_format_family"] == family
            ],
        ))
    for stratum_label, stratum in strata:
        stratum = sorted(
            stratum,
            key=lambda row: str(row["source_url"]),
        )
        chosen = sampling_rng.choice(stratum)
        selected_reasons[(chosen["election_id"], chosen["source_url"])].add(
            f"reproducible_random_sample:{stratum_label}"
        )
    review_sample = [
        {
            **row,
            "selection_reasons": sorted(
                selected_reasons[(row["election_id"], row["source_url"])]
            ),
            "second_official_source_url": reviews.get(
                (row["election_id"], row["source_url"]), {}
            ).get("second_official_source_url"),
            "second_source_type": reviews.get(
                (row["election_id"], row["source_url"]), {}
            ).get("second_source_type"),
            "second_source_review_status": reviews.get(
                (row["election_id"], row["source_url"]), {}
            ).get("review_status", "pending_manual_official_review"),
        }
        for row in pages
        if (row["election_id"], row["source_url"]) in selected_reasons
    ]
    # The user requested eight review records, one for each tied candidate.
    # Each repeats full page context so a reviewer never has to join records
    # before judging a tie at, above, or below an elected cutoff.
    tie_candidate_review_list = [
        {
            **tie,
            "tied_candidate_name": candidate["candidate_name"],
            "tied_candidate_votes": candidate["votes"],
            "tied_candidate_outcome": candidate["outcome"],
            "tied_candidate_rank": candidate["derived_rank"],
            "declaration_or_returning_officer_record_needed": (
                tie["second_source_review_status"] != "verified"
            ),
        }
        for tie in tie_pages
        for candidate in tie["candidates"]
        if candidate["derived_rank"] in tie["tied_ranks"]
    ]
    fully_verified_reviews = sum(
        row["second_source_review_status"] == "verified" for row in review_sample
    )
    outcome_only_reviews = sum(
        row["second_source_review_status"] == "official_outcome_only"
        for row in review_sample
    )
    completed_reviews = fully_verified_reviews + outcome_only_reviews
    # Internal outcome checks and independent-source corroboration answer
    # different questions. The primary official result pages support analysis
    # readiness; the extra source sample reports its own completion status and
    # never converts a pending review into a failed primary result.
    summary = {
        "result_page_count": len(pages),
        "automatically_validated_pages": sum(
            str(row["validation_result"]).startswith("passed_") for row in pages
        ),
        "tied_candidate_rows": len(tie_candidate_review_list),
        "required_independent_official_reviews": len(review_sample),
        "fully_verified_independent_official_reviews": fully_verified_reviews,
        "outcome_only_independent_official_reviews": outcome_only_reviews,
        "completed_independent_official_reviews": completed_reviews,
        "pending_independent_official_reviews": len(review_sample) - completed_reviews,
        "analysis_readiness_status": (
            "analysis_ready_from_primary_official_sources"
            if all(
                str(row["validation_result"]).startswith("passed_")
                for row in pages
            )
            else "not_analysis_ready"
        ),
        "secondary_risk_sample_status": (
            "secondary_risk_sample_complete"
            if completed_reviews == len(review_sample)
            else "secondary_risk_sample_incomplete"
        ),
        "second_source_review_scope": (
            "All tied pages plus a reproducible risk sample; secondary review "
            "does not replace or downgrade the primary official result source. "
            "Outcome-only corroboration is explicitly labelled and never treated "
            "as a complete independent candidate-rank table."
        ),
    }
    return {
        "summary": summary,
        "page_validation": pages,
        "tie_page_context": tie_pages,
        "tie_candidate_review_list": tie_candidate_review_list,
        "official_review_sample": review_sample,
    }
