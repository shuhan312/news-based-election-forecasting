"""Seat-count and election-date validation for the modelling contract.

The brief's data-validation list includes "validate the number of seats" and
"validate election dates". Both were missing: the data-quality report checked
identifiers, share ranges and contest reconciliation, but nothing asserted
that a contest's seat count was coherent or that its date was.

Both checks matter for specific, non-hypothetical reasons in this dataset.

**Seats** decide the prediction. Predicted elected status is "top *N* by
predicted share" where *N* is the seat count, so a wrong seat count does not
degrade a prediction, it produces a different prediction that looks equally
valid. A contest whose rows disagreed about *N* would silently allocate a
different number of seats depending on which row was read first.

**Dates** decide the split. Every fold boundary is a date comparison, so a
row dated wrongly does not merely carry a wrong feature - it moves between
training and test. A 2026 row dated 2021 would train on the holdout, which is
the one failure this project's whole design exists to prevent.

Findings are returned as data rather than raised, because the data-quality
report is meant to describe the contract including its problems. The build
raises separately on the checks that must never fail.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

from .election_dates import parse_election_date

# The study period. Anything outside it is a data error rather than an
# unusual election: Surrey's first modelled county election is 2013 and the
# secondary holdout is the latest event in the workbook.
EARLIEST_PLAUSIBLE = date(2013, 1, 1)
LATEST_PLAUSIBLE = date(2026, 12, 31)


def _by_contest(
    rows: Sequence[Mapping[str, object]]
) -> dict[tuple[str, str], list[Mapping[str, object]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["election_id"]), str(row["division_id"]))].append(row)
    return dict(grouped)


def seat_validation(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Check that every contest's seat count is coherent.

    Four properties, each of which would change a prediction if violated:

    1. at least one seat - a contest electing nobody is not a contest;
    2. one seat count per contest - rows of one contest must agree;
    3. seats no greater than candidates - more seats than candidates would
       mean electing people who did not stand, and would make the top-N
       allocation return the whole ballot;
    4. ``contest_structure`` agrees with the count, since the structure label
       is derived from it and a disagreement means one of them is stale.
    """

    non_positive: list[str] = []
    inconsistent: list[dict[str, object]] = []
    more_seats_than_candidates: list[dict[str, object]] = []
    structure_mismatch: list[dict[str, object]] = []
    seats_by_structure: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    for key, group in sorted(_by_contest(rows).items()):
        contest = f"{key[0]}|{key[1]}"
        seats = {int(row["analysis_number_of_seats"]) for row in group}

        if len(seats) > 1:
            inconsistent.append({"contest": contest, "seat_counts": sorted(seats)})
            continue

        count = seats.pop()
        if count < 1:
            non_positive.append(contest)
            continue

        candidates = len(group)
        if count > candidates:
            more_seats_than_candidates.append(
                {"contest": contest, "seats": count, "candidates": candidates}
            )

        # candidate_count_in_contest is published per row; it must equal the
        # number of rows actually present, or the two disagree about what the
        # contest contained.
        declared = {int(row["candidate_count_in_contest"]) for row in group}
        if declared != {candidates}:
            more_seats_than_candidates.append({
                "contest": contest,
                "declared_candidate_count": sorted(declared),
                "rows_present": candidates,
                "note": "declared candidate count disagrees with rows present",
            })

        structures = {str(row["contest_structure"]) for row in group}
        expected = "single_member" if count == 1 else "multi_member"
        if structures != {expected}:
            structure_mismatch.append({
                "contest": contest, "seats": count,
                "contest_structure": sorted(structures), "expected": expected,
            })

        for structure in structures:
            seats_by_structure[structure][count] += 1

    return {
        "contests_checked": len(_by_contest(rows)),
        "contests_with_non_positive_seats": non_positive,
        "contests_with_inconsistent_seat_counts": inconsistent,
        "contests_with_more_seats_than_candidates": more_seats_than_candidates,
        "contests_where_structure_disagrees_with_seats": structure_mismatch,
        "contest_counts_by_structure_and_seats": {
            structure: dict(sorted(counts.items()))
            for structure, counts in sorted(seats_by_structure.items())
        },
        "all_checks_passed": not (
            non_positive or inconsistent or more_seats_than_candidates
            or structure_mismatch
        ),
    }


def election_date_validation(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Check that every row's polling date is parseable, plausible and consistent.

    Four properties:

    1. the date parses - an unparseable date cannot be compared to a fold
       boundary, so the row would land wherever the comparison happened to
       fall;
    2. it lies inside the study period;
    3. one date per election_id - an election has one polling day, and two
       would split its contests across a fold boundary;
    4. ``election_year`` matches the date's year, since a mismatch means one
       of the two was edited without the other.
    """

    unparseable: list[dict[str, object]] = []
    implausible: list[dict[str, object]] = []
    year_mismatch: list[dict[str, object]] = []
    dates_by_election: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        row_id = str(row["candidate_contest_id"])
        raw = str(row["election_date"])
        try:
            parsed = parse_election_date(raw).date()
        except Exception as error:  # noqa: BLE001 - reported, not raised
            unparseable.append({"row": row_id, "election_date": raw,
                                "error": str(error)})
            continue

        dates_by_election[str(row["election_id"])].add(parsed.isoformat())

        if not EARLIEST_PLAUSIBLE <= parsed <= LATEST_PLAUSIBLE:
            implausible.append({"row": row_id, "election_date": parsed.isoformat()})

        declared_year = row.get("election_year")
        if declared_year is not None and int(declared_year) != parsed.year:
            year_mismatch.append({
                "row": row_id, "election_date": parsed.isoformat(),
                "election_year": int(declared_year),
            })

    multiple_dates = {
        election_id: sorted(dates)
        for election_id, dates in sorted(dates_by_election.items())
        if len(dates) > 1
    }
    # Contests must not straddle dates either; this is the property the split
    # design relies on, so it is checked rather than assumed.
    contest_multiple_dates = [
        f"{key[0]}|{key[1]}"
        for key, group in sorted(_by_contest(rows).items())
        if len({str(row["election_date"]) for row in group}) > 1
    ]

    all_dates = sorted({d for dates in dates_by_election.values() for d in dates})
    return {
        "rows_checked": len(rows),
        "elections_checked": len(dates_by_election),
        "unparseable_dates": unparseable,
        "dates_outside_study_period": implausible,
        "elections_with_more_than_one_date": multiple_dates,
        "contests_spanning_more_than_one_date": contest_multiple_dates,
        "rows_where_election_year_disagrees_with_date": year_mismatch,
        "distinct_polling_dates": all_dates,
        "earliest_polling_date": all_dates[0] if all_dates else None,
        "latest_polling_date": all_dates[-1] if all_dates else None,
        "all_checks_passed": not (
            unparseable or implausible or multiple_dates
            or contest_multiple_dates or year_mismatch
        ),
    }
