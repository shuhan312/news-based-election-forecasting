# Local / national relevance - audit (Phase 6 Step 8)

Contract `loc-nat-v1.0-2026-07-27` | prompt v1.0 | rules v1.0 |
model `claude-sonnet-5` | batch `msgbatch_01CK9AhGzcXtvCZJwR7evPtB`,
67 articles, ~$0.6 (the smallest and cheapest layer). Raw outputs:
`local_national_relevance_outputs.json` (out of Git).

## Dataset (recorded)

The SAME 67-article stratified pilot sample as Steps 2-7 (method in
`llm_context_pilot_sample_v1.csv`). Full corpus was NOT run.

## Schema compliance

| outcome | articles |
|---|---|
| fully valid (structure + G1-G6) | **65 (97%)** |
| validation errors (caught) | 1 (under-flagged low confidence) |
| unparseable | 1 (a stray trailing comma) |

Zero G3 flag/entity incoherences and zero G4 scope/score
contradictions in the entire sample - the label-and-sliders
consistency rules were never needed, which suggests the model
internalises the coherence requirement well.

## Distributions

Scope: national 48, ward_specific_local 7, mixed 6, surrey_wide 3,
regional 1 - matching the sample's design skew (40 national-arm
quota plus Reform top-ups). Relevance scores: local mean 0.20,
national mean 0.79, with dual high scores only in genuinely mixed
articles. Electoral interpretation: national_political_trend 26,
local_campaign_signal 4, national_local_interaction 2, none 33 -
interaction claimed only where the article makes the connection.

## Finding 1 - the arm label is a channel, the scope is the content

Cross-checking extracted scope against the COLLECTION arm (which
search channel found the article): the national arm agrees 41/41
(100%); the local arm agrees 16/24, with **8 local-arm articles
extracted as nationally-scoped** - national newspaper stories that
local search queries legitimately matched (e.g. a national campaign
piece naming Surrey councils). Reading: the arm records how we FOUND
an article; this layer records what the article IS. For the
local-vs-national predictive comparison, the extracted scope (or
the dual scores) should define the analysis arms, with the
collection arm retained as provenance. Flagged for the modelling
design.

## Finding 2 - the national-to-local Reform linkage is rare

11 articles activated the Reform addendum, but only ONE connects
national momentum to local electoral competition and NONE carries a
ward-level conversion signal. The study's key question - does
national Reform momentum convert locally - concerns a linkage that
coverage itself rarely makes explicit. Implication: at full scale
these connector articles will be a small, precious subset; the G5
two-precondition rule (a connection requires both national momentum
and local activity present) protects their purity, and the
modelling stage should expect to work with sparse interaction
signals.

## Manual review

The Spelthorne Reform piece extracts the full national-to-local
chain correctly (momentum + local office + ward targeting = the one
connector article); mixed articles carry defensible dual scores;
the Davey home-counties piece lands as mixed with both scores >=
0.5 - the boundary case handled as designed. No unsupported
geographic assumption found.

## Verdict

The relevance layer validates at pilot scale and is ready for
downstream temporal and representation analysis. With Step 8, all
EIGHT Phase 6 layers are pilot-validated. Full-corpus runs await
the budget conversation. No prediction or embedding stages were
started.
