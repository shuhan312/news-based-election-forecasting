# LLM context extraction schema - documentation (v1)

Schema: `llm_context_schema_v1.json` | version `llm-context-v1.0-2026-07-26`
Status: design only - no LLM has been called, no article processed.

## Why this schema exists

The research question is whether pre-election news context improves
election prediction, comparing local Surrey coverage with national
political coverage. Raw text cannot enter a prediction model directly
and a single sentiment score would throw away exactly the signals the
question needs (who is criticised, over what issue, with what implied
electoral consequence). This schema defines the structured middle
layer: one JSON record per canonical article, every claim grounded in
a verbatim quote, every uncertainty represented rather than papered
over.

Design principles, each traceable to a requirement:

1. **evidence or it did not happen** - every LLM-derived claim
   carries an `evidence_span` quoted verbatim from the article.
   Validation fails a span that does not appear in the text, which is
   the structural defence against LLM hallucination.
2. **uncertainty is data** - `null` primary issue, `uncertain`
   directions, `ambiguity_notes` and confidence scores make "the
   article does not say" a recordable answer. Nothing forces the
   extractor to guess.
3. **no outcome prediction** - `electoral_consequences` captures what
   the ARTICLE implies (direction, mechanism, affected group), never
   a forecast of the election result. Prediction happens downstream
   with proper controls.
4. **versioned and append-only** - `schema_version` and
   `taxonomy_version` are pinned constants. Stage M articles arriving
   later validate against the same contract; changing the contract
   means a v2 schema, never a silent edit.

## Field reference

### Record header

| field | purpose |
|---|---|
| `schema_version` | pinned const - a record states what contract it satisfies |
| `article_id` / `canonical_article_id` | join keys back to the frozen duplicate mapping layer; only canonical records are extracted |
| `extraction_status` | `extracted` / `partial` / `failed` / `not_attempted` - the pipeline state, so coverage gaps are queryable |
| `review_status` | `unreviewed` / `human_reviewed` / `flagged` - low-confidence claims force `flagged` (rule R3) |

### `input` (extraction context, copied from frozen layers)

Carries what the extractor was shown and what downstream needs for
stratification: `title`, `source`, `publication_date`,
`temporal_availability_status` (Step 5 vocabulary - the leakage
gate), `geographic_scope`, `local_national` (the local-vs-national
comparison axis), `election_id`, `provenance_ref` (pointer into
`duplicate_mapping_layer_v1_provisional.csv`). All provenance, no new
judgement.

### `entities`

Who appears: `party`, `candidate`, `council`, `constituency_ward`,
`political_organisation`, `other`. Research purpose: party/candidate
mention counts and co-occurrence are the base features for the
coverage-vs-outcome analysis.

### `issues`

`primary_issue` (nullable - honest absence beats forced choice) plus
`secondary_issues`, all coded against **taxonomy `issues-v1.0`**
(16 codes below). Research purpose: issue salience comparison between
local and national coverage, and issue-party interaction signals.

Taxonomy v1.0 codes: `housing_planning`, `council_tax_finance`,
`transport_roads`, `education_schools`, `health_social_care`,
`environment_green_belt`, `crime_policing`, `local_economy_jobs`,
`national_economy`, `immigration`, `party_politics_campaigning`,
`governance_competence`, `scandal_integrity`, `community_identity`,
`national_politics_general`, `other` (with free-text
`issue_other_label`). Extension procedure: new codes are added in a
new `issues-vX.Y` taxonomy version; existing records keep their
version stamp and are never rewritten.

### `stances`

Target-directed judgements: who/what is supported or criticised
(`support` / `criticism` / `neutral` / `mixed`), with optional tonal
`sentiment`. The specification's warning is honoured structurally:
there is no article-level sentiment number to reduce to - stance
without a target is unrepresentable.

### `frames`

How the story is told: `economic`, `competence_governance`,
`accountability`, `conflict`, `public_service`,
`identity_community`, `other`. Multiple frames expected. Research
purpose: framing differences between local and national outlets are
a study dimension in their own right.

### `credit_blame`

`actor` + `attribution` (`credit` / `blame` / `mixed`) +
`action_event`. Research purpose: attribution of responsibility is
the classic mechanism linking coverage to incumbent vote share -
kept separate from stance because a critical article can still
credit an actor for a specific action.

### `electoral_consequences`

The article's implied signals: `affected_actor`, `direction`
(`favourable` / `unfavourable` / `unclear`), optional `voter_group`
and `mechanism`, and a `temporal_horizon`
(`immediate` / `short_term` / `medium_term` / `long_term` /
`uncertain`). Explicitly NOT an election forecast.

### `relevance`

`local_surrey` / `national_with_local_link` / `national_only` /
`uncertain`, plus `linked_surrey_area` naming the division/ward when
applicable. Research purpose: the local-vs-national arm split rests
on this field being evidence-backed per article.

### `ambiguity_notes`

Per-section free-text reasons for what could not be determined. The
representation of missing information is a required capability, not
an error state.

### `evidence_span` (shared definition)

`text` (verbatim, >= 10 chars) + optional `char_start`/`char_end`
offsets + `from_title` flag. Validation rule R1 rejects any span not
found verbatim in the stated source text; R2 rejects offsets that do
not slice to the text.

### `confidence` (shared definition)

Number in [0,1] reported by the extractor per claim. Rule R3 binds
`< 0.5` to mandatory review routing, so low confidence can never be
silently consumed downstream.

## Stage M compatibility

Validation is per-record against a pinned schema version: articles
arriving from the ongoing Stage M sweep validate against exactly this
contract, and already-processed records are never re-touched. Schema
changes require `llm_context_schema_v2.json` alongside (the Phase 5
freeze-guard convention applies to schema files too).
