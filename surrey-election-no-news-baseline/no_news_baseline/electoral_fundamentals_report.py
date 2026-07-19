"""Render the concise quality report for an electoral-fundamentals release."""

from __future__ import annotations

import hashlib
from collections import Counter
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
    method_version: str,
) -> str:
    """Summarise coverage, evidence boundaries and the exact input version."""

    predictor_counts = _non_null_counts(rows, PREDICTOR_COLUMNS)
    evaluation_counts = _non_null_counts(rows, EVALUATION_COLUMNS)
    reform_rows = [row for row in rows if row["standard_party_name"] == "Reform UK"]
    ukip_known = sum(row["previous_ukip_vote_share_in_area"] is not None for row in reform_rows)
    crosswalk_party_zeros = sum(
        row["previous_party_vote_share_status"]
        == "observed_zero_across_complete_previous_crosswalk"
        for row in rows
    )
    method_counts = Counter(row["evaluation_party_vote_share_method"] for row in rows)
    multi_member_gaps = [
        float(row["evaluation_party_vote_share_sensitivity_gap_pp"])
        for row in rows
        if row["evaluation_party_vote_share_method"]
        == "multi_member_best_placed_candidate_normalised"
    ]
    input_hashes = tuple(_sha256(path) for path in input_paths)
    # Unlike the generation timestamp, this identifier changes only when the
    # content of one of the four upstream data contracts changes.
    input_data_version = hashlib.sha256(
        "".join(input_hashes).encode("ascii")
    ).hexdigest()[:16]
    release_version = hashlib.sha256(
        f"{method_version}:{input_data_version}".encode("utf-8")
    ).hexdigest()[:16]
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

**Input data version:** `{input_data_version}`

**Method version:** `{method_version}`

**Release version:** `{release_version}`

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

Party vote-share outcomes are complete. {method_counts['single_member_candidate_share']}
single-member rows retain their candidate share. The {method_counts['multi_member_best_placed_candidate_normalised']}
party rows in the 2026 two-member wards use each party's best-placed candidate
vote, normalised across parties within the ward. This is the conventional UK
multi-member reporting method documented in House of Commons Standard Note
SN05064; it is not a claim that a separate party ballot was observed.

The release also calculates an average-candidate alternative for sensitivity
analysis, following the method discussed by Ware et al. (2006). Across the
2026 party rows, the mean absolute difference between definitions is
{sum(multi_member_gaps) / len(multi_member_gaps):.3f} percentage points and the
maximum is {max(multi_member_gaps):.3f} percentage points. Model conclusions
for 2026 vote share should be reported under the primary definition and checked
against this alternative.

Method references:

- House of Commons Library, *Calculation of Vote Shares in Multi-Member
  Wards*, Standard Note SN05064, pp. 18–19:
  https://researchbriefings.files.parliament.uk/documents/SN05064/SN05064.pdf
- Ware, Borisyuk, Rallings and Thrasher (2006), *A new algorithm for estimating
  voter turnout when the number of ballot papers issued is unknown*,
  `doi:10.1016/j.electstud.2005.04.003`.
- Electoral Commission guidance confirms that multi-seat local results count
  votes for each candidate and elect the candidates with the most votes:
  https://www.electoralcommission.org.uk/full-guidance/guidance-candidates-and-agents-local-government-elections-england

## Reform UK and UKIP boundary

Reform UK and UKIP remain separate political identities. The dedicated UKIP
context is populated for {ukip_known}/{len(reform_rows)} Reform UK rows; the
remaining {len(reform_rows) - ukip_known} rows stay NULL where approved direct
history or defensible exact-zero evidence is unavailable. UKIP context never
fills Reform UK's `previous_party_vote_share`.

## Changed-boundary exact zeros

The official 2021-to-2026 GIS crosswalk and complete 2021 candidate lists prove
{crosswalk_party_zeros} additional same-party historical shares to be exactly
zero. A value is released only when the crosswalk covers at least 99.8% of the
target ward and the party is absent from every contributing division. Polygon
area is never used to allocate positive votes; those cases remain NULL pending
polling-district electorate evidence.

## Interpretation boundaries

- Historical predictors require an approved predecessor strictly earlier than
  the target election.
- Current vote share, winner and seats are evaluation fields, not predictors.
- Multi-member party shares are analytical outcomes derived from complete
  official candidate votes and carry an explicit method label.
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
