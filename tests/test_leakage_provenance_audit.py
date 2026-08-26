"""Regression tests for the final cross-layer provenance audit."""

from audit_leakage_provenance import run_audit


def test_leakage_provenance_audit_passes():
    report = run_audit()
    assert report["status"] == "pass"
    assert all(check["status"] == "pass"
               for check in report["checks"].values())
