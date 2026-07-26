# Issue / topic classification - error analysis (Phase 6 Step 3)

11 error lines across 10 of 67 articles; every one caught by the
validator and quarantined. No error reached usable data.

## 1. Under-flagged low confidence - 5 records (6 lines, S2)

The model reported honest confidences of 0.40-0.45 but left
review_status "unreviewed" instead of "flagged". The rule exists for
exactly this: the validator force-fails the record, so it lands in
the review pool regardless of the model's self-report. Fix for full
scale: none needed structurally; a one-line prompt reminder ("if ANY
confidence is below 0.5 you MUST set review_status to flagged") may
cut the rate.

## 2. Invented FIELDS (not categories) - 3 records (structural)

`secondary_issues_note`, `taxonomy_version_check`, and a misplaced
`ambiguity_notes` inside the issues object. additionalProperties:
false rejected all three - the schema's strictness is doing its job.
Notably the model never invented a taxonomy VALUE; the enum makes
that impossible. Fix: prompt reminder that ambiguity_notes is
top-level and no other fields exist.

## 3. Non-verbatim quote - 1 record (S1)

One evidence span paraphrased a sentence about a GP surgery. Caught
by string-matching, consistent with the ~5% residual rate observed
in Step 2.5. Quarantined for review; no prompt change beyond the
existing hardened rule.

## 4. Empty claiming "extracted" - 1 record (S5)

One no-issue article kept status "extracted" instead of "partial"
with a note. Caught; same prompt-compliance class as (1).

## Non-errors worth recording

- 22 legitimately empty classifications (letters, non-political
  editorials) passed correctly as partial-with-note - the
  never-force-a-code rule holds;
- zero S3 violations: primary/secondary separation and secondary
  uniqueness were respected in all 67 outputs;
- zero S4 violations among valid records: every asserted relevance
  carried evidence;
- the cross-layer disagreements with Step 2 (audit) are
  conservatism and adjacent-code ambiguity, not fabrication - no
  case was found where Step 3 asserted an issue the article does
  not discuss.
