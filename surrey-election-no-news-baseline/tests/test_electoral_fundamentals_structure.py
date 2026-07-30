"""Tests for pre-election contest-structure fundamentals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_rows import (
    build_fundamentals_row_index,
    load_party_feature_rows,
)
from no_news_baseline.electoral_fundamentals_structure import (
    add_contest_structure_features,
)
from contract_expectations import FUNDAMENTALS_INDEX_ROWS


def _party_feature(
    contest_id: str,
    party: str,
    *,
    candidate_count: int = 1,
    seats: int = 1,
) -> dict[str, object]:
    """Create one predictor-side party record for a shared target area."""

    return {
        "party_contest_id": contest_id,
        "election_id": "target-election",
        "election_date": "2026-05-07",
        "election_type": "County Council election",
        "division_id": "target-area",
        "division_name": "Target Area",
        "standard_party_name": party,
        "analysis_number_of_seats": seats,
        "candidate_count_for_party": candidate_count,
    }


def _candidate(candidate_id: str, party: str) -> dict[str, object]:
    """Create one candidate belonging to the same target contest."""

    return {
        "candidate_id": candidate_id,
        "election_id": "target-election",
        "division_id": "target-area",
        "standard_party_name": party,
    }


def test_adds_shared_pre_election_contest_structure() -> None:
    """Every party row should receive the same ballot structure."""

    features = [
        _party_feature("contest-a", "Party A", candidate_count=2, seats=2),
        _party_feature("contest-b", "Party B", seats=2),
    ]
    candidates = [
        _candidate("candidate-a1", "Party A"),
        _candidate("candidate-a2", "Party A"),
        _candidate("candidate-b1", "Party B"),
    ]
    rows = build_fundamentals_row_index(features)

    completed = add_contest_structure_features(rows, features, candidates)

    assert len(completed) == 2
    assert {row["election_type"] for row in completed} == {
        "County Council election"
    }
    assert {row["number_of_seats"] for row in completed} == {2}
    assert {row["number_of_candidates"] for row in completed} == {3}


def test_rejects_disagreement_in_shared_seat_count() -> None:
    """Conflicting party records must not silently define the same contest."""

    features = [
        _party_feature("contest-a", "Party A", seats=1),
        _party_feature("contest-b", "Party B", seats=2),
    ]
    candidates = [
        _candidate("candidate-a", "Party A"),
        _candidate("candidate-b", "Party B"),
    ]

    with pytest.raises(ValueError, match="disagree on analysis_number_of_seats"):
        add_contest_structure_features(
            build_fundamentals_row_index(features), features, candidates
        )


def test_rejects_incomplete_candidate_count() -> None:
    """The party contract and complete candidate table must reconcile exactly."""

    features = [_party_feature("contest-a", "Party A", candidate_count=2)]
    candidates = [_candidate("candidate-a", "Party A")]

    with pytest.raises(ValueError, match="candidate counts disagree"):
        add_contest_structure_features(
            build_fundamentals_row_index(features), features, candidates
        )


def test_real_release_has_complete_reconciled_structure() -> None:
    """All released Surrey fundamentals rows should receive valid structure."""

    project_root = Path(__file__).resolve().parents[1]
    extractor_outputs = project_root.parent / "surrey-election-extractor" / "outputs"
    feature_path = (
        extractor_outputs
        / "no_news_party_contests/no_news_party_contest_features.json"
    )
    master_path = (
        extractor_outputs
        / "master_surrey_election_database/master_election_database_payload.json"
    )
    if not feature_path.exists() or not master_path.exists():
        pytest.skip("Regenerate extractor outputs for integration QA.")

    party_features = load_party_feature_rows(feature_path)
    master = json.loads(master_path.read_text(encoding="utf-8"))
    completed = add_contest_structure_features(
        build_fundamentals_row_index(party_features),
        party_features,
        master["Candidate Results"],
    )

    assert len(completed) == FUNDAMENTALS_INDEX_ROWS
    assert all(isinstance(row["election_type"], str) for row in completed)
    assert all(row["number_of_seats"] in {1, 2} for row in completed)
    assert all(row["number_of_candidates"] >= row["number_of_seats"] for row in completed)

    # The two 2026 principal releases used two-member wards. The separate 2026
    # Haslemere and Warlingham by-elections remain valid single-seat contests,
    # so the check selects the two principal election IDs explicitly.
    principal_2026_ids = {
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }
    rows_2026 = [
        row for row in completed if row["election_id"] in principal_2026_ids
    ]
    assert rows_2026
    assert {row["number_of_seats"] for row in rows_2026} == {2}
