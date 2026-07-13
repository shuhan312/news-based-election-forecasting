"""Build the Surrey election and news research workbook from its spec file.

The workbook structure (15 tabs, headers, Elections register and Data
Dictionary) lives in src/workbook_spec.json, so the xlsx is reproducible
output rather than a hand-maintained file.  Result data is loaded from the
CSV files written by the extraction scripts whenever those files exist:

    data/elections/official_scc_candidate_results.csv -> Candidate Results
    data/elections/2026_east_surrey_results.csv       -> 2026 East Surrey
    data/elections/2026_west_surrey_results.csv       -> 2026 West Surrey

The default output is the canonical workbook.  An existing file is never
overwritten without --force, and --force first copies the current file to a
timestamped backup, because manually entered analysis would otherwise be lost.

Usage:
    python3 src/build_research_workbook.py
    python3 src/build_research_workbook.py --force
    python3 src/build_research_workbook.py --output /tmp/check.xlsx
"""

import argparse
import csv
import datetime
import json
import shutil
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = Path(__file__).resolve().parent / "workbook_spec.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/surrey_election_news_workbook_2026_07_14/Surrey_Election_News_Workbook.xlsx"

CSV_SOURCES = {
    "Candidate Results": REPO_ROOT / "data/elections/official_scc_candidate_results.csv",
    "Political Parties": REPO_ROOT / "data/elections/party_name_standardisation.csv",
    "Candidates": REPO_ROOT / "data/elections/candidate_name_standardisation.csv",
    "2026 East Surrey": REPO_ROOT / "data/elections/2026_east_surrey_results.csv",
    "2026 West Surrey": REPO_ROOT / "data/elections/2026_west_surrey_results.csv",
}

NUMERIC_FIELDS = {
    "Seats Available", "Votes Received", "Vote Share", "Final Position",
    "Winning Margin Votes", "Winning Margin Percentage Points", "Electorate",
    "Ballot Papers Issued", "Turnout", "Rejected Ballots",
    "Previous Party Vote Share", "Change In Vote Share",
}

HEADER_FONT = Font(bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill(fill_type="solid", fgColor="FF1F4E78")
HEADER_ROW_HEIGHT = 38
DATE_FORMAT = "yyyy-mm-dd"


def decode(value):
    # JSON has no date type, so the spec tags dates as {"__date__": "YYYY-MM-DD"}.
    if isinstance(value, dict) and "__date__" in value:
        return datetime.datetime.strptime(value["__date__"], "%Y-%m-%d")
    return value


def to_number(text):
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def write_row(sheet, row_index, values, headers):
    for column_index, value in enumerate(values, start=1):
        cell = sheet.cell(row=row_index, column=column_index, value=value)
        if isinstance(value, datetime.datetime):
            cell.number_format = DATE_FORMAT
        header = headers[column_index - 1] if column_index <= len(headers) else None
        # CSV values arrive as strings; cast known numeric columns so Excel
        # sorts/filters them as numbers instead of text.
        if header in NUMERIC_FIELDS and isinstance(value, str):
            cell.value = to_number(value)


def load_csv_rows(sheet_name, csv_path, headers):
    """Return CSV rows in workbook column order; the headers must match."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != headers:
            # A silent column-order mismatch would misfile votes under the
            # wrong header, so refuse to guess and stop instead.
            raise SystemExit(
                f"{csv_path} columns do not match the '{sheet_name}' tab; "
                "update src/workbook_spec.json or the extraction script first."
            )
        return [[row[h] if row[h] != "" else None for h in headers] for row in reader]


def build(spec, output_path):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_spec in spec["sheets"]:
        sheet = workbook.create_sheet(sheet_spec["name"])
        headers = sheet_spec["headers"]
        for column_index, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=column_index, value=header)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
        sheet.row_dimensions[1].height = HEADER_ROW_HEIGHT
        for letter, width in sheet_spec["column_widths"].items():
            sheet.column_dimensions[letter].width = width
        for column_index in range(len(sheet_spec["column_widths"]) + 1, len(headers) + 1):
            sheet.column_dimensions[get_column_letter(column_index)].width = 22

        rows = [[decode(v) for v in row] for row in sheet_spec["rows"]]
        source = CSV_SOURCES.get(sheet_spec["name"])
        if source is not None:
            if source.exists():
                rows = load_csv_rows(sheet_spec["name"], source, headers)
                print(f"{sheet_spec['name']}: loaded {len(rows)} rows from {source.relative_to(REPO_ROOT)}")
            else:
                print(f"{sheet_spec['name']}: {source.relative_to(REPO_ROOT)} not found; tab left empty")
        for row_index, values in enumerate(rows, start=2):
            write_row(sheet, row_index, values, headers)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    print(f"Wrote {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing workbook after saving a timestamped backup.")
    args = parser.parse_args()

    if args.output.exists():
        if not args.force:
            # The spec only holds structure and CSV-sourced rows; anything
            # typed straight into the workbook would be lost on rebuild.
            raise SystemExit(
                f"{args.output} already exists. The workbook may contain manual analysis; "
                "rerun with --force to back it up and rebuild."
            )
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = args.output.with_name(f"{args.output.stem}.pre-rebuild-{stamp}.xlsx")
        shutil.copy2(args.output, backup)
        print(f"Backed up existing workbook to {backup}")

    spec = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    build(spec, args.output)


if __name__ == "__main__":
    main()
