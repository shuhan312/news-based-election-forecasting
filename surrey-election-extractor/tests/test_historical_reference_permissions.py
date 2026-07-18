"""Tests for the additive official-boundary historical-reference audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from election_extractor.historical_baseline import load_crosswalk_resolution
from election_extractor.historical_reference_permissions import (
    APPROVED_STATUS,
    INSUFFICIENT_STATUS,
    build_historical_reference_permission_audit,
    historical_reference_permission_markdown,
    load_historical_reference_permission_configuration,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CROSSWALK_PATH = (
    PROJECT_ROOT
    / "outputs/geographic_crosswalk_resolution/geographic_crosswalk_resolution_dataset.json"
)
CONFIGURATION_PATH = PROJECT_ROOT / "config/historical_reference_permissions.json"


def _crosswalk_rows() -> tuple[dict[str, object], ...]:
    """Load the completed crosswalk exactly as the audit reads it."""

    return load_crosswalk_resolution(CROSSWALK_PATH)


def _configuration_payload() -> dict[str, object]:
    """Return an isolated editable copy for rejection tests."""

    return json.loads(CONFIGURATION_PATH.read_text(encoding="utf-8"))


def test_all_24_configured_direct_mappings_have_official_boundary_permission() -> None:
    """Every configured approval must be exact, sourced and limited in scope."""

    audit = build_historical_reference_permission_audit(_crosswalk_rows())
    records = audit["permission_records"]
    assert audit["summary"] == {
        "accepted_direct_relationships_reviewed": 24,
        "approved_for_historical_reference": 24,
        "insufficient_official_evidence": 0,
        "other_crosswalk_relationships_retained_without_reclassification": 143,
    }
    assert len(records) == 24
    assert all(record["historical_reference_status"] == APPROVED_STATUS for record in records)
    assert all(record["previous_winner_allowed"] is True for record in records)
    assert all(len(record["source_urls"]) == 5 for record in records)
    labels = {record["mapping_id"]: record["historical_event_area_name"] for record in records}
    assert labels["geographic-mapping-review:049"] == "Epsom Town & Downs"


def test_permission_cannot_transfer_candidates_incumbency_or_vote_change() -> None:
    """Even an approved boundary never becomes personal or swing evidence."""

    audit = build_historical_reference_permission_audit(_crosswalk_rows())
    for record in audit["permission_records"]:
        assert record["candidate_history_allowed"] is False
        assert record["incumbency_allowed"] is False
        assert record["party_vote_share_change_allowed"] is False


def test_unconfigured_direct_relationship_remains_insufficient(tmp_path: Path) -> None:
    """An omitted approval stays unavailable instead of being name-matched."""

    payload = _configuration_payload()
    payload["approved_mappings"] = payload["approved_mappings"][:1]
    configuration = tmp_path / "partial_permissions.json"
    configuration.write_text(json.dumps(payload), encoding="utf-8")

    audit = build_historical_reference_permission_audit(
        _crosswalk_rows(),
        configuration_path=configuration,
    )
    by_id = {record["mapping_id"]: record for record in audit["permission_records"]}

    assert by_id["geographic-mapping-review:006"]["historical_reference_status"] == APPROVED_STATUS
    assert by_id["geographic-mapping-review:007"]["historical_reference_status"] == INSUFFICIENT_STATUS
    assert by_id["geographic-mapping-review:007"]["previous_winner_allowed"] is False


def test_mismatched_or_non_direct_approval_is_rejected(tmp_path: Path) -> None:
    """A configuration cannot approve an area different from the reviewed GIS row."""

    payload = _configuration_payload()
    payload["approved_mappings"][0]["previous_area_name"] = "Different historic area"
    configuration = tmp_path / "mismatched_permissions.json"
    configuration.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        build_historical_reference_permission_audit(
            _crosswalk_rows(),
            configuration_path=configuration,
        )


def test_source_registry_requires_public_https_provenance(tmp_path: Path) -> None:
    """Permission evidence cannot be represented by an opaque or local path."""

    payload = _configuration_payload()
    payload["source_registry"][0]["source_url"] = "file:///private/evidence.pdf"
    configuration = tmp_path / "bad_source.json"
    configuration.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="HTTPS"):
        load_historical_reference_permission_configuration(configuration)


def test_report_keeps_citable_sources_and_explicit_limitations() -> None:
    """The report must explain evidence and limits without exposing raw results."""

    report = historical_reference_permission_markdown(
        build_historical_reference_permission_audit(_crosswalk_rows())
    )

    assert "Historic Surrey (2013–2021) to 2026 Historical Reference Permission Audit" in report
    assert "surrey-structural-changes-order-2026" in report
    assert "candidate identity" in report
    assert "legal succession" in report
