# LLM context extraction pilot - audit (Phase 6 Step 2)

Pilot `pilot-v1.0-2026-07-26` | schema `llm-context-v1.1-2026-07-26`
| model `claude-sonnet-5` (the project's standing frozen model, same
as the approved eligibility classification pipeline) | Message
Batches API (50% pricing) with a cached shared system prompt.
Batches: `msgbatch_0115hJ1Q2Wubc1ipERTve7t5` (67 requests) +
`msgbatch_01JCBpiQvXNuKndh2foV5y2U` (14 truncation retries at a
raised token limit). Full outputs (with verbatim quotes) live in
`llm_context_pilot_outputs.json` - kept OUT of Git under the
copyright three-tier policy; this audit carries numbers only.

## Sample (recorded method, no manual selection)

Frame: 1,535 canonical full-text articles (use_as_canonical_input).
Strata: election x arm; quotas 6 local + 10 national per election
(all eight strata filled); within-stratum order sha256(article_id) -
fixed and reproducible; Reform UK top-up to 10 mentioning articles
(7 landed in the base sample, 3 topped up). Total **67 articles**.
The sample list is versioned in `llm_context_pilot_sample_v1.csv`.

## Schema compliance

| outcome | articles |
|---|---|
| fully valid (structure + rules R1-R8) | **58 (87%)** |
| validation errors (all caught and quarantined) | 9 |
| unparseable after retry | 0 |

First pass at a 16k output-token limit truncated 14 outputs
mid-JSON (`stop_reason: max_tokens` - adaptive thinking and the JSON
share one budget). This was a pipeline parameter fault, not model
quality; the limit is now 40k and all retried articles parsed.

## Evidence completeness and confidence

- 790 evidence-bearing claims across the 58 valid records
  (413 entities, 117 party rows, 22 candidate rows, 36 council
  accountability rows, 66 electoral-consequence signals, 136 frames);
  every one carries a verbatim quote that string-matched the article.
- 8 records activated the Reform UK layer, all with grounded quotes.
- Confidence: mean 0.713 over 790 claims, min 0.30; 30 claims below
  0.5 - and rule R3 correctly forced **22 records** into
  `review_status: flagged`, so no low-confidence claim can be
  consumed silently.

## Manual review (close reading)

Three strata-diverse valid records were read against their articles
by the pipeline operator, plus all nine error records:

1. *"Vote Lib Dem or regret it..."* (ESWS-2026, local arm, Reform
   present): five party rows with correct context/trajectory
   readings, Davey candidate row, Reform layer flags all supported
   by quotes - high quality.
2. Guardian food-bank editorial (SCC-2021, national): correctly
   yields empty political sections rather than forced content -
   the honest-emptiness design works.
3. A 2017 local report: entities/issues/geography consistent with
   the text.

Independent review of a larger subset by the researcher/supervisor is
recommended before full-scale extraction.

## Cost (actuals)

Sonnet batches: ~288k input + 31k cached + 711k output tokens ≈
**$4.8 total** (both batches, intro batch pricing). A discarded
first attempt on claude-opus-4-8 cost $2.89 before the account
balance ran out; those outputs were deleted and play no part in the
pilot (single-model discipline).

**Full-corpus projection** (1,535 articles at the observed ~$0.06
per article): **≈ $85-95** at current intro batch pricing. The
driver is output length (~10.6k tokens/article across thinking +
the 11-layer record); see the revision notes for cost levers
(effort parameter, span length caps).

## Verdict

The schema is suitable for full-scale extraction after the small
revisions listed in `llm_context_schema_revision_notes_v1.md`: 87%
of articles validate end-to-end on the first real run, every failure
mode was caught by the validator rather than leaking through, empty
and ambiguous cases are represented honestly, and the specialised
Reform UK layer activates only with grounded evidence. Full corpus
extraction was NOT started.
