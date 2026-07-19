"""Tests for exact previous-party zeros across changed 2026 boundaries."""

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
from no_news_baseline.independent_previous_share_audit import (
    audit_independent_previous_share_nulls,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR_OUTPUTS = PROJECT_ROOT.parent / "surrey-election-extractor" / "outputs"
TARGET_2026 = {
    "surrey-county-council-2026-east-surrey",
    "surrey-county-council-2026-west-surrey",
}


def _real_inputs() -> tuple[tuple[dict[str, object], ...], dict, dict]:
    """Load the released extractor contracts used by integration QA."""

    feature_path = EXTRACTOR_OUTPUTS / "no_news_party_contests/no_news_party_contest_features.json"
    master_path = EXTRACTOR_OUTPUTS / "master_surrey_election_database/master_election_database_payload.json"
    overlap_path = EXTRACTOR_OUTPUTS / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json"
    if not all(path.exists() for path in (feature_path, master_path, overlap_path)):
        pytest.skip("Regenerate extractor outputs for integration QA.")
    return (
        load_party_feature_rows(feature_path),
        json.loads(master_path.read_text(encoding="utf-8")),
        json.loads(overlap_path.read_text(encoding="utf-8")),
    )


def test_real_crosswalk_recovers_only_exact_zero_party_history() -> None:
    """The audited overlay should recover 74 zeros and no estimated positives."""

    party_features, master, overlap = _real_inputs()
    rows = build_electoral_fundamentals_features(party_features, master, overlap)
    recovered = [
        row
        for row in rows
        if row["previous_party_vote_share_status"]
        == "observed_zero_across_complete_previous_crosswalk"
    ]

    assert len(recovered) == 74
    assert all(row["election_id"] in TARGET_2026 for row in recovered)
    assert all(row["previous_party_vote_share"] == 0.0 for row in recovered)
    assert all(row["previous_party_rank"] is None for row in recovered)
    assert all(row["previous_party_was_winner"] is False for row in recovered)
    assert all(row["previous_election_id"] is None for row in recovered)
    assert all(row["standard_party_name"] != "Independent" for row in recovered)


def test_incomplete_crosswalk_cannot_release_zero() -> None:
    """Removing geographic coverage must return the affected party row to NULL."""

    party_features, master, overlap = _real_inputs()
    original = build_electoral_fundamentals_features(party_features, master, overlap)
    example = next(
        row
        for row in original
        if row["previous_party_vote_share_status"]
        == "observed_zero_across_complete_previous_crosswalk"
        and row["standard_party_name"] != "Reform UK"
    )

    incomplete = deepcopy(overlap)
    for item in incomplete["candidate_overlap_rows"]:
        if (
            item["current_election_id"] == example["election_id"]
            and item["current_area_name"].removesuffix(" Ward").casefold()
            == str(example["area_name"]).removesuffix(" Ward").casefold()
        ):
            item["current_area_overlap_percent"] = 0.0

    altered = build_electoral_fundamentals_features(
        party_features, master, incomplete
    )
    changed = next(
        row
        for row in altered
        if row["election_id"] == example["election_id"]
        and row["area_id"] == example["area_id"]
        and row["standard_party_name"] == example["standard_party_name"]
    )
    assert changed["previous_party_vote_share"] is None
    assert changed["previous_party_vote_share_status"] == (
        "unavailable_no_direct_or_zero_proof"
    )


def test_validator_rejects_positive_crosswalk_imputation() -> None:
    """The crosswalk method must never be relabelled as a positive estimate."""

    party_features, master, overlap = _real_inputs()
    rows = build_electoral_fundamentals_features(party_features, master, overlap)
    example = next(
        row
        for row in rows
        if row["previous_party_vote_share_status"]
        == "observed_zero_across_complete_previous_crosswalk"
    )
    invalid = dict(example)
    invalid["previous_party_vote_share"] = 1.0

    with pytest.raises(ValueError, match="only an exact zero"):
        validate_completed_fundamentals_rows([invalid])


def test_independent_history_is_explicitly_not_applicable() -> None:
    """Generic Independent rows stay NULL without looking unresolved."""

    party_features, master, overlap = _real_inputs()
    rows = build_electoral_fundamentals_features(party_features, master, overlap)
    independents = [
        row for row in rows if row["standard_party_name"] == "Independent"
    ]

    # The current party-level release contains 59 Independent rows. Keep the
    # explicit count as a regression check against accidental row loss or
    # splitting caused by future standardisation changes.
    assert len(independents) == 59
    assert all(row["previous_party_vote_share"] is None for row in independents)
    assert {
        row["previous_party_vote_share_status"] for row in independents
    } == {"not_applicable_generic_independent_identity"}


def test_real_later_independent_null_review_is_complete() -> None:
    """Every Independent with an approved predecessor receives a final review."""

    party_features, master, overlap = _real_inputs()
    rows = build_electoral_fundamentals_features(party_features, master, overlap)
    audit = audit_independent_previous_share_nulls(
        rows, master["Candidate Results"]
    )

    assert audit["audited_rows"] == 38
    assert audit["status"] == "complete_no_party_level_values_recoverable"
    assert audit["decision_counts"] == {
        "candidate_history_available_not_party_history": 7,
        "different_or_ambiguous_independent_identity": 7,
        "generic_independent_label_not_continuing_entity": 24,
    }
