/**
 * Add a reproducible geographic-linkage review sheet to the E5 workbook.
 *
 * The JSON builder performs only deterministic candidate extraction. This
 * exporter keeps those search aids visually separate from the yellow human
 * review fields, because an exact place-name match is not itself proof that
 * L1-L4 is satisfied. The existing Review and Independent Review sheets are
 * preserved, including any development notes already entered there.
 *
 * Usage:
 *   node update_e5_geographic_review_workbook.mjs /path/to/repository
 */

import fs from "node:fs/promises";
import path from "node:path";
import {
  FileBlob,
  SpreadsheetFile,
} from "@oai/artifact-tool";

const repositoryRoot = process.argv[2];
if (!repositoryRoot) {
  throw new Error("Pass the repository root as the first argument.");
}

const workbookPath = path.join(
  repositoryRoot,
  "outputs/e5_disagreement_review_2026-07-24/" +
    "E5_Hard_Disagreement_Review.xlsx",
);
const reviewDataPath = path.join(
  repositoryRoot,
  "news_collection/e5_hard_disagreement_review_data.json",
);

const reviewRows = JSON.parse(await fs.readFile(reviewDataPath, "utf8"));
const localRows = reviewRows.filter((row) => row.arm === "local");
if (localRows.length !== 28) {
  throw new Error(
    `Expected 28 local hard disagreements, found ${localRows.length}.`,
  );
}

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getOrAdd("Geographic Linkage");

const manualFields = [
  "linkage_review_status",
  "confirmed_link_type",
  "confirmed_linked_place",
  "confirmed_sampled_division",
  "confirmed_geographic_evidence",
  "linkage_decision",
  "reviewer_notes",
  "reviewer_id",
  "reviewed_at",
];

/**
 * Preserve previously entered review cells before rebuilding automated data.
 *
 * The JSON can be regenerated when matching logic changes, but completed
 * human judgements are primary research records. Keying them by article_id
 * means rerunning this exporter refreshes only the deterministic candidates
 * and never silently erases review work.
 */
function readExistingManualValues(usedRange) {
  const preserved = new Map();
  if (!usedRange) {
    return preserved;
  }

  const rows = usedRange.values;
  const headerIndex = rows.findIndex(
    (row) =>
      row.includes("article_id") &&
      row.includes("linkage_review_status"),
  );
  if (headerIndex < 0) {
    return preserved;
  }

  const header = rows[headerIndex];
  const articleIdIndex = header.indexOf("article_id");
  const fieldIndexes = Object.fromEntries(
    manualFields.map((field) => [field, header.indexOf(field)]),
  );
  for (const row of rows.slice(headerIndex + 1)) {
    const articleId = row[articleIdIndex];
    if (!articleId) {
      continue;
    }
    preserved.set(
      articleId,
      Object.fromEntries(
        manualFields.map((field) => [
          field,
          fieldIndexes[field] >= 0 ? row[fieldIndexes[field]] : null,
        ]),
      ),
    );
  }
  return preserved;
}

// Rebuild only after the manual cells have been captured. Other worksheets
// are never cleared or rewritten by this script.
const oldUsedRange = sheet.getUsedRange();
const existingManualByArticleId =
  readExistingManualValues(oldUsedRange);
if (oldUsedRange) {
  oldUsedRange.clear({ applyTo: "all" });
}

sheet.showGridLines = false;
sheet.getRange("A1:T1").merge();
sheet.getRange("A1").values = [[
  "E5 local-arm geographic linkage review (28 hard disagreements)",
]];
sheet.getRange("A2:T2").merge();
sheet.getRange("A2").values = [[
  "Blue cells are deterministic search aids, not E5 decisions. " +
    "Complete the yellow cells from the full article and record an exact " +
    "supporting sentence before confirming L1-L4.",
]];
sheet.getRange("A3:T3").merge();
sheet.getRange("A3").values = [[
  "If the article names a place but the sampled division cannot be verified, " +
    "choose unresolved_missing_context rather than inferring a ward.",
]];

const headers = [
  "review_index",
  "article_id",
  "headline",
  "human_decision",
  "llm_decision",
  "ward_context_missing",
  "exact_sample_division_candidates",
  "sample_place_candidates",
  "surrey_authority_signals",
  "automated_evidence_sentences",
  "linkage_review_status",
  "confirmed_link_type",
  "confirmed_linked_place",
  "confirmed_sampled_division",
  "confirmed_geographic_evidence",
  "linkage_decision",
  "reviewer_notes",
  "reviewer_id",
  "reviewed_at",
  "qc_flag",
];
sheet.getRange("A5:T5").values = [headers];

