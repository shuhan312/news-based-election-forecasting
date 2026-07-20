#!/usr/bin/env python3
"""Generate the raw model-input contract and NULL-semantics report."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from no_news_baseline.electoral_fundamentals_builder import (
    build_electoral_fundamentals_features,
)
from no_news_baseline.electoral_fundamentals_rows import load_party_feature_rows
from no_news_baseline.model_input_preprocessing import (
    MODEL_CONTROL_COLUMNS,
    NULLABLE_PREDICTORS,
    NULL_REASON_COLUMNS,
    add_model_input_semantics,
    eligible_model_target_rows,
)
from no_news_baseline.electoral_fundamentals_schema import (
    IDENTIFIER_COLUMNS,
    PREDICTOR_COLUMNS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
EXTRACTOR_OUTPUTS = REPOSITORY_ROOT / "surrey-election-extractor/outputs"
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/model_input_contract"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _serialise(value: object) -> str | int | float:
    """Write stable CSV values while leaving source NULLs as empty cells."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value  # type: ignore[return-value]


def _report(rows: tuple[dict[str, object], ...]) -> str:
    """Summarise why predictor values are observed or unavailable."""

    # A fixed reason order keeps the generated Markdown table stable between
    # runs and makes changes in counts easy to review in version control.
    reason_names = (
        "observed",
        "study_start",
        "party_did_not_contest",
        "not_applicable",
        "changed_boundary",
        "insufficient_evidence",
    )
    by_field = {
        field: Counter(str(row[f"{field}__null_reason"]) for row in rows)
        for field in NULLABLE_PREDICTORS
    }
    eligible = eligible_model_target_rows(rows)
    # Report the two principal 2026 contests separately from 2026 by-elections
    # so QA can prove that changed-boundary wards were not dropped.
    principal_2026 = {
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }
    return "\n".join(
        [
            "# Electoral fundamentals model-input NULL audit",
            "",
            f"- Raw feature rows retained: {len(rows):,}",
            f"- Eligible target rows after excluding 2013: {len(eligible):,}",
            f"- 2026 principal-election rows retained: {sum(row['election_id'] in principal_2026 for row in eligible):,}",
            f"- All 2026 rows retained including by-elections: {sum('-2026' in str(row['election_id']) for row in eligible):,}",
            "- Complete-case deletion applied: No",
            "- Imputation applied in this output: No; fitting is required inside each training fold.",
            "",
            "## Predictor-level NULL semantics",
            "",
            "| Predictor | Observed | Study start | Did not contest | Not applicable | Changed boundary | Insufficient evidence |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *[
                "| `{}` | {} | {} | {} | {} | {} | {} |".format(
                    field, *(by_field[field][reason] for reason in reason_names)
                )
                for field in NULLABLE_PREDICTORS
            ],
            "",
            "The contract keeps raw NULLs. Missing and applicability indicators are "
            "available to the model, while reason columns remain audit information.",
            "",
        ]
    )


def main() -> None:
    """Build from extractor-owned inputs without reading target outcomes."""

    feature_path = EXTRACTOR_OUTPUTS / "no_news_party_contests/no_news_party_contest_features.json"
    master_path = EXTRACTOR_OUTPUTS / "master_surrey_election_database/master_election_database_payload.json"
    overlap_path = EXTRACTOR_OUTPUTS / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json"
    rows = build_electoral_fundamentals_features(
        load_party_feature_rows(feature_path), _json(master_path), _json(overlap_path)
    )
    # Export the raw, annotated contract rather than an imputed matrix. Model
    # evaluation must fit imputation later using training-fold rows only.
    model_rows = add_model_input_semantics(rows)
    columns = (
        IDENTIFIER_COLUMNS
        + PREDICTOR_COLUMNS
        + MODEL_CONTROL_COLUMNS
        + NULL_REASON_COLUMNS
    )
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIRECTORY / "electoral_fundamentals_model_input_contract.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        # Explicit field order makes the artefact reproducible and keeps each
        # predictor beside the controls defined by the shared schema.
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {column: _serialise(row.get(column)) for column in columns}
            for row in model_rows
        )
    report_path = OUTPUT_DIRECTORY / "electoral_fundamentals_null_semantics.md"
    report_path.write_text(_report(model_rows), encoding="utf-8")
    print(csv_path)
    print(report_path)


if __name__ == "__main__":
    main()
