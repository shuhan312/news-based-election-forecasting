# Article-level Feature Dictionary

Version `article-features-v1.0-2026-07-27`. Unit of observation:
**article x election x geographic target x focal party** (one row
per validated combination; 207 rows / 67 articles / 171 columns at
pilot scale). Files: `article_level_news_features.parquet` + `.csv`
(identical content; CSV byte-deterministic).

Conventions used below: **bin** = {0,1} integer, **score** = float
in [0,1], **cat** = categorical string, **cnt** = non-negative
integer. Every group has a `*_status` column with the five
missing-value states: `extracted` (values real), `confirmed_absent`
(layer valid, focal actor absent - zeros are genuine), 
`no_focal_party` (group needs a focal party, row has none),
`not_applicable` (group does not apply to this focal party),
`quarantined` (frozen record failed validation - extraction
failure, values None), plus `not_extracted` (field never in the
frozen contract). **None is never silently zero.** Evidence text
never enters these files: rows carry confidence plus availability,
and every span remains addressable in the frozen layer by
(article_id, layer, target name). Intended later aggregation is
noted per group; none of it is performed in this step.

## 1. Identity and provenance

| feature | type | source / rule |
|---|---|---|
| article_id, canonical_article_id | id | frozen card metadata; equal for every row (only canonical articles contribute; enforced by assertion + test) |
| election_id | id | Step 1 election link (collection window) |
| geographic_target_id | id | resolved Step 1 ward link (`ELECTION:Ward`), else `ELECTION:ELECTION_WIDE`; ward targets exist only where a validated link exists - national articles are never fanned out |
| geographic_target_level | cat | ward \| election_wide |
| focal_party_id / focal_party_name | id/cat | resolved Step 1 party link (registry ID + standardised name); None = article had no resolved Surrey party |
| candidate_id | id | first resolved Step 1 candidate link, else None |
| publication_id / source_type | cat | source name / collection arm (provenance only, decision D2) |
| article_presence | bin | constant 1 - the aggregation primitive |
| full_text_availability | cat | `valid_full_text` (corpus construction guarantees it) |
| extraction_confidence | score | 1 - review_required/total_claims from the Step 10 audit summary (share of the card's claims not needing review) |
| human_review_status / flagged_layer_count | cat/cnt | `flagged` if any frozen layer flagged the article |
| unresolved_ward_mentions / unresolved_party_mentions | cnt | Step 1 unresolved counts - the spec's unresolved-alignment indicators |
| features_version / frozen_dataset_version | id | version stamps |

Aggregation intent: keys + presence become counts per
ward-party-election cell; extraction_confidence supports
quality-weighted sensitivity runs.

## 2. Political mentions (focal party) - `mention_status`

| feature | type | source / rule |
|---|---|---|
| party_mentioned | bin | 1 by construction (focal set = resolved mentions); 0 never occurs on party rows |
| party_mention_count (+ _status) | cnt | **not_extracted** - the frozen contract records party presence per layer, not string counts (candidate rows do carry counts) |
| headline_party_mention | bin | normalised focal name variants found in the article title (deterministic string check) |
| party_prominence_score | score | share of the party-bearing frozen layers (entity, stance, attribution, consequence) carrying a row for the focal party |
| party_directly_quoted | bin | entity layer party_context.directly_quoted; None if no party_context row |
| candidate_mentioned / candidate_mention_count | bin/cnt | frozen candidate_context rows whose party or name resolves to the focal party; counts summed |
| candidate_prominence_level / _score | cat/score | frozen enum, scored headline 1.0 / major .75 / secondary .5 / passing .25 (mapping documented, raw kept) |
| candidate_directly_quoted | bin | any matched candidate row quoted |

Aggregation intent: mention/prominence averages per cell.
Cross-party isolation: a row only ever reads rows whose actor name
resolves to its own focal party_id (tested).

## 3. Geography and scope - `scope_status`

ward_specific_local / surrey_wide_local / regional /
national_political / mixed_local_national `_indicator` (bin,
one-hot of the Step 3 label), scope_classification (cat),
valid_ward_link_indicator (bin, row-level), 
unresolved_geography_indicator (bin: scope uncertain OR article had
unresolved ward mentions), local/national_relevance_score (score,
carried verbatim from the frozen layer), scope_confidence (score).
Aggregation intent: scores are the D2 continuous weights; labels
stratify reporting.

## 4. Issues and events - `issues_status`, `event_status`

primary_issue (cat, frozen taxonomy v1.3 codes), 
primary_issue_confidence (score), issues_taxonomy_version (id),
`sec_issue_<code>` x28 (bin multi-hot over exactly the frozen
codes - no new vocabulary, tested), poll_indicator (bin: any issue
code in {voter_switching, polling}), event_type (cat, frozen enum),
continuing_story (cat, group 9), election_prediction_indicator
(**not_extracted** - never a frozen field; honest None), 
election_result_indicator (bin from the deterministic Step 2 flag -
decision D3: flagged, exclusion is a modelling switch).

## 5. Stance and evaluation (focal) - `stance_status`

positive/neutral/negative/mixed_stance (bin one-hot of the stance
layer row for the focal party; stance_raw keeps the enum),
praise_indicator / criticism_indicator (bin, entity layer's own
credit/blame booleans - deliberately a different source from group
6's directed attributions), competence_positive/negative +
competence_raw, integrity_positive/negative + integrity_raw
(perception enums; `mixed` keeps both bins 0 and lives in the raw
column), stance_confidence (score), stance_evidence_available
(bin). Aggregation intent: net-negativity rates per cell.

## 6. Framing and attribution - `framing_status`, `attribution_status`

primary_frame (cat) + primary_frame_confidence + `frame_<cat>` x16
(bin multi-hot over the frozen 16-frame enum). blame_received /
credit_received (+ _count), blame_assigned / credit_assigned,
responsibility_unclear - received = focal is attribution TARGET,
assigned = focal is attribution SOURCE; the two directions never
mix (spec requirement).

## 7. Electoral context (focal) - `consequence_status`

potential_benefit / potential_damage / mixed_or_unclear_impact
(bin, from consequence-layer direction enum), growth_signal
{support_growth}, decline_signal {support_decline},
credible_challenger_signal {challenger_emergence,
increased_credibility}, anti_incumbent_signal
{incumbent_vulnerability or mechanism anti_incumbent_sentiment},
voter_switching_signal {voter_switching_possibility, mechanism
voter_switching_signal, or entity-layer switching discussion}
(enum-to-indicator mappings fixed here, no new vocabulary),
switch_from/to_party_id (registry IDs resolved from the entity
layer's switching endpoints), consequence_confidence (score, max
over the focal actor's rows). These are extracted context signals,
not predictions.

## 8. Reform UK block - `reform_status`

18 `reform_*` columns mapped field-for-field from the frozen
reform_uk section (in_headline, candidate_mentioned/quoted,
local_campaign_activity, policy_mentioned, gaining_support,
credible_challenger, threat_to_conservative/labour/
liberal_democrats, con/lab/ld_to_reform_switching,
protest_anti_incumbent, national_momentum,
local_organisational_strength (cat), credibility_score,
momentum_score, reform_confidence). Populated ONLY on Reform UK
focal rows; `not_applicable` (all None) on every other focal party
including UK Independence Party - Reform and UKIP are distinct
registry parties and never share a row (tested).

## 9. Temporal - `temporal_llm_status`

publication_date, polling_date (date; date-only precision as
frozen), days_before_polling (cnt, >0 always - post-polling rows
cannot exist, tested), individual_time_window (cat, six frozen
windows), `cum_previous_*` x6 (bin, nested memberships),
impact_horizon, persistence, continuing_story, expected_decay (cat,
frozen temporal layer; None + quarantined when that record failed).
No recency weighting is computed in this step.
