"""Render the concise quality report for an electoral-fundamentals release."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from no_news_baseline.electoral_fundamentals_schema import (
    EVALUATION_COLUMNS,
    PREDICTOR_COLUMNS,
    ROW_KEY_COLUMNS,
)


def render_quality_report(
    rows: Sequence[Mapping[str, object]],
    input_paths: Sequence[Path],
    generated_at: datetime,
) -> str:
    """Summarise coverage, evidence boundaries and the exact input version."""

    predictor_counts = _non_null_counts(rows, PREDICTOR_COLUMNS)
    evaluation_counts = _non_null_counts(rows, EVALUATION_COLUMNS)
    reform_rows = [row for row in rows if row["standard_party_name"] == "Reform UK"]
    ukip_known = sum(row["previous_ukip_vote_share_in_area"] is not None for row in reform_rows)
    input_hashes = tuple(_sha256(path) for path in input_paths)
    # Unlike the generation timestamp, this identifier changes only when the
    # content of one of the four upstream data contracts changes.
    data_version = hashlib.sha256("".join(input_hashes).encode("ascii")).hexdigest()[:16]
    input_lines = "\n".join(
        f"- `{_display_path(path)}` — SHA-256 `{file_hash}`"
        for path, file_hash in zip(input_paths, input_hashes, strict=True)
    )
    predictor_lines = "\n".join(
        f"| `{field}` | {predictor_counts[field]} | {len(rows) - predictor_counts[field]} | {predictor_counts[field] / len(rows):.1%} |"
        for field in PREDICTOR_COLUMNS
    )
    evaluation_lines = "\n".join(
        f"| `{field}` | {evaluation_counts[field]} | {len(rows) - evaluation_counts[field]} |"
        for field in EVALUATION_COLUMNS
    )
    unique_keys = len({tuple(row[column] for column in ROW_KEY_COLUMNS) for row in rows})
    return f"""# Electoral fundamentals data-quality report

**Generated (UTC):** {generated_at.astimezone(UTC).isoformat()}

**Data version:** `{data_version}`

## Release identity

- Rows: {len(rows):,}
- Unique `election × area × standardised party` keys: {unique_keys:,}
- Predictor columns: {len(PREDICTOR_COLUMNS)}
- NULL representation in CSV: empty cell
- Boolean representation in CSV: `true` / `false`
- Dates: ISO `YYYY-MM-DD`
- Evaluation outcomes are excluded from `electoral_fundamentals_predictors_only.csv`.

Input files and content hashes:

{input_lines}

## Predictor coverage

| Predictor | Non-NULL | NULL | Coverage |
| --- | ---: | ---: | ---: |
{predictor_lines}

## Evaluation-column coverage

| Evaluation field | Non-NULL | NULL |
| --- | ---: | ---: |
{evaluation_lines}

The 456 missing current-party vote shares are the party rows in the 2026
two-member wards. The extractor target contract does not treat an individual
candidate share, a direct sum of candidate percentages or a best-candidate
share as an interchangeable party-level outcome. Winner and seats-won targets
remain complete. This limitation affects later vote-share evaluation, not the
construction of pre-election predictors.

## Reform UK and UKIP boundary

Reform UK and UKIP remain separate political identities. The dedicated UKIP
context is populated for {ukip_known}/{len(reform_rows)} Reform UK rows; the
remaining {len(reform_rows) - ukip_known} rows stay NULL where approved direct
history or defensible exact-zero evidence is unavailable. UKIP context never
fills Reform UK's `previous_party_vote_share`.

## Interpretation boundaries

- Historical predictors require an approved predecessor strictly earlier than
  the target election.
- Current vote share, winner and seats are evaluation fields, not predictors.
- No news variables or same-election Surrey-wide aggregates are included.
- Missing historical values are retained as NULL rather than reconstructed
  across unapproved geography or political identity.
- Multiple component records sharing one standardised label are retained in
  `source_party_contest_ids`; evaluation totals are produced only when every
  component value is defined.
"""


def _non_null_counts(
    rows: Sequence[Mapping[str, object]], fields: Sequence[str]
) -> dict[str, int]:
    """Count observed values without treating valid zero or False as missing."""

    return {
        field: sum(row.get(field) is not None for row in rows)
        for field in fields
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    """Remove local user directories from input labels in the public report."""

    parts = path.resolve().parts
    for project_directory in (
        "surrey-election-extractor",
        "surrey-election-no-news-baseline",
    ):
        if project_directory in parts:
            return Path(*parts[parts.index(project_directory) :]).as_posix()
    return path.name
