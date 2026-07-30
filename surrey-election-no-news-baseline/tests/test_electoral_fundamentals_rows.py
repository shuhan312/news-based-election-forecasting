"""Tests for building the fundamentals election-area-party row index."""

import json
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_rows import (
    build_fundamentals_row_index,
    load_party_feature_rows,
)
from contract_expectations import FUNDAMENTALS_INDEX_ROWS, FUNDAMENTALS_SOURCE_ROWS


def _feature(
    contest_id: str,
    party: str,
    *,
    area_name: str = "Area A",
) -> dict[str, object]:
    """Create a small valid source record for focused unit tests."""

    return {
        "party_contest_id": contest_id,
        "election_id": "surrey-2021",
        "election_date": "6 May 2021",
        "division_id": "area-a",
        "division_name": area_name,
        "standard_party_name": party,
    }


def test_loader_reads_predictor_side_rows(tmp_path: Path) -> None:
    """The loader should return valid party-contest rows from the JSON contract."""

    # A temporary file keeps this unit test independent of generated project
    # outputs and checks the expected {"rows": [...]} input structure directly.
    path = tmp_path / "features.json"
    path.write_text(json.dumps({"rows": [_feature("a", "Party A")]}), encoding="utf-8")

    rows = load_party_feature_rows(path)

    assert len(rows) == 1
    assert rows[0]["standard_party_name"] == "Party A"


def test_builds_one_row_per_election_area_standard_party() -> None:
    """Records sharing an election-area-party key should form one traceable row."""

    # Two Independent candidate records have the same standardised party key.
    # They therefore belong to one party-level row, while Party A remains a
    # separate row in the same election and area.
    rows = build_fundamentals_row_index(
        [
            _feature("independent-a", "Independent"),
            _feature("independent-b", "Independent"),
            _feature("party-a", "Party A"),
        ]
    )

    assert len(rows) == 2
    independent = next(row for row in rows if row["standard_party_name"] == "Independent")
    # Both original IDs are retained so the grouped party row can be traced
    # back to the candidate-specific records produced by the extractor.
    assert independent["source_party_contest_count"] == 2
    assert independent["source_party_contest_ids"] == (
        "independent-a",
        "independent-b",
    )


def test_grouped_identifier_conflict_is_not_silently_resolved() -> None:
    """Conflicting area metadata within one row key should stop construction."""

    # The same election-area-party key cannot safely represent two different
    # area names, so the conflict must be reported rather than choosing one.
    conflicting = _feature("b", "Party A", area_name="Different Area Name")

    with pytest.raises(ValueError, match="disagree on division_name"):
        build_fundamentals_row_index([_feature("a", "Party A"), conflicting])


def test_duplicate_source_party_contest_id_is_rejected() -> None:
    """Each extractor party-contest record must be used at most once."""

    # Reusing one source ID for different parties would make row provenance
    # ambiguous and could also count the same extractor record twice.
    with pytest.raises(ValueError, match="Duplicate source"):
        build_fundamentals_row_index(
            [_feature("duplicate", "Party A"), _feature("duplicate", "Party B")]
        )


def test_local_extractor_contract_has_unique_fundamentals_keys() -> None:
    """The real extractor release should produce the expected unique row index."""

    project_root = Path(__file__).resolve().parents[1]
    path = (
        project_root.parent
        / "surrey-election-extractor"
        / "outputs/no_news_party_contests/no_news_party_contest_features.json"
    )
    # Generated extractor outputs may be absent in a clean clone. In that case
    # this integration check is skipped while the self-contained unit tests run.
    if not path.exists():
        pytest.skip("Regenerate the extractor party-feature contract for integration QA.")

    source_rows = load_party_feature_rows(path)
    index_rows = build_fundamentals_row_index(source_rows)

    assert len(source_rows) == FUNDAMENTALS_SOURCE_ROWS
    assert len(index_rows) == FUNDAMENTALS_INDEX_ROWS
    # Rebuild the composite keys independently to confirm that every final row
    # represents one unique election, area and standardised party combination.
    assert len(
        {
            (row["election_id"], row["area_id"], row["standard_party_name"])
            for row in index_rows
        }
    ) == len(index_rows)
