"""Supervisor-alignment outputs (pure logic; the script does the IO).

Three artefacts the supervisor's Stage 1 prompt asks for that the
existing baseline computes but does not export in that shape:

    1. leakage_audit    - every column, whether it may be a predictor,
                          and which declared rule governs it
    2. split_manifest   - the chronological train/validation/test
                          assignment, produced under BOTH the split
                          the supervisor wrote and the alternative
                          proposed after counting Reform observations
    3. reform_metrics   - baseline error restricted to Reform UK rows,
                          reported separately as the prompt requires

Nothing here refits a model or edits an existing output. The
fundamentals release, the benchmarks and their metrics stay exactly
as they are; this module re-describes them in the requested form.

Why two splits. The supervisor's email specifies train 2013-2019,
validate 2021, test 2026. Counting Reform UK rows in the
county-council universe gives 0 before 2021, 6 in 2021, 5 across the
2025 by-elections and 83 in 2026, so that split trains on zero
Reform observations. The alternative moves 2021 into training and
uses the 2025 by-elections as validation, which keeps the ordering
strictly chronological and puts all 11 pre-2026 Reform rows to work.
Both are emitted; the choice is the supervisor's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# ---- split definitions ---------------------------------------------

@dataclass(frozen=True)
class SplitDefinition:
    """A chronological split. Boundaries are dates, never row counts,
    so a whole election always lands in one fold - the supervisor's
    "don't split candidates from the same election" rule holds by
    construction."""

    split_id: str
    description: str
    train_end: date          # inclusive
    validation_end: date     # inclusive; test is everything after
    rationale: str


SUPERVISOR_SPLIT = SplitDefinition(
    split_id="supervisor_2013_2019",
    description="Train 2013-2019, validate 2021, test 2026",
    train_end=date(2019, 12, 31),
    validation_end=date(2021, 12, 31),
    rationale="As written in the supervisor's email of 2026-07-28.",
)

REFORM_AWARE_SPLIT = SplitDefinition(
    split_id="reform_aware_2021",
    description="Train to end of 2021, validate on the 2025 "
                "by-elections, test 2026",
    train_end=date(2021, 12, 31),
    validation_end=date(2025, 12, 31),
    rationale="Keeps the same chronological discipline but puts the "
              "6 Reform rows of 2021 into training and the 5 Reform "
              "rows of the 2025 by-elections into validation, so no "
              "pre-2026 Reform observation is wasted.",
)

SPLITS = (SUPERVISOR_SPLIT, REFORM_AWARE_SPLIT)


def assign_fold(election_date: date, split: SplitDefinition) -> str:
    """Which fold does an election fall in? Purely a date comparison,
    so every row of one election gets the same answer."""
    if election_date <= split.train_end:
        return "train"
    if election_date <= split.validation_end:
        return "validation"
    return "test"


# ---- leakage audit --------------------------------------------------

# Why each forbidden column is forbidden, in the supervisor's own
# terms ("nothing from the current election result can be used").
FORBIDDEN_REASONS = {
    "current_party_vote_share":
        "The quantity being predicted; known only after the count.",
    "target_party_vote_share":
        "Alias of the prediction target.",
    "current_party_was_winner":
        "Outcome label; known only after the count.",
    "target_party_elected":
        "Outcome label; known only after the count.",
    "current_turnout":
        "Published with the result, not before polling.",
    "current_winning_margin":
        "Derived from the count.",
    "change_in_vote_share":
        "Contains the current result by construction (current minus "
        "previous), so it leaks the target even though it looks "
        "historical.",
    "final_position":
        "Rank within the count.",
    "derived_final_position":
        "Rank within the count.",
}

# Which declared rule covers which class of column.
RULE_FOR_ROLE = {
    "predictor": "source_date_precedes_target",
    "evaluation": "no_current_outcome_predictors",
    "forbidden": "no_current_outcome_predictors",
    "identifier": "unique_election_area_party_row",
}


def build_leakage_audit(predictor_columns, evaluation_columns,
                        forbidden_columns, row_key_columns,
                        dictionary_rows, leakage_rules) -> list[dict]:
    """One row per column, saying whether it may enter the model and
    under which rule. The supervisor asked for "a leakage audit
    listing exactly what was excluded and why" - this is that list,
    including the columns that ARE allowed, so the boundary is
    visible from both sides."""
    defs = {r["field_name"]: r for r in dictionary_rows}
    rows = []

    def add(col, role, allowed, reason):
        d = defs.get(col, {})
        rows.append({
            "column": col,
            "role": role,
            "allowed_as_predictor": "yes" if allowed else "no",
            "governing_rule": RULE_FOR_ROLE.get(role, ""),
            "reason": reason,
            "temporal_availability": d.get("temporal_availability", ""),
            "definition": d.get("definition", ""),
        })

    for col in row_key_columns:
        add(col, "identifier", False,
            "Join key only; identifiers are never model inputs "
            "(candidate and area names included, per the brief).")
    for col in predictor_columns:
        add(col, "predictor", True,
            "Derived exclusively from elections strictly earlier than "
            "the target, on an approved comparable geography.")
    for col in evaluation_columns:
        add(col, "evaluation", False,
            "Scoring field. Available only after the count, so it may "
            "be read when evaluating and never when fitting.")
    for col in sorted(forbidden_columns):
        if col in predictor_columns or col in evaluation_columns:
            continue
        add(col, "forbidden", False, FORBIDDEN_REASONS.get(
            col, "Current-election outcome."))

    # the declared rules themselves, so the audit is self-contained
    for r in leakage_rules:
        rows.append({
            "column": f"(rule) {r.rule_id}",
            "role": "declared_rule",
            "allowed_as_predictor": "",
            "governing_rule": r.rule_id,
            "reason": r.requirement,
            "temporal_availability": "",
            "definition": "",
        })
    return rows


# ---- Reform-specific evaluation -------------------------------------

REFORM = "Reform UK"
UKIP = "UK Independence Party"


def reform_row_census(rows, date_of) -> dict:
    """Count Reform and UKIP rows per election and per fold, under
    both splits. This is the evidence behind the split question, not
    an opinion about it."""
    out = {"by_election": {}, "by_split": {}}
    for r in rows:
        eid = r["election_id"]
        party = r["standard_party_name"]
        if party not in (REFORM, UKIP):
            continue
        slot = out["by_election"].setdefault(
            eid, {"date": date_of(r).isoformat(), REFORM: 0, UKIP: 0})
        slot[party] += 1
    for split in SPLITS:
        folds = {"train": {REFORM: 0, UKIP: 0},
                 "validation": {REFORM: 0, UKIP: 0},
                 "test": {REFORM: 0, UKIP: 0}}
        for r in rows:
            party = r["standard_party_name"]
            if party in (REFORM, UKIP):
                folds[assign_fold(date_of(r), split)][party] += 1
        out["by_split"][split.split_id] = folds
    return out


def mae(pairs) -> float | None:
    """Mean absolute error in percentage points over (pred, actual)
    pairs. None when nothing is scoreable - never 0, which would read
    as a perfect score."""
    vals = [abs(p - a) for p, a in pairs
            if p is not None and a is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def reform_metrics(scored_rows) -> dict:
    """Baseline error restricted to Reform UK rows.

    ``scored_rows`` are dicts with standard_party_name, election_id,
    predicted and actual party vote share. The supervisor's prompt
    asks for Reform performance to be evaluated and reported
    separately - this reports it without refitting anything, and
    keeps the all-party figure beside it so the comparison is
    visible."""
    reform = [r for r in scored_rows
              if r["standard_party_name"] == REFORM]
    everyone = scored_rows
    by_election = {}
    for r in reform:
        by_election.setdefault(r["election_id"], []).append(r)
    return {
        "reform_rows_scored": len(reform),
        "reform_mae_pp": mae([(r["predicted"], r["actual"])
                              for r in reform]),
        "all_party_rows_scored": len(everyone),
        "all_party_mae_pp": mae([(r["predicted"], r["actual"])
                                 for r in everyone]),
        "reform_by_election": {
            eid: {"rows": len(rs),
                  "mae_pp": mae([(r["predicted"], r["actual"])
                                 for r in rs])}
            for eid, rs in sorted(by_election.items())},
        "note": "Reform UK and UKIP are never merged. UKIP history "
                "enters only through its own predictor column "
                "(previous_ukip_vote_share_in_area).",
    }
