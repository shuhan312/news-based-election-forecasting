/**
 * Apply the documented E5 development draft to the review workbook.
 *
 * This script never changes the preserved human or v1 LLM source columns.
 * It writes only the reassessment/diagnostic fields and records explicit
 * AI-assistance in reviewer_id and the Instructions sheet. The output is
 * therefore suitable for prompt-development analysis, but it cannot be
 * represented as an independent human blind review or formal validation.
 *
 * Usage:
 *   node apply_e5_ai_assisted_draft.mjs /path/to/repository
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
const sourceDataPath = path.join(
  repositoryRoot,
  "news_collection/e5_hard_disagreement_review_data.json",
);
const draftPath = path.join(
  repositoryRoot,
  "news_collection/e5_ai_assisted_development_draft.tsv",
);

const REVIEWER =
  "AI-assisted development draft (researcher verification required)";
const REVIEW_DATE = "2026-07-24";

function parseTsv(text) {
  const lines = text.trimEnd().split(/\r?\n/);
  const headers = lines[0].split("\t");
  return lines.slice(1).map((line) => {
    const values = line.split("\t");
    // National rows do not use the five trailing geographic fields. Treat
    // omitted trailing TSV cells as empty values so the source file does not
    // need invisible trailing tab characters.
    return Object.fromEntries(
      headers.map((header, index) => [header, values[index] ?? ""]),
    );
  });
}

const sourceRows = JSON.parse(await fs.readFile(sourceDataPath, "utf8"));
const sourceById = new Map(
  sourceRows.map((row) => [row.article_id, row]),
);
const drafts = parseTsv(await fs.readFile(draftPath, "utf8"));

const allowed = {
  reassessment: new Set([
    "include",
    "exclude",
    "needs_second_review",
    "insufficient_evidence",
  ]),
  status: new Set(["complete", "needs_adjudication"]),
  humanLabelReview: new Set(["yes", "no"]),
  fewShot: new Set(["yes", "no"]),
  linkageDecision: new Set([
    "",
    "confirmed",
    "rejected_incidental",
    "unresolved_missing_context",
  ]),
};

if (drafts.length !== 48) {
  throw new Error(`Expected 48 draft rows, found ${drafts.length}.`);
}
if (new Set(drafts.map((row) => row.article_id)).size !== 48) {
  throw new Error("Draft article_id values must be unique.");
}
for (const row of drafts) {
  if (!sourceById.has(row.article_id)) {
    throw new Error(`Unknown draft article_id: ${row.article_id}`);
  }
  if (!allowed.reassessment.has(row.reassessment)) {
    throw new Error(`Invalid reassessment for ${row.article_id}`);
  }
  if (!allowed.status.has(row.review_status)) {
    throw new Error(`Invalid review_status for ${row.article_id}`);
  }
  if (!allowed.humanLabelReview.has(row.human_label_review)) {
    throw new Error(`Invalid human_label_review for ${row.article_id}`);
  }
  if (!allowed.fewShot.has(row.few_shot_candidate)) {
    throw new Error(`Invalid few_shot_candidate for ${row.article_id}`);
  }
  if (!allowed.linkageDecision.has(row.linkage_decision)) {
    throw new Error(`Invalid linkage_decision for ${row.article_id}`);
  }
}

const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(workbookPath),
);

/**
 * Write one or more named columns by matching article_id.
 *
 * Column blocks are written independently so formulas, source columns,
 * formatting and data validation elsewhere in the existing workbook remain
 * untouched.
 */
function writeColumnsByArticleId(sheetName, assignments) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange().values;
  const headerRowIndex = values.findIndex(
    (row) => row.includes("article_id"),
  );
  if (headerRowIndex < 0) {
    throw new Error(`${sheetName} has no article_id header.`);
  }

  const headers = values[headerRowIndex];
  const articleIdColumn = headers.indexOf("article_id");
  const rowByArticleId = new Map();
  for (let rowIndex = headerRowIndex + 1; rowIndex < values.length; rowIndex++) {
    const articleId = values[rowIndex][articleIdColumn];
    if (articleId) {
      rowByArticleId.set(articleId, rowIndex);
    }
  }

  for (const [field, valueForDraft] of Object.entries(assignments)) {
    const columnIndex = headers.indexOf(field);
    if (columnIndex < 0) {
      throw new Error(`${sheetName} has no ${field} column.`);
    }
    const columnValues = values
      .slice(headerRowIndex + 1)
      .map((row) => {
        const articleId = row[articleIdColumn];
        const draft = drafts.find(
          (candidate) => candidate.article_id === articleId,
        );
        return [draft ? valueForDraft(draft) : row[columnIndex]];
      });
    sheet
      .getRangeByIndexes(
        headerRowIndex + 1,
        columnIndex,
        columnValues.length,
        1,
      )
      .values = columnValues;
  }

  const missing = drafts
    .map((draft) => draft.article_id)
    .filter((articleId) => !rowByArticleId.has(articleId));
  if (missing.length) {
    throw new Error(
      `${sheetName} is missing ${missing.length} draft article(s).`,
    );
  }
}

const evidenceFor = (draft) =>
  sourceById.get(draft.article_id).human_supporting_text;

writeColumnsByArticleId("Independent Review", {
  review_status: (draft) => draft.review_status,
  independent_reassessment: (draft) => draft.reassessment,
  rule_applied: (draft) => draft.rule_applied,
  review_evidence: evidenceFor,
  independent_notes: (draft) => draft.review_notes,
  reviewer_id: () => REVIEWER,
  reviewed_at: () => REVIEW_DATE,
});

