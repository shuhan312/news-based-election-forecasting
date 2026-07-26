# LLM context extraction pilot - error analysis (Phase 6 Step 2)

Every error below was CAUGHT by the validation layers - none reached
usable data. Counts are over the final merged results (67 articles).

## 1. Output truncation - 14 articles (fixed in-pilot)

`stop_reason: max_tokens` at the initial 16k limit: adaptive
thinking and the JSON draw on one output budget, and long articles
with many party rows ran out mid-string ("Unterminated string" at
~9-15k characters). **Pipeline fault, not model fault.** Fix applied:
`MAX_TOKENS = 40000`; all 14 retried articles parsed. Lesson for
full scale: budget ~11k output tokens per article.

## 2. R1 - non-verbatim evidence spans - 8 claims in 5 records

The dominant model error. Pattern: the model abbreviates a long
quote with an ellipsis ("London Councils ... says the formula...")
or lightly paraphrases while presenting it as a quote. R1's
string-match rejected every instance - this is the anti-hallucination
gate doing its job on real data. Fix: an explicit prompt rule
("copy spans character-for-character; never shorten with ...;
prefer a shorter contiguous span") - see revision notes. The
affected records remain quarantined in the review pool.

## 3. Taxonomy gap: `election_administration` - 2 records

The model twice wanted an issue code for polling-day administration
stories and reached for `election_administration`, which exists in
the EVENT taxonomy but not the ISSUE taxonomy - a genuine schema
gap surfaced by the pilot (exactly what pilots are for). Proposed
fix: add the code in issues taxonomy v1.2 (revision notes).

## 4. Singletons

- **R2 (1 claim)**: character offsets that do not slice to the span
  text. Offsets are optional and add no analytical value at this
  stage - the revision notes recommend instructing the model to omit
  them (verbatim text is the ground truth; offsets can be recomputed
  deterministically).
- **R7 (1 record)**: `contains_poll: true` without an evidence
  span. The rule held; prompt clarification added to revision notes.

## Non-errors worth recording

- 22 records were force-routed to review by R3 (low-confidence
  claims present) - working as designed, not a defect.
- Empty extractions (procedural notices, non-political editorials)
  used null primary issues and honest empty arrays instead of
  invented content - no R4 violations in the final set.
- Zero Reform UK consistency violations (R6) and zero duplicate
  party rows (R8) across all 67 outputs.
