# News Scope Classification Audit

Phase 7, Step 3. Version: `news-scope-v1.0-2026-07-27`
Inputs (read-only, hash-verified): frozen context layer
`context-cards-v1.0-pilot67`, Step 1 alignment layer.

## Methodology

The content-based scope judgement was already extracted in Phase 6
Step 8 - per article, from article text alone, with a verbatim
evidence span, mention flags, geographic entities, issue scope, the
two 0-1 relevance scores and a confidence score - and is frozen.
This step maps that frozen judgement deterministically onto the
required five-category scheme:

| frozen geographic_scope | this layer |
|---|---|
| ward_specific_local | ward_specific_local |
| surrey_wide | surrey_wide_local |
| regional | regional |
| national | national_political |
| mixed_national_local | mixed_local_national |

Evidence, scores and confidence are carried over verbatim, never
recomputed. No LLM call, zero cost. Articles whose frozen relevance
record is quarantined (1) or missing (1) are classified "uncertain"
and flagged - never forced. The publication source plays no role in
the mapping; the collection arm rides along as provenance only
(decision D2).

## Counts by category (67 articles)

| scope | articles |
|---|---|
| national_political | 48 |
| ward_specific_local | 7 |
| mixed_local_national | 6 |
| surrey_wide_local | 3 |
| uncertain | 2 |
| regional | 1 |

Issue scope: national 48, both 8, local 7, uncertain 4 (the 2
uncertain records plus 2 frozen nulls).

Local/national distribution: 10 local (ward + surrey-wide), 48
national, 6 mixed, 1 regional, 2 uncertain. The national dominance
reflects the pilot draw (43 of 67 came through the national
collection arm) and the Guardian-heavy sample - a property of the
sample, not of Surrey news.

## Source is not the rule - structural evidence

One source spreads across five categories: guardian_api articles
classify as national_political 48, mixed 4, surrey_wide_local 1,
regional 1, uncertain 2. Conversely surreylive (a local outlet)
still produces 2 mixed articles. Seven local-arm articles classify
as national_political on content (the D2 arm/content mismatch,
12% at pilot scale) and are preserved with their arm label rather
than corrected - both facts are tested in the suite.

## Ambiguous cases

* 6 mixed_local_national articles - genuinely dual-scope on
  content, each with both relevance scores recorded.
* 7 dual-relevance articles (both scores >= 0.4), of which some
  classify national_political with a strong Surrey echo - the
  continuous scores preserve what the hard category flattens;
  downstream features should use the scores, not only the label
  (this is why decision D2 keeps both).
* 6 flagged records: the 2 uncertain plus 4 low-confidence frozen
  judgements - all in the review pool, none force-classified.

Full difficult-case walkthrough in `news_scope_error_analysis.md`.

## Integrity

Every record passes rules L1-L5 (one valid scope; scores in [0,1];
evidence + confidence mandatory for classified records; uncertain
records must carry no fabricated evidence and must be flagged).
Rebuild is byte-identical; the frozen layer hash is verified before
and after. 9 new tests; full suite 530 passed.