writeColumnsByArticleId("Review", {
  review_status: (draft) => draft.review_status,
  independent_reassessment: (draft) => draft.reassessment,
  rule_at_issue: (draft) => draft.rule_at_issue,
  input_issue: (draft) => draft.input_issue,
  error_mechanism: (draft) => draft.error_mechanism,
  human_label_review: (draft) => draft.human_label_review,
  recommended_action: (draft) => draft.recommended_action,
  few_shot_candidate: (draft) => draft.few_shot_candidate,
  review_evidence: evidenceFor,
  review_notes: (draft) => draft.review_notes,
  reviewer_id: () => REVIEWER,
  reviewed_at: () => REVIEW_DATE,
});

const localDrafts = drafts.filter(
  (draft) => sourceById.get(draft.article_id).arm === "local",
);
if (localDrafts.length !== 28) {
  throw new Error(`Expected 28 local drafts, found ${localDrafts.length}.`);
}

const allDrafts = [...drafts];
// Geographic Linkage contains only local articles, so temporarily narrow the
// shared draft list used by writeColumnsByArticleId.
drafts.splice(0, drafts.length, ...localDrafts);
writeColumnsByArticleId("Geographic Linkage", {
  linkage_review_status: (draft) => draft.review_status,
  confirmed_link_type: (draft) => draft.geo_link_type,
  confirmed_linked_place: (draft) => draft.geo_place,
  confirmed_sampled_division: (draft) => draft.geo_division,
  confirmed_geographic_evidence: (draft) => {
    const source = sourceById.get(draft.article_id);
    return (
      source.automated_geographic_evidence[0] ||
      source.human_supporting_text
    );
  },
  linkage_decision: (draft) => draft.linkage_decision,
  reviewer_notes: (draft) => draft.geo_notes,
  reviewer_id: () => REVIEWER,
  reviewed_at: () => REVIEW_DATE,
});
drafts.splice(0, drafts.length, ...allDrafts);

const instructions = workbook.worksheets.getItem("Instructions");
instructions.getRange("A13:B13").values = [[
  "Draft provenance",
  "Rows populated on 2026-07-24 are AI-assisted development judgements " +
    "prepared from the stored full text and codebook. They support prompt " +
    "diagnosis only and must not be described as independent human blind " +
    "coding or formal validation.",
]];
instructions.getRange("A13:B13").format = {
  fill: "#FCE4D6",
  font: { color: "#9C0006", bold: true },
  wrapText: true,
  verticalAlignment: "top",
};

// Add compact, formula-driven diagnostics so the interpretation remains
// traceable to the editable Review sheet rather than to hard-coded totals.
const summary = workbook.worksheets.getItem("Summary");
summary.getRange("A15:H30").clear({ applyTo: "all" });
summary.getRange("A15:B15").values = [["Draft reassessment", "Count"]];
summary.getRange("A16:A18").values = [
  ["include"],
  ["exclude"],
  ["needs_second_review"],
];
summary.getRange("B16").formulas = [[
  '=COUNTIF(\'Review\'!$W$6:$W$53,A16)',
]];
summary.getRange("B16:B18").fillDown();

const mechanisms = [
  "missed_qualifying_evidence",
  "wrong_arm_rule",
  "local_effect_not_established",
  "incidental_place_overread",
  "codebook_boundary_unclear",
  "national_policy_scope_too_broad",
  "surrey_wide_rule_misapplied",
  "entity_or_namesake_confusion",
];
summary.getRange("D15:E15").values = [["Primary mechanism", "Count"]];
summary.getRange("D16:D23").values = mechanisms.map((value) => [value]);
summary.getRange("E16").formulas = [[
  '=COUNTIF(\'Review\'!$Z$6:$Z$53,D16)',
]];
summary.getRange("E16:E23").fillDown();

const actions = [
  "prompt_clarification",
  "decision_tree_change",
  "few_shot_example",
  "human_label_adjudication",
  "input_fix",
  "codebook_review",
  "multiple",
];
summary.getRange("G15:H15").values = [["Recommended action", "Count"]];
summary.getRange("G16:G22").values = actions.map((value) => [value]);
summary.getRange("H16").formulas = [[
  '=COUNTIF(\'Review\'!$AB$6:$AB$53,G16)',
]];
summary.getRange("H16:H22").fillDown();

for (const range of ["A15:B15", "D15:E15", "G15:H15"]) {
  summary.getRange(range).format = {
    fill: "#1F4E78",
    font: { color: "#FFFFFF", bold: true },
  };
}
for (const range of ["A16:B18", "D16:E23", "G16:H22"]) {
  summary.getRange(range).format.borders = {
    preset: "all",
    style: "thin",
    color: "#D9E1F2",
  };
}
summary.getRange("B16:B18").format.fill = "#E2F0D9";
summary.getRange("E16:E23").format.fill = "#E2F0D9";
summary.getRange("H16:H22").format.fill = "#E2F0D9";
summary.getRange("A:A").format.columnWidth = 28;
summary.getRange("D:D").format.columnWidth = 30;
summary.getRange("G:G").format.columnWidth = 28;

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(workbookPath);
console.log(`Applied ${drafts.length} E5 development drafts -> ${workbookPath}`);
