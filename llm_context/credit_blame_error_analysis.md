# Credit / blame attribution - error analysis (Phase 6 Step 6)

First pass: 20 error lines across 12 of 67 articles. After the
versioned fix and targeted re-run: 3 residual errors. Every error
was caught by the validator; nothing reached usable data unchecked.

## 1. Vocabulary gap: target_type "politician" - 7 articles (fixed)

The dominant first-pass failure and a genuine schema finding: the
model repeatedly (13 rows) wanted to attribute blame to named
individual politicians - Sunak, ministers, party leaders - and
v1.0's enum offered only "candidate" (which connotes the studied
Surrey elections) or "other". Structural validation rejected every
attempt, exactly as designed; the fix followed the Step 3
national-codes pattern: schema v1.1 adds "politician" with a
candidate-vs-politician instruction in prompt v1.1, old records
stay valid under their stamp, and the re-run used the new type 50
times. Lesson: national-arm content keeps stretching locally-scoped
vocabularies - each layer's pilot catches its own instance of this.

## 2. Duplicate attribution rows - 2 articles (fixed on re-run)

Same target credited/blamed twice for near-identical outcomes (C3).
Both articles passed on re-run under the sharpened prompt.

## 3. Truncation - 1 article (fixed)

One attribution-dense article hit the 14k output limit; recovered
at 20k. The limit stays at 20k for this layer.

## 4. Residual non-verbatim quotes - 3 articles (quarantined)

The familiar ~4% residual: lightly reconstructed quotes caught by
C1 string-matching (a Liam Fox Brussels line, a Badenoch support
line, a BBC defence line). They sit in the review pool; no further
mitigation beyond the existing hardened rule - this rate is the
documented cost of the strict gate and the review pool is its
designed destination.

## 5. Under-flagged low confidence - 1 article (fixed on re-run)

One 0.45-confidence row without the flagged status; C2 caught it,
and the re-run record self-flagged correctly.

## Non-errors worth recording

- Zero invented causal chains found in manual review - the
  no-invented-responsibility rule held;
- blame-shifting chains (council blames central government) extract
  as properly separated rows with named sources;
- 94% directional consistency with the independently-extracted
  stance layer;
- all 50 uses of the new politician type appeared only under the
  v1.1 stamp;
- 13 honest empty records passed as partial-with-note.
