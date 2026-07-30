"""Integration and leakage tests for the unified fundamentals builder."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_builder import (
    build_electoral_fundamentals_features,
    validate_completed_fundamentals_rows,
)
from no_news_baseline.electoral_fundamentals_rows import load_party_feature_rows
from no_news_baseline.electoral_fundamentals_schema import (
    PREDICTOR_COLUMNS,
    ROW_KEY_COLUMNS,
)
from contract_expectations import FUNDAMENTALS_INDEX_ROWS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR_OUTPUTS = PROJECT_ROOT.parent / "surrey-election-extractor" / "outputs"


def _real_inputs() -> tuple[
    tuple[dict[str, object], ...], dict[str, object], dict[str, object]
]:
    """Load the three generated extractor inputs used by the real builder."""

    feature_path = (
        EXTRACTOR_OUTPUTS
        / "no_news_party_contests/no_news_party_contest_features.json"
    )
    master_path = (
        EXTRACTOR_OUTPUTS
        / "master_surrey_election_database/master_election_database_payload.json"
    )
    overlap_path = (
        EXTRACTOR_OUTPUTS
        / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json"
    )
    if not all(path.exists() for path in (feature_path, master_path, overlap_path)):
        pytest.skip("Regenerate extractor outputs for integration QA.")
    return (
        load_party_feature_rows(feature_path),
        json.loads(master_path.read_text(encoding="utf-8")),
        json.loads(overlap_path.read_text(encoding="utf-8")),
    )


def test_real_builder_completes_every_declared_predictor_column() -> None:
    """The real release should produce one complete-schema row per party contest."""

    party_features, master, overlap = _real_inputs()
    rows = build_electoral_fundamentals_features(party_features, master, overlap)

    assert len(rows) == FUNDAMENTALS_INDEX_ROWS
    assert all(all(column in row for column in PREDICTOR_COLUMNS) for row in rows)
    keys = [tuple(row[column] for column in ROW_KEY_COLUMNS) for row in rows]
    assert len(keys) == len(set(keys))


def test_current_2026_outcomes_cannot_change_2026_predictors() -> None:
    """Changing target outcomes must leave every 2026 predictor unchanged."""

    party_features, master, overlap = _real_inputs()
    original = build_electoral_fundamentals_features(party_features, master, overlap)
    altered_master = deepcopy(master)
    principal_2026 = {
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }
    for candidate in altered_master["Candidate Results"]:
        if candidate["election_id"] in principal_2026:
            # These are realised result fields that must never drive a
            # pre-election fundamentals predictor.
            candidate["votes"] = 999_999
            candidate["analysis_vote_share"] = 99.99
            candidate["elected_yes_no"] = "No"
            candidate["derived_final_position"] = 999

    altered = build_electoral_fundamentals_features(
        party_features, altered_master, overlap
    )
    original_2026 = {
        tuple(row[column] for column in ROW_KEY_COLUMNS): tuple(
            row[column] for column in PREDICTOR_COLUMNS
        )
        for row in original
        if row["election_id"] in principal_2026
    }
    altered_2026 = {
        tuple(row[column] for column in ROW_KEY_COLUMNS): tuple(
            row[column] for column in PREDICTOR_COLUMNS
        )
        for row in altered
        if row["election_id"] in principal_2026
    }
    assert altered_2026 == original_2026


def test_completed_validator_rejects_current_outcome_column() -> None:
    """A current-result field must never be accepted in the predictor table."""

    party_features, master, overlap = _real_inputs()
    row = dict(
        build_electoral_fundamentals_features(party_features, master, overlap)[0]
    )
    row["current_party_vote_share"] = 50.0

    with pytest.raises(ValueError, match="outcome columns entered"):
        validate_completed_fundamentals_rows([row])


def test_completed_validator_rejects_same_election_surrey_aggregate() -> None:
    """An undeclared current-election county aggregate must fail the release."""

    party_features, master, overlap = _real_inputs()
    row = dict(
        build_electoral_fundamentals_features(party_features, master, overlap)[0]
    )
    row["same_election_surrey_wide_party_share"] = 25.0

    with pytest.raises(ValueError, match="Undeclared columns"):
        validate_completed_fundamentals_rows([row])


def test_completed_validator_rejects_non_earlier_history() -> None:
    """Historical evidence dated on the target day must fail the release."""

    party_features, master, overlap = _real_inputs()
    rows = build_electoral_fundamentals_features(party_features, master, overlap)
    row = next(item for item in rows if item["previous_election_id"] is not None)
    invalid = dict(row)
    invalid["previous_election_date"] = invalid["election_date"]
    invalid["days_since_previous_comparable_election"] = 0

    with pytest.raises(ValueError, match="must precede"):
        validate_completed_fundamentals_rows([invalid])
