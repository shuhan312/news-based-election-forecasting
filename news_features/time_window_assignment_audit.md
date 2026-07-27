# Election Time Window Assignment Audit

Phase 7, Step 2. Assignment version:
`article-time-window-v1.0-2026-07-27`
Inputs (read-only): Step 1 alignment layer
(`article-entity-alignment-v1.0`), frozen deterministic temporal
layer (sha256-verified against the Phase 6 freeze manifest before
building; byte-untouched).

## Method

No second window calculator was written. Every assignment is
re-derived by calling the SAME frozen `assign_windows()` function
from Phase 6 Step 9 and asserted field-for-field against the stored
deterministic layer (drift check W2, executed for all 67 articles
at build time; any mismatch aborts the build). This step's
contribution is the join to the Step 1 election links, the
exclusion handling, the validation rules W1-W5, and the record
format the feature stage will consume. Publication dates are the
validated effective dates from the Phase 4 date-resolution layer;
the LLM never saw them.

## Headline numbers

Total articles processed: 67 (exactly the set carrying Step 1
election links). Assigned: 67. Excluded: 0. Missing dates: 0.
Invalid dates: 0. Post-election articles: 0 (upstream corpus
eligibility already removes post-polling publication; the exclusion
path exists and is tested on synthetic cases).

Articles per election: SCC-2013-05: 16, SCC-2017-05: 16,
SCC-2021-05: 16, ESWS-2026-05: 19.

Articles per individual window (each article in exactly one):

| window | articles |
|---|---|
| 180_to_91_days | 47 |
| 90_to_31_days | 11 |
| 30_to_15_days | 2 |
| 14_to_8_days | 2 |
| 7_to_4_days | 3 |
| final_72_hours | 2 |

Cumulative membership (nested by construction, verified W4):
previous_72_hours 2 ⊂ previous_7_days 5 ⊂ previous_14_days 7 ⊂
previous_30_days 9 ⊂ previous_90_days 20 ⊂ previous_180_days 67.

## Observations for the research design

* The pilot sample is heavily weighted to the 91-180 day window
  (47/67, 70%) - a property of the stratified pilot draw over the
  collection corpus, not of Surrey election news as such. The
  near-election windows carry 2-3 articles each at pilot scale, so
  any pilot-level "does timing matter" reading would be
  underpowered; the window design proves itself here and gets its
  statistical use at full-corpus scale.
* The 6 result-flagged articles (decision D3: retained + flagged,
  main-analysis exclusion happens at the modelling stage as
  configuration, with a with/without sensitivity pair) sit in
  180_to_91_days (5) and 90_to_31_days (1). Their flag rides on
  every assignment record; this layer takes no side.

## Integrity

Rebuild is byte-identical (tested). The deterministic layer's
sha256 matches the freeze manifest before and after (tested). Every
record passes W1 (valid ISO dates), W2 (days arithmetic re-checked),
W3 (exactly one individual window), W4 (cumulative consistency and
nesting), W5 (no post-polling assignment). 12 new tests; full suite
521 passed.
