# Credit / blame attribution - audit (Phase 6 Step 6)

Contract `credit-blame-v1.1-2026-07-27` (v1.0 first pass, v1.1
re-run - see below) | prompt v1.1 | rules
`credit-blame-rules-v1.0-2026-07-27` | model `claude-sonnet-5` |
batches `msgbatch_0145Nridq1kaYAhgcAaB76mr` (67 articles) +
`msgbatch_01UuHJvGvWBLF46ykqh2YQrB` (12 retries), ~$2.2 total. Raw
outputs with verbatim quotes: `credit_blame_outputs.json` (out of
Git under the copyright policy).

## Dataset (recorded)

The SAME 67-article stratified pilot sample as Steps 2-5 (method
versioned in `llm_context_pilot_sample_v1.csv`). Full corpus was
NOT run.

## Schema compliance (after the versioned fix)

| outcome | articles |
|---|---|
| fully valid (structure + C1-C6) | **64 (96%)** |
| validation errors (caught, quarantined) | 3 |
| unparseable | 0 |

First pass validated 55/67. The dominant failure (7 articles, 13
error lines) was a genuine vocabulary gap, the Step 6 analogue of
the Step 3 national-codes finding: national articles attribute blame
to INDIVIDUAL POLITICIANS (ministers, party leaders) who are not
local candidates, and v1.0's target enum had no such type. Fix,
with the usual discipline: schema v1.1 adds target_type
"politician" (v1.0 records stay valid under their own stamp), the
prompt explains candidate-vs-politician, and the 12 failed articles
were re-run under v1.1 - the new type was used 50 times in the
final outputs, confirming the gap was real. One truncation also
recovered at the raised 20k limit.

## Attribution completeness and distributions

348 attribution rows across valid records. Type: blame 184 / credit
74 / mixed 4 / unclear 2 - pre-election coverage skews to blame, as
expected. Targets: government 111, politician 50, party 40,
organisation 35, council 18, candidate 19, other. **Sources** (the
specification's who-assigns dimension): politician 105, journalist
93, organisation 35, resident 11, public_group 3 - and 181 rows
name the assigner. Implication direction: may_damage 135,
may_benefit 50, both 4, unclear 75 - with rule C4 guaranteeing
every directional claim carries its reading. 13 honest empty
records.

## Evidence and confidence

Every accepted row's quote string-matched the article. Confidence
mean 0.648, min 0.35; all low-confidence rows landed in
review-flagged records (11 flagged, C2). The three residual errors
are all C1 non-verbatim quotes (~4%, the familiar residual) -
quarantined in the review pool.

## Cross-layer validation (vs the stance layer)

For (article, target) pairs present in both layers, blame/credit
direction is consistent with the Step 4 stance reading in **94%
(95/101)** of cases - blamed targets carry negative or mixed
stance, credited targets positive or mixed. Two independently
prompted layers agreeing at 94% on directional judgements is the
strongest inter-layer quality evidence in the pilot so far.

## Manual review (representative subset)

Blame-shifting chains extract correctly: council leaders blaming
central government funding cuts appear as separate
government-target rows sourced to the named politician - the
who-caused-it-versus-who-says-so structure the research design
needs. Multi-party rows, Reform coverage and empty sets
spot-checked; no invented causal chains found in the reviewed
subset.

## Verdict

The attribution layer validates at pilot scale and is ready to
support electoral consequence extraction. Full-corpus run awaits
the budget conversation. No downstream prediction or embedding
stages were started.
