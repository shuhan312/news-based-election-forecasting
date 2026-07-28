"""Chronological split design for the candidate-level no-news model.

This is step 2 of the supervisor's own ordering ("Finalise the modelling
dataset / Lock in the chronological split / Do the leakage audit / Build the
no-news baseline model"), implemented at the candidate estimand established in
``candidate_cohort.py``.

Design rules taken directly from the Stage 1 brief
--------------------------------------------------
1. "Never randomly split candidate rows."
2. "The grouping unit is: election_id + division_id. All candidates from one
   contest must remain in the same split."
3. "Use chronological, rolling-origin evaluation."
4. Named development folds: train through 2016 and test 2017; train through
   2020 and test 2021; train through 2023 and test the 2025 by-elections;
   train through the first 2025 by-election date and test later 2025
   by-elections.
5. "Treat all elections held on 7 May 2026 as one holdout period ... Do not
   train on one event from 7 May 2026 and test on another event from the same
   date."
6. The 7 July 2026 Haslemere by-election is a secondary temporal holdout,
   evaluated both without any 7 May 2026 results and, optionally, after
   retraining through 7 May 2026.

How the rules are enforced rather than remembered
-------------------------------------------------
Every split is defined by **dates**, never by election names or by position in
a sorted list:

    train = elections polled on or before ``train_end``
    test  = elections polled between ``test_start`` and ``test_end``

and construction asserts ``train_end < test_start``. Rules 2 and 5 then hold
by arithmetic rather than by care. A contest belongs to exactly one election,
and an election has exactly one polling date, so a contest cannot straddle the
boundary; and because the primary holdout's ``train_end`` is 6 May 2026, no
event polled on 7 May 2026 can reach training even though three separate
elections share that date.

The same date-based construction is why by-elections need no special handling:
a by-election is simply an election with its own polling date, and it lands in
training or test according to that date like any other.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from no_news_baseline.candidate_cohort import contest_key, is_within_candidate_cohort
from no_news_baseline.election_dates import parse_election_date


# Roles a split can play in the research design. Kept as constants because
# they are written into the manifest and read by later evaluation code.
DEVELOPMENT_FOLD = "development_fold"
PRIMARY_HOLDOUT = "primary_holdout"
SECONDARY_HOLDOUT = "secondary_holdout"
ROLLING_ORIGIN = "rolling_origin_fold"

# The two dates the brief names explicitly.
PRIMARY_HOLDOUT_DATE = date(2026, 5, 7)
SECONDARY_HOLDOUT_DATE = date(2026, 7, 7)

TRAIN = "train"
TEST = "test"
UNUSED = "unused"


@dataclass(frozen=True)
class CandidateSplit:
    """One chronological split, defined purely by polling dates.

    ``train_end`` is inclusive, and the test window ``[test_start, test_end]``
    is inclusive at both ends. The gap assertion in ``__post_init__`` is the
    single structural guarantee that no election can be in both halves.
    """

    split_id: str
    role: str
    description: str
    train_end: date
    test_start: date
    test_end: date
    rationale: str

    def __post_init__(self) -> None:
        if self.train_end >= self.test_start:
            raise ValueError(
                f"Split {self.split_id!r} would train on its own test period: "
                f"train_end={self.train_end} test_start={self.test_start}."
            )
        if self.test_start > self.test_end:
            raise ValueError(f"Split {self.split_id!r} has an empty test window.")

    def fold_for(self, election_day: date) -> str:
        """Which half of this split does an election polled on this day fall in?"""

        if election_day <= self.train_end:
            return TRAIN
        if self.test_start <= election_day <= self.test_end:
            return TEST
        # Elections after the test window are genuinely unusable for this
        # split: training on them would be time travel, and testing on them
        # would silently widen the declared test period.
        return UNUSED


# --------------------------------------------------------------------------
# The named splits from the brief
# --------------------------------------------------------------------------

# Fold 4's boundary is the first 2025 by-election polling date. It is written
# as a literal rather than discovered from the data so that the split design
# is fixed in code and cannot move if a further 2025 by-election is ever
# added to the release - which would otherwise silently redefine an already
# reported fold.
FIRST_2025_BY_ELECTION_DATE = date(2025, 8, 21)

NAMED_SPLITS: tuple[CandidateSplit, ...] = (
    CandidateSplit(
        split_id="dev_through_2016_test_2017",
        role=DEVELOPMENT_FOLD,
        description="Train through 2016, test the 2017 county election",
        train_end=date(2016, 12, 31),
        test_start=date(2017, 1, 1),
        test_end=date(2017, 12, 31),
        rationale="Brief: 'Train through 2016 and test 2017.' Training is the "
                  "2013 county election plus the four 2015-2016 by-elections; "
                  "2013 rows carry no lagged predictors and enter as rows with "
                  "recorded missingness, not as deleted cases.",
    ),
    CandidateSplit(
        split_id="dev_through_2020_test_2021",
        role=DEVELOPMENT_FOLD,
        description="Train through 2020, test the 2021 county election",
        train_end=date(2020, 12, 31),
        test_start=date(2021, 1, 1),
        test_end=date(2021, 12, 31),
        rationale="Brief: 'Train through 2020 and test 2021.' This is the first "
                  "fold whose test period contains any Reform UK observations.",
    ),
    CandidateSplit(
        split_id="dev_through_2023_test_2025_by_elections",
        role=DEVELOPMENT_FOLD,
        description="Train through 2023, test all 2025 by-elections",
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2025, 12, 31),
        rationale="Brief: 'Train through 2023 and test the 2025 by-elections.' "
                  "The test window opens in 2024 so that any future 2024 event "
                  "added to the release is tested rather than silently dropped.",
    ),
    CandidateSplit(
        split_id="dev_through_first_2025_test_later_2025",
        role=DEVELOPMENT_FOLD,
        description="Train through the first 2025 by-election date, test the later ones",
        train_end=FIRST_2025_BY_ELECTION_DATE,
        test_start=date(2025, 8, 22),
        test_end=date(2025, 12, 31),
        rationale="Brief: 'Train through the first 2025 by-election date and test "
                  "later 2025 by-elections where chronology permits.' Both events "
                  "polled on 21 August 2025 are training; the three polled on "
                  "16 October 2025 are test.",
    ),
    CandidateSplit(
        split_id="primary_holdout_7_may_2026",
        role=PRIMARY_HOLDOUT,
        description="Train through 6 May 2026, test every event polled on 7 May 2026",
        train_end=date(2026, 5, 6),
        test_start=PRIMARY_HOLDOUT_DATE,
        test_end=PRIMARY_HOLDOUT_DATE,
        rationale="Brief: 'Treat all elections held on 7 May 2026 as one holdout "
                  "period ... Do not train on one event from 7 May 2026 and test "
                  "on another event from the same date.' The 6 May train boundary "
                  "makes that impossible by construction for all three same-day "
                  "events (East Surrey, West Surrey, the Warlingham by-election).",
    ),
    CandidateSplit(
        split_id="secondary_holdout_haslemere_before_may",
        role=SECONDARY_HOLDOUT,
        description="Train through 6 May 2026, test the 7 July 2026 Haslemere by-election",
        train_end=date(2026, 5, 6),
        test_start=SECONDARY_HOLDOUT_DATE,
        test_end=SECONDARY_HOLDOUT_DATE,
        rationale="Brief: 'Predict Haslemere without using any 7 May 2026 "
                  "results.' This is the honest secondary evaluation, run before "
                  "the primary holdout has been opened.",
    ),
    CandidateSplit(
        split_id="secondary_holdout_haslemere_after_may",
        role=SECONDARY_HOLDOUT,
        description="Retrain through 7 May 2026, test the 7 July 2026 Haslemere by-election",
        train_end=PRIMARY_HOLDOUT_DATE,
        test_start=SECONDARY_HOLDOUT_DATE,
        test_end=SECONDARY_HOLDOUT_DATE,
        rationale="Brief: 'After the primary holdout has been evaluated, "
                  "optionally retrain through 7 May 2026 and predict Haslemere "
                  "again.' Reported separately and never as the headline result, "
                  "because by then the primary holdout has been seen.",
    ),
)


# --------------------------------------------------------------------------
# Rolling-origin folds, generated from the data
# --------------------------------------------------------------------------


def build_rolling_origin_splits(
    features: Iterable[Mapping[str, object]],
    *,
    stop_before: date = PRIMARY_HOLDOUT_DATE,
) -> tuple[CandidateSplit, ...]:
    """One fold per polling date, training on everything strictly earlier.

    The brief asks for rolling-origin evaluation in addition to the named
    folds, so that stability over time can be inspected rather than inferred
    from four hand-picked boundaries. Surrey's elections are unevenly spaced -
    a few large principal polls plus scattered by-elections - and this design
    interleaves both without a special case.

    Grouping is by **polling date**, not by election, so that two elections
    sharing a date form one fold and can never train on each other. That is
    the same rule the primary holdout relies on, applied everywhere.

    ``stop_before`` defaults to the primary holdout date so that routine
    development evaluation cannot accidentally consume the untouched holdout.
    Raising it is a deliberate act, not a default.
    """

    polling_days = sorted(
        {
            parse_election_date(str(row["election_date"])).date()
            for row in features
            if is_within_candidate_cohort(row)
        }
    )

    splits: list[CandidateSplit] = []
    for position, election_day in enumerate(polling_days):
        # The first polling day has nothing earlier to train on. It stays
        # available as training data for every later fold; it is simply not
        # evaluable itself. This reproduces the release's own "study start"
        # boundary without a special case.
        if position == 0 or election_day >= stop_before:
            continue
        previous_day = polling_days[position - 1]
        splits.append(
            CandidateSplit(
                split_id=f"rolling_{election_day.isoformat()}",
                role=ROLLING_ORIGIN,
                description=f"Train through {previous_day.isoformat()}, "
                            f"test every event polled on {election_day.isoformat()}",
                # Training ends at the previous polling day, so every earlier
                # election is included and no same-day election is.
                train_end=previous_day,
                test_start=election_day,
                test_end=election_day,
                rationale="Generated rolling-origin fold; train on all strictly "
                          "earlier polling days, test one polling day.",
            )
        )
    return tuple(splits)


def all_splits(
    features: Iterable[Mapping[str, object]],
) -> tuple[CandidateSplit, ...]:
    """Named splits from the brief, then generated rolling-origin folds."""

    return NAMED_SPLITS + build_rolling_origin_splits(features)


# --------------------------------------------------------------------------
# Assignment and manifest
# --------------------------------------------------------------------------


def assign_split(
    features: Iterable[Mapping[str, object]], split: CandidateSplit
) -> dict[str, str]:
    """Map every cohort row id to ``train``, ``test`` or ``unused``.

    Rows outside the cohort are omitted entirely rather than labelled
    ``unused``: they are not prediction targets at all, so including them
    would overstate how much data a fold declined to use.
    """

    assignment: dict[str, str] = {}
    for row in features:
        if not is_within_candidate_cohort(row):
            continue
        election_day = parse_election_date(str(row["election_date"])).date()
        assignment[str(row["candidate_contest_id"])] = split.fold_for(election_day)
    return assignment


def build_split_manifest(
    features: Iterable[Mapping[str, object]],
    splits: Sequence[CandidateSplit],
) -> tuple[dict[str, object], ...]:
    """Rows for the brief's required ``split_manifest.csv``.

    One row per cohort row per split, including ``unused``, so that the file
    accounts for every row in every split rather than leaving a reader to
    infer absence. ``contest_id`` is carried explicitly so the contest-
    integrity guarantee can be re-checked from the published file alone,
    without re-running this code.
    """

    feature_rows = [row for row in features if is_within_candidate_cohort(row)]
    manifest: list[dict[str, object]] = []
    for split in splits:
        assignment = assign_split(feature_rows, split)
        for row in feature_rows:
            row_id = str(row["candidate_contest_id"])
            election_id, division_id = contest_key(row)
            manifest.append(
                {
                    "split_id": split.split_id,
                    "split_role": split.role,
                    "candidate_contest_id": row_id,
                    "contest_id": f"{election_id}|{division_id}",
                    "election_id": election_id,
                    "division_id": division_id,
                    "election_date": str(row["election_date"]),
                    "fold": assignment[row_id],
                    "train_end": split.train_end.isoformat(),
                    "test_start": split.test_start.isoformat(),
                    "test_end": split.test_end.isoformat(),
                }
            )
    return tuple(manifest)


# --------------------------------------------------------------------------
# Integrity checks
# --------------------------------------------------------------------------


def assert_contest_integrity(manifest: Iterable[Mapping[str, object]]) -> None:
    """No contest may appear in more than one fold of the same split.

    The brief's rule 2 in executable form. It holds by construction given
    date-based splitting, so this is a guard against a future change breaking
    the construction rather than a runtime necessity - which is exactly the
    kind of check the brief asks to be automated ("Add automated tests that
    fail if a prohibited field enters the feature matrix", same discipline).
    """

    seen: dict[tuple[str, str], str] = {}
    for row in manifest:
        key = (str(row["split_id"]), str(row["contest_id"]))
        fold = str(row["fold"])
        if key in seen and seen[key] != fold:
            raise ValueError(
                f"Contest {row['contest_id']} is split across folds "
                f"{seen[key]} and {fold} in split {row['split_id']}."
            )
        seen[key] = fold


def assert_holdout_untouched(
    manifest: Iterable[Mapping[str, object]],
    *,
    holdout_date: date = PRIMARY_HOLDOUT_DATE,
) -> None:
    """No development or rolling fold may train on the primary holdout.

    The brief's strongest evaluation constraint. Checked against the published
    manifest rather than against the split definitions, so that a bug in
    assignment cannot pass merely because the definitions look right.
    """

    for row in manifest:
        if str(row["split_role"]) in {PRIMARY_HOLDOUT, SECONDARY_HOLDOUT}:
            continue
        if row["fold"] != TRAIN:
            continue
        election_day = parse_election_date(str(row["election_date"])).date()
        if election_day >= holdout_date:
            raise ValueError(
                f"Split {row['split_id']} trains on a row polled "
                f"{election_day.isoformat()}, at or after the primary holdout."
            )


def split_summary(
    features: Iterable[Mapping[str, object]],
    splits: Sequence[CandidateSplit],
) -> tuple[dict[str, object], ...]:
    """Per-split row, contest, Reform UK and UKIP counts for each fold.

    The brief requires "the number of Reform observations used in each fold"
    and a warning where Reform estimates rest on a very small sample. Counting
    it here, from the same assignment the model will use, means the reported
    number cannot drift from the number actually trained on.
    """

    feature_rows = [row for row in features if is_within_candidate_cohort(row)]
    by_id = {str(row["candidate_contest_id"]): row for row in feature_rows}

    summaries: list[dict[str, object]] = []
    for split in splits:
        assignment = assign_split(feature_rows, split)
        counts: dict[str, dict[str, object]] = {
            fold: {
                "rows": 0,
                "contests": set(),
                "reform_uk_rows": 0,
                "ukip_rows": 0,
                "elections": set(),
            }
            for fold in (TRAIN, TEST, UNUSED)
        }
        for row_id, fold in assignment.items():
            row = by_id[row_id]
            entry = counts[fold]
            entry["rows"] = int(entry["rows"]) + 1
            entry["contests"].add(contest_key(row))
            entry["elections"].add(str(row["election_id"]))
            if row.get("is_reform_uk"):
                entry["reform_uk_rows"] = int(entry["reform_uk_rows"]) + 1
            if row.get("is_ukip"):
                entry["ukip_rows"] = int(entry["ukip_rows"]) + 1

        summary: dict[str, object] = {
            "split_id": split.split_id,
            "split_role": split.role,
            "description": split.description,
            "train_end": split.train_end.isoformat(),
            "test_start": split.test_start.isoformat(),
            "test_end": split.test_end.isoformat(),
            "rationale": split.rationale,
        }
        for fold in (TRAIN, TEST):
            entry = counts[fold]
            summary[f"{fold}_rows"] = entry["rows"]
            summary[f"{fold}_contests"] = len(entry["contests"])
            summary[f"{fold}_elections"] = len(entry["elections"])
            summary[f"{fold}_reform_uk_rows"] = entry["reform_uk_rows"]
            summary[f"{fold}_ukip_rows"] = entry["ukip_rows"]
        # A fold that trains on no Reform observation cannot estimate any
        # Reform-specific effect. Flagged as data rather than left for a
        # reader to notice.
        summary["reform_estimable"] = bool(summary["train_reform_uk_rows"])
        summaries.append(summary)
    return tuple(summaries)
