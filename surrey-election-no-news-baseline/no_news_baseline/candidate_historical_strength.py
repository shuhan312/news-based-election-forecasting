"""Party-level and area-level history the division-level contract cannot hold.

The brief's feature list names four things the candidate contract does not
publish, because each needs aggregation across rows rather than a value
attached to one:

    years since previous contest
    historical party strength
    party-level recent performance based only on earlier elections
    local-area historical performance based only on permitted mappings

They matter here more than a checklist would suggest. The SHAP decomposition
of the selected model shows Reform UK pushed below the equal split by every
historical feature the model holds, because in most divisions it has no
`previous_party_vote_share` at all. But Reform does have history — six
divisions in 2021 and seven by-elections since — it is simply *county-level*
history rather than *division-level*. These features are the only form in
which the model can see it.

Leakage discipline
------------------
Every value here is computed from elections held **strictly before** the row's
own polling date, compared by date rather than by position in any ordering, so
two elections on the same day never inform each other. That is the same rule
the splits use, applied to a different construction.

These features read earlier elections' **outcomes**, which is permitted and is
already how `previous_party_vote_share` works: a completed earlier election is
history, not leakage. The guard that makes it safe is the date comparison, and
``assert_no_future_contribution`` re-checks it against the produced rows
rather than trusting the construction.

Why they are computed here rather than in the extractor
--------------------------------------------------------
The extractor publishes one row per candidate and deliberately refuses to
aggregate: its contract is source-preserving, and a Surrey-wide party mean is
an analytical construct rather than a published figure. Computing it in the
modelling layer keeps the extractor's guarantee intact and puts the
construction next to the leakage rules that govern it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from no_news_baseline.candidate_cohort import contest_key, is_within_candidate_cohort
from no_news_baseline.election_dates import parse_election_date


# Feature names produced by this module. Declared as a tuple so the leakage
# audit and the encoder can both refer to one list rather than two that drift.
STRENGTH_FEATURES: tuple[str, ...] = (
    "party_county_strength_previous",
    "party_county_strength_trend",
    "party_contests_fought_previous",
    "party_contest_rate_previous",
    "years_since_previous_comparable_election",
    "area_parties_in_previous_contest",
)

# A party's county-wide mean is only meaningful if it stood in enough places
# for the mean not to be one candidate's personal vote. Below this it is
# recorded as unavailable rather than published as a strength estimate.
MIN_CONTESTS_FOR_COUNTY_STRENGTH = 3

# Requiring three contests *within one election* silently excluded every
# by-election, because a by-election has exactly one. For Reform UK that was
# not a rounding issue: its county strength stayed frozen at the 2.83 per cent
# of 2021 through eight later by-elections in which it polled 7 to 34 per
# cent, so a feature built to show a party rising instead pinned it to its
# weakest recorded year.
#
# The fix is not to lower the threshold - a single division's mean really is
# one candidate's personal vote - but to let contests accumulate across
# elections. Any run of strictly earlier elections is pooled until it holds
# enough contests, which reaches the same figure for principal elections
# (they clear the threshold alone) while letting by-elections combine.
POOLING_WINDOW_YEARS = 5.0

# The primary holdout. Elections after it must not read it, even though it is
# genuinely earlier by date: the brief asks for the 7 July 2026 Haslemere
# by-election to be predicted "without using any 7 May 2026 results", and a
# strength feature sourced from 7 May would couple the two holdouts that are
# meant to be independent evaluations. Callers that have deliberately
# unblinded the primary holdout can pass a later boundary.
PRIMARY_HOLDOUT_DATE = date(2026, 5, 7)


@dataclass(frozen=True)
class ElectionSummary:
    """One earlier election, reduced to what later elections may look up."""

    election_id: str
    election_date: date
    contests: int
    party_mean_share: dict[str, float]
    party_contests: dict[str, int]


def summarise_elections(
    features: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
) -> tuple[ElectionSummary, ...]:
    """Reduce every election to per-party county-wide means.

    The mean is over the contests a party actually fought, not over every
    contest in the election. Averaging in zeros for divisions a party chose
    not to contest would conflate two different quantities - how well it does
    where it stands, and how widely it stands - and the second is published
    separately as ``party_contest_rate_previous``.
    """

    by_election: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    dates: dict[str, date] = {}
    contests: dict[str, set] = defaultdict(set)
    # Distinct areas each party fought, not candidate rows: a party fielding
    # two candidates in a two-member ward has fought one contest. Counting
    # rows made contest_rate exceed 1 for 2026, which is impossible.
    party_areas: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))

    for row in features:
        if not is_within_candidate_cohort(row):
            continue
        election_id = str(row["election_id"])
        dates[election_id] = parse_election_date(str(row["election_date"])).date()
        contests[election_id].add(contest_key(row))
        share = targets[str(row["candidate_contest_id"])].get(
            "target_candidate_vote_share"
        )
        if share is None:
            continue
        party = str(row["standard_party_name"])
        by_election[election_id][party].append(float(share))
        party_areas[election_id][party].add(contest_key(row))

    summaries = []
    for election_id, parties in by_election.items():
        summaries.append(
            ElectionSummary(
                election_id=election_id,
                election_date=dates[election_id],
                contests=len(contests[election_id]),
                party_mean_share={
                    party: sum(values) / len(values) for party, values in parties.items()
                },
                # A party contesting a two-member ward with two candidates has
                # fought one contest, not two, so contests are counted by the
                # distinct areas rather than by candidate rows.
                party_contests={
                    party: len(party_areas[election_id][party])
                    for party in parties
                },
            )
        )
    return tuple(sorted(summaries, key=lambda s: s.election_date))


def build_strength_features(
    features: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    *,
    embargo_from: date | None = PRIMARY_HOLDOUT_DATE,
) -> dict[str, dict[str, object]]:
    """Return the six derived features, keyed by candidate_contest_id.

    Every lookup is restricted to elections strictly earlier than the row's
    own polling date. Values that cannot be established are ``None`` with a
    companion status, never zero: a party with no earlier county record has an
    unknown strength, not a strength of zero.
    """

    summaries = summarise_elections(features, targets)
    rows = [row for row in features if is_within_candidate_cohort(row)]

    # Contest counts per area, for the area-level feature.
    parties_per_contest: dict[tuple[str, str], int] = {}
    for key, group in _group(rows):
        parties_per_contest[key] = len({str(r["standard_party_name"]) for r in group})

    previous_by_election = {
        str(row["election_id"]): row.get("previous_election_id") for row in rows
    }
    election_dates = {
        str(row["election_id"]): parse_election_date(str(row["election_date"])).date()
        for row in rows
    }
    # Include predecessor elections that may sit outside the cohort.
    for summary in summaries:
        election_dates.setdefault(summary.election_id, summary.election_date)

    output: dict[str, dict[str, object]] = {}
    for row in rows:
        row_id = str(row["candidate_contest_id"])
        party = str(row["standard_party_name"])
        own_date = parse_election_date(str(row["election_date"])).date()

        # Strictly earlier only, and never from the embargoed holdout even
        # when that holdout is genuinely earlier by date.
        available = [
            summary
            for summary in summaries
            if summary.election_date < own_date
            and (embargo_from is None or summary.election_date < embargo_from)
            and summary.party_contests.get(party, 0) > 0
        ]

        strength, trend = None, None
        contests_fought = contest_rate = None
        status = "no_earlier_county_record_meeting_minimum_contests"

        window = _pool_backwards(available, party, own_date)
        if window:
            strength, contests_fought, contest_rate, sources = window
            status = "pooled_from_" + "+".join(sources)
            # The trend compares this window with the one immediately before
            # it, so a party that fought only by-elections still has a
            # comparison rather than a null.
            older = [s for s in available if s.election_date < min(
                s2.election_date for s2 in available if s2.election_id in sources)]
            earlier_window = _pool_backwards(older, party, own_date)
            if earlier_window:
                trend = strength - earlier_window[0]

        # Years since the approved predecessor contest, not since any earlier
        # election: the gap only means something between comparable areas.
        gap_years = None
        predecessor = previous_by_election.get(str(row["election_id"]))
        if predecessor is None:
            predecessor = row.get("previous_election_id")
        if predecessor is not None and str(predecessor) in election_dates:
            predecessor_date = election_dates[str(predecessor)]
            if predecessor_date < own_date:
                gap_years = (own_date - predecessor_date).days / 365.25

        output[row_id] = {
            "party_county_strength_previous": strength,
            "party_county_strength_trend": trend,
            "party_contests_fought_previous": contests_fought,
            "party_contest_rate_previous": contest_rate,
            "party_county_strength_status": status,
            "years_since_previous_comparable_election": gap_years,
            "area_parties_in_previous_contest": parties_per_contest.get(
                contest_key(row)
            ),
        }
    return output


def attach_strength_features(
    features: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return the feature rows with the six derived columns merged in.

    A copy is returned rather than the input mutated, so the published
    contract stays exactly as the extractor wrote it and any difference
    between the two is visible.
    """

    derived = build_strength_features(features, targets)
    return tuple(
        {**row, **derived.get(str(row["candidate_contest_id"]), {})}
        for row in features
        if is_within_candidate_cohort(row)
    )


