"""Select a provenance-labelled candidate vote share for analysis.

The official ``vote_share`` field remains authoritative and is never filled by
this module.  A separate analysis value may be calculated only from a complete
single-member candidate table published at one official source URL.  This
narrow rule recovers percentages omitted from the Epsom West 2015 declaration
without estimating turnout, reallocating votes or changing source evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from election_extractor.extraction import CandidateResultRecord


def build_analysis_vote_share_rows(
    records: Iterable[CandidateResultRecord],
) -> dict[tuple[str, str], dict[str, object]]:
    """Return one analysis value and audit status for every candidate record.

    Rows are keyed by the official source URL and exact published candidate
    name, matching the master database's existing candidate-row identity.  An
    official percentage always takes precedence.  Derivation is permitted only
    when every candidate on that page has a non-negative vote count, every row
    reports one seat, candidate names are unique and the total vote count is
    positive.
    """

    records_by_source: defaultdict[str, list[CandidateResultRecord]] = defaultdict(list)
    for record in records:
        records_by_source[record.source_url].append(record)

    output: dict[tuple[str, str], dict[str, object]] = {}
    for source_url, page_records in records_by_source.items():
        candidate_counts = Counter(record.candidate_name for record in page_records)
        complete_votes = all(
            isinstance(record.votes_received, int) and record.votes_received >= 0
            for record in page_records
        )
        single_member = all(record.number_of_seats == 1 for record in page_records)
        total_votes = (
            sum(int(record.votes_received) for record in page_records)
            if complete_votes
            else None
        )

        for record in page_records:
            key = (source_url, record.candidate_name)
            if record.vote_share is not None:
                output[key] = {
                    "analysis_vote_share": record.vote_share,
                    "analysis_vote_share_provenance": "official_result_page",
                    "analysis_vote_share_status": "official_vote_share_retained",
                }
            elif candidate_counts[record.candidate_name] != 1:
                output[key] = _unavailable(
                    "not_derived_duplicate_candidate_name_on_source_page"
                )
            elif not complete_votes:
                output[key] = _unavailable(
                    "not_derived_incomplete_official_candidate_votes"
                )
            elif not single_member:
                output[key] = _unavailable(
                    "not_derived_not_single_member_result"
                )
            elif total_votes is None or total_votes <= 0:
                output[key] = _unavailable(
                    "not_derived_non_positive_official_candidate_vote_total"
                )
            else:
                # Six decimal places preserve substantially more precision than
                # the published display while keeping deterministic JSON/Excel
                # output.  The calculation uses candidate votes only; turnout
                # and issued ballots are deliberately not substituted.
                value = round(int(record.votes_received) / total_votes * 100, 6)
                output[key] = {
                    "analysis_vote_share": value,
                    "analysis_vote_share_provenance": (
                        "governed_derived_from_official_candidate_votes"
                    ),
                    "analysis_vote_share_status": (
                        "derived_single_member_complete_official_candidate_vote_total"
                    ),
                }
    return output


def _unavailable(
    status: str,
) -> dict[str, object]:
    """Keep an unsupported analysis percentage visibly unavailable."""

    return {
        "analysis_vote_share": None,
        "analysis_vote_share_provenance": "unavailable",
        "analysis_vote_share_status": status,
    }
