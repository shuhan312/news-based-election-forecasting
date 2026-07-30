"""Tests for unified NULL semantics and fold-only model preprocessing."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_builder import (
    build_electoral_fundamentals_features,
)
from no_news_baseline.electoral_fundamentals_rows import load_party_feature_rows
from no_news_baseline.model_input_preprocessing import (
    NULLABLE_PREDICTORS,
    add_model_input_semantics,
    apply_fold_imputation,
    eligible_model_target_rows,
    fit_fold_imputation,
)
from contract_expectations import (FUNDAMENTALS_INDEX_ROWS,
                                   FUNDAMENTALS_ELIGIBLE_ROWS)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR_OUTPUTS = PROJECT_ROOT.parent / "surrey-election-extractor/outputs"


def _row(**updates: object) -> dict[str, object]:
    """Create one complete synthetic fundamentals row for focused tests."""

    # Start from a valid 2021 Labour row, then change only the field relevant to
    # each test. This keeps a failure attributable to one modelling rule.
    row: dict[str, object] = {
        "election_id": "target",
        "election_date": "2021-05-06",
        "area_id": "area",
        "area_name": "Area",
        "standard_party_name": "Labour",
        "previous_party_vote_share": 20.0,
        "previous_party_rank": 2,
        "previous_party_was_winner": False,
        "previous_winning_margin": 100.0,
        "previous_turnout": 40.0,
        "incumbent_party": False,
        "incumbent_candidate_present": False,
        "candidate_previously_stood": False,
        "party_previously_stood": True,
        "first_party_appearance_in_area": False,
        "new_party_indicator": False,
        "election_type": "County Council election",
        "number_of_seats": 1,
        "number_of_candidates": 4,
        "days_since_previous_comparable_election": 1460,
        "previous_ukip_vote_share_in_area": None,
        "previous_election_id": "previous",
        "previous_party_vote_share_status": "observed_in_approved_previous_result",
        "evaluation_current_party_vote_share": 25.0,
    }
    row.update(updates)
    return row


def test_2013_is_history_only_and_outcomes_are_excluded() -> None:
    """Study-start rows remain documented but cannot become model targets."""

    row = _row(election_date="2013-05-02", previous_election_id=None)
    prepared = add_model_input_semantics((row,))[0]
    assert prepared["model_target_eligible"] is False
    assert prepared["historical_context_status"] == "study_start_history_only"
    assert "evaluation_current_party_vote_share" not in prepared
    assert eligible_model_target_rows((prepared,)) == ()


def test_zero_share_has_no_invented_rank() -> None:
    """A non-contesting party is observed at zero but has no electoral rank."""

    prepared = add_model_input_semantics(
        (_row(previous_party_vote_share=0.0, previous_party_rank=None),)
    )[0]
    assert prepared["previous_party_vote_share__missing"] is False
    assert prepared["previous_party_rank__missing"] is True
    assert prepared["previous_party_rank__applicable"] is False
    assert prepared["previous_party_rank__null_reason"] == "party_did_not_contest"


def test_unknown_boolean_is_not_changed_to_false_in_raw_contract() -> None:
    """Unknown remains NULL and receives a separate missing flag."""

    prepared = add_model_input_semantics((_row(incumbent_party=None),))[0]
    assert prepared["incumbent_party"] is None
    assert prepared["incumbent_party__missing"] is True
    assert prepared["incumbent_party__null_reason"] == "insufficient_evidence"


def test_fold_imputation_uses_training_rows_only() -> None:
    """A held-out extreme value cannot influence the training median."""

    training = add_model_input_semantics(
        (
            _row(area_id="a", previous_party_vote_share=10.0),
            _row(area_id="b", previous_party_vote_share=20.0),
        )
    )
    held_out = add_model_input_semantics(
        (_row(area_id="c", previous_party_vote_share=None),)
    )
    # Only 10 and 20 are fitted, so the expected median is 15. A value from the
    # held-out row would change this result and reveal preprocessing leakage.
    parameters = fit_fold_imputation(training)
    transformed = apply_fold_imputation(held_out, parameters)[0]
    assert transformed["previous_party_vote_share"] == 15.0
    assert transformed["previous_party_vote_share__missing"] is True


def test_real_release_retains_every_2026_row_without_complete_case_filter() -> None:
    """Boundary-change missingness must not remove any 2026 party contest."""

    feature_path = EXTRACTOR_OUTPUTS / "no_news_party_contests/no_news_party_contest_features.json"
    master_path = EXTRACTOR_OUTPUTS / "master_surrey_election_database/master_election_database_payload.json"
    overlap_path = EXTRACTOR_OUTPUTS / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json"
    if not all(path.exists() for path in (feature_path, master_path, overlap_path)):
        pytest.skip("Regenerate extractor outputs for integration QA.")
    master = json.loads(master_path.read_text(encoding="utf-8"))
    rows = build_electoral_fundamentals_features(
        load_party_feature_rows(feature_path),
        master,
        json.loads(overlap_path.read_text(encoding="utf-8")),
    )
    prepared = add_model_input_semantics(rows)
    eligible = eligible_model_target_rows(prepared)

    # These release-level counts guard against an apparently harmless filter
    # silently deleting parties or all changed-boundary wards in a later edit.
    assert len(prepared) == FUNDAMENTALS_INDEX_ROWS
    assert len(eligible) == FUNDAMENTALS_ELIGIBLE_ROWS
    principal_2026 = {
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }
    assert sum(row["election_id"] in principal_2026 for row in eligible) == 456
    assert sum("-2026" in str(row["election_id"]) for row in eligible) == 466
    assert all(
        f"{field}__missing" in row and f"{field}__applicable" in row
        for field in NULLABLE_PREDICTORS
        for row in prepared
    )


def test_real_pre_2026_fit_can_transform_every_2026_row() -> None:
    """Out-of-time preprocessing fits before 2026 and retains all held-out rows."""

    feature_path = EXTRACTOR_OUTPUTS / "no_news_party_contests/no_news_party_contest_features.json"
    master_path = EXTRACTOR_OUTPUTS / "master_surrey_election_database/master_election_database_payload.json"
    overlap_path = EXTRACTOR_OUTPUTS / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json"
    if not all(path.exists() for path in (feature_path, master_path, overlap_path)):
        pytest.skip("Regenerate extractor outputs for integration QA.")
    master = json.loads(master_path.read_text(encoding="utf-8"))
    prepared = add_model_input_semantics(
        build_electoral_fundamentals_features(
            load_party_feature_rows(feature_path),
            master,
            json.loads(overlap_path.read_text(encoding="utf-8")),
        )
    )
    eligible = eligible_model_target_rows(prepared)
    # This is the intended out-of-time design: historical eligible elections
    # fit preprocessing parameters, while every 2026 row is held out.
    training = tuple(row for row in eligible if "-2026" not in str(row["election_id"]))
    held_out_2026 = tuple(row for row in eligible if "-2026" in str(row["election_id"]))

    parameters = fit_fold_imputation(training)
    transformed = apply_fold_imputation(held_out_2026, parameters)

    assert parameters.fitted_row_count == len(training)
    assert len(transformed) == 466
    assert all(
        row[field] is not None
        for row in transformed
        for field in NULLABLE_PREDICTORS
    )


def test_model_input_release_script_runs_directly() -> None:
    """The documented script entry point must work without setting PYTHONPATH.

    Generated extractor inputs are intentionally not committed, so a clean
    clone may skip this integration check until those contracts are rebuilt.
    """

    required_inputs = (
        EXTRACTOR_OUTPUTS
        / "no_news_party_contests/no_news_party_contest_features.json",
        EXTRACTOR_OUTPUTS
        / "master_surrey_election_database/master_election_database_payload.json",
        EXTRACTOR_OUTPUTS
        / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json",
    )
    if not all(path.exists() for path in required_inputs):
        pytest.skip("Regenerate extractor outputs for release-entry-point QA.")

    # The current script writes to its ignored release directory. Running it
    # as a separate process reproduces the way another researcher will invoke
    # it and catches missing package-path setup that an imported test cannot.
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/build_model_input_contract.py")],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "electoral_fundamentals_model_input_contract.csv" in completed.stdout
    assert "electoral_fundamentals_null_semantics.md" in completed.stdout

    contract_path = (
        PROJECT_ROOT
        / "outputs/model_input_contract/electoral_fundamentals_model_input_contract.csv"
    )
    with contract_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    # All target dates must use the same machine-readable format. This also
    # confirms that the 456 principal-election rows and ten 2026 by-election
    # rows survive the release entry point together.
    assert all(len(row["election_date"]) == 10 for row in rows)
    assert all(row["election_date"][4] == "-" for row in rows)
    rows_2026 = [row for row in rows if row["election_date"].startswith("2026-")]
    assert len(rows_2026) == 466
    assert all(row["model_target_eligible"] == "true" for row in rows_2026)