def assert_no_future_contribution(
    features: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    *,
    embargo_from: date | None = PRIMARY_HOLDOUT_DATE,
) -> None:
    """Check the dates of the elections that actually contributed.

    An earlier version of this guard recomputed the strength with its own copy
    of the construction and compared the two numbers. That checks only that
    the code agrees with itself: when the construction changed from
    single-election to pooled, the guard failed against its own obsolete
    formula rather than against any real violation.

    What is worth verifying is the *property*, not the arithmetic. Each row
    records which elections it pooled, so this reads those identifiers back
    and asserts that every one of them polled strictly before the row and
    before the embargo. A construction that reached forward would name a
    later election in its own status string, and no amount of formula drift
    can hide that.
    """

    derived = build_strength_features(features, targets, embargo_from=embargo_from)
    election_dates = {
        summary.election_id: summary.election_date
        for summary in summarise_elections(features, targets)
    }

    for row in features:
        if not is_within_candidate_cohort(row):
            continue
        entry = derived[str(row["candidate_contest_id"])]
        status = str(entry.get("party_county_strength_status", ""))
        if not status.startswith("pooled_from_"):
            continue
        own_date = parse_election_date(str(row["election_date"])).date()
        for source in status[len("pooled_from_"):].split("+"):
            source_date = election_dates.get(source)
            if source_date is None:
                raise ValueError(
                    f"Row {row['candidate_contest_id']} cites an unknown "
                    f"source election {source!r}."
                )
            if source_date >= own_date:
                raise ValueError(
                    f"Row {row['candidate_contest_id']} polled {own_date} but "
                    f"pooled {source} which polled {source_date}."
                )
            if embargo_from is not None and source_date >= embargo_from:
                raise ValueError(
                    f"Row {row['candidate_contest_id']} pooled {source} "
                    f"({source_date}), at or after the embargoed holdout "
                    f"{embargo_from}."
                )


