"""Predicted winning party and party seat totals, as exported outputs.

The brief lists seven things the model must "produce": candidate vote share,
rank, elected status, probability of election, **predicted winning party or
parties**, **predicted party seat totals**, and Reform UK-specific
predictions. The first four and the last were exported; the two in bold were
computed only far enough to score them. ``metrics.json`` carried
``party_seat_total_absolute_error`` — the *error* in the seat totals — with no
artefact anywhere stating what the predicted totals actually were.

That is the wrong way round. A seat projection is the output a reader wants
first and the one they can check against the real result themselves; an error
statistic summarising it is downstream of it. This module produces the
projection, and the error is then computed from the same numbers rather than
in parallel with them.

Ties are recorded, not resolved
-------------------------------
A contest whose seat boundary falls inside a group of equally predicted
candidates has no single winning party under this model. Breaking the tie
arbitrarily would manufacture a prediction the model did not make, so the
contest reports every party tied on the boundary and a status saying so.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

# Rank positions this far apart in predicted share are treated as tied. Set
# small: predictions are shares in percentage points, so a thousandth of a
# point is numerical noise rather than a distinction.
TIE_TOLERANCE = 1e-6


def _as_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def contest_projections(
    predictions: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """One row per contest: who is predicted to win it, and who actually did.

    ``predictions`` are the per-candidate prediction records the fold code
    already produces, so this reads the shipped architecture's own output
    rather than recomputing anything.
    """

    contests: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in predictions:
        contests[(str(row["election_id"]), str(row["division_id"]))].append(row)

    projections: list[dict[str, object]] = []
    for (election_id, division_id), rows in sorted(contests.items()):
        seats = int(_as_float(rows[0].get("analysis_number_of_seats")) or 1)
        ordered = sorted(
            rows,
            key=lambda row: (-(_as_float(row.get("predicted_vote_share")) or 0.0),
                             str(row.get("standard_party_name"))),
        )
        winners = ordered[:seats]

        # A candidate outside the seat boundary but level with the last one
        # inside it is a tie the model did not break.
        boundary = _as_float(winners[-1].get("predicted_vote_share")) if winners else None
        tied_out = [
            row for row in ordered[seats:]
            if boundary is not None
            and abs((_as_float(row.get("predicted_vote_share")) or 0.0) - boundary)
            <= TIE_TOLERANCE
        ]

        predicted_parties = sorted(
            {str(row["standard_party_name"]) for row in winners}
        )
        observed_winners = [
            row for row in rows
            if str(row.get("observed_elected")).lower() in {"true", "1", "yes"}
        ]
        observed_parties = sorted(
            {str(row["standard_party_name"]) for row in observed_winners}
        )

        projections.append({
            "election_id": election_id,
            "division_id": division_id,
            "election_date": rows[0].get("election_date"),
            "contest_structure": rows[0].get("contest_structure"),
            "seats": seats,
            "candidates": len(rows),
            "predicted_winning_parties": "|".join(predicted_parties),
            "predicted_winning_candidates": "|".join(
                str(row.get("candidate_contest_id")) for row in winners
            ),
            "observed_winning_parties": "|".join(observed_parties),
            "winning_parties_correct": (
                predicted_parties == observed_parties if observed_parties else None
            ),
            "tie_at_seat_boundary": bool(tied_out),
            "tied_parties_at_boundary": "|".join(sorted(
                {str(row["standard_party_name"]) for row in tied_out}
            )),
            "reform_predicted_elected": any(
                str(row.get("is_reform_uk")).lower() in {"true", "1", "yes"}
                for row in winners
            ),
            "reform_observed_elected": any(
                str(row.get("is_reform_uk")).lower() in {"true", "1", "yes"}
                for row in observed_winners
            ),
        })
    return tuple(projections)


def party_seat_totals(
    predictions: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Predicted and observed seat totals per party, per election.

    Per election rather than pooled, because a total across elections held
    years apart is not a quantity anybody wants: the interesting comparison is
    "how did the model do on this election's council", and pooling hides an
    election where it did badly behind one where it did well.

    Parties are listed if they won a seat in *either* the prediction or the
    result, so a party the model wrongly awarded seats to appears with an
    observed total of zero rather than being absent.
    """

    projections = contest_projections(predictions)
    predicted: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    observed: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for projection in projections:
        election = str(projection["election_id"])
        # A two-member ward won by one party contributes two seats to it, so
        # the seats are counted from the winning candidates, not the parties.
        for row_id, party in zip(
            str(projection["predicted_winning_candidates"]).split("|"),
            _parties_per_seat(predictions, projection, predicted_side=True),
        ):
            if row_id:
                predicted[election][party] += 1
        for party in _parties_per_seat(predictions, projection, predicted_side=False):
            observed[election][party] += 1

    totals: list[dict[str, object]] = []
    for election in sorted(set(predicted) | set(observed)):
        parties = sorted(set(predicted[election]) | set(observed[election]))
        for party in parties:
            predicted_seats = predicted[election].get(party, 0)
            observed_seats = observed[election].get(party, 0)
            totals.append({
                "election_id": election,
                "standard_party_name": party,
                "predicted_seats": predicted_seats,
                "observed_seats": observed_seats,
                "seat_error": predicted_seats - observed_seats,
                "absolute_seat_error": abs(predicted_seats - observed_seats),
            })
    return tuple(totals)


def _parties_per_seat(
    predictions: Sequence[Mapping[str, object]],
    projection: Mapping[str, object],
    *,
    predicted_side: bool,
) -> list[str]:
    """The party of each seat won in one contest, one entry per seat."""

    key = (str(projection["election_id"]), str(projection["division_id"]))
    rows = [
        row for row in predictions
        if (str(row["election_id"]), str(row["division_id"])) == key
    ]
    if predicted_side:
        seats = int(projection["seats"])
        ordered = sorted(
            rows,
            key=lambda row: (-(_as_float(row.get("predicted_vote_share")) or 0.0),
                             str(row.get("standard_party_name"))),
        )
        return [str(row["standard_party_name"]) for row in ordered[:seats]]
    return [
        str(row["standard_party_name"]) for row in rows
        if str(row.get("observed_elected")).lower() in {"true", "1", "yes"}
    ]


def seat_projection_summary(
    predictions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Headline figures over the projections, for metrics.json."""

    projections = contest_projections(predictions)
    scored = [p for p in projections if p["winning_parties_correct"] is not None]
    totals = party_seat_totals(predictions)

    by_election: dict[str, int] = defaultdict(int)
    for total in totals:
        by_election[str(total["election_id"])] += int(total["absolute_seat_error"])

    return {
        "contests": len(projections),
        "contests_scored": len(scored),
        "winning_party_set_correct": (
            sum(1 for p in scored if p["winning_parties_correct"]) / len(scored)
            if scored else None
        ),
        "contests_with_a_tie_at_the_seat_boundary": sum(
            1 for p in projections if p["tie_at_seat_boundary"]
        ),
        "party_seat_total_absolute_error_by_election": dict(sorted(by_election.items())),
        "party_seat_total_absolute_error": sum(by_election.values()),
        "reform_uk": {
            "contests_predicted_elected": sum(
                1 for p in projections if p["reform_predicted_elected"]
            ),
            "contests_observed_elected": sum(
                1 for p in projections if p["reform_observed_elected"]
            ),
        },
    }
