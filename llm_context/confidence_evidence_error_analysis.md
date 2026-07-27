# Confidence + evidence layer - error analysis (Phase 6 Step 10)

This layer creates no new extractions, so its "errors" are audit
findings about the stored layers.

## 1. Unsupported claims - 41 (0.8% of 5,335)

31 are the issue layer's political-relevance booleans, whose source
schema carries one evidence span per record rather than per
boolean - a schema-granularity artefact, not hallucination (the
record-level span exists and was verified). 10 are pilot-layer
judgement fields on rows whose spans failed re-verification.
Handling: all 41 are review_required; the full-scale issue prompt
can attach the relevance span explicitly if per-boolean granularity
is wanted.

## 2. weak_evidence_high_confidence - 108 (2%)

Dominated by honest-absence values (not_addressed 45, none 29,
not_indicated 20) inheriting their row's high confidence. The audit
flags the combination on purpose: absence fields should not ride a
confident row into downstream aggregation unexamined. Downstream
guidance: treat absence values as absence regardless of row
confidence.

## 3. Low-confidence and review pool - 1,414 claims across the
## corpus

The consolidated review pool now has a single uniform surface (one
row per claim with field, value, quote and reason) - this is the
worksheet source for the planned trial review (D4) and the
full-scale adjudication pass.

## 4. Ambiguous articles

48 of 67 articles carry at least one canonical article-level
uncertainty reason, overwhelmingly the national-without-local-
linkage case - consistent with the sample's national-arm majority
and the Step 8 finding that the local-national connector subset is
small.

## Non-errors worth recording

- Evidence coverage 98.1% at claim level across seven layers built
  in eight days of pilots - the Step 1 evidence-or-nothing design
  carried through the whole pipeline;
- zero hallucinated spans SURVIVED to this layer that had not
  already been quarantined by the per-layer validators - the final
  re-verification found no new fabrications in valid records;
- the build is deterministic (verified byte-identical re-run) and
  free, so it can be re-run after every future layer or full-scale
  batch as a standing audit gate.