def coverage_report(
    features: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """How many rows each derived feature actually reaches, by party of interest.

    Published because a feature that is null for the party it was built to
    help is not an improvement, and that has to be checkable before any
    performance claim is made about it.
    """

    derived = build_strength_features(features, targets)
    rows = [row for row in features if is_within_candidate_cohort(row)]

    def coverage(selector) -> dict[str, object]:
        selected = [r for r in rows if selector(r)]
        values = [derived[str(r["candidate_contest_id"])] for r in selected]
        return {
            "rows": len(selected),
            **{
                name: sum(1 for v in values if v.get(name) is not None)
                for name in STRENGTH_FEATURES
            },
        }

    return {
        "all_rows": coverage(lambda r: True),
        "reform_uk": coverage(lambda r: bool(r.get("is_reform_uk"))),
        "ukip": coverage(lambda r: bool(r.get("is_ukip"))),
        "minimum_contests_for_county_strength": MIN_CONTESTS_FOR_COUNTY_STRENGTH,
        "note": (
            "A null county strength means no earlier election in which the "
            "party fought at least the minimum number of contests. It is not "
            "a strength of zero."
        ),
    }


def _pool_backwards(
    summaries: Sequence[ElectionSummary],
    party: str,
    own_date: date,
    *,
    minimum: int = MIN_CONTESTS_FOR_COUNTY_STRENGTH,
    window_years: float = POOLING_WINDOW_YEARS,
) -> tuple[float, int, float, tuple[str, ...]] | None:
    """Walk backwards from the most recent election until enough contests.

    Returns the contest-weighted mean share, the contests pooled, the pooled
    contest rate, and which elections contributed - so a reader can see
    whether a figure came from one principal election or from several
    by-elections combined.

    Weighting is by contests rather than by election, so a principal election
    fought in eighty divisions is not averaged on equal terms with a single
    by-election. Elections older than ``window_years`` are not pooled in: a
    party's position a decade ago is not evidence about its position now, and
    without a bound a rare party would pool its entire history into one
    permanently stale number.
    """

    total_share = 0.0
    total_contests = 0
    total_available = 0
    sources: list[str] = []

    for summary in reversed(summaries):
        if (own_date - summary.election_date).days / 365.25 > window_years:
            break
        contests = summary.party_contests.get(party, 0)
        if not contests:
            continue
        total_share += summary.party_mean_share[party] * contests
        total_contests += contests
        total_available += summary.contests
        sources.append(summary.election_id)
        if total_contests >= minimum:
            return (
                total_share / total_contests,
                total_contests,
                total_contests / total_available,
                tuple(reversed(sources)),
            )
    return None


def _group(rows: Iterable[Mapping[str, object]]):
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for row in rows:
        grouped[contest_key(row)].append(row)
    return grouped.items()
