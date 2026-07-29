"""Build the single research workbook, with the fifteen tabs the brief asks for.

The supervisor's original email lists fifteen tabs and asks for them in one
workbook. What exists is two: an election workbook of fourteen tabs and a news
workbook of seven. Between them they hold all fifteen, plus six more that
Prompt 1 depends on. Nobody reading either one sees the project.

    "Please use the following tabs: 1. Elections 2. Candidate Results
     3. Divisions and Wards 4. Candidates 5. Political Parties 6. Party
     History and New Entrants 7. NewsAPI Searches 8. News Articles
     9. Article-Party Context 10. Article-Candidate Context 11. Local News
     Searches 12. Excluded Articles 13. 2026 East Surrey 14. 2026 West Surrey
     15. Data Dictionary"

Two decisions worth stating
---------------------------
**The extra sheets are kept, after the fifteen.** Geographic Mapping and
Analysis Voting Summary are not on the supervisor's tab list but Prompt 1
names both as canonical sources - historical information may only be
transferred where Geographic Mapping permits it, and Analysis Voting Summary
is "the preferred analysis-level source for contest-level values". Dropping
them to hit a tab count would remove the evidence the leakage controls rest
on. They follow the fifteen so the requested order is intact when the file is
opened.

**The election side is rebuilt, not copied.** The committed election workbook
was generated on 21 July and holds 20 elections and 1,971 candidate rows. Four
by-elections have been recovered from the archive since, and the current
contract holds 24 and 1,992. Copying the old file would ship a workbook that
disagrees with every figure in the model bundle, so the election sheets are
read from the freshly regenerated payload instead.

Run from the repository root:

    .venv/bin/python scripts/build_combined_research_workbook.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = REPO / (
    "surrey-election-extractor/outputs/master_surrey_election_database/"
    "master_election_database_payload.json"
)
NEWS_WORKBOOK = REPO / "outputs/news_workbook_2026-07-28/Surrey_Election_News_Workbook.xlsx"
OUT_DIRECTORY = REPO / "outputs/combined_research_workbook"

EAST_2026 = "surrey-county-council-2026-east-surrey"
WEST_2026 = "surrey-county-council-2026-west-surrey"

# The fifteen, in the supervisor's order. The second element says where the
# sheet comes from: "payload" is the election side, "news" the news workbook,
# and the two 2026 sheets are filtered out of Candidate Results exactly as the
# existing workbook builder does it.
REQUESTED_TABS: tuple[tuple[str, str], ...] = (
    ("Elections", "payload"),
    ("Candidate Results", "payload"),
    ("Divisions and Wards", "payload"),
    ("Candidates", "payload"),
    ("Political Parties", "payload"),
    ("Party History and New Entrants", "payload"),
    ("NewsAPI Searches", "news"),
    ("News Articles", "news"),
    ("Article-Party Context", "news"),
    ("Article-Candidate Context", "news"),
    ("Local News Searches", "news"),
    ("Excluded Articles", "news"),
    ("2026 East Surrey", "derived"),
    ("2026 West Surrey", "derived"),
    ("Data Dictionary", "combined"),
)

# Kept after the fifteen. Each is either named by Prompt 1 as canonical or
# carries provenance the rest of the workbook refers to.
SUPPORTING_TABS: tuple[tuple[str, str], ...] = (
    ("Geographic Mapping", "payload"),
    ("Analysis Voting Summary", "payload"),
    ("Supplementary Metadata", "payload"),
    ("Derived Metadata", "payload"),
    ("Party Standardisation Issues", "payload"),
    ("News Provenance", "news"),
)

HEADER_FILL = PatternFill("solid", fgColor="DDDDDD")
HEADER_FONT = Font(bold=True)
MAX_COLUMN_WIDTH = 60
# Evidence and supporting-passage columns are long prose; wrapping them keeps
# a row readable instead of running one cell off the screen.
WRAP_HINTS = ("passage", "evidence", "note", "reason", "text", "summary",
              "description", "definition")
URL_HINTS = ("url", "link", "source_url")


def read_news_sheets() -> dict[str, list[dict]]:
    """Every news sheet as a list of dicts, keyed by sheet name."""

    if not NEWS_WORKBOOK.exists():
        raise FileNotFoundError(
            f"News workbook not found at {NEWS_WORKBOOK}. Build it with "
            "src/news_features/build_news_workbook.py first."
        )
    workbook = load_workbook(NEWS_WORKBOOK, read_only=True, data_only=True)
    sheets: dict[str, list[dict]] = {}
    for name in workbook.sheetnames:
        rows = list(workbook[name].iter_rows(values_only=True))
        if not rows:
            sheets[name] = []
            continue
        headers = [str(h) if h is not None else "" for h in rows[0]]
        sheets[name] = [
            {header: value for header, value in zip(headers, row)}
            for row in rows[1:]
        ]
    workbook.close()
    return sheets


def rows_for(name: str, origin: str, payload: dict,
             news: dict[str, list[dict]]) -> list[dict]:
    """The rows for one sheet, from whichever source owns it."""

    if origin == "payload":
        return list(payload.get(name, []))
    if origin == "news":
        return list(news.get(name, []))
    if origin == "derived":
        # The supervisor asked for 2026 East and West on separate tabs and for
        # every candidate to be recorded, not only the two elected. Filtering
        # Candidate Results rather than re-deriving keeps these identical to
        # the canonical table.
        election = EAST_2026 if "East" in name else WEST_2026
        return [row for row in payload.get("Candidate Results", [])
                if str(row.get("election_id")) == election]
    if origin == "combined":
        return combined_data_dictionary(payload, news)
    raise ValueError(f"Unknown origin {origin!r} for sheet {name!r}")


def combined_data_dictionary(payload: dict,
                             news: dict[str, list[dict]]) -> list[dict]:
    """One dictionary covering both halves of the workbook.

    The two source workbooks each document their own sheets and neither
    documents the other's, so a reader of the merged file would find half its
    columns undefined. Rows are tagged with which half they came from, and the
    news half is normalised onto the election half's column names where they
    describe the same thing.
    """

    election_rows = list(payload.get("Data Dictionary", []))
    for row in election_rows:
        row.setdefault("dictionary_section", "election data")

    news_rows: list[dict] = []
    for source_sheet in ("Data Dictionary", "News Data Dictionary"):
        for row in news.get(source_sheet, []):
            entry = dict(row)
            entry["dictionary_section"] = "news data"
            news_rows.append(entry)

    # Where the news workbook has no dictionary of its own, describe its
    # sheets from their headers rather than leaving them undocumented.
    if not news_rows:
        for sheet_name, rows in news.items():
            if not rows:
                continue
            for column in rows[0]:
                news_rows.append({
                    "dictionary_section": "news data",
                    "sheet": sheet_name,
                    "field_name": column,
                    "description": (
                        "Documented in news_protocol/raw_news_schema.md and the "
                        "news collection report; listed here so no column in "
                        "this workbook is undefined."
                    ),
                })
    return election_rows + news_rows


def write_sheet(workbook: Workbook, name: str, rows: list[dict],
                headers: list[str] | None = None) -> int:
    """Write one sheet with the formatting the brief asks for.

    Freeze the header, add filters, size columns sensibly, wrap long prose and
    make source URLs clickable. Returns the number of data rows written.
    """

    sheet = workbook.create_sheet(title=name[:31])

    if headers is None:
        headers = []
        for row in rows:
            for column in row:
                if column not in headers:
                    headers.append(column)
    if not headers:
        # A sheet with no rows still gets a placeholder header, so its
        # absence is visible as "no data yet" rather than as a missing tab.
        headers = ["(no rows)"]

    sheet.append(headers)
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")

    for row in rows:
        sheet.append([_excel_safe(row.get(header)) for header in headers])

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(headers))}{max(len(rows) + 1, 1)}"
    )

    for index, header in enumerate(headers, start=1):
        letter = get_column_letter(index)
        lowered = header.lower()
        widest = max(
            [len(str(header))]
            + [len(str(row.get(header, ""))) for row in rows[:400]]
        )
        sheet.column_dimensions[letter].width = min(widest + 2, MAX_COLUMN_WIDTH)
        if any(hint in lowered for hint in WRAP_HINTS):
            for cell in sheet[letter][1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        if any(hint in lowered for hint in URL_HINTS):
            for cell in sheet[letter][1:]:
                value = str(cell.value or "")
                if value.startswith("http"):
                    cell.hyperlink = value
                    cell.style = "Hyperlink"
    return len(rows)


def _excel_safe(value):
    """Flatten anything Excel cannot hold, without losing it.

    Lists and dicts appear in the payload for multi-valued provenance fields.
    Writing them as JSON keeps the content readable and reversible; letting
    openpyxl raise would lose the column entirely.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def main() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    news = read_news_sheets()

    workbook = Workbook()
    workbook.remove(workbook.active)

    written: dict[str, int] = {}
    for name, origin in REQUESTED_TABS + SUPPORTING_TABS:
        rows = rows_for(name, origin, payload, news)
        written[name] = write_sheet(workbook, name, rows)

    OUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    path = OUT_DIRECTORY / f"Surrey_Election_Research_Workbook_{stamp}.xlsx"
    workbook.save(path)

    print(f"{len(REQUESTED_TABS)} requested tabs + "
          f"{len(SUPPORTING_TABS)} supporting tabs -> {path}\n")
    print("requested, in the supervisor's order:")
    for index, (name, _) in enumerate(REQUESTED_TABS, start=1):
        print(f"  {index:2d}. {name:32s} {written[name]:6d} rows")
    print("\nsupporting (named by Prompt 1 or carrying provenance):")
    for name, _ in SUPPORTING_TABS:
        print(f"      {name:32s} {written[name]:6d} rows")

    elections = len(payload.get("Elections", []))
    candidates = len(payload.get("Candidate Results", []))
    print(f"\nelection side: {elections} elections, {candidates} candidate rows")


if __name__ == "__main__":
    main()
