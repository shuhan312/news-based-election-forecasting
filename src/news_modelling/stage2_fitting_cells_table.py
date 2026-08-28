"""Emit the Stage 2 fitting-cell chronology table (appendix table a20).

The frozen v2 protocol records that the enrichment model was fitted on 45
election x party cells but does not enumerate them.  This module derives the
enumeration the same way the frozen pipeline did - the protocol's
``fitting_elections`` joined to the Stage 1 bundle's out-of-fold predictions
under the production party mapping - so the table cannot drift from the
evidence it summarises.  One further row states the frozen 2026 test side.

Every cell row carries the election, its polling date, the news cut-off (the
last publication day eligible for that election's features, one day before
polling), the party key, the number of Stage 1 candidate rows behind the
cell's party-mean residual, and its role.  The chronology answers, in one
table, when each piece of information became available and how it was used.

Usage:
    PYTHONPATH=src .venv/bin/python -m news_modelling.stage2_fitting_cells_table
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from news_modelling.production_news_experiment import party_key

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "news_features/blinded_2026_predictions_v2/frozen_protocol.json"
OOF = (ROOT / "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
              "out_of_fold_predictions.csv")
OUT_DIR = ROOT / "outputs/report_tables_v1"
OUT_CSV = OUT_DIR / "a20_stage2_fitting_cells.csv"
OUT_TEX = OUT_DIR / "latex/a20_stage2_fitting_cells.tex"

PARTY_TEXT = {
    "conservative": "Conservative", "green": "Green", "labour": "Labour",
    "liberal_democrat": "Liberal Democrats", "reform_uk": "Reform UK",
    "ukip": "UKIP",
}


def _iso(value: str) -> date:
    """Parse the ISO and human-readable date formats carried by Stage 1."""

    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%d %B %Y").date()


def _election_text(election_id: str) -> str:
    if election_id == "surrey-county-council-2017":
        return "SCC 2017"
    if election_id == "surrey-county-council-2021":
        return "SCC 2021"
    name = election_id.replace("surrey-county-council-by-election-", "")
    return "By-election " + " ".join(
        part.capitalize() for part in name.rsplit("-", 3)[0].split("-"))


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    fitting_elections = protocol["fitting_elections"]

    cells: dict[tuple[str, str], int] = defaultdict(int)
    polling: dict[str, date] = {}
    with OOF.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["election_id"] not in fitting_elections:
                continue
            key = party_key(row["standard_party_name"])
            if key is None:
                continue
            cells[(row["election_id"], key)] += 1
            polling[row["election_id"]] = _iso(row["election_date"])
    assert len(cells) == protocol["fitting_rows"], (
        f"derived {len(cells)} cells against the protocol's "
        f"{protocol['fitting_rows']}")

    rows = []
    for (election_id, key), n_rows in sorted(
            cells.items(), key=lambda item: (polling[item[0][0]], item[0])):
        polling_day = polling[election_id]
        rows.append({
            "election": _election_text(election_id),
            "election_id": election_id,
            "polling_date": polling_day.isoformat(),
            "news_cutoff": (polling_day - timedelta(days=1)).isoformat(),
            "party": PARTY_TEXT[key],
            "party_key": key,
            "stage1_candidate_rows": n_rows,
            "role": "training",
        })
    test_day = date(2026, 5, 7)
    rows.append({
        "election": "2026 East and West Surrey (pooled)",
        "election_id": "ESWS-2026-05",
        "polling_date": test_day.isoformat(),
        "news_cutoff": (test_day - timedelta(days=1)).isoformat(),
        "party": "all six parties",
        "party_key": "",
        "stage1_candidate_rows": protocol["blinded_candidate_rows"],
        "role": "frozen test (blinded until the one-time unblinding)",
    })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("wrote", OUT_CSV)

    lines = ["\\begin{tabular}{llllrl}", "\\toprule",
             "election & polling date & news cut-off & party & "
             "Stage 1 rows & role \\\\", "\\midrule"]
    for row in rows:
        lines.append(
            f"{row['election']} & {row['polling_date']} & "
            f"{row['news_cutoff']} & {row['party']} & "
            f"{row['stage1_candidate_rows']} & {row['role'].split(' (')[0]}"
            " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    OUT_TEX.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT_TEX)
    reform = sum(1 for row in rows if row["party_key"] == "reform_uk")
    print(f"{len(rows) - 1} training cells ({reform} Reform UK) + 1 frozen "
          "test row")


if __name__ == "__main__":
    main()
