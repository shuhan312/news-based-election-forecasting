"""The three news-window schemes the supervisor has specified, side by side.

Three documents give three different sets of pre-election windows and they do
not reconcile:

* the original email - six windows out to 180 days, plus six cumulative
  snapshots. This is what the extraction pipeline implements today
  (``src/llm_extraction/temporal_horizon.py``).
* Prompt 1's covering note and Prompt 2 - three windows inside 30 days, plus
  cumulative snapshots at 30, 7 and 1 days.
* the desktop application specification - seven labelled periods, splitting
  the last three days into "final 48 hours", "previous day" and "election
  day", and requiring anything older than 30 days to be *excluded* from
  influence features rather than merely placed in an earlier window.

The differences are not cosmetic. Under the original scheme an article
published three days before polling sits in ``final_72_hours``; under Prompt 2
it belongs to the "7 to 2 days" window; under the desktop spec it belongs to
"final week". Prompt 2 also requires the windows to be strictly
non-overlapping, so the same article cannot be placed in two of them, and
every news feature is computed per window - which means the choice of scheme
changes every downstream number.

Rather than guess, all three are implemented here and the default stays the
one already in use, so nothing changes until the question is answered. The
comparison function exists so the difference can be shown as a table of real
articles rather than argued about in the abstract.

What this module does and does not decide
-----------------------------------------
It decides **timing only**: how many days before polling an article was
published, which window that puts it in under a given scheme, and whether
timing alone disqualifies it. It does not decide relevance, geography or
duplication - those are content judgements made elsewhere, and an article can
be perfectly timed and still be excluded for any of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# The brief's default timezone and poll close. Polls in England close at
# 22:00, and an article published on polling day before that time was
# genuinely available to voters; one published after was not.
UK = ZoneInfo("Europe/London")
POLL_CLOSE = time(22, 0)

# News election identifiers carry the polling month; Stage 1 identifiers carry
# the full election name. Mapping on the polling *date* rather than on either
# string keeps the two naming schemes independent of each other. This is the
# canonical home for the map; other modules import it from here.
NEWS_ELECTION_DATES: dict[str, date] = {
    "SCC-2013-05": date(2013, 5, 2),
    "SCC-2017-05": date(2017, 5, 4),
    "SCC-2021-05": date(2021, 5, 6),
    "ESWS-2026-05": date(2026, 5, 7),
}

# Timing-based exclusion reasons. Prompt 2 requires an auditable reason for
# every excluded article; these are the ones timing alone can establish.
# Content-based reasons (irrelevant geography, low-confidence match, duplicate,
# synthetic) are assigned elsewhere and are deliberately not invented here.
AFTER_POLLS_CLOSED = "after_polls_closed"
AFTER_POLLING_DATE = "after_polling_date"
BEFORE_COLLECTION_WINDOW = "outside_configured_news_window"
UNKNOWN_DATE = "unknown_publication_date"
ELECTION_DAY_TIME_UNKNOWN = "election_day_publication_time_unknown"


@dataclass(frozen=True)
class WindowScheme:
    """One document's definition of the pre-election windows.

    ``windows`` are (label, first_day, last_day) with days counted backwards
    from polling day, both bounds inclusive, and must not overlap.
    ``cumulative`` are (label, days) meaning "everything from 1 to N days
    before polling", so the same article legitimately appears in several.

    ``max_days`` is the point beyond which an article is excluded from
    influence features rather than placed in an earlier window. The original
    email collects 180 days and models all of them; the desktop spec is
    explicit that anything older than 30 days "must be removed from the
    active influence dataset". That is a substantive difference in what the
    model is allowed to see, not a labelling one.
    """

    key: str
    source: str
    windows: tuple[tuple[str, int, int], ...]
    cumulative: tuple[tuple[str, int], ...]
    max_days: int
    includes_election_day: bool = False

    def validate(self) -> None:
        """Non-overlap is a requirement, so it is checked rather than assumed."""

        covered: set[int] = set()
        for label, first, last in self.windows:
            if first > last:
                raise ValueError(f"{self.key}/{label}: first day {first} after last {last}")
            days = set(range(first, last + 1))
            clash = covered & days
            if clash:
                raise ValueError(
                    f"{self.key}/{label} overlaps an earlier window on day(s) "
                    f"{sorted(clash)}. Prompt 2 requires non-overlapping windows."
                )
            covered |= days


# --- the three schemes ------------------------------------------------------

ORIGINAL_EMAIL = WindowScheme(
    key="original_email_180d",
    source="supervisor's original email: 'Please collect articles individually "
           "with exact publication dates and then assign them to...'",
    windows=(
        ("final_72_hours", 1, 3),
        ("7_to_4_days", 4, 7),
        ("14_to_8_days", 8, 14),
        ("30_to_15_days", 15, 30),
        ("90_to_31_days", 31, 90),
        ("180_to_91_days", 91, 180),
    ),
    cumulative=(
        ("previous_72_hours", 3), ("previous_7_days", 7),
        ("previous_14_days", 14), ("previous_30_days", 30),
        ("previous_90_days", 90), ("previous_180_days", 180),
    ),
    max_days=180,
)

PROMPT_1_AND_2 = WindowScheme(
    key="prompt_1_and_2_30d",
    source="Prompt 1 covering note and Prompt 2: '30-8 days before, 7-2 days "
           "before, final day before'",
    windows=(
        # "The final complete day before polling day" is day 1 alone.
        ("final_day", 1, 1),
        ("7_to_2_days", 2, 7),
        ("30_to_8_days", 8, 30),
    ),
    cumulative=(
        ("previous_1_day", 1), ("previous_7_days", 7), ("previous_30_days", 30),
    ),
    max_days=30,
)

DESKTOP_SPEC = WindowScheme(
    key="desktop_spec_30d",
    source="desktop application specification: 'Use the following exact, "
           "non-overlapping periods relative to the target election date'",
    windows=(
        # Election day before polls close is a period in its own right here,
        # which neither other scheme has.
        ("election_day", 0, 0),
        ("previous_day", 1, 1),
        ("final_48_hours", 2, 2),
        ("final_week", 3, 7),
        ("two_weeks_out", 8, 14),
        ("one_month_out", 15, 30),
    ),
    cumulative=(
        ("previous_1_day", 1), ("previous_7_days", 7), ("previous_30_days", 30),
    ),
    max_days=30,
    includes_election_day=True,
)

SCHEMES: dict[str, WindowScheme] = {
    scheme.key: scheme
    for scheme in (ORIGINAL_EMAIL, PROMPT_1_AND_2, DESKTOP_SPEC)
}

# The scheme the pipeline currently uses. Left as the original email's so that
# adding this module changes no existing number; switching is a one-line edit
# once the question is settled.
DEFAULT_SCHEME = ORIGINAL_EMAIL.key


@dataclass(frozen=True)
class WindowAssignment:
    """Where one article falls, and why it was or was not included."""

    days_before: int | None
    window: str | None
    cumulative: tuple[str, ...]
    included: bool
    exclusion_reason: str | None
    scheme: str

    def as_record(self) -> dict:
        return {
            "days_before_polling": self.days_before,
            "window": self.window,
            "cumulative_windows": list(self.cumulative),
            "included_in_influence_features": self.included,
            "exclusion_reason": self.exclusion_reason,
            "window_scheme": self.scheme,
        }


def days_before_polling(
    published: date,
    polling_day: date,
) -> int:
    """Calendar days between publication and polling day.

    Positive means before, zero means polling day itself, negative means
    after. Calendar days rather than 24-hour periods, because that is how
    every one of the three schemes is written ("30 calendar days before
    election day").
    """

    return (polling_day - published).days


def assign(
    published: date | None,
    polling_day: date,
    *,
    scheme: str = DEFAULT_SCHEME,
    published_time: time | None = None,
    poll_close: time = POLL_CLOSE,
) -> WindowAssignment:
    """Place one article in a window, or record why it cannot be used.

    ``published_time`` matters only on polling day itself. An article dated
    polling day with no time is *not* assumed to precede the close: the
    desktop spec is explicit that it must not be included unless the user
    confirms it, and assuming otherwise would let results coverage into a
    pre-election forecast. That is the one leakage this function exists to
    prevent.
    """

    chosen = SCHEMES[scheme]

    if published is None:
        return WindowAssignment(None, None, (), False, UNKNOWN_DATE, scheme)

    days = days_before_polling(published, polling_day)

    if days < 0:
        return WindowAssignment(days, None, (), False, AFTER_POLLING_DATE, scheme)

    if days == 0:
        # Polling day. Whether it counts depends on the scheme and the time.
        if not chosen.includes_election_day:
            return WindowAssignment(days, None, (), False, AFTER_POLLS_CLOSED, scheme)
        if published_time is None:
            return WindowAssignment(
                days, None, (), False, ELECTION_DAY_TIME_UNKNOWN, scheme)
        if published_time >= poll_close:
            return WindowAssignment(days, None, (), False, AFTER_POLLS_CLOSED, scheme)

    if days > chosen.max_days:
        return WindowAssignment(
            days, None, (), False, BEFORE_COLLECTION_WINDOW, scheme)

    window = next(
        (label for label, first, last in chosen.windows if first <= days <= last),
        None,
    )
    if window is None:
        # Reachable only if a scheme leaves a gap in its coverage, which
        # validate() is meant to prevent. Reported rather than guessed.
        return WindowAssignment(
            days, None, (), False, BEFORE_COLLECTION_WINDOW, scheme)

    cumulative = tuple(
        label for label, limit in chosen.cumulative if 1 <= days <= limit
    )
    return WindowAssignment(days, window, cumulative, True, None, scheme)


def compare_schemes(
    published: date | None,
    polling_day: date,
    *,
    published_time: time | None = None,
) -> dict[str, dict]:
    """The same article under all three schemes.

    Written so the disagreement can be shown as a table of real articles
    rather than argued from the definitions. Two of the schemes exclude
    everything older than 30 days that the third models, and the last three
    days are cut differently by all three.
    """

    return {
        key: assign(published, polling_day, scheme=key,
                    published_time=published_time).as_record()
        for key in SCHEMES
    }


def scheme_summary() -> list[dict]:
    """A plain description of each scheme, for the report to the supervisor."""

    rows = []
    for scheme in SCHEMES.values():
        scheme.validate()
        rows.append({
            "scheme": scheme.key,
            "source": scheme.source,
            "windows": [f"{label}: day {first}-{last}"
                        for label, first, last in scheme.windows],
            "cumulative": [label for label, _ in scheme.cumulative],
            "modelled_horizon_days": scheme.max_days,
            "includes_election_day": scheme.includes_election_day,
        })
    return rows
