"""Assemble and validate the complete in-memory fundamentals feature rows.

Each specialised module owns one transparent transformation.  This builder
applies them in a fixed order, then checks the combined table against the
declared predictor and leakage contract.  File export and model training remain
separate later stages.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime

from no_news_baseline.electoral_fundamentals_history import add_previous_election_features
from no_news_baseline.electoral_fundamentals_participation import (
    add_participation_features,
)
from no_news_baseline.electoral_fundamentals_previous_party_zero import (
    add_crosswalk_previous_party_zeros,
)
from no_news_baseline.electoral_fundamentals_rows import (
    build_fundamentals_row_index,
)
from no_news_baseline.electoral_fundamentals_schema import (
    EVALUATION_COLUMNS,
    FORBIDDEN_CURRENT_OUTCOME_COLUMNS,
    IDENTIFIER_COLUMNS,
    PREDICTOR_COLUMNS,
    PROVENANCE_COLUMNS,
    validate_unique_row_keys,
)
from no_news_baseline.electoral_fundamentals_structure import (
    add_contest_structure_features,
)
from no_news_baseline.electoral_fundamentals_ukip import (
    add_previous_ukip_feature,
)


# The extractor uses these reviewed labels to explain *why* a historical link
# was approved. The history module separately gates every link on
# ``geographic_reference_eligibility == approved_historical_reference`` before
# any predictor is released.
APPROVED_HISTORICAL_REFERENCE_STATUSES = frozenset(
    {
        "approved_pre_2024_legal_continuity",
        "approved_for_historical_reference",
        "approved_same_statutory_division",
    }
)

# These two construction fields retain the extractor rows consolidated into a
# party-level observation. Every other final column must be declared centrally
# as an identifier, predictor or provenance field. This closed allow-list also
# prevents a future same-election Surrey-wide aggregate from slipping into the
# table merely because its name was not on a prohibited-outcome list.
CONSTRUCTION_COLUMNS = frozenset(
    {"source_party_contest_ids", "source_party_contest_count"}
)


def build_electoral_fundamentals_features(
    party_features: Iterable[Mapping[str, object]],
    master_payload: Mapping[str, object],
    geographic_overlap_audit: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    """Build one validated row per election, area and standardised party."""

    # Materialise the predictor contract once because each stage must read the
    # same records. Re-consuming a generator would silently produce empty
    # inputs after the first stage.
    source_features = tuple(party_features)
    elections = _payload_table(master_payload, "Elections")
    candidates = _payload_table(master_payload, "Candidate Results")

    # The order follows the research design: establish unique rows, attach only
    # approved earlier results, add audited participation evidence, attach
    # target contest structure, then add the separately governed UKIP context.
    rows = build_fundamentals_row_index(source_features)
    rows = add_previous_election_features(rows, source_features, master_payload)
    rows = add_participation_features(rows, source_features, candidates)
    # Recover only exact party absences across the complete official GIS
    # crosswalk. Positive votes are never redistributed between boundaries.
    rows = add_crosswalk_previous_party_zeros(
        rows, elections, candidates, geographic_overlap_audit
    )
    rows = add_contest_structure_features(rows, source_features, candidates)
    rows = add_previous_ukip_feature(
        rows,
        elections,
        candidates,
        geographic_overlap_audit,
    )

    validate_completed_fundamentals_rows(rows)
    return rows


def validate_completed_fundamentals_rows(
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Enforce the combined schema, time order and evidence boundaries."""

    if not rows:
        raise ValueError("Electoral fundamentals table cannot be empty.")
    validate_unique_row_keys(rows)

    required_columns = set(IDENTIFIER_COLUMNS + PREDICTOR_COLUMNS + PROVENANCE_COLUMNS)
    allowed_columns = required_columns | set(CONSTRUCTION_COLUMNS)
    prohibited_columns = set(EVALUATION_COLUMNS) | set(FORBIDDEN_CURRENT_OUTCOME_COLUMNS)
    for row in rows:
        missing = sorted(required_columns - row.keys())
        if missing:
            raise ValueError(f"Completed fundamentals row is missing columns: {missing!r}.")
        present_outcomes = sorted(prohibited_columns & row.keys())
        if present_outcomes:
            raise ValueError(
                "Current-election outcome columns entered the predictor table: "
                f"{present_outcomes!r}."
            )
        unexpected = sorted(row.keys() - allowed_columns)
        if unexpected:
            raise ValueError(
                "Undeclared columns entered the fundamentals table: "
                f"{unexpected!r}."
            )
        _validate_previous_party_share_evidence(row)
        _validate_historical_reference(row)
        _validate_ukip_identity_boundary(row)