const values = localRows.map((row) => {
  const previous = existingManualByArticleId.get(row.article_id) ?? {};
  return [
    row.review_index,
    row.article_id,
    row.headline,
    row.human_decision,
    row.llm_decision,
    row.ward_context_missing,
    row.automated_exact_sample_division_candidates.join("; "),
    row.automated_sample_place_candidates.join("; "),
    row.automated_authority_signals.join("; "),
    row.automated_geographic_evidence.join("\n"),
    previous.linkage_review_status || "not_started",
    previous.confirmed_link_type || "",
    previous.confirmed_linked_place || "",
    previous.confirmed_sampled_division || "",
    previous.confirmed_geographic_evidence || "",
    previous.linkage_decision || "",
    previous.reviewer_notes || "",
    previous.reviewer_id || "",
    previous.reviewed_at || "",
    null,
  ];
});
sheet.getRange(`A6:T${5 + values.length}`).values = values;

// A completed row is mechanically flagged if the minimum audit fields are
// missing. The formula does not assess whether the research judgement is
// substantively correct.
const lastRow = 5 + values.length;
sheet.getRange("T6").formulas = [[
  '=IF(K6<>"complete","",IF(OR(L6="",P6="",O6="",R6="",S6=""),' +
    '"CHECK","OK"))',
]];
sheet.getRange(`T6:T${lastRow}`).fillDown();

sheet.getRange(`K6:K${lastRow}`).dataValidation = {
  rule: {
    type: "list",
    values: ["not_started", "in_progress", "complete", "needs_adjudication"],
  },
};
sheet.getRange(`L6:L${lastRow}`).dataValidation = {
  rule: {
    type: "list",
    values: ["L1_place", "L2_candidate", "L3_council_issue", "L4_county_wide", "no_link"],
  },
};
sheet.getRange(`P6:P${lastRow}`).dataValidation = {
  rule: {
    type: "list",
    values: [
      "confirmed",
      "rejected_incidental",
      "unresolved_missing_context",
      "not_applicable",
    ],
  },
};

// Match the existing workbook's restrained research-audit palette: dark blue
// headers, light blue automated aids, and pale yellow fields requiring human
// judgement.
sheet.getRange("A1:T1").format = {
  fill: "#17365D",
  font: { color: "#FFFFFF", bold: true, size: 14 },
  verticalAlignment: "center",
};
sheet.getRange("A2:T3").format = {
  fill: "#DCE6F1",
  font: { color: "#1F1F1F", italic: true },
  wrapText: true,
};
sheet.getRange("A5:T5").format = {
  fill: "#1F4E78",
  font: { color: "#FFFFFF", bold: true },
  wrapText: true,
  verticalAlignment: "center",
};
sheet.getRange(`A6:F${lastRow}`).format.fill = "#F2F2F2";
sheet.getRange(`G6:J${lastRow}`).format.fill = "#DDEBF7";
sheet.getRange(`K6:S${lastRow}`).format.fill = "#FFF2CC";
sheet.getRange(`T6:T${lastRow}`).format.fill = "#E2F0D9";
sheet.getRange(`A5:T${lastRow}`).format.borders = {
  preset: "all",
  style: "thin",
  color: "#D9E1F2",
};
sheet.getRange(`A5:T${lastRow}`).format.verticalAlignment = "top";
sheet.getRange(`A5:T${lastRow}`).format.wrapText = true;

const widths = {
  A: 10, B: 30, C: 38, D: 12, E: 12, F: 16, G: 24, H: 22, I: 20, J: 55,
  K: 18, L: 20, M: 22, N: 24, O: 55, P: 25, Q: 42, R: 22, S: 14, T: 10,
};
for (const [column, width] of Object.entries(widths)) {
  sheet.getRange(`${column}:${column}`).format.columnWidth = width;
}
sheet.getRange("1:1").format.rowHeight = 24;
sheet.getRange("2:3").format.rowHeight = 32;
sheet.getRange("5:5").format.rowHeight = 42;
sheet.freezePanes.freezeRows(5);
sheet.freezePanes.freezeColumns(2);

const instructions = workbook.worksheets.getItem("Instructions");
instructions.getRange("A12:B12").values = [[
  "Geographic linkage",
  "For the 28 local hard disagreements, use Geographic Linkage before final " +
    "diagnosis. Automated candidates only locate possible evidence; confirm " +
    "the sampled division/place and quote an exact sentence, or record why " +
    "the linkage remains unresolved.",
]];
instructions.getRange("A12:B12").format = {
  fill: "#DCE6F1",
  wrapText: true,
  verticalAlignment: "top",
};

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(workbookPath);
console.log(`Updated ${workbookPath}`);
