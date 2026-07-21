"""Non-geographic naive reference rules for the no-news benchmark suite.

Purpose
-------
``persistence_benchmark.py`` shows how well "this exact area's own previous
result" predicts the current result. On its own, a single benchmark cannot
say whether that area-specific information is doing any real work: a rule
that ignores which division it is looking at might score almost as well,
simply because most parties keep a fairly stable Surrey-wide support level
between elections. This module supplies that missing comparison with naive
rules that deliberately do not use area identity (``division_id``) as
information, so that any advantage persistence_benchmark shows can be
attributed specifically to genuine local information rather than to party
identity alone.

The pairing implemented here follows the "persistence vs. climatology"
distinction standard in forecast verification, which is also the logic
behind Hanretty (2021, Section 5.4)'s comparison of his model against a
uniform-swing method, and Stoetzer et al. (2025, Sections 4-5.1)'s
fundamentals-only comparator:

* ``evaluate_equal_share_reference`` is the "no information at all" floor:
  split the vote equally among the parties known to be on the current
  ballot. It needs no historical data, so it can score every single-member
  row, including rows persistence_benchmark cannot score.
* ``evaluate_party_historical_mean_reference`` is a genuine "climatology"
  reference: the mean vote share that party has actually won anywhere in
  Surrey, in any election strictly before the target election, ignoring
  which division is being predicted. Hanretty's uniform-swing method plays
  an equivalent comparator role, but it relies on contemporaneous national
  polling data that does not exist for Surrey county elections; a historical
  cross-area mean is the closest no-news equivalent this project's own data
  can support.

Leakage discipline
-------------------
Both rules obey the rules declared in
``electoral_fundamentals_schema.LEAKAGE_RULES``. Neither rule aggregates
CURRENT-election results from other areas ("no_same_election_surrey_wide_
features"): the climatology pool is built strictly from elections whose own
``election_date`` predates the row being predicted, never from other areas
within the same target election.

Common support with the persistence benchmark
-----------------------------------------------
Both naive rules are eligible on a wider set of rows than
``persistence_benchmark.PRIMARY_COHORT_STATUS`` (neither needs this exact
area's own approved lagged share). Reporting only their own wider-eligible
figures next to persistence_benchmark's narrower figures would not be a fair
comparison (``docs/persistence_benchmark.md``, "Interpretation boundary": a
model does not show added value merely by scoring more rows). Every
prediction below is tagged with whether it falls inside
persistence_benchmark's own cohort, and the metrics block reports both the
full-cohort figures and a cohort-matched "common_support" figure.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime

from no_news_baseline.benchmark_metrics import (
    assert_one_to_one_party_contest_release,
    grouped_metrics,
    share_metrics_for_predictions,
    winner_metrics_for_predictions,
)
from no_news_baseline.persistence_benchmark import (
    is_within_share_cohort,
    is_within_winner_cohort,
)


def evaluate_equal_share_reference(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[tuple[dict[str, object], ...], dict[str, object], dict[str, int]]:
    """Predict an equal split of the vote among the current ballot's parties.

    This is the "no information" floor described in the module docstring: it
    uses only how many standardised parties are contesting the area, a fact
    that is public from nomination day and therefore genuinely available
    before the election, but no historical result of any kind. Any later
    benchmark that cannot beat this rule has not learned anything useful from
    the past.
    """

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = assert_one_to_one_party_contest_release(feature_rows, target_rows)

    # The party vote-share estimand is defined only for single-member
    # contests (see no_news_party_contest.py, ``_target_party_vote_share``),
    # so multi-member wards are out of scope here exactly as they are for
    # persistence_benchmark.
    eligible = [row for row in feature_rows if row["contest_structure"] == "single_member"]
    parties_per_area: dict[tuple[str, str], int] = defaultdict(int)
    for row in eligible:
        parties_per_area[(str(row["election_id"]), str(row["division_id"]))] += 1

    predictions: list[dict[str, object]] = []
    for feature in eligible:
        target = target_by_id[str(feature["party_contest_id"])]
        area_key = (str(feature["election_id"]), str(feature["division_id"]))
        predicted_share = 100.0 / parties_per_area[area_key]
        target_share = target.get("target_party_vote_share")
        has_target = isinstance(target_share, (int, float))
        error = predicted_share - float(target_share) if has_target else None
        predictions.append(
            {
                "party_contest_id": feature["party_contest_id"],
                "election_id": feature["election_id"],
                "election_year": feature["election_year"],
                "election_type": feature["election_type"],
                "division_id": feature["division_id"],
                "division_name": feature["division_name"],
                "standard_party_name": feature["standard_party_name"],
                "benchmark_id": "equal_share_reference_v1",
                "predicted_party_vote_share": predicted_share,
                "actual_party_vote_share": target_share if has_target else None,
                "share_error": error,
                "absolute_share_error": abs(error) if error is not None else None,
                "squared_share_error": error**2 if error is not None else None,
                # Every party on the ballot receives an identical predicted
                # share under this rule, so singling one out as "the winner"
                # would be an arbitrary tie-break rather than a genuine
                # prediction. The rule is deliberately silent on winners.
                "winner_prediction_status": "not_applicable_equal_share_reference",
                "predicted_party_elected": "Unknown",
                "actual_party_elected": target["target_party_elected"],
                "winner_prediction_correct": None,
                "within_persistence_share_cohort": is_within_share_cohort(feature),
                "within_persistence_winner_cohort": is_within_winner_cohort(feature),
                "target_source_urls": target["target_source_urls"],
            }
        )

    _assert_predictions_well_formed(predictions, expected_row_count=len(eligible))
    metrics = _metrics_block(
        benchmark_id="equal_share_reference_v1",
        research_interpretation=(
            "Equal division of the vote among the standardised parties on the current "
            "single-member ballot. Uses no historical data and makes no winner prediction; "
            "establishes the uninformed floor every other benchmark must beat."
        ),
        predictions=predictions,
    )
    audit = _share_audit(predictions)
    return tuple(predictions), metrics, audit


def evaluate_party_historical_mean_reference(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[tuple[dict[str, object], ...], dict[str, object], dict[str, int]]:
    """Predict each party's mean realised share in strictly earlier elections.

    This is the "climatology" reference described in the module docstring:
    for a party contesting a given target election, pool every election that
    has already happened by that date - anywhere in Surrey, not only this
    specific area - and average whatever share that party actually won
    wherever it stood. A brand-new party (most notably early Reform UK
    contests) has no such history and is left unscored rather than assigned
    an invented value; that is itself a research-relevant limitation, since
    identifying new-party momentum before it has a voting record is exactly
    the gap the supervisor's news-based models are meant to test (see
    ``Supervisor Requirement/Supervisor requirement.txt``: "Whether news can
    identify the emergence of a newer party before it has a substantial
    historical voting record").
    """

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = assert_one_to_one_party_contest_release(feature_rows, target_rows)

    eligible = [row for row in feature_rows if row["contest_structure"] == "single_member"]
    history_pool = _build_party_history_pool(eligible, target_by_id)

    predictions: list[dict[str, object]] = []
    for feature in eligible:
        target = target_by_id[str(feature["party_contest_id"])]
        target_election_date = _parse_election_date(str(feature["election_date"]))
        # Only elections that had already happened before this row's own
        # election qualify: this is the "source_date_precedes_target"
        # leakage rule applied across areas rather than within one area.
        prior_shares = [
            share
            for election_date, share in history_pool.get(str(feature["standard_party_name"]), ())
            if election_date < target_election_date
        ]
        climatology = sum(prior_shares) / len(prior_shares) if prior_shares else None
        target_share = target.get("target_party_vote_share")
        has_target = isinstance(target_share, (int, float))
        error = (
            climatology - float(target_share)
            if climatology is not None and has_target
            else None
        )
        predictions.append(
            {
                "party_contest_id": feature["party_contest_id"],
                "election_id": feature["election_id"],
                "election_year": feature["election_year"],
                "election_type": feature["election_type"],
                "division_id": feature["division_id"],
                "division_name": feature["division_name"],
                "standard_party_name": feature["standard_party_name"],
                "benchmark_id": "party_historical_mean_reference_v1",
                "predicted_party_vote_share": climatology,
                "actual_party_vote_share": target_share if has_target else None,
                "share_error": error,
                "absolute_share_error": abs(error) if error is not None else None,
                "squared_share_error": error**2 if error is not None else None,
                # Auditable evidence trail: how many prior elections fed the
                # mean, so a reviewer can see a thin two-observation average
                # apart from a well-supported one.
                "climatology_source_election_count": len(prior_shares),
                "within_persistence_share_cohort": is_within_share_cohort(feature),
                "within_persistence_winner_cohort": is_within_winner_cohort(feature),
                "target_source_urls": target["target_source_urls"],
                # Winner status is decided per area below, once every party's
                # climatology figure in that area is known.
                "winner_prediction_status": None,
                "predicted_party_elected": None,
                "actual_party_elected": target["target_party_elected"],
                "winner_prediction_correct": None,
            }
        )

    _assign_climatology_winner_predictions(predictions)
    _assert_predictions_well_formed(predictions, expected_row_count=len(eligible))
    metrics = _metrics_block(
        benchmark_id="party_historical_mean_reference_v1",
        research_interpretation=(
            "Mean realised party vote share across Surrey areas in elections strictly before "
            "the target election date. No parameters are fitted; a party with no qualifying "
            "prior election (most notably a new entrant) is left unscored rather than assigned "
            "an invented value."
        ),
        predictions=predictions,
    )
    audit = _climatology_audit(predictions)
    return tuple(predictions), metrics, audit


def _build_party_history_pool(
    rows: list[Mapping[str, object]],
    target_by_id: Mapping[str, Mapping[str, object]],
) -> dict[str, tuple[tuple[datetime, float], ...]]:
    """Index every row's own realised share by party, for date filtering.

    Each row's ``target_party_vote_share`` is the outcome of THAT row's own
    election. By the time a later election is being predicted, that outcome
    is settled historical fact rather than a "current" value to protect -
    exactly the same sense in which ``previous_party_vote_share`` already
    treats one area's immediately preceding result as a legitimate predictor
    (Hanretty 2021, Section 3.3). This function only pools those already-
    realised values across areas; it is never used to look up a row's own
    target to predict that same row (enforced by the strict date filter
    applied by the caller).
    """

    pool: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        target = target_by_id[str(row["party_contest_id"])]
        share = target.get("target_party_vote_share")
        if not isinstance(share, (int, float)):
            continue
        election_date = _parse_election_date(str(row["election_date"]))
        pool[str(row["standard_party_name"])].append((election_date, float(share)))
    return {party: tuple(entries) for party, entries in pool.items()}


def _assign_climatology_winner_predictions(predictions: list[dict[str, object]]) -> None:
    """Fill in winner fields area-by-area, mutating predictions in place.

    Mirrors persistence_benchmark's area-level gate: a winner is only called
    when exactly one party has the (unique) highest climatology figure among
    parties with a defined figure in that area. A tie, or an area where no
    party has any qualifying history, leaves every party in that area
    "Unknown" rather than guessing among near-equal or absent figures.
    """

    by_area: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in predictions:
        by_area[(str(row["election_id"]), str(row["division_id"]))].append(row)

    for area_rows in by_area.values():
        scored = [row for row in area_rows if row["predicted_party_vote_share"] is not None]
        best = max(
            (row["predicted_party_vote_share"] for row in scored), default=None
        )
        leaders = [row for row in scored if row["predicted_party_vote_share"] == best]
        area_eligible = best is not None and len(leaders) == 1
        status = (
            "eligible_unique_historical_mean_leader"
            if area_eligible
            else "unavailable_no_unique_historical_mean_leader"
        )
        leader_id = leaders[0]["party_contest_id"] if area_eligible else None
        for row in area_rows:
            row["winner_prediction_status"] = status
            row["predicted_party_elected"] = (
                ("Yes" if row["party_contest_id"] == leader_id else "No")
                if area_eligible
                else "Unknown"
            )
            row["winner_prediction_correct"] = (
                row["predicted_party_elected"] == row["actual_party_elected"]
                if row["predicted_party_elected"] != "Unknown"
                else None
            )


def _combined_metrics(rows: list[Mapping[str, object]]) -> dict[str, object]:
    result = share_metrics_for_predictions(rows)
    result.update(winner_metrics_for_predictions(rows))
    return result


def _metrics_block(
    benchmark_id: str,
    research_interpretation: str,
    predictions: list[dict[str, object]],
) -> dict[str, object]:
    """Full-cohort figures alongside a persistence-benchmark common-support figure.

    "full_cohort" scores every row this rule can predict. Because both naive
    rules here are eligible on more rows than persistence_benchmark, that
    figure alone is not comparable to persistence_benchmark's headline
    numbers. "common_support_with_persistence_benchmark" restricts scoring to
    the same rows persistence_benchmark itself scored, so the benchmarks can
    be read side by side (module docstring, "Common support").

    The share half and the winner half are restricted separately, each to
    persistence_benchmark's own respective cohort (775 vs 781 rows in the
    live release - see docs/persistence_benchmark.md), rather than being
    pooled into one combined row set first. persistence_benchmark's winner
    cohort is a strict superset of its share cohort, so pooling them with an
    "or" before scoring would silently let extra winner-cohort rows leak into
    the share comparison and inflate its row count past 775.
    """

    share_common_support = [
        row for row in predictions if row["within_persistence_share_cohort"]
    ]
    winner_common_support = [
        row for row in predictions if row["within_persistence_winner_cohort"]
    ]
    common_support_metrics = share_metrics_for_predictions(share_common_support)
    common_support_metrics.update(winner_metrics_for_predictions(winner_common_support))
    return {
        "benchmark_id": benchmark_id,
        "research_interpretation": research_interpretation,
        "full_cohort": {
            "overall": _combined_metrics(predictions),
            "by_election": grouped_metrics(predictions, "election_id", _combined_metrics),
            "by_election_year": grouped_metrics(
                predictions, "election_year", _combined_metrics
            ),
            "by_election_type": grouped_metrics(
                predictions, "election_type", _combined_metrics
            ),
        },
        "common_support_with_persistence_benchmark": common_support_metrics,
    }


def _assert_predictions_well_formed(
    predictions: list[Mapping[str, object]], expected_row_count: int
) -> None:
    # A missing row would silently bias both the full-cohort and the
    # common-support figures, so row count and identifier uniqueness are
    # checked explicitly rather than assumed from the construction logic.
    if len(predictions) != expected_row_count:
        raise ValueError("A naive-benchmark eligible row was lost during prediction.")
    if len({row["party_contest_id"] for row in predictions}) != len(predictions):
        raise ValueError("Naive benchmark predictions contain duplicate identifiers.")
    for row in predictions:
        predicted_share = row["predicted_party_vote_share"]
        if predicted_share is not None and not 0 <= float(predicted_share) <= 100:
            raise ValueError("Predicted share lies outside 0-100.")
        if row["predicted_party_elected"] == "Unknown" and row["winner_prediction_correct"] is not None:
            raise ValueError("An unavailable winner prediction was scored.")


def _share_audit(predictions: list[Mapping[str, object]]) -> dict[str, int]:
    counts = Counter(
        {
            "party_share_rows_full_cohort": sum(
                row["predicted_party_vote_share"] is not None for row in predictions
            ),
            "party_share_rows_common_support": sum(
                row["predicted_party_vote_share"] is not None
                and row["within_persistence_share_cohort"]
                for row in predictions
            ),
            "winner_party_rows_common_support": sum(
                row["predicted_party_elected"] != "Unknown"
                and row["within_persistence_winner_cohort"]
                for row in predictions
            ),
        }
    )
    for row in predictions:
        counts[f"winner_status_{row['winner_prediction_status']}"] += 1
    return dict(sorted(counts.items()))


def _climatology_audit(predictions: list[Mapping[str, object]]) -> dict[str, int]:
    counts = Counter(_share_audit(predictions))
    counts["party_rows_without_qualifying_history"] = sum(
        row["predicted_party_vote_share"] is None for row in predictions
    )
    return dict(sorted(counts.items()))


def _parse_election_date(value: str) -> datetime:
    """Parse the ``election_date`` string used throughout the data contract.

    Duplicated intentionally rather than imported from the extractor: this
    modelling project does not import the extractor's internal Python
    package (README, "The modelling layer... does not import the extractor's
    internal Python modules"), and this is the smallest possible piece of
    logic needed to compare election dates chronologically.
    """

    for date_format in ("%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    raise ValueError(f"Unsupported election date: {value!r}")
