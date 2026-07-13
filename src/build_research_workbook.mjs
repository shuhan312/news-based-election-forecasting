// Build the research workbook that will hold the Surrey election and news data.
// Run with Node.js in an environment that provides @oai/artifact-tool.

import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDirectory = "outputs/surrey_research_workbook";
const outputFile = `${outputDirectory}/Surrey_Election_News_Workbook.xlsx`;
const officialCandidateResultsFile = "data/elections/official_scc_candidate_results.csv";

const sources = {
  sccArchive: "https://mycouncil.surreycc.gov.uk/mgManageElectionResults.aspx?bcr=1",
  scc2013: "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=5&RPID=0",
  scc2017: "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=10&RPID=0",
  scc2021: "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0",
  east2026: "https://www10.surreycc.gov.uk/electionmap/eastSurrey/",
  west2026: "https://www10.surreycc.gov.uk/electionmap/WestSurrey/",
  newsApi: "https://newsapi.org/docs/endpoints/everything",
  surreyLive: "https://www.getsurrey.co.uk/",
  getSurreyArea: "https://www.getsurrey.co.uk/in-your-area",
  bbcSurrey: "https://www.bbc.co.uk/news/england/surrey",
  wokingNewsMail: "https://www.wokingnewsandmail.co.uk/",
  farnhamHerald: "https://www.farnhamherald.com/",
  guildfordDragon: "https://guildford-dragon.com/",
  epsomEwellTimes: "https://epsomandewelltimes.com/",
  surreyComet: "https://www.surreycomet.co.uk/",
  sccNewsArchive: "https://www.surreycc.gov.uk/community/culture-and-heritage/history-centre/marvels/newspapers",
};

const candidateResultHeaders = [
  "Candidate Result ID", "Election ID", "Election Name", "Election Date", "Election Type", "Authority", "Division/Ward ID", "Division/Ward Name", "Seats Available", "Candidate ID", "Candidate Name As Published", "Party ID", "Party Name As Published", "Standardised Party Name", "Party Category", "Votes Received", "Vote Share", "Final Position", "Elected", "Winning Candidate", "Winning Party", "Winning Margin Votes", "Winning Margin Percentage Points", "Electorate", "Ballot Papers Issued", "Turnout", "Rejected Ballots", "Previous Winning Party", "Previous Party Vote Share", "Change In Vote Share", "Candidate Previously Stood", "Incumbent Candidate", "Incumbent Party", "First Appearance Of Party In Area", "Source URL", "Notes",
];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let insideQuotes = false;

  // The official-results script writes standard CSV.  This small parser keeps
  // quoted commas in names and notes within one cell when the workbook is built.
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const nextCharacter = text[index + 1];
    if (character === '"' && insideQuotes && nextCharacter === '"') {
      value += '"';
      index += 1;
    } else if (character === '"') {
      insideQuotes = !insideQuotes;
    } else if (character === "," && !insideQuotes) {
      row.push(value);
      value = "";
    } else if ((character === "\n" || character === "\r") && !insideQuotes) {
      if (character === "\r" && nextCharacter === "\n") index += 1;
      row.push(value);
      if (row.some((cell) => cell !== "")) rows.push(row);
      row = [];
      value = "";
    } else {
      value += character;
    }
  }
  row.push(value);
  if (row.some((cell) => cell !== "")) rows.push(row);
  return rows;
}

async function loadOfficialCandidateRows() {
  try {
    const csvText = await fs.readFile(officialCandidateResultsFile, "utf8");
    const [headers, ...rawRows] = parseCsv(csvText);
    const headerPositions = new Map(headers.map((header, index) => [header, index]));
    const numericFields = new Set([
      "Seats Available", "Votes Received", "Vote Share", "Final Position",
      "Winning Margin Votes", "Winning Margin Percentage Points", "Electorate",
      "Ballot Papers Issued", "Turnout", "Rejected Ballots", "Previous Party Vote Share",
      "Change In Vote Share",
    ]);

    return rawRows.map((rawRow) => candidateResultHeaders.map((header) => {
      const cell = rawRow[headerPositions.get(header)] ?? "";
      if (header === "Election Date" && cell) return new Date(cell);
      if (numericFields.has(header) && cell !== "") return Number(cell);
      return cell;
    }));
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }
}

