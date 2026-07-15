/** Build the source-preserving master workbook from a prepared JSON payload. */

import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [payloadPath, outputPath] = process.argv.slice(2);

if (!payloadPath || !outputPath) {
  throw new Error(
    "Usage: node build_master_election_workbook.mjs <payload.json> <output.xlsx>",
  );
}

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const tableDefinitions = [
  ["Elections", "ElectionsTable"],
  ["Candidate Results", "CandidateResultsTable"],
  ["Divisions and Wards", "DivisionsAndWardsTable"],
  ["Candidates", "CandidatesTable"],
  ["Political Parties", "PoliticalPartiesTable"],
  ["Party History and New Entrants", "PartyHistoryTable"],
  ["Supplementary Metadata", "SupplementaryMetadataTable"],
  ["Data Dictionary", "DataDictionaryTable"],
];

const longTextColumns = new Set([
  "source_reference",
  "source_url",
  "official_source_url",
  "secondary_seats_source_url",
  "secondary_seats_evidence",
  "definition",
  "missing_value_policy",
  "notes",
  "source",
]);
const wholeNumberColumns = new Set([
  "election_year",
  "official_number_of_seats",
  "secondary_number_of_seats",
  "electorate",
  "ballot_papers_issued",
  "rejected_ballots",
  "total_votes",
  "votes",
  "first_observed_year",
]);
const percentageColumns = new Set(["vote_share", "turnout"]);
const identifierColumns = new Set(["metadata_id", "division_id", "candidate_id"]);

function widthFor(fieldName) {
  if (longTextColumns.has(fieldName)) return 48;
  if (identifierColumns.has(fieldName)) return 28;
  if (fieldName.endsWith("_status") || fieldName === "source_type") return 24;
  if (wholeNumberColumns.has(fieldName) || percentageColumns.has(fieldName)) return 16;
  if (fieldName.includes("name") || fieldName.includes("party")) return 28;
  return Math.min(Math.max(14, fieldName.length + 3), 28);
}

function formatTable(sheet, rowCount, headers, tableName) {
  const columnCount = headers.length;
  const range = sheet.getRangeByIndexes(0, 0, rowCount + 1, columnCount);
  const header = sheet.getRangeByIndexes(0, 0, 1, columnCount);
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  header.format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
  };
  range.format.wrapText = true;
  range.format.verticalAlignment = "top";
  range.format.borders = { preset: "inside", style: "thin", color: "#D9E2F3" };
  for (let index = 0; index < headers.length; index += 1) {
    const fieldName = headers[index];
    const column = sheet.getRangeByIndexes(0, index, rowCount + 1, 1);
    column.format.columnWidth = widthFor(fieldName);
    if (wholeNumberColumns.has(fieldName)) column.format.numberFormat = "#,##0";
    if (percentageColumns.has(fieldName)) column.format.numberFormat = '0.0"%"';
  }
  const table = sheet.tables.add(
    `A1:${columnLetter(columnCount)}${rowCount + 1}`,
    true,
    tableName,
  );
  table.style = "TableStyleMedium2";
}

function columnLetter(columnNumber) {
  let output = "";
  let value = columnNumber;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    output = String.fromCharCode(65 + remainder) + output;
    value = Math.floor((value - 1) / 26);
  }
  return output;
}

const workbook = Workbook.create();
const previewRanges = [];
for (const [sheetName, tableName] of tableDefinitions) {
  const rows = payload[sheetName];
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error(`Workbook payload has no rows for ${sheetName}.`);
  }
  const headers = Object.keys(rows[0]);
  const sheet = workbook.worksheets.add(sheetName);
  // Values are copied field-for-field from the prepared audited payload. Null
  // remains a blank Excel cell; this writer never substitutes zero or derives
  // final position, party history, or missing official Seats values.
  const matrix = [
    // Database headers retain the documented snake_case field names so that
    // later analysis code can refer to the schema without display-name mapping.
    headers,
    ...rows.map((row) => headers.map((header) => row[header] ?? null)),
  ];
  sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).values = matrix;
  formatTable(sheet, rows.length, headers, tableName);
  // Large candidate tables are checked through a representative top range so
  // visual verification remains practical without altering the workbook data.
  previewRanges.push({
    sheetName,
    range: `A1:${columnLetter(Math.min(headers.length, 8))}${Math.min(matrix.length, 20)}`,
  });
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 2500,
  tableMaxRows: 3,
  tableMaxCols: 8,
});
console.log(overview.ndjson);

// The new generic evidence table has provenance columns beyond the standard
// preview width, so inspect its complete header and the two approved 2013
// turnout records before exporting the workbook.
const supplementaryCheck = await workbook.inspect({
  kind: "table",
  range: "Supplementary Metadata!A1:N3",
  tableMaxRows: 3,
  tableMaxCols: 14,
  maxChars: 5000,
});
console.log(supplementaryCheck.ndjson);

// The master database is value-based, but scan for standard Excel formula
// errors before export so a future calculated column cannot silently ship a
// broken reference in an otherwise valid workbook.
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { use_regex: true, max_results: 100 },
  summary: "final formula error scan",
});
console.log(formulaErrors.ndjson);

// Save one preview per populated worksheet so the generated workbook can be
// visually checked after each audited election is added to the master dataset.
for (const { sheetName, range } of previewRanges) {
  const preview = await workbook.render({
    sheetName,
    range,
    scale: 1,
    format: "png",
  });
  const previewName = `preview_${sheetName.replaceAll(" ", "_")}.png`;
  await fs.writeFile(
    path.join(path.dirname(outputPath), previewName),
    new Uint8Array(await preview.arrayBuffer()),
  );
}
