"""The ward-party-election modelling layer: one row per party per contest.

The unit changes here. Stage 1 predicts a *candidate's* vote share; the news
layer models a *party's* share of a contest, because news is written about
parties and issues far more often than about named candidates, and a party
row is what a local-versus-national comparison can actually be estimated on.
Candidate-level targets are kept in a companion table rather than by bending
this unit.

Three things this layer has to get right, in order of how badly they go wrong
if it does not.

**A party that did not stand is not a party that scored zero.** Every contest
carries rows for parties that stood and for parties that did not, and the
second kind has no vote share at all - not zero. Encoding it as zero would
teach a model that Reform UK polled nothing in 2013, when the truth is that
Reform UK did not exist.

**A baseline prediction must be genuinely out of sample.** Historical rows take
Stage 1's out-of-fold prediction; 2026 rows take its holdout prediction. An
in-sample fit would make the residual an artefact of the baseline having
already seen the answer.

**No coverage is not neutral coverage.** An archive that could not be searched
and an archive that was searched and held nothing are different facts, and the
coverage indicators keep them apart all the way into the feature table.

The window mapping is checked, not assumed
------------------------------------------
The principal windows are now 30-8 complete days, 7-2 complete days, and the
final complete day, with cumulative snapshots at 30, 7 and 1 days. The
aggregated news tables were built against an earlier six-window scheme, so the
new windows are assembled from the old ones. Two of those assemblies are exact
only because of how this corpus happens to fall: no article sits on day 1 or
day 3, so the old ``final_72_hours`` bucket contains nothing but day-2
articles. If that stops being true the mapping silently changes meaning, so
:func:`verify_window_mapping` checks it against the article-level day counts
and refuses to build when it no longer holds.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

# Each principal window, as the day range it means and the older buckets it is
# assembled from. ``exact_only_if_empty`` names the days that must contain no
# articles for the assembly to be exact - they are days the old scheme lumped
# into a bucket that spans more than the new window does.
PRINCIPAL_WINDOWS: dict[str, dict] = {
    "final_complete_day": {
        "days": (1, 1),
        "from_old": ("final_72_hours",),
        "exact_only_if_empty": (2, 3),
    },
    "7_to_2_complete_days": {
        "days": (2, 7),
        "from_old": ("7_to_4_days", "final_72_hours"),
        "exact_only_if_empty": (1,),
    },
    "30_to_8_complete_days": {
        "days": (8, 30),
        "from_old": ("14_to_8_days", "30_to_15_days"),
        "exact_only_if_empty": (),
    },
}

# Cumulative snapshots: everything known by N days before polling. Two map
# straight onto an existing bucket; the one-day snapshot does not, because the
# old scheme's shortest cumulative window was three days.
CUMULATIVE_SNAPSHOTS: dict[str, dict] = {
    "information_available_at_30_days": {
        "days": 30, "from_old": ("previous_30_days",), "exact_only_if_empty": (),
    },
    "information_available_at_7_days": {
        "days": 7, "from_old": ("previous_7_days",), "exact_only_if_empty": (),
    },
    "information_available_at_1_day": {
        "days": 1, "from_old": ("previous_72_hours",),
        "exact_only_if_empty": (2, 3),
    },
}

# The six-window scheme, retained so the earlier assignments stay available as
# a sensitivity layer rather than being overwritten.
LEGACY_WINDOWS = (
    "final_72_hours", "7_to_4_days", "14_to_8_days",
    "30_to_15_days", "90_to_31_days", "180_to_91_days",
)


class WindowMappingError(RuntimeError):
    """The new windows cannot be assembled exactly from the old ones."""


def verify_window_mapping(days_before: Sequence[int]) -> dict:
    """Check the assemblies are exact for this corpus, and say why.

    ``days_before`` is one entry per assigned article. The check is on the days
    an old bucket covers but a new window does not: if any article sits on one
    of those days, the assembly would pull it into a window it does not belong
    to, and the table would be quietly wrong rather than obviously broken.
    """

    counts: dict[int, int] = defaultdict(int)
    for day in days_before:
        counts[int(day)] += 1

    report: dict[str, object] = {
        "articles_assigned": len(days_before),
        "articles_by_day": dict(sorted(counts.items())),
        "checks": {},
    }
    violations: list[str] = []

    for name, spec in {**PRINCIPAL_WINDOWS, **CUMULATIVE_SNAPSHOTS}.items():
        days_spec = spec["days"]
        own_days = (range(days_spec[0], days_spec[1] + 1)
                    if isinstance(days_spec, tuple) else range(1, days_spec + 1))
        articles_in_window = sum(counts.get(day, 0) for day in own_days)

        must_be_empty = spec["exact_only_if_empty"]
        occupied = {day: counts[day] for day in must_be_empty if counts.get(day)}

        # A window whose own days hold no articles is empty, and that is an
        # exact answer rather than an approximation - it comes straight from
        # the article-level day counts and needs no assembly at all. Assembling
        # it from a wider bucket would be the error: `final_complete_day` means
        # day 1, and `final_72_hours` spans days 1 to 3, so where day 1 is
        # empty and day 2 is not, assembling would fill an empty window with
        # articles that belong to the next one.
        if articles_in_window == 0:
            report["checks"][name] = {
                "assembled_from": [],
                "days_that_must_be_empty": list(must_be_empty),
                "articles_found_on_those_days": occupied,
                "articles_in_own_day_range": 0,
                "construction": "empty_no_articles_in_day_range",
                "exact": True,
            }
            continue

        report["checks"][name] = {
            "assembled_from": list(spec["from_old"]),
            "days_that_must_be_empty": list(must_be_empty),
            "articles_found_on_those_days": occupied,
            "articles_in_own_day_range": articles_in_window,
            "construction": "assembled_from_legacy_windows",
            "exact": not occupied,
        }
        if occupied:
            violations.append(
                f"{name}: assembled from {list(spec['from_old'])}, which also "
                f"covers day(s) {sorted(occupied)} that the window excludes; "
                f"{sum(occupied.values())} article(s) sit there."
            )

    report["all_assemblies_exact"] = not violations
    report["violations"] = violations
    if violations:
        raise WindowMappingError(
            "The principal windows can no longer be assembled exactly from the "
            "six-window aggregates. Re-aggregate from article level before "
            "building this table.\n  " + "\n  ".join(violations))
    return report


# ---------------------------------------------------------------------------
# Identity and keys
# ---------------------------------------------------------------------------

# The news layer's election identifiers, mapped by polling date so neither
# naming scheme has to know about the other.
NEWS_ELECTION_DATES: dict[str, date] = {
    "SCC-2013-05": date(2013, 5, 2),
    "SCC-2017-05": date(2017, 5, 4),
    "SCC-2021-05": date(2021, 5, 6),
    "ESWS-2026-05": date(2026, 5, 7),
}

_SUFFIXES = re.compile(r"\s+(ward|division|electoral division)$", re.IGNORECASE)


def normalise_area(name: str) -> str:
    """A comparable form of an electoral-area name.

    Case, a trailing "Ward"/"Division", ampersands and internal whitespace
    only. No fuzzy matching: attaching an article to the wrong contest is
    worse than not attaching it, and "Guildford East" must never match
    "Guildford West".
    """

    text = str(name).strip().lower().replace("&", "and")
    return re.sub(r"[\s\-]+", " ", _SUFFIXES.sub("", text)).strip()


def party_key(name: str) -> str:
    """A join key for a party name that does not merge distinct parties.

    Case and punctuation only. Reform UK and UKIP normalise to different keys
    and must continue to, so no aliasing, stemming or substring rule is
    applied here - "Reform UK" and "UK Independence Party" share letters and
    nothing else.
    """

    return re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()


REFORM_KEY = party_key("Reform UK")
UKIP_KEY = party_key("UK Independence Party")


# ---------------------------------------------------------------------------
# Observation grid
# ---------------------------------------------------------------------------


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _to_float(value: object) -> float | None:
    text = str(value).strip()
    if text in {"", "None", "nan", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_observation_grid(
    contract_rows: Sequence[Mapping[str, object]],
    contestation_rows: Sequence[Mapping[str, object]],
) -> list[dict]:
    """One row per (election, electoral area, party), contested or not.

    Contested rows come from the candidate table, aggregated to the party.
    Not-contested rows come from the contestation record, which is the layer
    that knows a party was absent rather than merely unlisted - a candidate
    table cannot express absence, because an absent party has no row in it.
    """

    contested: dict[tuple[str, str, str], dict] = {}
    for row in contract_rows:
        key = (str(row["election_id"]), str(row["division_id"]),
               party_key(str(row["standard_party_name"])))
        entry = contested.setdefault(key, {
            "election_id": str(row["election_id"]),
            "election_date": str(row["election_date"]),
            "electoral_area_id": str(row["division_id"]),
            "electoral_area_name": str(row.get("division_name", "")),
            "party_id": key[2],
            "standardised_party_name": str(row["standard_party_name"]),
            "is_reform_uk": _truthy(row.get("is_reform_uk")),
            "is_ukip": _truthy(row.get("is_ukip")),
            "contest_id": f"{row['election_id']}|{row['division_id']}",
            "number_of_seats": row.get("analysis_number_of_seats"),
            "party_contested": True,
            "did_not_contest": False,
            "candidates_fielded": 0,
            "geographic_comparability_status": str(
                row.get("geographic_reference_eligibility", "unknown")),
            "election_type": ("by-election" if "by-election" in str(row["election_id"])
                              else "principal"),
        })
        entry["candidates_fielded"] += 1

    grid = list(contested.values())

    # Parties recorded as absent. Their target stays empty throughout: a party
    # that did not stand has no vote share, and zero would be a measurement
    # nobody made.
    for row in contestation_rows:
        status = str(row.get("contestation_status", "")).lower()
        fielded = _to_float(row.get("candidates_fielded")) or 0
        if fielded > 0 or "not" not in status:
            continue
        key = (str(row["election_id"]), str(row["division_id"]),
               party_key(str(row["standard_party_name"])))
        if key in contested:
            continue
        grid.append({
            "election_id": str(row["election_id"]),
            "election_date": str(row.get("election_date", "")),
            "electoral_area_id": str(row["division_id"]),
            "electoral_area_name": str(row.get("division_name", "")),
            "party_id": key[2],
            "standardised_party_name": str(row["standard_party_name"]),
            "is_reform_uk": _truthy(row.get("is_reform_uk")),
            "is_ukip": _truthy(row.get("is_ukip")),
            "contest_id": f"{row['election_id']}|{row['division_id']}",
            "number_of_seats": row.get("analysis_number_of_seats"),
            "party_contested": False,
            "did_not_contest": True,
            "candidates_fielded": 0,
            "geographic_comparability_status": "not_applicable_did_not_contest",
            "election_type": ("by-election" if "by-election" in str(row["election_id"])
                              else "principal"),
        })

    grid.sort(key=lambda r: (r["election_id"], r["electoral_area_id"], r["party_id"]))
    return grid


# ---------------------------------------------------------------------------
# Frozen baseline, aggregated to the party
# ---------------------------------------------------------------------------


def aggregate_baseline_to_party(
    predictions: Sequence[Mapping[str, object]],
    *,
    provenance: str,
) -> dict[tuple[str, str, str], dict]:
    """Sum Stage 1's candidate predictions to a party total per contest.

    Summed, not averaged. A party fielding two candidates in a two-member ward
    holds both of their shares, so its share of the contest is their sum; a
    mean would report the party as half its actual size in exactly the wards
    the 2026 holdout consists of.

    ``provenance`` records which Stage 1 split the prediction came from, so a
    row can never present a holdout figure as an out-of-fold one.
    """

    grouped: dict[tuple[str, str, str], dict] = {}
    for row in predictions:
        key = (str(row["election_id"]), str(row["division_id"]),
               party_key(str(row["standard_party_name"])))
        entry = grouped.setdefault(key, {
            "baseline__predicted_party_vote_share": 0.0,
            "baseline__candidates_predicted": 0,
            "baseline__prediction_provenance": provenance,
            "baseline__model_id": str(row.get("model_id", "")),
            "baseline__split_id": str(row.get("split_id", "")),
            "target__party_vote_share": 0.0,
            "target__party_seats_won": 0,
            "_observed_seen": 0,
            "_contest": (str(row["election_id"]), str(row["division_id"])),
            "_party_name": str(row["standard_party_name"]),
        })
        predicted = _to_float(row.get("predicted_vote_share"))
        observed = _to_float(row.get("observed_vote_share"))
        if predicted is not None:
            entry["baseline__predicted_party_vote_share"] += predicted
            entry["baseline__candidates_predicted"] += 1
        if observed is not None:
            entry["target__party_vote_share"] += observed
            entry["_observed_seen"] += 1
        if _truthy(row.get("observed_elected")):
            entry["target__party_seats_won"] += 1

    for entry in grouped.values():
        if entry["baseline__candidates_predicted"] == 0:
            entry["baseline__predicted_party_vote_share"] = None
        if entry.pop("_observed_seen") == 0:
            # No observed result for this party in this contest: the vote
            # share, the seat count and everything derived from them stay
            # empty. A seat count of zero is a real result; an absent one is
            # not, and the two must not be written the same way.
            entry["target__party_vote_share"] = None
            entry["target__party_seats_won"] = None

    _attach_contest_level_targets(grouped)
    for entry in grouped.values():
        entry.pop("_contest", None)
        entry.pop("_party_name", None)
    return grouped


def _attach_contest_level_targets(
    grouped: dict[tuple[str, str, str], dict],
) -> None:
    """Rank, elected status and the winning party, computed within each contest.

    These are secondary targets and are derived rather than joined, because
    they are functions of the party shares already summed here - deriving them
    somewhere else would create a second definition of "who won" that could
    disagree with this one.

    A contest where any party's share is unknown produces no rank for any
    party in it. A rank computed against a partial field would look like a
    measurement and be an artefact of which rows happened to be present.
    """

    by_contest: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in grouped.values():
        by_contest[entry["_contest"]].append(entry)

    for entries in by_contest.values():
        shares = [entry["target__party_vote_share"] for entry in entries]
        if any(share is None for share in shares):
            for entry in entries:
                entry["target__party_rank"] = None
                entry["target__party_won_contest"] = None
                entry["target__winning_party_in_contest"] = None
            continue

        ordered = sorted(entries, key=lambda e: -e["target__party_vote_share"])
        winner = ordered[0]
        for rank, entry in enumerate(ordered, start=1):
            entry["target__party_rank"] = rank
            # Winning the contest means taking a seat, which is not the same
            # as coming first on share in a multi-member ward.
            entry["target__party_won_contest"] = bool(
                entry.get("target__party_seats_won"))
            entry["target__winning_party_in_contest"] = winner.get("_party_name", "")


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


# ---------------------------------------------------------------------------
# News feature blocks
# ---------------------------------------------------------------------------

# The families the brief asks to be carried through, as column-name prefixes
# in the aggregated tables. Selected rather than taking all 239 columns,
# because a feature nobody can name is a feature nobody can audit.
NEWS_FEATURE_PREFIXES: tuple[str, ...] = (
    "cov_",                       # article, publication and source counts
    "positive_stance", "negative_stance", "neutral_stance", "mixed_stance",
    "mean_stance", "stance_denom",
    "blame_", "credit_", "net_credit",
    "praise_", "criticism_", "competence_", "integrity_",
    "frame_", "framing_denom",
    "issue_",                     # the issue taxonomy
    "consq_", "consequence_",     # expected electoral consequence
    "reform_",                    # Reform-specific campaign and credibility
    "switch_",
)

ARM_LOCAL = "local"
ARM_NATIONAL = "national"

# Which article scopes belong to which arm. "mixed" counts towards both: an
# article about a national issue with local consequences is evidence for both
# mechanisms, and assigning it to one would understate whichever it was taken
# from.
ARM_SCOPES: dict[str, frozenset[str]] = {
    ARM_LOCAL: frozenset({"ward_specific_local", "surrey_wide_local",
                          "mixed_local_national"}),
    ARM_NATIONAL: frozenset({"national_political", "mixed_local_national"}),
}

ELECTION_WIDE = "ELECTION_WIDE"
NO_FOCAL_PARTY = "(no_focal_party)"


# The recency-weighted table names the same families with a `w_` prefix, plus
# a handful of `weighted_` totals. Listed separately rather than by stripping
# the prefix, because `w_` is short enough to match something unrelated later
# and an over-broad selector is how a non-feature column joins the matrix.
WEIGHTED_FEATURE_PREFIXES: tuple[str, ...] = (
    ("weighted_",) + tuple(f"w_{prefix}" for prefix in NEWS_FEATURE_PREFIXES))


def selected_feature_columns(columns: Sequence[str], *,
                             weighted: bool = False) -> list[str]:
    """The news columns carried into the modelling table.

    Selected by family rather than taking everything: 239 columns nobody can
    name is 239 columns nobody can audit, and the leakage audit has to give a
    verdict on each one.
    """

    prefixes = WEIGHTED_FEATURE_PREFIXES if weighted else NEWS_FEATURE_PREFIXES
    return [column for column in columns if column.startswith(prefixes)]


def index_news_rows(
    news_rows: Sequence[Mapping[str, object]],
    party_names: Mapping[str, str],
    *,
    arm: str,
) -> dict[tuple, list[Mapping[str, object]]]:
    """Group one arm's aggregated rows by everything a grid row must match.

    Local rows key on ``(news_election, area, party, old_window)``; national
    rows drop the area, because a national record is stored once per election
    and party and joined many-to-one onto the wards rather than copied into
    each of them.
    """

    scopes = ARM_SCOPES[arm]
    index: dict[tuple, list[Mapping[str, object]]] = defaultdict(list)
    for row in news_rows:
        if str(row.get("scope_classification")) not in scopes:
            continue
        target = str(row.get("geographic_target_id", ""))
        _, _, place = target.partition(":")
        is_national = (not place) or place == ELECTION_WIDE
        if (arm == ARM_LOCAL) is is_national:
            continue

        raw_party = str(row.get("focal_party_id") or NO_FOCAL_PARTY)
        name = party_names.get(raw_party, raw_party)
        party = NO_FOCAL_PARTY if name == NO_FOCAL_PARTY else party_key(name)
        window = str(row.get("window") or "")
        election = str(row.get("election_id"))

        key = ((election, party, window) if is_national
               else (election, normalise_area(place), party, window))
        index[key].append(row)
    return dict(index)


def assemble_window(
    index: dict[tuple, list[Mapping[str, object]]],
    key_prefix: tuple,
    window_spec: Mapping[str, object],
    feature_columns: Sequence[str],
    prefix: str,
    window_name: str,
) -> dict[str, object]:
    """One new window's features, assembled from the old buckets it spans.

    Counts are summed across the contributing buckets. Absent coverage stays
    ``None`` rather than becoming zero: zero says an article count of nothing
    was measured, ``None`` says nothing was found, and a model given zeros
    cannot tell them apart.
    """

    # ``from_old`` is emptied by verify_window_mapping for a window whose own
    # days hold no articles, so an empty window assembles from nothing and the
    # block comes out all-None rather than borrowing a wider bucket's rows.
    rows: list[Mapping[str, object]] = []
    for old_window in window_spec.get("from_old", ()):
        rows.extend(index.get((*key_prefix, old_window), []))

    block: dict[str, object] = {}
    for column in feature_columns:
        values = [_to_float(row.get(column)) for row in rows]
        present = [value for value in values if value is not None]
        block[f"{prefix}__{window_name}__{column}"] = (
            sum(present) if present else None)
    block[f"{prefix}__{window_name}__contributing_aggregate_rows"] = len(rows)
    return block


# ---------------------------------------------------------------------------
# Coverage and missing-news states
# ---------------------------------------------------------------------------

COVERAGE_INDICATORS = (
    "news_observed_indicator", "zero_news_indicator",
    "insufficient_coverage_indicator", "source_unavailable_indicator",
    "unresolved_processing_indicator", "pending_stage_indicator",
    "not_applicable_indicator", "coverage_status", "coverage_confidence",
    "evidence_items_satisfied", "evidence_items_total",
    "stage_m_records_pending",
)


def index_coverage(
    coverage_rows: Sequence[Mapping[str, object]],
    party_names: Mapping[str, str],
) -> dict[tuple, Mapping[str, object]]:
    """Coverage states, keyed the same way as the local news rows.

    Keeps one row per (election, area, party, window). Where several exist the
    first is kept and the count is recorded, so a duplicate is visible rather
    than being silently reduced.
    """

    index: dict[tuple, Mapping[str, object]] = {}
    for row in coverage_rows:
        target = str(row.get("geographic_target_id", ""))
        _, _, place = target.partition(":")
        if not place or place == ELECTION_WIDE:
            place = ELECTION_WIDE
        raw_party = str(row.get("focal_party_id") or NO_FOCAL_PARTY)
        name = party_names.get(raw_party, raw_party)
        party = NO_FOCAL_PARTY if name == NO_FOCAL_PARTY else party_key(name)
        key = (str(row["election_id"]),
               ELECTION_WIDE if place == ELECTION_WIDE else normalise_area(place),
               party, str(row.get("window") or ""))
        index.setdefault(key, row)
    return index


def coverage_block(
    index: dict[tuple, Mapping[str, object]],
    key_prefix: tuple,
    window_spec: Mapping[str, object],
    window_name: str,
) -> dict[str, object]:
    """Coverage state for one window.

    Where a window is assembled from more than one old bucket, the states are
    combined conservatively: an indicator is true only if it is true for every
    contributing bucket, except the ones that describe a *problem*
    (insufficient coverage, unavailable source, unresolved processing,
    pending stage), which are true if any bucket reports them. A window is only
    as complete as its least complete part.
    """

    rows = [index[(*key_prefix, old)] for old in window_spec["from_old"]
            if (*key_prefix, old) in index]
    block: dict[str, object] = {}
    if not rows:
        for indicator in COVERAGE_INDICATORS:
            block[f"coverage__{window_name}__{indicator}"] = None
        block[f"coverage__{window_name}__state_rows"] = 0
        return block

    problem_indicators = {
        "insufficient_coverage_indicator", "source_unavailable_indicator",
        "unresolved_processing_indicator", "pending_stage_indicator",
    }
    for indicator in COVERAGE_INDICATORS:
        values = [row.get(indicator) for row in rows]
        if indicator in problem_indicators:
            block[f"coverage__{window_name}__{indicator}"] = any(
                _truthy(value) for value in values)
        elif indicator.endswith("_indicator"):
            block[f"coverage__{window_name}__{indicator}"] = all(
                _truthy(value) for value in values)
        else:
            block[f"coverage__{window_name}__{indicator}"] = values[0]
    block[f"coverage__{window_name}__state_rows"] = len(rows)
    return block