const officialCandidateRows = await loadOfficialCandidateRows();

// Each sheet is deliberately a flat table: later scripts can append records
// without changing the workbook layout by hand.
const sheets = [
  {
    name: "Elections",
    headers: [
      "Election ID", "Election Name", "Election Date", "Election Type",
      "Authority", "Geography Type", "Seats per Division/Ward", "Source URL",
      "Source Status", "Extraction Status", "Notes",
    ],
    rows: [
      ["SCC-2013-05", "2013 Surrey County Council election", new Date("2013-05-02"), "Scheduled", "Surrey County Council", "Electoral division", null, sources.scc2013, "Official source", "Not started", "Use the official result page as the raw source."],
      ["SCC-2017-05", "2017 Surrey County Council election", new Date("2017-05-04"), "Scheduled", "Surrey County Council", "Electoral division", null, sources.scc2017, "Official source", "To reconcile", "Existing project data needs to be reconciled with the official source."],
      ["SCC-2021-05", "2021 Surrey County Council election", new Date("2021-05-06"), "Scheduled", "Surrey County Council", "Electoral division", null, sources.scc2021, "Official source", "To reconcile", "Existing project data needs to be reconciled with the official source."],
      ["SCC-BYELECTIONS", "Surrey County Council by-elections", null, "By-election", "Surrey County Council", "Electoral division", null, sources.sccArchive, "Official archive", "Not started", "Keep by-elections separate from scheduled elections."],
      ["EAST-2026-05", "2026 East Surrey Council election", new Date("2026-05-07"), "Scheduled", "East Surrey Council", "Ward", 2, sources.east2026, "Official source", "Not started", "Do not merge with historic divisions without a documented crosswalk."],
      ["WEST-2026-05", "2026 West Surrey Council election", new Date("2026-05-07"), "Scheduled", "West Surrey Council", "Ward", 2, sources.west2026, "Official source", "Not started", "Do not merge with historic divisions without a documented crosswalk."],
    ],
  },
  {
    name: "Candidate Results",
    headers: candidateResultHeaders,
    rows: officialCandidateRows,
  },
  {
    name: "Divisions and Wards",
    headers: [
      "Division/Ward ID", "Name As Published", "Standardised Name", "Authority", "Geography Type", "Election ID", "Seats Available", "Town/Village", "Borough/District", "2026 Council", "Old Division To 2026 Ward Mapping Status", "Source URL", "Notes",
    ],
    rows: [],
  },
  {
    name: "Candidates",
    headers: [
      "Candidate ID", "Candidate Name As Published", "Standardised Candidate Name", "Known Variants", "First Election ID", "Latest Election ID", "Previously Stood", "Incumbent Candidate", "Current/Last Known Party", "Source URL", "Notes",
    ],
    rows: [],
  },
  {
    name: "Political Parties",
    headers: [
      "Party ID", "Party Name As Published", "Standardised Party Name", "Party Category", "Established/Emerging/Local/Independent", "First Appearance Election ID", "Source URL", "Notes",
    ],
    rows: [],
  },
  {
    name: "Party History and New Entrants",
    headers: [
      "Party History ID", "Party ID", "Standardised Party Name", "Start Election ID", "End Election ID", "Relationship To Earlier Party", "Related Earlier Party", "New Entrant Flag", "Evidence/Source URL", "Notes",
    ],
    rows: [],
  },
  {
    name: "NewsAPI Searches",
    headers: [
      "Search ID", "Election ID", "Division/Ward ID", "Division/Ward Name", "Search Scope", "Time Window", "Date From", "Date To", "Exact Search Query", "Domains Searched", "Sorting Method", "Search Date", "Results Returned", "Results Accepted", "Results Excluded", "NewsAPI Subscription/Access Note", "Status", "Notes",
    ],
    rows: [],
  },
  {
    name: "News Articles",
    headers: [
      "Article ID", "Election ID", "Division/Ward ID", "Search ID", "Publication", "Author", "Headline", "Description", "Article URL", "Publication Date And Time", "Original/Updated Date", "Article Type", "NewsAPI Content Extract", "Article Text/Archive Reference", "Word Count", "Paywall Status", "Duplicate/Syndicated Indicator", "Relevance Decision", "Reason For Inclusion/Exclusion", "Notes",
    ],
    rows: [],
  },
  {
    name: "Article-Party Context",
    headers: [
      "Party Context ID", "Article ID", "Party ID", "Party Name", "Number Of Mentions", "Prominence", "Context Tone", "Blame", "Credit", "Competence", "Integrity", "Main Associated Issue", "Directly Quoted", "Gaining/Losing Support", "Credible Challenger", "Voter Switching Discussed", "Switching From Party", "Switching To Party", "Local Relevance Score", "Electoral Relevance Score", "Supporting Text", "Notes",
    ],
    rows: [],
  },
  {
    name: "Article-Candidate Context",
    headers: [
      "Candidate Context ID", "Article ID", "Candidate ID", "Candidate Name", "Party ID", "Party Name", "Number Of Mentions", "Prominence", "Context Tone", "Blame", "Credit", "Competence", "Integrity", "Main Issue", "Directly Quoted", "Credible/Gaining Momentum/Protest Candidate", "Local Relevance Score", "Electoral Relevance Score", "Supporting Text", "Notes",
    ],
    rows: [],
  },
  {
    name: "Local News Searches",
    headers: [
      "Local Search ID", "Election ID", "Division/Ward ID", "Source Name", "Source URL/Domain", "Exact Search Query", "Date From", "Date To", "Search Date", "Results Returned", "Results Accepted", "Results Excluded", "Archive/Access Note", "Status", "Notes",
    ],
    rows: [],
  },
  {
    name: "Excluded Articles",
    headers: [
      "Excluded Article ID", "Article ID", "Search ID", "Publication", "Headline", "Article URL", "Publication Date", "Exclusion Reason", "Reviewed By", "Review Date", "Notes",
    ],
    rows: [],
  },
  {
    name: "2026 East Surrey",
    headers: [
      "Candidate Result ID", "Election Name", "Election Date", "Authority", "Ward Name", "Seats Available", "Candidate Name As Published", "Party Name As Published", "Standardised Party Name", "Votes Received", "Vote Share", "Final Position", "Elected", "Electorate", "Ballot Papers Issued", "Turnout", "Rejected Ballots", "Source URL", "Notes",
    ],
    rows: [],
  },
  {
    name: "2026 West Surrey",
    headers: [
      "Candidate Result ID", "Election Name", "Election Date", "Authority", "Ward Name", "Seats Available", "Candidate Name As Published", "Party Name As Published", "Standardised Party Name", "Votes Received", "Vote Share", "Final Position", "Elected", "Electorate", "Ballot Papers Issued", "Turnout", "Rejected Ballots", "Source URL", "Notes",
    ],
    rows: [],
  },
];

