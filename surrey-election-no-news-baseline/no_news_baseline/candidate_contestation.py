"""Explicit records for parties that did not contest a seat.

The supervisor's brief singles this out:

    "an important distinction: if Reform didn't stand in a seat, that's not
    the same as a zero vote share -- it should be recorded properly as
    'did not contest'."

The candidate release is structurally correct already: a party with no
candidate simply has no row, so nothing anywhere claims it scored zero. What
it lacks is a *record*. Absence is not queryable - you cannot ask "in how many
2021 divisions did Reform decline to stand" of a table that has no rows for
them, and you cannot use non-contestation as a modelling signal or as a
denominator without first materialising it.

This module builds that record. It never enters the vote-share feature matrix,
because a contestation flag for the target election is only knowable once
nominations close, which the leakage audit treats as pre-election - but the
*outcome* of contesting is what the share model predicts, so mixing the two
would confuse the estimand. It exists for three other purposes the brief and
Prompt 2 need:

* reporting - how much of an election a party actually fought;
* denominators - "Reform's mean share across Surrey" means something quite
  different if it is averaged over 6 divisions or over 81;
* the news layer - Prompt 2 asks whether coverage predicts where Reform
  becomes a serious challenger, and "did they even stand" is the first,
  coarsest form of that question.

Why the party universe is per election, not global
---------------------------------------------------
A non-contest record only makes sense for a party that existed and was
contesting somewhere in that election. Emitting "Reform did not contest" for
2013 would state a fact about a party that had not yet been founded, and
"Official Monster Raving Loony did not contest" for all 343 areas would bury
the signal in noise. The universe for each election is therefore the set of
parties that fielded at least one candidate somewhere in that election.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from no_news_baseline.candidate_cohort import contest_key, is_within_candidate_cohort


CONTESTED = "contested"
DID_NOT_CONTEST = "did_not_contest"

# A party is only asked "did you contest here?" if it contested somewhere in
# that same election. See the module docstring.
UNIVERSE_RULE = "parties_fielding_at_least_one_candidate_in_that_election"


@dataclass(frozen=True)
class ContestationRecord:
    """One party's participation decision in one contest."""

    election_id: str
    election_date: str
    division_id: str
    division_name: str
    standard_party_name: str
    is_reform_uk: bool
    is_ukip: bool
    contestation_status: str
    candidates_fielded: int
    contest_structure: str
    seats: int | None

    def as_row(self) -> dict[str, object]:
        return {
            "election_id": self.election_id,
            "election_date": self.election_date,
            "division_id": self.division_id,
            "division_name": self.division_name,
            "standard_party_name": self.standard_party_name,
            "is_reform_uk": self.is_reform_uk,
            "is_ukip": self.is_ukip,
            "contestation_status": self.contestation_status,
            "candidates_fielded": self.candidates_fielded,
            "contest_structure": self.contest_structure,
            "analysis_number_of_seats": self.seats,
        }


def build_contestation_records(
    features: Iterable[Mapping[str, object]],
    *,
    exclude_independents: bool = True,
) -> tuple[ContestationRecord, ...]:
    """One row per election x division x party in that election's universe.

    ``exclude_independents`` is on by default. The release keeps every
    independent as its own political identity, so including them would emit
    "this specific independent did not contest" for every division they were
    never going to stand in - hundreds of rows asserting something nobody
    would claim. Party-level non-contestation is the meaningful quantity, and
    the flag is exposed so the choice is visible rather than silent.
    """

    rows = [row for row in features if is_within_candidate_cohort(row)]

    # Who stood where, and what each contest looks like.
    fielded: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    contest_meta: dict[tuple[str, str], Mapping[str, object]] = {}
    party_meta: dict[str, dict[str, bool]] = {}
    universe: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        if exclude_independents and row.get("party_category") == "independent":
            continue
        key = contest_key(row)
        party = str(row["standard_party_name"])
        fielded[key][party] += 1
        contest_meta.setdefault(key, row)
        universe[str(row["election_id"])].add(party)
        party_meta.setdefault(
            party,
            {"is_reform_uk": bool(row.get("is_reform_uk")),
             "is_ukip": bool(row.get("is_ukip"))},
        )

    records: list[ContestationRecord] = []
    for key, meta in sorted(contest_meta.items()):
        election_id, division_id = key
        seats = meta.get("analysis_number_of_seats")
        for party in sorted(universe[election_id]):
            count = fielded[key].get(party, 0)
            records.append(
                ContestationRecord(
                    election_id=election_id,
                    election_date=str(meta["election_date"]),
                    division_id=division_id,
                    division_name=str(meta["division_name"]),
                    standard_party_name=party,
                    is_reform_uk=party_meta[party]["is_reform_uk"],
                    is_ukip=party_meta[party]["is_ukip"],
                    contestation_status=CONTESTED if count else DID_NOT_CONTEST,
                    candidates_fielded=count,
                    contest_structure=str(meta["contest_structure"]),
                    seats=None if seats is None else int(seats),
                )
            )
    return tuple(records)


def contestation_summary(
    records: Iterable[ContestationRecord],
) -> dict[str, dict[str, object]]:
    """Per-election contest coverage, with Reform UK and UKIP called out.

    The brief asks for Reform UK results to be reported separately throughout,
    and coverage is the first such number: a mean vote share computed over the
    divisions a party fought says something different from one computed over
    every division in the county, and the difference is exactly this table.
    """

    by_election: dict[str, dict[str, object]] = {}
    grouped: dict[str, list[ContestationRecord]] = defaultdict(list)
    for record in records:
        grouped[record.election_id].append(record)

    for election_id, group in sorted(grouped.items()):
        divisions = {record.division_id for record in group}
        parties = {record.standard_party_name for record in group}

        def coverage(selector) -> dict[str, object]:
            selected = [record for record in group if selector(record)]
            stood = [record for record in selected if record.contestation_status == CONTESTED]
            return {
                "divisions_in_election": len(divisions),
                "divisions_contested": len(stood),
                "divisions_not_contested": len(selected) - len(stood),
                "contest_rate": (len(stood) / len(selected)) if selected else None,
                "candidates_fielded": sum(record.candidates_fielded for record in stood),
            }

        by_election[election_id] = {
            "election_date": group[0].election_date,
            "parties_in_universe": len(parties),
            "party_contest_rows": len(group),
            # Reform UK and UKIP are reported separately and never combined.
            "reform_uk": coverage(lambda record: record.is_reform_uk),
            "ukip": coverage(lambda record: record.is_ukip),
            "universe_rule": UNIVERSE_RULE,
        }
    return by_election


def reform_contest_history(
    records: Iterable[ContestationRecord],
) -> tuple[dict[str, object], ...]:
    """Every division Reform UK could have contested, and whether it did.

    Published as its own table because Prompt 2's central question - can
    coverage identify the wards where national momentum converts - has a
    coarser precursor that this table answers directly: which wards did Reform
    choose to fight at all, and when did that change.
    """

    return tuple(
        record.as_row()
        for record in sorted(
            (record for record in records if record.is_reform_uk),
            key=lambda record: (record.election_date, record.division_name),
        )
    )
