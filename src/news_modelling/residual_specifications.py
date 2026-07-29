"""Build the five model specifications, with news attached to the right party.

The comparison the project is built to make:

    1. no-news baseline      the frozen Stage 1 model, nothing added
    2. local news            division-level coverage only
    3. national news         election-wide coverage only
    4. combined              both
    5. full                  both, plus permitted baseline context

Local and national are kept apart throughout, because they are hypothesised to
do different jobs - national coverage showing whether a party is rising at
all, local coverage showing which divisions convert that into votes. A single
pooled "news" block would answer neither question, since one coefficient
cannot say which mechanism produced it.

The join is on party, not only on place
---------------------------------------
An earlier version of this join keyed news rows on ``(election, division)``
alone. Each division carries one news row per party per window - five parties
and three windows in the 2021 sample - so the rows overwrote each other and
whichever survived was attached to every candidate in the division regardless
of party. A candidate for Reform UK would have been given the Conservatives'
coverage. Every figure produced that way was about the wrong thing.

News rows are therefore keyed on ``(election, division, party, window)``, and
a candidate only ever sees coverage of their own party - plus the
party-agnostic rows described next.

Two kinds of news row, treated differently
------------------------------------------
Some rows name a focal party: coverage *of the Conservatives* in Guildford
East. Those attach only to that party's candidates.

Others carry ``(no_focal_party)``: a planning row, a council-finance story,
coverage of the division rather than of anyone standing in it. Those attach to
every candidate in the division, because they are context that applies to the
contest as a whole. Discarding them would throw away most of the local
corpus; attaching them to one party would invent a slant the article does not
have.

Both kinds keep their own feature prefixes, so a model can distinguish "my
party was covered" from "this division was in the news".
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

from .news_arms import ARM_SCOPES, SPECIFICATIONS
from .residual_dataset import (
    ELECTION_WIDE,
    NEWS_ELECTION_DATES,
    normalise_division,
)

# The token the aggregation uses for a row that is about a place or an issue
# rather than about a named party.
NO_FOCAL_PARTY = "(no_focal_party)"

# Feature name prefixes, so a model and a reader can tell the four sources
# apart without consulting anything.
PREFIX_LOCAL_PARTY = "local_party"
PREFIX_LOCAL_CONTEXT = "local_context"
PREFIX_NATIONAL_PARTY = "national_party"
PREFIX_NATIONAL_CONTEXT = "national_context"


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _to_float(value: object) -> float | None:
    text = str(value).strip()
    if text in {"", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def index_news(
    news_rows: Sequence[Mapping[str, object]],
    party_names: Mapping[str, str],
    *,
    arm: str,
) -> dict[tuple, list[Mapping[str, object]]]:
    """Group one arm's news rows by everything a candidate row must match on.

    Local rows are keyed by ``(news_election, division, party, window)`` and
    national rows by ``(news_election, party, window)`` - the national tier has
    no division, which is the whole point of the distinction. Values are lists
    rather than single rows, because a division and party can legitimately have
    several rows for one window if the aggregation split them by scope.
    """

    scopes = ARM_SCOPES.get(arm, frozenset())
    index: dict[tuple, list[Mapping[str, object]]] = defaultdict(list)

    for row in news_rows:
        if str(row.get("scope_classification")) not in scopes:
            continue

        target = str(row.get("geographic_target_id", ""))
        _, _, place = target.partition(":")
        is_national = (not place) or place == ELECTION_WIDE

        # An arm only indexes the tier it is about. A national arm that
        # silently included division rows would make the local and national
        # models overlap, and the comparison between them meaningless.
        if arm == "local" and is_national:
            continue
        if arm == "national" and not is_national:
            continue

        party_id = str(row.get("focal_party_id") or NO_FOCAL_PARTY)
        party = party_names.get(party_id, party_id)
        window = str(row.get("window") or "")
        election = str(row.get("election_id"))

        key = ((election, party, window) if is_national
               else (election, normalise_division(place), party, window))
        index[key].append(row)
    return dict(index)


def feature_block(
    rows: Sequence[Mapping[str, object]],
    prefix: str,
    window: str,
    feature_columns: Sequence[str],
) -> dict[str, object]:
    """One window's worth of features from one group of news rows.

    Summed rather than averaged: these are counts of articles, publications
    and mentions, and two rows covering the same division from different
    scopes describe more coverage, not the same coverage twice. A mean would
    make two matching rows look like one.
    """

    block: dict[str, object] = {}
    for column in feature_columns:
        values = [_to_float(row.get(column)) for row in rows]
        present = [value for value in values if value is not None]
        block[f"{prefix}__{window}__{column}"] = sum(present) if present else None
    return block


def build_specification_rows(
    specification: str,
    out_of_fold: Sequence[Mapping[str, object]],
    news_rows: Sequence[Mapping[str, object]],
    division_names: Mapping[str, str],
    election_dates: Mapping[str, date],
    party_names: Mapping[str, str],
    *,
    feature_columns: Sequence[str],
    windows: Sequence[str],
) -> list[dict]:
    """The training rows for one of the five specifications.

    Every candidate row that has a usable baseline appears, whether or not any
    news attached to it. A contest nobody wrote about is evidence about
    coverage, and dropping it would leave the model fitted only on divisions
    the press happened to notice - which is a selected sample, not a smaller
    one. Absent coverage arrives as ``None``, never as zero, so a missingness
    indicator can distinguish "no coverage found" from "coverage found, none
    of it relevant".
    """

    if specification not in SPECIFICATIONS:
        raise ValueError(
            f"Unknown specification {specification!r}. "
            f"Known: {list(SPECIFICATIONS)}."
        )

    date_to_news = {v: k for k, v in NEWS_ELECTION_DATES.items()}
    arms: list[str] = []
    if specification in ("local", "combined", "full"):
        arms.append("local")
    if specification in ("national", "combined", "full"):
        arms.append("national")

    indexes = {arm: index_news(news_rows, party_names, arm=arm) for arm in arms}

    built: list[dict] = []
    for row in out_of_fold:
        election = str(row["election_id"])
        polling = election_dates.get(election)
        news_election = date_to_news.get(polling) if polling else None

        predicted = _to_float(row.get("predicted_vote_share"))
        observed = _to_float(row.get("observed_vote_share"))
        if predicted is None or observed is None:
            # A residual against an unknown baseline is not a residual.
            continue

        party = str(row.get("standard_party_name"))
        division = normalise_division(division_names.get(str(row["division_id"]), ""))

        record: dict[str, object] = {
            "candidate_contest_id": str(row["candidate_contest_id"]),
            "election_id": election,
            "election_date": row.get("election_date"),
            "division_id": str(row["division_id"]),
            "division_name": division_names.get(str(row["division_id"]), ""),
            "standard_party_name": party,
            "is_reform_uk": _truthy(row.get("is_reform_uk")),
            "is_ukip": _truthy(row.get("is_ukip")),
            "baseline_predicted_vote_share": predicted,
            "observed_vote_share": observed,
            "residual": observed - predicted,
            "specification": specification,
            "news_election_id": news_election,
        }

        # The baseline specification adds no news columns at all, by
        # definition. It is what the other four have to beat, so giving it any
        # news feature would make the comparison circular.
        #
        # Every other specification emits its full column set on every row,
        # even where nothing matched. Two reasons. A training matrix needs the
        # same columns on every row, and rows whose keys differ cannot form
        # one. And an all-None column is itself the finding - it says this arm
        # reached nothing - whereas an absent column looks identical to a
        # column that was never asked for. An earlier version attached columns
        # only when a news election matched, and the coverage report then read
        # its column list off the first row, found none, and reported zero
        # news for every specification including one that had 17 rows of it.
        for arm in arms:
            index = indexes[arm]
            for window in windows:
                if arm == "local":
                    party_rows = index.get(
                        (news_election, division, party, window), []) \
                        if news_election else []
                    context_rows = index.get(
                        (news_election, division, NO_FOCAL_PARTY, window), []) \
                        if news_election else []
                    record.update(feature_block(
                        party_rows, PREFIX_LOCAL_PARTY, window, feature_columns))
                    record.update(feature_block(
                        context_rows, PREFIX_LOCAL_CONTEXT, window,
                        feature_columns))
                else:
                    party_rows = index.get(
                        (news_election, party, window), []) if news_election else []
                    context_rows = index.get(
                        (news_election, NO_FOCAL_PARTY, window), []) \
                        if news_election else []
                    record.update(feature_block(
                        party_rows, PREFIX_NATIONAL_PARTY, window,
                        feature_columns))
                    record.update(feature_block(
                        context_rows, PREFIX_NATIONAL_CONTEXT, window,
                        feature_columns))
        built.append(record)
    return built


def specification_coverage(rows: Sequence[Mapping[str, object]]) -> dict:
    """How much news actually reached the rows, before anything is fitted.

    A specification whose news columns are empty on every row is not a weak
    model, it is the baseline wearing a different name, and the comparison
    would report a difference of exactly zero without saying why. This makes
    that visible first.
    """

    if not rows:
        return {"rows": 0, "reform_rows": 0, "rows_with_any_news": 0,
                "reform_rows_with_news": 0, "verdict": "no rows built"}

    # The union across all rows, not the keys of the first one. The columns
    # are uniform now, but reading a schema off a single row is the mistake
    # that produced a report of zero news for a specification that had it.
    news_columns = sorted({
        column for row in rows for column in row
        if column.startswith((PREFIX_LOCAL_PARTY, PREFIX_LOCAL_CONTEXT,
                              PREFIX_NATIONAL_PARTY, PREFIX_NATIONAL_CONTEXT))
    })

    def has_news(row: Mapping[str, object]) -> bool:
        return any(row.get(column) is not None for column in news_columns)

    reform = [row for row in rows if row.get("is_reform_uk")]
    with_news = [row for row in rows if has_news(row)]
    reform_with_news = [row for row in reform if has_news(row)]

    by_prefix = {
        prefix: sum(
            1 for row in rows
            if any(row.get(column) is not None
                   for column in news_columns if column.startswith(prefix))
        )
        for prefix in (PREFIX_LOCAL_PARTY, PREFIX_LOCAL_CONTEXT,
                       PREFIX_NATIONAL_PARTY, PREFIX_NATIONAL_CONTEXT)
    }

    verdicts: list[str] = []
    if news_columns and not with_news:
        verdicts.append(
            "NO NEWS REACHED ANY ROW: this specification is the baseline under "
            "another name, and any comparison against the baseline will show "
            "exactly zero difference for that reason rather than for a finding."
        )
    if reform and not reform_with_news:
        verdicts.append(
            f"NO REFORM UK ROW HAS NEWS: {len(reform)} Reform rows are present "
            "and none carries a news feature, so nothing Reform-specific is "
            "estimable from this specification."
        )
    elif reform_with_news and len(reform_with_news) < 30:
        verdicts.append(
            f"REFORM SAMPLE {len(reform_with_news)} ROWS WITH NEWS: any "
            "Reform-specific estimate rests on this and must be quoted with it."
        )

    return {
        "rows": len(rows),
        "reform_rows": len(reform),
        "rows_with_any_news": len(with_news),
        "reform_rows_with_news": len(reform_with_news),
        "news_columns": len(news_columns),
        "rows_by_feature_source": by_prefix,
        "elections": sorted({str(row["election_id"]) for row in rows}),
        "verdicts": verdicts,
    }
