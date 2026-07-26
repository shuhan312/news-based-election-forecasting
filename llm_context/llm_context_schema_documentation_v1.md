# LLM context extraction schema - documentation (v1.1)

Schema: `llm_context_schema_v1.json` | version `llm-context-v1.1-2026-07-26`
Status: design only - no LLM has been called, no article processed.

Revision note: v1.0 -> v1.1 incorporates the supervisor's full
variable list (eleven layers, 25-code issue taxonomy, party/candidate
context rows, council accountability, the Reform UK specialised
layer, geographic and leakage layers). No extraction record was ever
validated against v1.0, so no processed data is affected; the version
constant was still bumped because content changed.

## Why this schema exists

The research tests whether pre-election news context improves
prediction of winning party, vote share, vote-share change and seat
outcomes beyond historical election information - comparing
ward-local, Surrey-wide, regional and national coverage. Raw text
cannot enter a model directly, and a single sentiment number would
discard exactly the mechanisms of interest (who is blamed, over what
issue, with what claimed switching). This schema is the structured
middle layer: one JSON record per canonical article, every claim
grounded in a verbatim quote, every uncertainty representable.

Design principles: evidence-or-nothing (R1 verbatim check =
anti-hallucination gate); uncertainty is data (nullables,
`not_addressed` defaults, ambiguity notes); mechanisms not sentiment
(actor-directed context rows, switching fields, accountability
distinctions); no outcome prediction (consequence signals only);
versioned append-only contract (Stage M compatible).

## Layer reference

### Record header + `input`

Join keys and extraction context copied from the frozen layers:
title, source, author (nullable), `publication_datetime` (date-only
when no time is resolvable - a time is never invented), temporal
availability (Step 5 vocabulary), URL, `article_type` (news /
opinion / letter / live blog / listing / other - opinion pieces
behave differently as evidence), local/national axis, geographic
relevance, `election_id`, linked wards/candidates/parties (from the
collection metadata), `provenance_ref` into
`duplicate_mapping_layer_v1_provisional.csv`.

### 1. `event_context`

What happened, where, when, affecting which organisation/service;
`continuing_story` + `previous_related_events` (only as described IN
the article). Purpose: separates substantive events from procedural
notices and supports running-story analysis.

### 2. `issues` - taxonomy `issues-v1.1` (25 codes)

`council_finance, council_tax, roads_transport, planning_housing,
schools_send, social_care, waste_recycling, crime_policing,
environment_flooding, healthcare, local_business, immigration,
council_performance, candidate_party_conduct, scandal, protest,
service_closure, investment_funding,
local_government_reorganisation, candidate_selection_withdrawal,
resignation_defection, new_party_emergence, voter_switching,
anti_incumbent_sentiment, other`. Primary (nullable) + secondary.
Extension = new taxonomy version, never an edit.

### 3. `entities`

Parties, candidates, councils, wards, political organisations,
national leaders - with `mention_count`, `prominence`
(headline/lead/major/passing) and `directly_quoted`. Purpose: raw
salience features (who gets covered, how prominently).

### 4. `party_context` - one row per party

The per-party feature surface: overall context
(positive/neutral/negative/mixed), stance, blame/credit booleans,
competence and integrity portrayals (`not_addressed` default),
associated issue, quoted flag, `support_trajectory`
(gaining/losing/stable/not_indicated), `challenger_credibility`,
voter-switching discussion with origin/destination parties, and
0-1 local/electoral relevance scores. Purpose: these rows aggregate
into the party-level covariates the prediction models consume.

### 5. `candidate_context` - one row per candidate

Name, party, mentions, prominence, stance, blame/credit,
competence/integrity, main issue, quoted, credibility, momentum,
`protest_candidate`. Purpose: candidate-level signals for seat-level
outcomes.

### 6. `council_accountability`

The supervisor's three-way distinction kept as three fields:
`caused_by` (who created the problem), `responsible_for_fix` (who
must solve it), `electoral_beneficiary`/`electorally_damaged` (who
gains or loses politically) - plus controlling party, praised and
criticised actors, and explicit/implied/none blame and credit
assignments. Purpose: responsibility attribution is the classic
mechanism linking coverage to incumbent vote share.

### 7. `electoral_consequences`

Signals only, never forecasts: affected actor, direction, potential
benefit/damage, voter group, mechanism, and four boolean mechanism
signals (`voter_switching_signal`, `party_growth_decline_signal`,
`anti_incumbent_signal`, `challenger_emergence_signal`) with a
temporal horizon (immediate/short/medium/long/uncertain).

### 8. `reform_uk` - specialised layer

Tests whether coverage signals Reform UK emergence and local
conversion potential (coverage is never assumed to cause votes):
headline presence, candidate mention/quotes, local campaign
activity, policy mention, gaining-support and credible-challenger
descriptions, threat-to list, three switching flags
(Con/Lab/LD -> Reform), protest support, national momentum, local
organisational strength, 0-1 credibility and momentum scores.
Consistency is enforced by rule R6: `reform_uk_present: false`
forbids positive flags; any positive flag requires an evidence quote.

### 9. `geographic`

Level (ward_specific_local / surrey_wide / regional / national /
mixed), affected geography, wards mentioned, Surrey mention flag and
0-1 local/national relevance scores. Purpose: the four-arm
comparison (local / Surrey-wide / national / combined) rests on this
layer.

### 10. `leakage`

Publication and availability dates plus `contains_poll`,
`contains_prediction`, `contains_election_result` and a
`leakage_risk` grade (none/low/high/disqualifying). Purpose:
articles written after voting began, or containing results, are
identifiable at a glance; flag claims require evidence (R7).

### 11. Evidence and confidence (shared)

`evidence_span` (verbatim text >= 10 chars, optional offsets,
`from_title` flag) and `confidence` in [0,1] on every claim;
`extraction_status` and `review_status` on every record; R3 routes
any claim below 0.5 to mandatory review.

`frames` (economic / competence_governance / accountability /
conflict / public_service / identity_community / other) is retained
from the earlier specification as an optional layer - framing
differences between local and national outlets remain a study
dimension.

## Stage M compatibility

Validation is per-record against the pinned version constant. Future
Stage M articles validate against exactly this contract; already-
processed records are never re-touched; contract changes require a
new version file alongside this one.
