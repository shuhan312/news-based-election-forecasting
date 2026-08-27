"""Regression tests for the final cross-layer provenance audit."""

import pytest

from audit_leakage_provenance import (PROVENANCE_FIELDS, AuditFailure,
                                      _require, run_audit)


def test_leakage_provenance_audit_passes():
    report = run_audit()
    assert report["status"] == "pass"
    assert all(check["status"] == "pass"
               for check in report["checks"].values())
    assert set(report["checks"]) == {
        "query_provenance",
        "article_chronology_and_duplicates",
        "feature_outcome_isolation_and_party_identity",
        "stage1_split_leakage_and_contestation",
        "blinded_prediction_freeze_integrity",
        "area_selection_chronology",
    }
    stage1 = report["checks"]["stage1_split_leakage_and_contestation"]
    assert stage1["selected_target_fields"] == 0
    assert stage1["contests_present_in_both_train_and_test"] == 0
    assert stage1["did_not_contest_encoded_as_candidate_rows"] is False


def test_unknown_chronology_is_left_blank():
    rows = run_audit()["event_chronology"]
    assert len(rows) == 4
    assert all(tuple(row) == PROVENANCE_FIELDS for row in rows)
    assert all(row["outcome_available_date"] == "" for row in rows)
    assert all(row["prediction_created_at"] == "" for row in rows)
    assert all(row["commit_hash"] for row in rows)
    assert len({row["event_id"] for row in rows}) == len(rows)


def test_guard_is_not_disabled_by_python_optimisation():
    with pytest.raises(AuditFailure, match="deliberate failure"):
        _require(False, "deliberate failure")
