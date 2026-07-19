"""Release-level tests for the Electoral Fundamentals Feature Table files."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from no_news_baseline.electoral_fundamentals_release import (
    DICTIONARY_COLUMNS,
    FULL_FEATURE_COLUMNS,
    PREDICTORS_ONLY_COLUMNS,
    create_electoral_fundamentals_release,
    load_feature_dictionary,
)
from no_news_baseline.electoral_fundamentals_schema import (
    EVALUATION_COLUMNS,
    FORBIDDEN_CURRENT_OUTCOME_COLUMNS,
    PREDICTOR_COLUMNS,
    ROW_KEY_COLUMNS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR_OUTPUTS = PROJECT_ROOT.parent / "surrey-election-extractor" / "outputs"
FIXED_GENERATION_TIME = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def _release(output_directory: Path) -> tuple[Path, ...]:
    """Generate a test release from the authentic extractor contracts."""

    return create_electoral_fundamentals_release(
        EXTRACTOR_OUTPUTS / "no_news_party_contests/no_news_party_contest_features.json",
        EXTRACTOR_OUTPUTS / "no_news_party_contests/no_news_party_contest_targets.json",
        EXTRACTOR_OUTPUTS
        / "master_surrey_election_database/master_election_database_payload.json",
        EXTRACTOR_OUTPUTS
        / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json",
        output_directory,
        generated_at=FIXED_GENERATION_TIME,
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def test_release_writes_the_four_requested_outputs(tmp_path: Path) -> None:
    """One construction run must create both tables, dictionary and report."""

    paths = _release(tmp_path)
    assert [path.name for path in paths] == [
        "electoral_fundamentals_features.csv",
        "electoral_fundamentals_predictors_only.csv",
        "electoral_feature_dictionary.csv",
        "electoral_fundamentals_data_quality.md",
    ]
    assert all(path.is_file() for path in paths)


def test_predictor_release_has_fixed_rows_columns_and_unique_keys(tmp_path: Path) -> None:
    """The modelling matrix must retain exactly one stable row per unit."""

    _, predictors_path, _, _ = _release(tmp_path)
    columns, rows = _read_csv(predictors_path)
    assert columns == list(PREDICTORS_ONLY_COLUMNS)
    assert len(rows) == 1_592
    keys = [tuple(row[column] for column in ROW_KEY_COLUMNS) for row in rows]
    assert len(keys) == len(set(keys))
    # All published target dates use one machine-readable format even though
    # the extractor preserves some dates in official long-form wording.
    assert all(len(row["election_date"]) == 10 for row in rows)
    assert all(row["election_date"][4] == "-" for row in rows)


def test_predictors_only_file_contains_no_evaluation_or_outcome_columns(
    tmp_path: Path,
) -> None:
    """Realised results must remain outside the future modelling matrix."""

    _, predictors_path, _, _ = _release(tmp_path)
    columns, _ = _read_csv(predictors_path)
    assert not set(EVALUATION_COLUMNS) & set(columns)
    assert not set(FORBIDDEN_CURRENT_OUTCOME_COLUMNS) & set(columns)
    assert set(PREDICTOR_COLUMNS) <= set(columns)


def test_full_table_keeps_evaluation_columns_separate_and_traceable(
    tmp_path: Path,
) -> None:
    """The inspection table may retain outcomes only under evaluation names."""

    full_path, _, _, _ = _release(tmp_path)
    columns, rows = _read_csv(full_path)
    assert columns == list(FULL_FEATURE_COLUMNS)
    assert set(EVALUATION_COLUMNS) <= set(columns)
    assert all(row["evaluation_source_urls"] for row in rows)


def test_dictionary_documents_every_released_column_once(tmp_path: Path) -> None:
    """Published fields must have one definition and an explicit model role."""

    _, _, dictionary_path, _ = _release(tmp_path)
    columns, rows = _read_csv(dictionary_path)
    assert columns == list(DICTIONARY_COLUMNS)
    assert [row["field_name"] for row in rows] == list(FULL_FEATURE_COLUMNS)
    assert all(row["definition"] and row["missing_value_policy"] for row in rows)
    allowed = {row["field_name"] for row in rows if row["allowed_in_no_news_model"] == "Yes"}
    assert allowed == set(PREDICTOR_COLUMNS)


def test_metadata_reader_rejects_a_dictionary_that_does_not_match_schema(
    tmp_path: Path,
) -> None:
    """Documentation drift must stop release instead of silently changing it."""

    invalid_metadata = tmp_path / "metadata.csv"
    invalid_metadata.write_text(
        ",".join(DICTIONARY_COLUMNS) + "\nwrong_field,predictor,number,x,x,x,x,Yes\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="document released columns"):
        load_feature_dictionary(invalid_metadata)


def test_quality_report_discloses_multi_member_evaluation_gap(tmp_path: Path) -> None:
    """The release must not hide undefined 2026 party-share outcomes."""

    _, _, _, report_path = _release(tmp_path)
    report = report_path.read_text(encoding="utf-8")
    assert "456 missing current-party vote shares" in report
    assert "two-member wards" in report
    assert "/Users/" not in report


def test_release_is_byte_reproducible_with_fixed_generation_time(
    tmp_path: Path,
) -> None:
    """Identical inputs and metadata must produce byte-identical artifacts."""

    first = _release(tmp_path / "first")
    second = _release(tmp_path / "second")
    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
