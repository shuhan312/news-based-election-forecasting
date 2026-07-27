# Confidence + evidence audit layer (Phase 6 Step 10)

Version `confidence-evidence-v1.0-2026-07-27`. Built OFFLINE from
the seven stored extraction layers - no LLM call, zero API cost,
byte-identical on re-execution (verified). Raw table with quotes:
`confidence_evidence_outputs.json` (out of Git); this audit carries
methodology and numbers.

## Methodology

Evidence and confidence were mandatory per claim from Step 1
onward, so this layer CONSOLIDATES rather than creates: every claim
from every valid record across the eight extraction outputs (pilot
full schema, issues, stance, framing, credit/blame, consequence,
relevance, temporal) is flattened into one uniform row -
article_id, extraction_field, extracted_value, evidence_span,
confidence_score, uncertainty_flag, uncertainty_reason,
human_review_required - then every span is re-verified against the
article text one final time, and per-article plus corpus summaries
are computed. Quarantined records stay quarantined (excluded here);
provenance (file, prompt and schema versions per layer) is embedded
in the outputs. Row-level evidence is shared by the row's judgement
fields: the span supports the row, each judgement stays
individually auditable. Per decision D1, the pilot record's issues
section is excluded (the focused issue layer is the authority).

## Confidence definitions (evidence quality, never outcome
## probability)

high 0.80-1.00 = clear explicit evidence; medium 0.50-0.79 =
reasonable interpretation, incomplete evidence; low 0.00-0.49 =
requires inference / weak evidence. These bands describe how well
the text supports the judgement - they are NOT probabilities of any
election outcome, party victory or effect size.

## Validation results (corpus)

- 67 articles, **5,335 claims** flattened;
- **evidence coverage 98.1%** (5,233 supported claims);
- confidence distribution: high 828, medium 3,938, low 396,
  missing 173 (missing = judgement fields inheriting no row
  confidence, e.g. relevance booleans - recorded, not hidden);
- consistency flags: unsupported 41, weak_evidence_high_confidence
  108, missing_evidence_recorded 63 (uncertain values legitimately
  without spans - explicit, never dropped);
- **review_required 1,414 claims (27%)** - the union of low
  confidence, flagged records, unsupported evidence and
  weak-high combinations; concentrated in the flagged records the
  layer validators already routed;
- article-level canonical uncertainty reasons attach to 48
  articles ("National issue without explicit local electoral
  linkage" and/or "Coverage indicates national momentum but local
  conversion uncertain").

## Reading the flags honestly

The 108 weak_evidence_high_confidence flags are dominated by
not_addressed / none / not_indicated values inheriting their ROW's
high confidence (45+29+20 of 108): a row judged confidently can
still contain honest absence fields, and the audit deliberately
flags the combination rather than letting uncertainty ride on a
confident row. The 41 unsupported claims sit mostly in the issue
layer's relevance booleans (31), where the source schema attaches
one span per record rather than per boolean. Both are audit-layer
strictness findings, not extraction errors - documented so
downstream users weight these fields accordingly.

## Verdict

Every important LLM judgement is now traceable to a verbatim quote
or explicitly recorded as unsupported/uncertain; confidence is
separated from prediction probability by definition and by
documentation; uncertainty is visible at claim and article level.
The audit layer passes validation. No embedding or prediction stage
was started.
