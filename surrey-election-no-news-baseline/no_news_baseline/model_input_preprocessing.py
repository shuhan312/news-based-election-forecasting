"""Prepare leakage-safe model inputs from the electoral fundamentals table.

The completed feature table keeps scientifically meaningful NULLs. This module
adds their modelling semantics without changing the source table: every
nullable predictor receives a missing flag, an applicability flag and a reason.
It also provides fold-fitted imputation, so validation or future-election rows
can never influence values learned from the training rows.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from no_news_baseline.electoral_fundamentals_schema import (
    EVALUATION_COLUMNS,
    IDENTIFIER_COLUMNS,
    PREDICTOR_COLUMNS,
    ROW_KEY_COLUMNS,
    validate_unique_row_keys,
)


# Numeric and boolean fields are separated because later preprocessing uses a
# median for numeric values and a deterministic mode for boolean values.  The
# two groups still receive exactly the same missing/applicability audit fields.
NUMERIC_NULLABLE_PREDICTORS = (
    "previous_party_vote_share",
    "previous_party_rank",
    "previous_winning_margin",
    "previous_turnout",
    "days_since_previous_comparable_election",
    "previous_ukip_vote_share_in_area",
)

BOOLEAN_NULLABLE_PREDICTORS = (
    "previous_party_was_winner",
    "incumbent_party",
    "incumbent_candidate_present",
    "candidate_previously_stood",
    "party_previously_stood",
    "first_party_appearance_in_area",
    "new_party_indicator",
)

NULLABLE_PREDICTORS = NUMERIC_NULLABLE_PREDICTORS + BOOLEAN_NULLABLE_PREDICTORS

# These are candidate-specific, non-party labels. Their party-history fields
# are not applicable even though candidate history can still be observed.
UNAFFILIATED_LABELS = frozenset({"Independent", "No published party label"})
PARTY_IDENTITY_PREDICTORS = frozenset(
    {
        "previous_party_vote_share",
        "previous_party_rank",
        "previous_party_was_winner",
        "incumbent_party",
        "party_previously_stood",
        "first_party_appearance_in_area",
        "new_party_indicator",
    }
)

# ``__missing`` records whether the source value was absent. ``__applicable``
# records whether the concept itself makes sense for that row.  Keeping both is
# important: an unknown incumbent is different from an unaffiliated candidate
# for whom party-history fields are not applicable.
MISSINGNESS_INDICATOR_COLUMNS = tuple(
    column
    for predictor in NULLABLE_PREDICTORS
    for column in (f"{predictor}__missing", f"{predictor}__applicable")
)
NULL_REASON_COLUMNS = tuple(
    f"{predictor}__null_reason" for predictor in NULLABLE_PREDICTORS
)
MODEL_CONTROL_COLUMNS = (
    "model_target_eligible",
    "historical_context_status",
) + MISSINGNESS_INDICATOR_COLUMNS


@dataclass(frozen=True)
class FoldImputationParameters:
    """Store values learned from one training fold and no other rows."""

    numeric_values: Mapping[str, float]
    boolean_values: Mapping[str, bool]
    fitted_row_count: int


def add_model_input_semantics(
    rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return predictor-only rows with explicit NULL semantics and controls."""

    output: list[dict[str, object]] = []
    allowed_source_columns = set(IDENTIFIER_COLUMNS + PREDICTOR_COLUMNS)
    for source in rows:
        # Copy through an allow-list so realised outcomes cannot enter the
        # model-input table even if the full release row is supplied here.
        row = {column: source.get(column) for column in allowed_source_columns}
        row["model_target_eligible"] = _target_eligible(source)
        row["historical_context_status"] = _historical_context(source)
        for predictor in NULLABLE_PREDICTORS:
            # Classify the raw value before creating the two model-facing
            # indicators so all three columns describe the same decision.
            reason = _null_reason(source, predictor)
            row[f"{predictor}__missing"] = source.get(predictor) is None
            row[f"{predictor}__applicable"] = reason not in {
                "not_applicable",
                "party_did_not_contest",
            }
            row[f"{predictor}__null_reason"] = reason
        output.append(row)

    validate_unique_row_keys(output)
    if len(output) != len(rows):
        raise ValueError("Model-input semantics changed the number of feature rows.")
    if any(column in row for row in output for column in EVALUATION_COLUMNS):
        raise ValueError("Evaluation outcomes leaked into the model-input contract.")
    return tuple(output)


