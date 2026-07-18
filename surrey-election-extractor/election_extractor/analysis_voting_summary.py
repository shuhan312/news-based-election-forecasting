"""Publish analysis-ready voting-summary values without changing official fields.

The supervisor needs Seats, issued ballots, turnout and rejected ballots for
modelling.  Surrey publishes these through a mixture of official result pages,
separately cited official evidence and narrowly governed calculations.  This
module selects the strongest already-audited value for analysis while retaining
the official column and the source/provenance layer unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping


_FIELD_SOURCES = {
    "number_of_seats": ("official_number_of_seats", "secondary_number_of_seats", None),
    "ballot_papers_issued": (
        "ballot_papers_issued",
        "secondary_division_ballot_papers_issued",
        "derived_ballot_papers_issued",
    ),
    "turnout": ("turnout", "secondary_division_turnout", None),
    "rejected_ballots": ("rejected_ballots", None, "derived_rejected_ballots"),
}


def build_analysis_voting_summary(
    divisions: Iterable[Mapping[str, object]],
    supplementary_metadata: Iterable[Mapping[str, object]],
    derived_metadata: Iterable[Mapping[str, object]],
    candidate_results: Iterable[Mapping[str, object]] = (),
) -> tuple[dict[str, object], ...]:
    """Return one provenance-labelled analysis value per requested field.

    Precedence is deliberately fixed: official result-page value, then a
    separately cited official supplementary record, then a governed derived
    value.  An absent value remains NULL; this function never estimates a
    statistic or treats a supplementary/derived value as official.
    """

    division_rows = tuple(divisions)
    candidate_rows_by_division: defaultdict[str, list[Mapping[str, object]]] = (
        defaultdict(list)
    )
    for candidate in candidate_results:
        candidate_rows_by_division[str(candidate["division_id"])].append(candidate)

    supplementary = {
        (str(row["division_id"]), str(row["field_name"])): row
        for row in supplementary_metadata
        if row.get("division_id") is not None
    }
    derived = {
        (str(row["division_id"]), str(row["field_name"])): row
        for row in derived_metadata
        if row.get("division_id") is not None
    }
    rows: list[dict[str, object]] = []
    for division in division_rows:
        division_id = str(division["division_id"])
        analysis_seats: object = None
        analysis_seats_provenance = "unavailable"
        analysis_seats_source_id: object = None
        for analysis_field, (official_field, supplementary_field, derived_field) in _FIELD_SOURCES.items():
            official_value = division.get(official_field)
            selected_value = official_value
            provenance = "official_result_page" if official_value is not None else "unavailable"
            source_id = None
            if selected_value is None and supplementary_field:
                # Seats evidence is already denormalised into the division
                # table; the other supplementary values remain in metadata.
                source = supplementary.get((division_id, supplementary_field))
                secondary_value = (
                    division.get(supplementary_field)
                    if supplementary_field == "secondary_number_of_seats"
                    else source.get("value") if source is not None else None
                )
                if secondary_value is not None:
                    selected_value = secondary_value
                    provenance = "supplementary_official_evidence"
                    source_id = source.get("metadata_id") if source is not None else None
            if selected_value is None and derived_field:
                source = derived.get((division_id, derived_field))
                if source is not None:
                    selected_value = source.get("value")
                    provenance = "governed_derived_value"
                    source_id = source.get("metadata_id")
            rows.append(
                {
                    "election_id": division["election_id"],
                    "division_id": division_id,
                    "division_name": division["division_name"],
                    "field_name": f"analysis_{analysis_field}",
                    "value": selected_value,
                    "provenance_layer": provenance,
                    "source_metadata_id": source_id,
                    "official_field_name": official_field,
                    "official_value": official_value,
                }
            )
            if analysis_field == "number_of_seats":
                # Winning-margin eligibility uses the already selected
                # analysis Seats value. This permits separately cited statutory
                # evidence without relabelling it as result-page evidence.
                analysis_seats = selected_value
                analysis_seats_provenance = provenance
                analysis_seats_source_id = source_id

        margin_value, margin_provenance = _analysis_winning_margin(
            official_margin=division.get("winning_margin"),
            analysis_seats=analysis_seats,
            analysis_seats_provenance=analysis_seats_provenance,
            candidates=candidate_rows_by_division.get(division_id, []),
        )
        rows.append(
            {
                "election_id": division["election_id"],
                "division_id": division_id,
                "division_name": division["division_name"],
                "field_name": "analysis_winning_margin",
                "value": margin_value,
                "provenance_layer": margin_provenance,
                # For the 28 affected 2021 divisions this points back to the
                # statutory Seats record that authorises single-seat analysis.
                "source_metadata_id": analysis_seats_source_id,
                "official_field_name": "winning_margin",
                "official_value": division.get("winning_margin"),
            }
        )
    return tuple(rows)


def _analysis_winning_margin(
    *,
    official_margin: object,
    analysis_seats: object,
    analysis_seats_provenance: str,
    candidates: Iterable[Mapping[str, object]],
) -> tuple[object, str]:
    """Select or calculate the last-seat winning margin for one contest.

    The formula is the lowest officially elected vote total minus the highest
    officially non-elected vote total. It is the ordinary winner/runner-up gap
    in a single-seat contest and the final-seat cutoff gap in a multi-seat
    contest. Official outcomes identify both groups; votes never choose or
    replace an officially published winner.
    """

    if official_margin is not None:
        return official_margin, "official_result_page"
    if not isinstance(analysis_seats, int) or analysis_seats < 1:
        return None, "unavailable_missing_or_invalid_seats_evidence"

    candidate_rows = tuple(candidates)
    elected = [row for row in candidate_rows if row.get("outcome") == "Elected"]
    not_elected = [
        row for row in candidate_rows if row.get("outcome") == "Not elected"
    ]
    if (
        len(elected) != analysis_seats
        or not not_elected
        or len(elected) + len(not_elected) != len(candidate_rows)
        or any(
            not isinstance(row.get("votes"), int) or row["votes"] < 0
            for row in candidate_rows
        )
    ):
        return None, "unavailable_incomplete_official_candidate_evidence"

    # The weakest elected candidate defines the final seat; the strongest
    # non-elected candidate is the nearest challenger. This definition is
    # identical across one- and multi-seat contests.
    winner_votes = min(row["votes"] for row in elected)
    runner_up_votes = max(row["votes"] for row in not_elected)
    assert isinstance(runner_up_votes, int)
    assert isinstance(winner_votes, int)
    if winner_votes < runner_up_votes:
        return None, "unavailable_official_outcome_cutoff_vote_conflict"

    seats_layer = (
        "official_seats"
        if analysis_seats_provenance == "official_result_page"
        else "supplementary_official_seats"
    )
    return (
        winner_votes - runner_up_votes,
        f"governed_derived_from_official_candidate_votes_and_{seats_layer}",
    )