const dataDictionaryHeaders = ["Table", "Field/Resource", "Data Type", "Definition/Rule", "Source/Rule URL"];

function columnName(index) {
  let name = "";
  let value = index + 1;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
}

function preferredWidth(header) {
  if (header.includes("URL") || header.includes("Source/Rule")) return 42;
  if (header.includes("Notes") || header.includes("Supporting Text") || header.includes("Reason")) return 36;
  if (header.includes("Name") || header.includes("Description") || header.includes("Definition")) return 26;
  if (header.includes("Date")) return 15;
  if (header.includes("ID")) return 18;
  if (header.includes("Votes") || header.includes("Share") || header.includes("Turnout")) return 17;
  return 20;
}

function addSheet(workbook, sheetDefinition) {
  const sheet = workbook.worksheets.add(sheetDefinition.name);
  const allRows = [sheetDefinition.headers, ...sheetDefinition.rows];
  const lastColumn = columnName(sheetDefinition.headers.length - 1);

  sheet.getRange(`A1:${lastColumn}${allRows.length}`).values = allRows;
  sheet.getRange(`A1:${lastColumn}1`).format = {
    fill: "#1F4E78",
    font: { color: "#FFFFFF", bold: true },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: "#17365D" },
  };
  sheet.getRange(`A1:${lastColumn}1`).format.rowHeight = 38;
  sheet.getRange(`A1:${lastColumn}${allRows.length}`).format.wrapText = true;
  sheet.getRange(`A1:${lastColumn}${Math.max(2, allRows.length)}`).format.borders = {
    bottom: { style: "thin", color: "#D9E2F3" },
  };
  for (let index = 0; index < sheetDefinition.headers.length; index += 1) {
    sheet.getRange(`${columnName(index)}:${columnName(index)}`).format.columnWidth = preferredWidth(sheetDefinition.headers[index]);
  }
  if (allRows.length > 1) {
    sheet.getRange(`A2:${lastColumn}${allRows.length}`).format.autofitRows();
  }
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;

  // Keep election dates as dates, so later filters and checks still work.
  for (let index = 0; index < sheetDefinition.headers.length; index += 1) {
    if (sheetDefinition.headers[index].includes("Date")) {
      sheet.getRange(`${columnName(index)}2:${columnName(index)}${Math.max(2, allRows.length)}`).setNumberFormat("yyyy-mm-dd");
    }
  }
}

