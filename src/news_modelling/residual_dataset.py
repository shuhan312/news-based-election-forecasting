"""Join Stage 1 out-of-fold predictions to news features, and diagnose the join.

Prompt 2's Approach A:

    residual = actual vote share - out-of-fold baseline prediction
    train a news model to predict that residual
    final prediction = baseline + predicted news adjustment

The arithmetic is trivial. The join is not, and the join is where this either
works or does not, so this module's first output is a **coverage diagnosis**
and the training matrix is second. A residual model that silently trained on
whatever happened to join would report a number, and the number would be about
nothing.

Three things make the join non-trivial
--------------------------------------
**The identifier systems differ.** Stage 1 elections are
``surrey-county-council-2021``; news elections are ``SCC-2021-05``. Stage 1
divisions are opaque row keys (``...:result:169``); news targets are ward
names (``SCC-2021-05:Guildford East``). The join therefore runs on election
date and normalised division name, and every unmatched name on either side is
reported rather than dropped.

**News has two scopes, and they behave completely differently.** A
division-level article attaches to one contest. An election-wide article
attaches to every contest in that election — which means an election-wide
news feature takes **one value per election**. Across a training set of two
elections that is a variable with two distinct values, and no model can
separate it from "which election is this". That is not a small-sample problem
that more careful fitting would fix; it is collinearity with the fold
structure itself. This module measures it and refuses to present it as a news
effect.

**A missing article is not an absent feature.** The news pipeline already
distinguishes "searched and found nothing" from "archive unavailable", and
that distinction has to survive the join: a contest with no news coverage is
an observation about coverage, not a row to be dropped.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# News election identifiers carry the polling month; Stage 1 identifiers carry
# the full election name. Mapping on the polling *date* rather than on either
# string keeps the two naming schemes independent of each other.
NEWS_ELECTION_DATES: dict[str, date] = {
    "SCC-2013-05": date(2013, 5, 2),
    "SCC-2017-05": date(2017, 5, 4),
    "SCC-2021-05": date(2021, 5, 6),
    "ESWS-2026-05": date(2026, 5, 7),
}

# The token the news layer uses for an article that belongs to a whole
# election rather than one ward.
ELECTION_WIDE = "ELECTION_WIDE"

_SUFFIXES = re.compile(r"\s+(ward|division|electoral division)$", re.IGNORECASE)


def normalise_division(name: str) -> str:
    """A comparable form of a division or ward name.

    Deliberately conservative: case, the trailing "Ward"/"Division" suffix,
    ampersands and internal whitespace only. Anything cleverer - stripping
    directional words, fuzzy matching - would create matches nobody declared,
    and a wrongly matched division attaches an article to the wrong contest.
    """

    text = str(name).strip().lower().replace("&", "and")
    text = _SUFFIXES.sub("", text)
    return re.sub(r"[\s\-]+", " ", text).strip()


@dataclass(frozen=True)
class CoverageDiagnosis:
    """What the join can and cannot support, before any model is fitted."""

    stage1_rows: int
    stage1_elections: tuple[str, ...]
    news_elections: tuple[str, ...]
    shared_elections: tuple[str, ...]
    stage1_only_elections: tuple[str, ...]
    news_only_elections: tuple[str, ...]

    division_level_rows: int
    division_level_reform_rows: int
    division_level_divisions: tuple[str, ...]

    election_wide_rows: int
    election_wide_reform_rows: int
    election_wide_distinct_values: int

    unmatched_news_divisions: tuple[str, ...]
    # Divisions whose news exists but whose election has no out-of-fold
    # baseline. Counted separately because it is a coverage fact, not a
    # join failure.
    divisions_in_elections_without_baseline: int = 0

    def as_record(self) -> dict:
        return {
            "stage1_out_of_fold_rows": self.stage1_rows,
            "stage1_elections": list(self.stage1_elections),
            "news_elections": list(self.news_elections),
            "shared_elections": list(self.shared_elections),
            "stage1_elections_without_news": list(self.stage1_only_elections),
            "news_elections_without_stage1_baseline": list(self.news_only_elections),
            "division_level": {
                "candidate_rows": self.division_level_rows,
                "reform_uk_rows": self.division_level_reform_rows,
                "divisions": list(self.division_level_divisions),
            },
            "election_wide": {
                "candidate_rows": self.election_wide_rows,
                "reform_uk_rows": self.election_wide_reform_rows,
                "distinct_feature_values": self.election_wide_distinct_values,
            },
            "unmatched_news_divisions": list(self.unmatched_news_divisions),
            "divisions_with_news_but_no_baseline_election":
                self.divisions_in_elections_without_baseline,
            "verdicts": self.verdicts(),
        }

    def verdicts(self) -> list[str]:
        """Plain statements about what may and may not be concluded.

        Written as data rather than left to a reader's judgement, because the
        failure this guards against is a number being quoted without them.
        """

        verdicts: list[str] = []

        if self.division_level_rows == 0:
            verdicts.append(
                "NO DIVISION-LEVEL TRAINING DATA: no candidate row can be "
                "matched to division-level news. Approach A cannot be "
                "estimated at division level."
            )
        elif self.division_level_reform_rows == 0:
            verdicts.append(
                f"NO REFORM UK OBSERVATIONS: {self.division_level_rows} "
                "candidate rows have division-level news, none of them Reform "
                "UK. A Reform-specific news effect is not estimable from this "
                "data at any confidence level - the sample is zero, not small."
            )
        elif self.division_level_reform_rows < 30:
            verdicts.append(
                f"REFORM SAMPLE {self.division_level_reform_rows} ROWS: any "
                "Reform-specific news estimate rests on this and must not be "
                "quoted without it."
            )

        if self.election_wide_distinct_values <= len(self.shared_elections):
            verdicts.append(
                f"ELECTION-WIDE NEWS IS COLLINEAR WITH ELECTION IDENTITY: the "
                f"feature takes {self.election_wide_distinct_values} distinct "
                f"value(s) across {len(self.shared_elections)} election(s), so "
                "it cannot be separated from everything else that differed "
                "between those elections. Any apparent effect is a "
                "between-election difference, not a news effect."
            )

        if len(self.shared_elections) < 3:
            verdicts.append(
                f"ONLY {len(self.shared_elections)} ELECTION(S) HAVE BOTH A "
                "BASELINE AND NEWS: chronological folds need more than this "
                "to show stability over time."
            )

        if self.unmatched_news_divisions:
            verdicts.append(
                f"{len(self.unmatched_news_divisions)} news division name(s) "
                "did not match any Stage 1 division and were not used."
            )
        return verdicts


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


def diagnose_coverage(
    out_of_fold: list[dict],
    news_rows: list[dict],
    division_names: dict[str, str],
    election_dates: dict[str, date],
) -> CoverageDiagnosis:
    """Measure what the join supports. Fits nothing.

    ``division_names`` maps Stage 1 ``division_id`` to its name; ``election_dates``
    maps Stage 1 ``election_id`` to its polling date. Both come from the
    published contract rather than being parsed out of identifiers, so a change
    in identifier format cannot silently change the join.
    """

    date_to_news_election = {v: k for k, v in NEWS_ELECTION_DATES.items()}

    stage1_elections = sorted({str(row["election_id"]) for row in out_of_fold})
    news_elections = sorted({str(row["election_id"]) for row in news_rows})

    # An election is shared when its polling date appears on both sides.
    shared, stage1_only = [], []
    for election in stage1_elections:
        polling = election_dates.get(election)
        news_id = date_to_news_election.get(polling) if polling else None
        (shared if news_id in news_elections else stage1_only).append(election)
    shared_news_ids = {
        date_to_news_election[election_dates[e]] for e in shared
    }
    news_only = sorted(set(news_elections) - shared_news_ids)

    # Division-level news, per shared election.
    by_election_divisions: dict[str, set[str]] = defaultdict(set)
    unmatched: set[str] = set()
    for row in news_rows:
        target = str(row.get("geographic_target_id", ""))
        _, _, name = target.partition(":")
        if not name or name == ELECTION_WIDE:
            continue
        by_election_divisions[str(row["election_id"])].add(normalise_division(name))

    division_rows, division_reform, matched_divisions = 0, 0, set()
    election_wide_rows, election_wide_reform = 0, 0
    for row in out_of_fold:
        election = str(row["election_id"])
        if election not in shared:
            continue
        election_wide_rows += 1
        election_wide_reform += int(_truthy(row.get("is_reform_uk")))

        news_id = date_to_news_election[election_dates[election]]
        name = normalise_division(division_names.get(str(row["division_id"]), ""))
        if name and name in by_election_divisions.get(news_id, set()):
            division_rows += 1
            division_reform += int(_truthy(row.get("is_reform_uk")))
            matched_divisions.add(division_names[str(row["division_id"])])

    stage1_names_by_news_election: dict[str, set[str]] = defaultdict(set)
    for row in out_of_fold:
        election = str(row["election_id"])
        if election in shared:
            news_id = date_to_news_election[election_dates[election]]
            stage1_names_by_news_election[news_id].add(
                normalise_division(division_names.get(str(row["division_id"]), ""))
            )
    # Only shared elections can produce an unmatched name. A division in an
    # election with no out-of-fold baseline - the 2026 holdout, or 2013 which
    # is the study start - has nothing to match against, and reporting it as
    # unmatched would suggest a broken join where there is only a missing
    # baseline.
    for news_id in shared_news_ids:
        for name in by_election_divisions.get(news_id, set()):
            if name not in stage1_names_by_news_election.get(news_id, set()):
                unmatched.add(f"{news_id}:{name}")

    # How many distinct election-wide feature vectors exist. One per election
    # means the feature is the election.
    election_wide_values = len({
        str(row["election_id"]) for row in news_rows
        if str(row.get("geographic_target_id", "")).endswith(ELECTION_WIDE)
        and str(row["election_id"]) in shared_news_ids
    })

    return CoverageDiagnosis(
        stage1_rows=len(out_of_fold),
        stage1_elections=tuple(stage1_elections),
        news_elections=tuple(news_elections),
        shared_elections=tuple(shared),
        stage1_only_elections=tuple(stage1_only),
        news_only_elections=tuple(news_only),
        division_level_rows=division_rows,
        division_level_reform_rows=division_reform,
        division_level_divisions=tuple(sorted(matched_divisions)),
        election_wide_rows=election_wide_rows,
        election_wide_reform_rows=election_wide_reform,
        election_wide_distinct_values=election_wide_values,
        unmatched_news_divisions=tuple(sorted(unmatched)),
        divisions_in_elections_without_baseline=sum(
            len(names) for news_id, names in by_election_divisions.items()
            if news_id not in shared_news_ids
        ),
    )


def build_residual_rows(
    out_of_fold: list[dict],
    news_rows: list[dict],
    division_names: dict[str, str],
    election_dates: dict[str, date],
    *,
    feature_columns: list[str],
    window: str | None = None,
) -> list[dict]:
    """The Approach A training matrix: one row per matched candidate.

    ``residual = observed_vote_share - predicted_vote_share``. Only rows with
    division-level news are returned; election-wide news is excluded because
    it is constant within an election and would enter the model as an election
    indicator wearing a news feature's name.

    Rows whose baseline prediction or observed share is missing are dropped
    with a reason rather than imputed: a residual against an unknown baseline
    is not a residual.
    """

    date_to_news_election = {v: k for k, v in NEWS_ELECTION_DATES.items()}

    news_by_key: dict[tuple[str, str], dict] = {}
    for row in news_rows:
        target = str(row.get("geographic_target_id", ""))
        _, _, name = target.partition(":")
        if not name or name == ELECTION_WIDE:
            continue
        if window is not None and str(row.get("window")) != window:
            continue
        news_by_key[(str(row["election_id"]), normalise_division(name))] = row

    residuals: list[dict] = []
    for row in out_of_fold:
        election = str(row["election_id"])
        polling = election_dates.get(election)
        news_id = date_to_news_election.get(polling) if polling else None
        if news_id is None:
            continue
        name = normalise_division(division_names.get(str(row["division_id"]), ""))
        news = news_by_key.get((news_id, name))
        if news is None:
            continue

        predicted = _to_float(row.get("predicted_vote_share"))
        observed = _to_float(row.get("observed_vote_share"))
        if predicted is None or observed is None:
            continue

        record = {
            "candidate_contest_id": str(row["candidate_contest_id"]),
            "election_id": election,
            "election_date": row.get("election_date"),
            "division_id": str(row["division_id"]),
            "division_name": division_names.get(str(row["division_id"]), ""),
            "standard_party_name": row.get("standard_party_name"),
            "is_reform_uk": _truthy(row.get("is_reform_uk")),
            "is_ukip": _truthy(row.get("is_ukip")),
            "baseline_predicted_vote_share": predicted,
            "observed_vote_share": observed,
            # The Approach A target.
            "residual": observed - predicted,
            "news_election_id": news_id,
            "news_window": news.get("window"),
        }
        for column in feature_columns:
            record[f"news__{column}"] = news.get(column)
        residuals.append(record)
    return residuals


def reform_rows_by_fold(residuals: list[dict]) -> dict[str, dict[str, int]]:
    """Rows and Reform rows per election.

    Prompt 2 requires the number of Reform observations in every fold to be
    reported. Reported as a table rather than a total, because a total of six
    spread across two elections and a total of six inside one are different
    situations and only the table distinguishes them.
    """

    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rows": 0, "reform_uk": 0, "ukip": 0}
    )
    for row in residuals:
        entry = counts[str(row["election_id"])]
        entry["rows"] += 1
        entry["reform_uk"] += int(bool(row["is_reform_uk"]))
        entry["ukip"] += int(bool(row["is_ukip"]))
    return dict(sorted(counts.items()))
