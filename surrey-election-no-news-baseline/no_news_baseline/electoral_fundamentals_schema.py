"""Column contract for the Electoral Fundamentals Feature Table.

This module defines the table before any data-construction code is written.
It contains no election values, fits no model and creates no output file.  Its
purpose is to make the unit of analysis and leakage boundary explicit enough
that later builders and tests can enforce the same design.

Method references
-----------------
Hanretty (2021, Section 3.3) motivates using previous vote share, whether a
party/candidate stood, incumbency and previous turnout as pre-election local
predictors.  Stoetzer et al. (2025, Sections 4 and 5.1) motivate a
fundamentals-only comparison based on previous vote share, incumbency and a
new-party indicator.  The schema borrows those predictor ideas only; no model
from either paper is implemented at this stage.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


# One row represents exactly one standardised party contesting one area in one
# target election.  ``area_id`` is used instead of area name for uniqueness;
# the readable name is retained as descriptive metadata.
ROW_KEY_COLUMNS = (
    "election_id",
    "area_id",
    "standard_party_name",
)

IDENTIFIER_COLUMNS = (
    "election_id",
    "election_date",
    "area_id",
    "area_name",
    "standard_party_name",
)


# Pre-election electoral fundamentals selected for the Surrey baseline. Their
# exact definitions, evidence restrictions and methodological references will
# be recorded in the feature dictionary and project methodology. Current-
# election outcomes are deliberately excluded from this list.
#
# Rank, margin, contest structure, elapsed time and the separate UKIP history
# field are Surrey-specific additions required by this project's design.
PREDICTOR_COLUMNS = (
    "previous_party_vote_share",
    "previous_party_rank",
    "previous_party_was_winner",
    "previous_winning_margin",
    "previous_turnout",
    "incumbent_party",
    "incumbent_candidate_present",
    "candidate_previously_stood",
    "party_previously_stood",
    "first_party_appearance_in_area",
    "new_party_indicator",
    "election_type",
    "number_of_seats",
    "number_of_candidates",
    "days_since_previous_comparable_election",
    # UKIP history is deliberately separate contextual information.  It is
    # never an alias for Reform UK and can never populate Reform's own previous
    # party vote-share field.
    "previous_ukip_vote_share_in_area",
)


# These columns explain where historical values came from. They may accompany
# the full feature table but are not electoral outcomes and are not part of the
# minimal predictors-only matrix.
PROVENANCE_COLUMNS = (
    "previous_election_id",
    "previous_election_date",
    "previous_area_id",
    "previous_area_name",
    "historical_reference_status",
    "historical_source_url",
    # These columns distinguish an observed earlier UKIP share from an
    # observed zero and from a changed-boundary value that cannot be recovered
    # from the available official result geography.  They describe evidence;
    # they are not additional model predictors.
    "previous_ukip_vote_share_status",
    "previous_ukip_vote_share_method",
    "previous_ukip_source_election_id",
    "previous_ukip_source_area_id",
    "previous_ukip_source_area_ids",
    "previous_ukip_geographic_coverage_percent",
)


# Realised target-election values are useful only after a prediction has been
# made.  The ``evaluation_`` prefix and a separate allow-list ensure that later
# code cannot silently treat them as fundamentals predictors.
EVALUATION_COLUMNS = (
    "evaluation_current_party_vote_share",
    "evaluation_current_party_was_winner",
    "evaluation_current_party_seats_won",
    "evaluation_source_urls",
)


# Names that must never appear in the predictor matrix.  This includes direct
# outcomes and quantities derived from the current result.
FORBIDDEN_CURRENT_OUTCOME_COLUMNS = frozenset(
    {
        "current_party_vote_share",
        "target_party_vote_share",
        "current_party_was_winner",
        "target_party_elected",
        "current_turnout",
        "current_winning_margin",
        "change_in_vote_share",
        "final_position",
        "derived_final_position",
    }
)


@dataclass(frozen=True)
class LeakageRule:
    """Human-readable rule that later builders must implement as a test."""

    rule_id: str
    requirement: str


LEAKAGE_RULES = (
    LeakageRule(
        "source_date_precedes_target",
        "Every historical source election date must be strictly earlier than the target election date.",
    ),
    LeakageRule(
        "no_current_outcome_predictors",
        "Current vote share, winner, turnout, margin, rank and derived result fields are evaluation-only.",
    ),
    LeakageRule(
        "no_same_election_surrey_wide_features",
        "No aggregate calculated from other Surrey areas in the target election may be used as a predictor.",
    ),
    LeakageRule(
        "reform_ukip_identity_separation",
        "Reform UK and UKIP remain separate; UKIP history may appear only in its dedicated contextual column.",
    ),
    LeakageRule(
        "approved_geography_only",
        "Historical predictors require an explicitly approved comparable previous election and area.",
    ),
    LeakageRule(
        "unique_election_area_party_row",
        "The combination election_id, area_id and standard_party_name must be unique.",
    ),
)


def validate_schema_contract() -> None:
    """Fail if the declared column sets violate the leakage design."""

    predictor_set = set(PREDICTOR_COLUMNS)
    evaluation_set = set(EVALUATION_COLUMNS)
    if len(predictor_set) != len(PREDICTOR_COLUMNS):
        raise ValueError("Predictor schema contains duplicate column names.")
    if predictor_set & evaluation_set:
        raise ValueError("Predictor and evaluation columns must be disjoint.")
    if predictor_set & FORBIDDEN_CURRENT_OUTCOME_COLUMNS:
        raise ValueError("Current-election outcome appears in the predictor schema.")
    if any(column.startswith(("current_", "target_", "evaluation_")) for column in PREDICTOR_COLUMNS):
        raise ValueError("Outcome-prefixed column appears in the predictor schema.")
    if "previous_ukip_vote_share_in_area" not in predictor_set:
        raise ValueError("The separate UKIP historical feature is missing.")


def validate_unique_row_keys(rows: Iterable[Mapping[str, object]]) -> None:
    """Check the declared election x area x party unit without changing data."""

    keys: list[tuple[object, object, object]] = []
    for row in rows:
        key = tuple(row.get(column) for column in ROW_KEY_COLUMNS)
        if any(value is None or value == "" for value in key):
            raise ValueError("Fundamentals row has an incomplete election-area-party key.")
        keys.append(key)  # type: ignore[arg-type]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate election x area x standardised party row.")


# Validate the static contract when imported so a later edit cannot introduce
# a prohibited predictor without immediately failing the test suite or runner.
validate_schema_contract()