def eligible_model_target_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Exclude 2013 as a target while retaining it as upstream history.

    This function applies no complete-case filter. In particular, every 2026
    row is retained even when boundary change makes historical values missing.
    """

    selected = tuple(dict(row) for row in rows if row.get("model_target_eligible") is True)
    if any(_year(row) == 2013 for row in selected):
        raise ValueError("The 2013 study-start election cannot be a model target.")
    expected_2026 = sum(_year(row) == 2026 for row in rows)
    retained_2026 = sum(_year(row) == 2026 for row in selected)
    if retained_2026 != expected_2026:
        raise ValueError("Model-target selection deleted 2026 boundary-change rows.")
    return selected


def fit_fold_imputation(
    training_rows: Sequence[Mapping[str, object]],
) -> FoldImputationParameters:
    """Learn medians and boolean modes from one declared training fold only."""

    if not training_rows:
        raise ValueError("Cannot fit imputation on an empty training fold.")
    numeric = {
        field: _numeric_imputation_value(training_rows, field)
        for field in NUMERIC_NULLABLE_PREDICTORS
    }
    boolean = {
        field: _boolean_mode(training_rows, field)
        for field in BOOLEAN_NULLABLE_PREDICTORS
    }
    return FoldImputationParameters(numeric, boolean, len(training_rows))


def apply_fold_imputation(
    rows: Sequence[Mapping[str, object]],
    parameters: FoldImputationParameters,
) -> tuple[dict[str, object], ...]:
    """Fill model copies while retaining missing and applicability indicators.

    A filled value is never interpreted alone: the corresponding ``__missing``
    and ``__applicable`` controls remain in the same row. The raw feature table
    is not mutated, and Unknown is therefore never silently recoded as False.
    """

    output: list[dict[str, object]] = []
    for source in rows:
        row = dict(source)
        for field, value in parameters.numeric_values.items():
            if row.get(field) is None:
                row[field] = value
        for field, value in parameters.boolean_values.items():
            if row.get(field) is None:
                row[field] = value
        output.append(row)
    validate_unique_row_keys(output)
    if len(output) != len(rows):
        raise ValueError("Fold imputation changed the number of rows.")
    return tuple(output)


def _target_eligible(row: Mapping[str, object]) -> bool:
    """Use 2013 as history only because no earlier election is in scope."""

    return _year(row) != 2013


def _historical_context(row: Mapping[str, object]) -> str:
    """Summarise the row's overall relationship to earlier election evidence."""

    if _year(row) == 2013:
        return "study_start_history_only"
    if row.get("previous_election_id") is not None:
        return "approved_direct_predecessor"
    if _year(row) == 2026:
        if row.get("previous_party_vote_share_status") == (
            "observed_zero_across_complete_previous_crosswalk"
        ):
            return "changed_boundary_exact_party_zero_only"
        return "changed_boundary_no_direct_predecessor"
    return "insufficient_approved_history"


def _null_reason(row: Mapping[str, object], field: str) -> str:
    """Assign one mutually exclusive meaning to an observed or missing value."""

    # The order is deliberate. An observed value always remains observed;
    # field-specific non-applicability is then resolved before the wider
    # election-level reasons such as study start or boundary change.
    if row.get(field) is not None:
        return "observed"
    party = str(row.get("standard_party_name", ""))
    if field == "previous_ukip_vote_share_in_area" and party != "Reform UK":
        return "not_applicable"
    if party in UNAFFILIATED_LABELS and field in PARTY_IDENTITY_PREDICTORS:
        return "not_applicable"
    # A confirmed zero share means the party did not stand. Such a party has
    # no rank; assigning last place would invent an electoral observation.
    if field == "previous_party_rank" and row.get("previous_party_vote_share") == 0:
        return "party_did_not_contest"
    if _year(row) == 2013:
        return "study_start"
    if _year(row) == 2026 and row.get("previous_election_id") is None:
        return "changed_boundary"
    return "insufficient_evidence"


def _year(row: Mapping[str, object]) -> int:
    value = row.get("election_date")
    if not isinstance(value, str):
        raise ValueError("Model-input row has no ISO election date.")
    for date_format in ("%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value, date_format).year
        except ValueError:
            continue
    raise ValueError(f"Invalid election date: {value!r}.")


def _observed_numbers(
    rows: Sequence[Mapping[str, object]], field: str
) -> tuple[float, ...]:
    """Return genuine numeric observations without treating booleans as 0/1."""

    values = tuple(
        float(row[field])
        for row in rows
        if isinstance(row.get(field), (int, float))
        and not isinstance(row.get(field), bool)
    )
    return values


def _numeric_imputation_value(
    rows: Sequence[Mapping[str, object]], field: str
) -> float:
    """Fit a median, or a harmless placeholder when a field is inapplicable.

    If no training row can use the field, zero is only a matrix placeholder;
    every row still carries ``__applicable=False`` and ``__missing=True``. If
    the field is applicable but all evidence is missing, fitting stops rather
    than inventing a value.
    """

    values = _observed_numbers(rows, field)
    if values:
        return float(median(values))
    applicable_column = f"{field}__applicable"
    if all(row.get(applicable_column) is False for row in rows):
        return 0.0
    raise ValueError(f"Training fold has no observed applicable values for {field}.")


def _boolean_mode(rows: Sequence[Mapping[str, object]], field: str) -> bool:
    values = [row[field] for row in rows if isinstance(row.get(field), bool)]
    if not values:
        raise ValueError(f"Training fold has no observed values for {field}.")
    counts = Counter(values)
    # False wins an exact tie for deterministic output; the missing indicator
    # still distinguishes an imputed row from an observed False.
    return False if counts[False] >= counts[True] else True
