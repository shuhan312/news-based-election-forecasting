#!/usr/bin/env python3
"""Generate the final review of later Independent previous-share NULLs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from no_news_baseline.independent_previous_share_audit import (
    audit_independent_previous_share_nulls,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_FEATURES = (
    PROJECT_ROOT
    / "outputs/electoral_fundamentals/electoral_fundamentals_features.csv"
)
DEFAULT_MASTER = (
    REPOSITORY_ROOT
    / "surrey-election-extractor/outputs/master_surrey_election_database/"
    "master_election_database_payload.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "outputs/electoral_fundamentals/independent_history_null_audit.md"
)


def _read_features(path: Path) -> tuple[dict[str, object], ...]:
    """Read released CSV values back into the small typed audit contract."""

    with path.open(encoding="utf-8", newline="") as handle:
        rows = []
        for source in csv.DictReader(handle):
            row: dict[str, object] = dict(source)
            row["previous_party_vote_share"] = (
                None
                if source["previous_party_vote_share"] == ""
                else float(source["previous_party_vote_share"])
            )
            rows.append(row)
    return tuple(rows)


def _render(audit: dict[str, object]) -> str:
    """Render a concise row-level decision table for dissertation review."""

    counts = audit["decision_counts"]
    lines = [
        "# Independent previous-party-share NULL audit",
        "",
        "## Conclusion",
        "",
        f"Reviewed {audit['audited_rows']} later-election Independent rows with an "
        "approved previous area. No party-level previous vote share is recoverable.",
        "",
        "`Independent` is not one continuing party. A verified candidate link remains "
        "available through `candidate_previously_stood`; it is not copied into "
        "`previous_party_vote_share`.",
        "",
        "## Decision counts",
        "",
    ]
    lines.extend(f"- `{name}`: {value}" for name, value in counts.items())
    lines.extend(
        [
            "",
            "## Row review",
            "",
            "| Date | Area | Current Independent | Previous Independent | Decision |",
            "|---|---|---|---|---|",
        ]
    )
    for row in audit["decisions"]:
        current = "; ".join(row["current_independent_candidates"]) or "None"
        previous = "; ".join(row["previous_independent_candidates"]) or "None"
        lines.append(
            f"| {row['election_date']} | {row['area_name']} | {current} | "
            f"{previous} | `{row['decision']}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    """Load the current release and write the reproducible review report."""

    master = json.loads(DEFAULT_MASTER.read_text(encoding="utf-8"))
    audit = audit_independent_previous_share_nulls(
        _read_features(DEFAULT_FEATURES), master["Candidate Results"]
    )
    DEFAULT_OUTPUT.write_text(_render(audit), encoding="utf-8")
    print(DEFAULT_OUTPUT)


if __name__ == "__main__":
    main()
