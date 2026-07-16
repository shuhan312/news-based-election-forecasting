"""Tests for the historical-election-only baseline feature safeguards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from election_extractor.historical_baseline import (
    NOT_COMPARABLE_STATUS,
    build_historical_baseline_features,
    classify_geographic_status,
)
from election_extractor.election_history import build_election_history


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _row_for_area(baseline: dict[str, object], area_name: str) -> dict[str, object]:
    """Locate one 2026 feature row by its preserved published ward name."""

    return next(
        row
        for row in baseline["baseline_feature_table"]
        if row["area_name"] == area_name
    )


def test_unavailable_geographic_features_remain_null_not_zero() -> None:
    """A partial relationship cannot receive an invented historical baseline."""

    baseline = build_historical_baseline_features()
    row = _row_for_area(baseline, "Bookham & Fetcham West Ward")
    reference = row["direct_historical_reference"]

    assert row["geographic_status"] == "partial_crosswalk_available"
    assert row["historical_baseline_available"] is False
    assert reference["previous_election_event_id"] is None
    assert reference["previous_winning_party"] is None
    assert reference["previous_turnout"] is None
    assert reference["previous_number_of_candidates"] is None


def test_partial_crosswalk_cannot_generate_comparison_or_party_history() -> None:
    """Partial crosswalk evidence remains visible but cannot become electoral evidence."""

    baseline = build_historical_baseline_features()
    row = _row_for_area(baseline, "Addlestone Ward")
    party_rows = [
        item
        for item in baseline["party_history_features"]
        if item["area_id"] == row["area_id"]
    ]

    assert row["geographic_status"] == "partial_crosswalk_available"
    assert "previous_winning_party" in row["blocked_features"]
    assert party_rows
    assert all(item["party_previously_contested"] is None for item in party_rows)
    assert all(item["previous_election_participation_count"] is None for item in party_rows)


def test_not_comparable_status_is_classified_as_blocked() -> None:
    """A purely non-comparable relationship can never become a direct baseline."""

    assert classify_geographic_status(({"analytical_status": NOT_COMPARABLE_STATUS},)) == NOT_COMPARABLE_STATUS


def test_candidate_history_never_uses_identical_names_as_identity() -> None:
    """Every target candidate remains unresolved without an explicit identifier."""

    baseline = build_historical_baseline_features()
    rows = baseline["candidate_history_infrastructure"]

    assert rows
    assert all(
        row["candidate_identity_status"] == "unresolved_no_explicit_identifier"
        and row["candidate_appeared_in_previous_events"] is None
        and row["incumbent_candidate"] is None
        for row in rows
    )


def test_uk_independence_party_and_reform_uk_remain_separate() -> None:
    """The baseline input preserves the prohibited UKIP/Reform distinction."""

    history = build_election_history()
    pairs = {
        (row["original_party_name"], row["standardised_party_name"])
        for row in history["canonical_candidate_results"]
        if row["original_party_name"] in {"UK Independence Party", "Reform UK"}
    }

    assert ("UK Independence Party", "UK Independence Party") in pairs
    assert ("Reform UK", "Reform UK") in pairs


def test_accepted_direct_is_the_only_status_with_historical_reference() -> None:
    """Approved direct rows may reference history; every other status stays blocked."""

    baseline = build_historical_baseline_features()
    rows = baseline["baseline_feature_table"]
    direct_rows = [row for row in rows if row["geographic_status"] == "accepted_direct"]
    blocked_rows = [row for row in rows if row["geographic_status"] != "accepted_direct"]

    assert len(direct_rows) == 22
    assert all(row["historical_baseline_available"] is True for row in direct_rows)
    assert all(row["historical_baseline_available"] is False for row in blocked_rows)
    assert all(
        row["direct_historical_reference"]["previous_election_event_id"] is None
        for row in blocked_rows
    )


def test_baseline_build_is_read_only_over_official_extraction_data() -> None:
    """Derived feature construction must not alter a completed source audit."""

    audit_path = PROJECT_ROOT / "outputs/2021_archive_discovery_pilot/2021_archive_discovery_pilot_audit.json"
    before = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    baseline = build_historical_baseline_features()
    after = hashlib.sha256(audit_path.read_bytes()).hexdigest()

    assert before == after
    assert len(baseline["baseline_readiness_dataset"]) == 81


def test_not_comparable_mapping_file_leaves_target_baseline_blocked(tmp_path: Path) -> None:
    """The output honours a non-comparable mapping rather than falling back to names."""

    resolution_path = tmp_path / "resolution.json"
    resolution_path.write_text(
        json.dumps(
            {
                "resolution_rows": [
                    {
                        "current_election_id": "surrey-county-council-2026-east-surrey",
                        "current_area_name": "Ashtead",
                        "analytical_status": "not_comparable",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    baseline = build_historical_baseline_features(crosswalk_resolution_path=resolution_path)
    ashstead = _row_for_area(baseline, "Ashtead Ward")

    assert ashstead["geographic_status"] == "not_comparable"
    assert ashstead["historical_baseline_available"] is False
    assert ashstead["direct_historical_reference"]["previous_winner_status"] is None
