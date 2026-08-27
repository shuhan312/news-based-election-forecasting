"""Candidate-level cohort, contest normalisation and seat allocation.

Why this module exists
----------------------
The earlier party-level benchmarks scored the *party* estimand on the
single-member subset (that route is retired to Git history).  That
cohort was methodologically sound but it contained no rows at all from 7 May
2026, because those elections were fought in two-member wards where a party
vote share is not a defined quantity.  The supervisor's Stage 1 brief makes
7 May 2026 the primary holdout, so the package needs a second, candidate-level
estimand that the holdout can actually be scored on.

This module owns that estimand's shared machinery, so that every candidate-
level model - the three compared architectures and eventually the Stage 2
news layer - uses one
implementation of "the cohort", "normalise within a contest", "rank" and
"allocate seats", rather than four subtly different ones.

It is pure logic: no file IO, no model fitting.  Scripts do the IO; models do
the fitting.

The estimand
------------
    target_candidate_vote_share = candidate votes / all votes cast in that
    contest

Verified against the published 2026 result pages: in the two-member Ashtead
Ward, twelve candidates' published shares sum to 101 against a total of 11,502
votes, i.e. the denominator is total votes cast, exactly as in a single-member
contest.  The quantity is therefore observed and comparable *within* every
contest regardless of seat count.

What is NOT claimed: that a 25% candidate share in a two-member ward means the
same politically as 25% in a single-member division.  A party fielding two
candidates splits its support across two ballot lines, so its per-candidate
shares are mechanically lower.  This module handles that by keeping contest
structure attached to every row and by requiring metrics to be reported by
structure (``stratify_by_structure``), never as one pooled average.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


ELIGIBLE_STATUS = "eligible_candidate_vote_share"

# Published shares are rounded, so a real contest sums to 100 only
# approximately.  Same derivation as the extractor's release check: at worst
# 0.5pp of rounding error per candidate, plus two points of slack for the
# source's own rounding of the total.
def contest_rounding_tolerance(candidate_count: int) -> float:
    """Return the acceptable deviation from 100 for a contest of this size."""

    return 2.0 + 0.5 * candidate_count


# --------------------------------------------------------------------------
# Release validation
# --------------------------------------------------------------------------


def assert_one_to_one_candidate_release(
    features: Sequence[Mapping[str, object]],
    targets: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    """Fail fast on a malformed release; return targets indexed by row id.

    The candidate-level release check (the retired party-level route carried
    its own analogue).  A shared, key-name-parameterised validator was
    deliberately avoided: it would make it possible to validate a candidate
    release against a party key by passing the wrong string.
    """

    feature_ids = [str(row["candidate_contest_id"]) for row in features]
    target_ids = [str(row["candidate_contest_id"]) for row in targets]
    if len(feature_ids) != len(set(feature_ids)) or len(target_ids) != len(
        set(target_ids)
    ):
        raise ValueError("Candidate-contest release contains duplicate identifiers.")
    if set(feature_ids) != set(target_ids):
        raise ValueError(
            "Feature and target candidate-contest identifiers do not match."
        )
    return {str(row["candidate_contest_id"]): row for row in targets}


# --------------------------------------------------------------------------
# Cohort definition
# --------------------------------------------------------------------------


def is_within_candidate_cohort(feature: Mapping[str, object]) -> bool:
    """True when a row can serve as a candidate-share prediction target.

    Deliberately does NOT test historical predictor availability.  That is the
    single substantive difference from the party cohort and the reason 2026
    now has rows: a changed-boundary ward has a missing predictor, not a
    missing outcome, and the brief asks for missingness indicators rather than
    complete-case deletion.

    Complete-case deletion here would not merely shrink the sample; it would
    bias it, because the wards that lack an approved predecessor are exactly
    the reorganised ones, and reorganisation is not independent of political
    change.
    """

    return feature.get("candidate_baseline_eligibility") == ELIGIBLE_STATUS


def contest_key(row: Mapping[str, object]) -> tuple[str, str]:
    """The grouping unit the brief mandates: ``election_id + division_id``.

    Used for three separate purposes that must never disagree: normalising
    predictions, allocating seats, and keeping a contest's candidates together
    in one fold ("All candidates from one contest must remain in the same
    split").
    """

    return (str(row["election_id"]), str(row["division_id"]))


def group_by_contest(
    rows: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], list[Mapping[str, object]]]:
    """Group rows by contest, preserving input order within each contest."""

    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[contest_key(row)].append(row)
    return dict(grouped)


# --------------------------------------------------------------------------
# Contest normalisation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalisedPrediction:
    """One candidate's prediction before and after contest normalisation.

    Both values are retained.  The raw value is what the model actually
    produced and is what feature-importance and residual diagnostics must be
    traced back to; the normalised value is what may be compared with the
    observed share or used to allocate seats.  Overwriting the raw value would
    make a normalisation bug indistinguishable from a modelling one.
    """

    candidate_contest_id: str
    raw_prediction: float
    normalised_prediction: float | None
    normalisation_status: str


def normalise_within_contest(
    predictions: Sequence[Mapping[str, object]],
    *,
    prediction_field: str = "predicted_candidate_vote_share",
) -> tuple[NormalisedPrediction, ...]:
    """Rescale one contest's predicted shares so they sum to 100.

    The target is compositional - the shares of the candidates on one ballot
    are shares of the same denominator - so an unconstrained per-row regression
    will not generally produce a set that sums to 100.  The brief requires this
    step explicitly ("Normalise predictions within each election_id and
    division_id contest where appropriate") and it is a precondition for
    ranking and seat allocation being meaningful.

    Three cases, each labelled rather than silently handled:

    ``normalised``
        The ordinary case.  Negative predictions are first clipped to zero,
        because a negative vote share is not in the target's support and
        would otherwise flip another candidate's sign during rescaling.
    ``normalised_equal_split_zero_mass``
        Every clipped prediction is zero, so there is no mass to rescale.
        Falling back to an equal split keeps the contest scorable and is the
        most conservative option available; the status makes it visible so it
        can be counted and, if it ever becomes common, investigated.
    ``not_normalised_missing_prediction``
        At least one candidate has no prediction, so the contest is not a
        complete composition.  Every row in it is returned unnormalised with
        ``None``.  Partially normalising a contest would silently redistribute
        the missing candidate's mass to the others.
    """

    rows = list(predictions)
    if not rows:
        return ()

    raw_values: list[float | None] = []
    for row in rows:
        value = row.get(prediction_field)
        raw_values.append(None if value is None else float(value))

    if any(value is None for value in raw_values):
        return tuple(
            NormalisedPrediction(
                candidate_contest_id=str(row["candidate_contest_id"]),
                # Keep whatever the model produced, including nothing.
                raw_prediction=float("nan") if value is None else value,
                normalised_prediction=None,
                normalisation_status="not_normalised_missing_prediction",
            )
            for row, value in zip(rows, raw_values)
        )

    clipped = [max(0.0, float(value)) for value in raw_values]
    total = sum(clipped)

    if total <= 0.0:
        equal = 100.0 / len(clipped)
        return tuple(
            NormalisedPrediction(
                candidate_contest_id=str(row["candidate_contest_id"]),
                raw_prediction=float(value),
                normalised_prediction=equal,
                normalisation_status="normalised_equal_split_zero_mass",
            )
            for row, value in zip(rows, raw_values)
        )

    return tuple(
        NormalisedPrediction(
            candidate_contest_id=str(row["candidate_contest_id"]),
            raw_prediction=float(raw),
            normalised_prediction=value * 100.0 / total,
            normalisation_status="normalised",
        )
        for row, raw, value in zip(rows, raw_values, clipped)
    )


# --------------------------------------------------------------------------
# Ranking and seat allocation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ContestAllocation:
    """Predicted rank and elected status for every candidate in one contest."""

    candidate_contest_id: str
    predicted_rank: int
    predicted_rank_tied: bool
    predicted_elected: bool
    allocation_status: str


def allocate_contest(
    predictions: Sequence[Mapping[str, object]],
    *,
    seats: int | None,
    prediction_field: str = "predicted_candidate_vote_share",
    tie_break_field: str = "candidate_contest_id",
) -> tuple[ContestAllocation, ...]:
    """Rank one contest's candidates and elect the top ``seats`` of them.

    This is where the multi-member holdout is actually served: the brief says
    to "use the known pre-election number of seats to select the predicted
    winner or winners", which generalises the single-member winner rule to two
    -member wards without any new assumption.  Seat count is a pre-election
    fact, so using it leaks nothing.

    Ties are made explicit rather than resolved by luck.  A deterministic
    tie-break on a stable identifier keeps reruns reproducible, but any
    candidate sharing a predicted share with another is flagged
    ``predicted_rank_tied``.  When a tie straddles the seat cutoff the whole
    contest is labelled ``allocated_with_tie_at_cutoff``, because the elected
    set is then an artefact of the tie-break rather than of the model, and
    seat-accuracy metrics should be able to report how often that happened.

    A contest with an unknown seat count is ranked but elects nobody: without
    ``seats`` there is no defensible cutoff, and inventing one would fabricate
    a result.
    """

    rows = list(predictions)
    if not rows:
        return ()

    if any(row.get(prediction_field) is None for row in rows):
        return tuple(
            ContestAllocation(
                candidate_contest_id=str(row["candidate_contest_id"]),
                predicted_rank=0,
                predicted_rank_tied=False,
                predicted_elected=False,
                allocation_status="not_allocated_missing_prediction",
            )
            for row in rows
        )

    # Descending by predicted share; ascending by a stable id for determinism.
    ordered = sorted(
        rows,
        key=lambda row: (
            -float(row[prediction_field]),
            str(row[tie_break_field]),
        ),
    )
    share_counts = Counter(float(row[prediction_field]) for row in rows)

    if seats is None:
        status = "not_elected_unknown_seat_count"
        elected_count = 0
    else:
        elected_count = max(0, min(int(seats), len(ordered)))
        status = "allocated"
        # A tie straddles the cutoff when the last elected and first unelected
        # candidates share a predicted value.
        if 0 < elected_count < len(ordered):
            last_in = float(ordered[elected_count - 1][prediction_field])
            first_out = float(ordered[elected_count][prediction_field])
            if last_in == first_out:
                status = "allocated_with_tie_at_cutoff"

    return tuple(
        ContestAllocation(
            candidate_contest_id=str(row["candidate_contest_id"]),
            predicted_rank=position,
            predicted_rank_tied=share_counts[float(row[prediction_field])] > 1,
            predicted_elected=position <= elected_count,
            allocation_status=status,
        )
        for position, row in enumerate(ordered, start=1)
    )


# --------------------------------------------------------------------------
# Reporting strata
# --------------------------------------------------------------------------


def stratify_by_structure(
    features: Iterable[Mapping[str, object]],
) -> dict[str, list[str]]:
    """Split cohort row ids by contest structure.

    Metrics must be reported for these strata separately as well as pooled.
    A pooled figure alone would be uninterpretable, because single-member and
    multi-member contests have different numbers of candidates and therefore
    different mean shares - a model could look better simply by being
    evaluated on more multi-member contests.
    """

    strata: dict[str, list[str]] = defaultdict(list)
    for row in features:
        if not is_within_candidate_cohort(row):
            continue
        strata[str(row["contest_structure"])].append(
            str(row["candidate_contest_id"])
        )
    return dict(strata)


def reform_census(
    features: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, int]]:
    """Count Reform UK and UKIP cohort rows per election.

    The brief requires reporting "the number of Reform observations used in
    each fold" and warning when Reform-specific estimates rest on a very small
    sample.  Publishing the census as data - rather than as a sentence in a
    report - lets fold construction and the warning threshold both read the
    same numbers.

    Reform UK and UKIP are counted into separate keys and never summed.
    """

    census: dict[str, dict[str, int]] = defaultdict(
        lambda: {"reform_uk": 0, "ukip": 0, "all_candidates": 0}
    )
    for row in features:
        if not is_within_candidate_cohort(row):
            continue
        election_id = str(row["election_id"])
        census[election_id]["all_candidates"] += 1
        if row.get("is_reform_uk"):
            census[election_id]["reform_uk"] += 1
        if row.get("is_ukip"):
            census[election_id]["ukip"] += 1
    return dict(census)
