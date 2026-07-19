"""Audit non-start-period NULLs for Independent previous vote share.

``Independent`` is a ballot description, not one continuing political party.
This audit checks every later-election Independent NULL against the approved
previous area and its complete official candidate list. It records whether the
same verified candidate history exists, whether different Independents stood,
or whether no Independent stood. None of those cases is silently converted
into a party-level historical vote share.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence


AUDITABLE_STATUSES = frozenset(
    {
        "unavailable_no_direct_or_zero_proof",
        "not_applicable_generic_independent_identity",
    }
)
INDEPENDENT = "Independent"


def audit_independent_previous_share_nulls(
    fundamentals_rows: Sequence[Mapping[str, object]],
    candidate_results: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Classify every approved-history Independent NULL after the study start.

    Rows without an approved previous election are outside this audit because
    their missingness comes from the study boundary or geographic comparison,
    rather than the generic Independent label.
    """

    candidates_by_area = _candidate_index(candidate_results)
    decisions: list[dict[str, object]] = []
    for row in fundamentals_rows:
        if not _is_auditable_independent_null(row):
            continue

        target_key = (str(row["election_id"]), str(row["area_id"]))
        previous_key = (
            str(row["previous_election_id"]),
            str(row["previous_area_id"]),
        )
        current_independents = _independents(candidates_by_area.get(target_key, ()))
        previous_independents = _independents(
            candidates_by_area.get(previous_key, ())
        )
        if not current_independents:
            raise ValueError(f"Independent feature row has no candidate: {target_key!r}.")
        if previous_key not in candidates_by_area:
            raise ValueError(f"Approved previous area has no candidate list: {previous_key!r}.")

        verified_matches = _verified_same_candidate_matches(
            current_independents=current_independents,
            previous_independents=previous_independents,
            previous_election_id=previous_key[0],
        )
        decision, reason = _decision(
            previous_independents=previous_independents,
            verified_matches=verified_matches,
        )
        decisions.append(
            {
                "election_id": row["election_id"],
                "election_date": row["election_date"],
                "area_name": row["area_name"],
                "previous_election_id": row["previous_election_id"],
                "previous_area_name": row["previous_area_name"],
                "current_independent_candidates": tuple(
                    candidate["candidate_name"] for candidate in current_independents
                ),
                "previous_independent_candidates": tuple(
                    candidate["candidate_name"] for candidate in previous_independents
                ),
                "verified_same_candidate_names": tuple(verified_matches),
                "final_previous_party_vote_share": None,
                "decision": decision,
                "reason": reason,
            }
        )

    counts = Counter(str(row["decision"]) for row in decisions)
    return {
        "audit_id": "independent-previous-party-vote-share-null-review",
        "status": "complete_no_party_level_values_recoverable",
        "audited_rows": len(decisions),
        "decision_counts": dict(sorted(counts.items())),
        "methodological_decision": {
            "independent_is_continuing_party": False,
            "candidate_history_used_as_party_share": False,
            "zero_assigned_from_label_absence": False,
            "candidate_history_predictor_retained": True,
        },
        "decisions": decisions,
    }


def _is_auditable_independent_null(row: Mapping[str, object]) -> bool:
    """Select only later Independent rows with an approved previous area."""

    return (
        row.get("standard_party_name") == INDEPENDENT
        and row.get("previous_party_vote_share") is None
        and row.get("previous_party_vote_share_status") in AUDITABLE_STATUSES
        and isinstance(row.get("previous_election_id"), str)
        and bool(row.get("previous_election_id"))
        and isinstance(row.get("previous_area_id"), str)
        and bool(row.get("previous_area_id"))
    )


def _candidate_index(
    candidate_results: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], tuple[Mapping[str, object], ...]]:
    """Index complete official candidate tables by election and area ID."""

    grouped: defaultdict[
        tuple[str, str], list[Mapping[str, object]]
    ] = defaultdict(list)
    for candidate in candidate_results:
        key = (
            str(candidate.get("election_id", "")),
            str(candidate.get("division_id", "")),
        )
        if not all(key):
            raise ValueError("Candidate result has an incomplete election-area key.")
        grouped[key].append(candidate)
    return {key: tuple(rows) for key, rows in grouped.items()}


def _independents(
    candidates: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Return candidates published under the reviewed Independent identity."""

    return tuple(
        candidate
        for candidate in candidates
        if candidate.get("standard_party_name") == INDEPENDENT
    )


def _verified_same_candidate_matches(
    *,
    current_independents: Sequence[Mapping[str, object]],
    previous_independents: Sequence[Mapping[str, object]],
    previous_election_id: str,
) -> tuple[str, ...]:
    """Find same-name links only when the extractor already verified history.

    A name match alone is not treated as identity evidence. The current record
    must also carry a positive candidate-history value and explicitly list the
    approved previous election among its audited history events.
    """

    previous_names = {
        str(candidate.get("candidate_name", "")) for candidate in previous_independents
    }
    matches = []
    for candidate in current_independents:
        event_ids = {
            item.strip()
            for item in str(candidate.get("candidate_history_event_ids") or "").split(";")
            if item.strip()
        }
        name = str(candidate.get("candidate_name", ""))
        if (
            candidate.get("candidate_previously_stood") is True
            and previous_election_id in event_ids
            and name in previous_names
        ):
            matches.append(name)
    return tuple(sorted(matches))


def _decision(
    *,
    previous_independents: Sequence[Mapping[str, object]],
    verified_matches: Sequence[str],
) -> tuple[str, str]:
    """Explain why official candidate information cannot become party history."""

    if verified_matches:
        return (
            "candidate_history_available_not_party_history",
            "A verified candidate-level link exists, but Independent is not a "
            "continuing party. The history remains in candidate_previously_stood.",
        )
    if previous_independents:
        return (
            "different_or_ambiguous_independent_identity",
            "The previous result contains one or more Independent candidates, "
            "but no verified link identifies them as the current candidate.",
        )
    return (
        "generic_independent_label_not_continuing_entity",
        "No Independent candidate appears in the approved previous result, but "
        "absence of a generic label is not a zero for a continuing party.",
    )
