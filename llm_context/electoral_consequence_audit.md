# Expected electoral consequence - audit (Phase 6 Step 7)

Contract `elect-consq-v1.0-2026-07-27` | prompt v1.0 | rules
`elect-consq-rules-v1.1-2026-07-27` (v1.0 first pass; one rule
refined post-hoc, see below) | model `claude-sonnet-5` | batch
`msgbatch_0193fogkkUPSHF95D9JA2QmM`, 67 articles, ~$1.2. Raw
outputs with verbatim quotes: `electoral_consequence_outputs.json`
(out of Git under the copyright policy).

## Dataset (recorded)

The SAME 67-article stratified pilot sample as Steps 2-6 (method
versioned in `llm_context_pilot_sample_v1.csv`). Full corpus was
NOT run.

## The no-prediction guarantee

The specification's central constraint is enforced three ways and
tested: the schema has NO winner/vote-share/outcome field (adding
one fails structural validation - tested), every direction and
signal value is phrased as potential/suggested, and the prompt's
first rule forbids crossing the line. Manual review found no
prediction smuggled into free text.

## Schema compliance

| outcome | articles |
|---|---|
| fully valid (structure + E1-E6) | **59 (88%)** |
| validation errors (caught, quarantined) | 8 |
| unparseable | 0 |

One validator rule was refined during the audit: v1.0's duplicate
key (actor, direction, mechanism) wrongly rejected rows that differ
only by electoral signal - analytically distinct rows (incumbent
vulnerability AND switching possibility from one mechanism). Rules
v1.1 adds the signal to the key; stored outputs were re-validated
OFFLINE (no API respend), converting one record to valid. The five
remaining E3 errors are true duplicates. A validator-rule error
caught by the pilot is exactly what pilots are for - recorded here
for transparency.

## Consequence distributions

141 consequence rows across valid records. Direction: potential
damage 81 / benefit 43 / mixed 14 / unclear 3. Mechanisms used
across the full vocabulary: perceived_competence 31,
anti_incumbent_sentiment 21, service_dissatisfaction 19,
voter_switching_signal 17, issue_ownership 16,
challenger_credibility 14, party_momentum 12, increased_trust 5,
other 6. Signals: incumbent_vulnerability 49 dominates - the
pre-election corpus reads as an incumbency-risk record, consistent
with the blame skew in Step 6. Voter groups named only with basis
(specific_issue_voters 59, undecided 46...); 20 honest empty
records.

## Reform UK addendum

7 articles applicable; switching directions: Con->Reform 4,
Lab->Reform 2, LD->Reform 1 - the Conservative-to-Reform channel
dominating matches the historical record the study wants to test.
Signal nature: national_momentum 5, local_campaign_strength 3,
protest/anti-incumbent 3. Zero E4 violations - the addendum only
ever carried content with evidence, and non-Reform articles stayed
clean.

## Evidence and confidence

Every accepted row's quote string-matched the article. Confidence
mean 0.540 - the LOWEST of all layers, appropriately: consequence
judgements are the most interpretive, and the honesty shows up as
19 review-flagged records (the most of any layer), all correctly
routed by E2. Residual errors: 2 non-verbatim quotes (E1), 1
under-flagged low confidence (E2), 5 true duplicates (E3) - all
quarantined.

## Cross-layer validation (vs credit/blame implication directions)

For (article, actor) pairs carrying directional readings in both
layers, agreement is **79% (34/43)** - within the established
0.6-0.8 machine self-agreement band, at the interpretive end where
this most speculative layer should sit.

## Manual review (representative subset)

Multi-party consequence sets keep per-actor directions coherent
(the tax-row articles damage incumbents while benefiting
challengers, each with its own mechanism); Reform emergence
articles produce grounded addendum content; empty sets are honest.
No unsupported causal chain found in the reviewed subset.

## Verdict

The consequence layer validates at pilot scale. With this, ALL
SEVEN extraction layers of Phase 6 are pilot-validated, and the
layer is ready to support downstream consequence-aware
representation learning. Full-corpus runs await the budget
conversation. No prediction or embedding stages were started.
