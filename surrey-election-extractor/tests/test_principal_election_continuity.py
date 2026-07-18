"""Tests for the separate pre-2024 statutory continuity evidence layer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from election_extractor.principal_election_continuity import (
    APPROVED_STATUS,
    build_principal_election_continuity_audit,
    load_principal_election_continuity_configuration,
    principal_election_continuity_markdown,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIGURATION_PATH = (
    PROJECT_ROOT / "config/principal_election_continuity_permissions.json"
)


def _configuration_payload() -> dict[str, object]:
    """Return an isolated copy for configuration-rejection tests."""

    return json.loads(CONFIGURATION_PATH.read_text(encoding="utf-8"))


def test_two_adjacent_principal_transitions_have_exact_legal_continuity() -> None:
    """2013→2017 and 2017→2021 each require all 81 exact published names."""

    audit = build_principal_election_continuity_audit()

    assert audit["summary"] == {
        "transitions_approved": 2,
        "division_references_approved": 162,
        "party_history_references_approved": 706,
        "candidate_identity_references_created": 0,
        "incumbency_references_created": 0,
        "party_vote_share_change_values_created": 0,
    }
    assert all(
        row["matched_exact_area_count"] == 81
        and not row["previous_only_area_names"]
        and not row["current_only_area_names"]
        for row in audit["transition_records"]
    )


def test_continuity_exposes_only_allowed_source_reported_prior_values() -> None:
    """A legal-continuity reference never becomes candidate identity or swing data."""

    audit = build_principal_election_continuity_audit()
    reference = next(
        row
        for row in audit["division_references"]
        if row["current_election_id"] == "surrey-county-council-2017"
        and row["current_area_name"] == "Addlestone"
    )

    assert reference["historical_reference_status"] == APPROVED_STATUS
    assert reference["previous_election_event_id"] == "surrey-county-council-2013"
    assert reference["previous_winning_candidate_name"] == "Furey, John Raymond"
    assert reference["previous_winning_party"] == "Conservative"
    assert reference["candidate_history_allowed"] is False
    assert reference["incumbency_allowed"] is False
    assert reference["party_vote_share_change_allowed"] is False


def test_party_history_uses_exact_published_labels_without_party_merging() -> None:
    """The history rows compare spelling exactly and retain UKIP/Reform separation."""

    audit = build_principal_election_continuity_audit()
    rows = audit["party_history_references"]

    assert rows
    assert all(row["provenance"] == "deterministically_derived" for row in rows)
    assert all(isinstance(row["original_party_name"], str) for row in rows)
    assert not any(
        row["original_party_name"] == "Reform UK"
        and row["current_election_id"] == "surrey-county-council-2017"
        for row in rows
    )


def test_single_member_exact_label_prior_share_is_separate_from_swing() -> None:
    """Prior share is allowed only under the narrow configured baseline rule."""

    audit = build_principal_election_continuity_audit()
    reference = next(
        row for row in audit["party_history_references"]
        if row["current_election_id"] == "surrey-county-council-2017"
        and row["current_area_name"] == "Addlestone"
        and row["original_party_name"] == "Conservative"
    )
    assert reference["previous_party_vote_share"] == 40.0
    assert reference["previous_party_vote_share_status"] == (
        "derived_single_member_exact_label_prior_candidate_share"
    )


def test_configuration_rejects_non_https_legal_source(tmp_path: Path) -> None:
    """An opaque or local evidence reference cannot approve continuity."""

    payload = _configuration_payload()
    payload["source_registry"][0]["source_url"] = "file:///private/order.pdf"
    path = tmp_path / "invalid-continuity.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="HTTPS"):
        load_principal_election_continuity_configuration(path)


def test_continuity_build_is_read_only_over_official_audit_inputs() -> None:
    """The audit reads extracted values without altering the official source record."""

    audit_path = PROJECT_ROOT / "outputs/2017_full_extraction/2017_extraction_audit.json"
    before = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    report = build_principal_election_continuity_audit()
    after = hashlib.sha256(audit_path.read_bytes()).hexdigest()

    assert before == after
    assert "Candidate-identity references created: 0" in principal_election_continuity_markdown(report)
