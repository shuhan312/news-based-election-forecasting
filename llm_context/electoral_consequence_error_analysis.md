# Expected electoral consequence - error analysis (Phase 6 Step 7)

Nine first-pass error lines across 9 of 67 articles; one was a
VALIDATOR-rule error rather than a model error. After the rule fix:
8 residual errors, all caught and quarantined.

## 1. Validator rule error: duplicate key too coarse (fixed, v1.1)

The v1.0 duplicate rule keyed on (actor, direction, mechanism) and
wrongly rejected rows that differ only by electoral signal - e.g.
one mechanism producing BOTH incumbent_vulnerability and
voter_switching_possibility, which are analytically distinct
signals the schema stores one-per-row. Rules v1.1 adds the signal
to the key; stored outputs were re-validated offline at zero API
cost, converting one record to valid. Pilots exist to catch
validator errors too - this is the first one in seven layers, and
the offline re-validation shows why validation and extraction are
kept as separate passes.

## 2. True duplicates - 5 records (E3)

Identical (actor, direction, mechanism, signal) tuples repeated,
usually a Labour-government or Conservative-government row restated
with slightly different reasoning. Correctly rejected: these WOULD
double-weight signals downstream. Full-scale prompt gains a
one-line reminder ("one row per actor-mechanism-signal; merge
restatements").

## 3. Residual non-verbatim quotes - 2 records (E1)

The familiar residual (~3%): lightly reconstructed quotes caught by
string-matching. Quarantined; no new mitigation.

## 4. Under-flagged low confidence - 1 record (E2)

A 0.45-confidence row without the flagged status; forced to review
by the rule, as designed.

## Observations worth recording

- Confidence mean 0.540 is the lowest of all seven layers, and 19
  records self-routed to review - the model treats this layer as
  the most interpretive, which is honest and matches its design
  position at the speculation end of the pipeline;
- zero E4 violations: the Reform addendum never carried content
  without evidence, and Con->Reform dominated the switching
  directions (4/7) as the historical record suggests it should;
- the no-prediction guarantee held everywhere: no winner talk, no
  vote-share estimates, in structured fields or free text;
- 79% directional agreement with the independently-extracted
  credit/blame layer, at the interpretive end of the established
  cross-layer band;
- 20 honest empty records passed as partial-with-note.