const workbook = Workbook.create();
for (const sheetDefinition of sheets) {
  addSheet(workbook, sheetDefinition);
}

const dictionary = workbook.worksheets.add("Data Dictionary");
const dictionaryRows = [
  ...sheets.flatMap((sheet) => sheet.headers.map((header) => [
    sheet.name,
    header,
    header.includes("Date") ? "Date" : "Text/number as appropriate",
    "Leave values blank when the official source does not state them; do not infer missing election values.",
    "See the relevant election or news source recorded in the row.",
  ])),
  ...Object.entries(sources).map(([name, url]) => [
    "Source register", name, "URL", "Tutor-provided source to be used by later extraction scripts.", url,
  ]),
];
const dictionaryLastRow = dictionaryRows.length + 1;
dictionary.getRange(`A1:E${dictionaryLastRow}`).values = [dataDictionaryHeaders, ...dictionaryRows];
dictionary.getRange("A1:E1").format = {
  fill: "#1F4E78",
  font: { color: "#FFFFFF", bold: true },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#17365D" },
};
dictionary.getRange("A1:E1").format.rowHeight = 32;
dictionary.getRange(`A1:E${dictionaryLastRow}`).format.wrapText = true;
dictionary.getRange("A:A").format.columnWidth = 27;
dictionary.getRange("B:B").format.columnWidth = 32;
dictionary.getRange("C:C").format.columnWidth = 20;
dictionary.getRange("D:D").format.columnWidth = 62;
dictionary.getRange("E:E").format.columnWidth = 44;
dictionary.getRange(`A2:E${dictionaryLastRow}`).format.autofitRows();
dictionary.getRange(`A1:E${dictionaryLastRow}`).format.borders = {
  bottom: { style: "thin", color: "#D9E2F3" },
};
dictionary.freezePanes.freezeRows(1);
dictionary.showGridLines = false;

await fs.mkdir(outputDirectory, { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputFile);
console.log(`Created ${outputFile}`);