def _validate_historical_reference(row: Mapping[str, object]) -> None:
    """Check that populated historical predictors have an earlier approved source."""

    previous_election_id = row.get("previous_election_id")
    previous_area_id = row.get("previous_area_id")
    previous_date = row.get("previous_election_date")
    status = row.get("historical_reference_status")
    history_values = (
        row.get("previous_party_vote_share"),
        row.get("previous_party_rank"),
        row.get("previous_party_was_winner"),
        row.get("previous_winning_margin"),
        row.get("previous_turnout"),
        row.get("days_since_previous_comparable_election"),
    )

    if previous_election_id is None:
        if previous_area_id is not None or previous_date is not None:
            raise ValueError("Incomplete historical provenance identifiers.")
        # A separately proven crosswalk zero may populate party-only history
        # without pretending that one predecessor area was approved.
        crosswalk_zero = (
            row.get("previous_party_vote_share_status")
            == "observed_zero_across_complete_previous_crosswalk"
        )
        permitted_zero_values = (0.0, None, False, None, None, None)
        if history_values != permitted_zero_values and any(
            value is not None for value in history_values
        ):
            raise ValueError("Historical predictor has no approved previous source.")
        if any(value is not None for value in history_values) and not crosswalk_zero:
            raise ValueError("Historical predictor has no approved previous source.")
        return

    if previous_area_id is None or previous_date is None:
        raise ValueError("Approved historical reference has incomplete provenance.")
    if status not in APPROVED_HISTORICAL_REFERENCE_STATUSES:
        raise ValueError("Historical predictors require a reviewed approval status.")
    if not isinstance(row.get("historical_source_url"), str):
        raise ValueError("Approved historical reference has no source URL.")

    source_date = _parse_date(previous_date, "previous_election_date")
    target_date = _parse_date(row.get("election_date"), "election_date")
    if source_date >= target_date:
        raise ValueError("Historical source date must precede target election date.")
    elapsed = row.get("days_since_previous_comparable_election")
    if elapsed != (target_date - source_date).days:
        raise ValueError("Elapsed-day predictor disagrees with election dates.")


def _validate_previous_party_share_evidence(row: Mapping[str, object]) -> None:
    """Validate direct observations and the one-sided GIS zero proof."""

    value = row.get("previous_party_vote_share")
    status = row.get("previous_party_vote_share_status")
    method = row.get("previous_party_vote_share_method")
    source_election = row.get("previous_party_source_election_id")
    source_areas = row.get("previous_party_source_area_ids")
    coverage = row.get("previous_party_geographic_coverage_percent")
    if value is None:
        missing_statuses = {
            "unavailable_no_direct_or_zero_proof",
            "not_applicable_generic_independent_identity",
        }
        if status not in missing_statuses:
            raise ValueError("Missing previous party share has an invalid status.")
        if (
            status == "not_applicable_generic_independent_identity"
            and row.get("standard_party_name") != "Independent"
        ):
            raise ValueError("Independent non-applicability is assigned to another party.")
        if any(item is not None for item in (method, source_election, source_areas, coverage)):
            raise ValueError("Missing previous party share claims source evidence.")
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("Previous party share must be numeric or NULL.")
    if status == "observed_in_approved_previous_result":
        if method != "direct_approved_previous_area_result":
            raise ValueError("Direct previous party share has the wrong method.")
    elif status == "observed_zero_across_complete_previous_crosswalk":
        if value != 0.0:
            raise ValueError("Crosswalk absence can release only an exact zero.")
        if method != "complete_official_results_across_official_gis_crosswalk":
            raise ValueError("Crosswalk zero has the wrong method.")
        if row.get("previous_party_rank") is not None:
            raise ValueError("A party absent from the previous results has no rank.")
        if row.get("previous_party_was_winner") is not False:
            raise ValueError("A party absent from the previous results cannot be winner.")
    else:
        raise ValueError("Populated previous party share has an invalid status.")
    if not isinstance(source_election, str) or not source_election:
        raise ValueError("Previous party share has no source election.")
    if not isinstance(source_areas, tuple) or not source_areas:
        raise ValueError("Previous party share has no source areas.")
    if not isinstance(coverage, (int, float)) or isinstance(coverage, bool):
        raise ValueError("Previous party share has no geographic coverage value.")


def _validate_ukip_identity_boundary(row: Mapping[str, object]) -> None:
    """Keep UKIP context confined to Reform UK without merging party histories."""

    party = row.get("standard_party_name")
    ukip_value = row.get("previous_ukip_vote_share_in_area")
    ukip_status = row.get("previous_ukip_vote_share_status")
    if party != "Reform UK":
        if ukip_value is not None:
            raise ValueError("UKIP context appeared on a non-Reform party row.")
        if ukip_status != "not_applicable_non_reform_party":
            raise ValueError("Non-Reform row has an invalid UKIP evidence status.")


def _payload_table(
    payload: Mapping[str, object], table_name: str
) -> tuple[Mapping[str, object], ...]:
    """Return a required master table after checking its basic shape."""

    table = payload.get(table_name)
    if not isinstance(table, list) or not all(isinstance(row, dict) for row in table):
        raise ValueError(f"Master payload table is missing or invalid: {table_name!r}.")
    return tuple(table)


def _parse_date(value: object, field: str) -> date:
    """Parse the two date formats retained by the extractor contracts."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} is missing or invalid.")
    for format_string in ("%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value, format_string).date()
        except ValueError:
            continue
    raise ValueError(f"{field} has an unsupported date format: {value!r}.")
