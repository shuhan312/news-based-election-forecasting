# News artifact lineage

This file prevents two valid but incompatible news pipelines from being treated
as one analysis.

## Release authority table

This table is the authority for the role of every committed feature release.
Release names identify different corpora, feature constructions or case-study
targets; they are not interchangeable aliases.

| Release | Corpus | Feature table | Role | Enters primary confirmatory model |
| --- | --- | --- | --- | --- |
| v1 | `news_collection/canonical_corpus_release_v1.json` (`canonical-news-v1-59d113bb9c28`) | `news_features/news_feature_table_v1.csv` + metadata | frozen pre-enrichment reference | Yes |
| v2 | `news_collection/canonical_corpus_release_v2.json` (`canonical-news-v2-81000bf38785`) | `news_features/news_feature_table_v2.csv` + metadata | enriched final confirmatory release, including 627 by-election articles | Yes |
| v3exp | `news_collection/e5_local_backlog_v3/canonical_corpus_release_v3exp.json` | `news_features/news_feature_table_v3exp.csv` + metadata | local-backlog extension used for Woking South local-arm fitting and sensitivity analysis | No |
| v3party | `news_collection/canonical_corpus_release_v2.json` | `news_features/news_feature_table_v3party.csv` + metadata | party-level content-attribution diagnostics built on the v2 corpus | No |
| Haslemere | `news_collection/haslemere_probe/canonical_corpus_haslemere.json` | `news_features/haslemere_probe/news_feature_table_haslemere.csv` + metadata | isolated post-unblinding exploratory case study | No |
| Woking South | `news_collection/woking_south_blind/canonical_corpus_woking_south.json` | `news_features/woking_south_blind_v1/news_feature_table_wokingsouth.csv` + metadata | isolated blind-transfer target | No |

## Primary confirmatory releases: v1 and v2

The final report preserves two compatible, frozen primary releases so the
effect of the by-election enrichment remains visible rather than silently
replacing the earlier analysis:

- **v1** is the frozen pre-enrichment reference.
- **v2** adds 627 by-election articles and is the enriched final confirmatory
  release.

Both tables use **election × party × period** grain and the same
supervisor-confirmed six non-overlapping windows plus six cumulative periods.
The v2 release extends the corpus and training cells without redefining the
frozen feature specification. The final report evaluates v1 and v2 side by
side; v2 supplies its main positive confirmatory results.

The v1 release id is also written into
`article_area_attribution_summary.json` and `feature_grain_diagnosis.json`,
which document the pre-enrichment corpus rather than the later v2 extension.

`PRODUCTION_NEWS_EVIDENCE_REGISTER.md` is the current human-readable result
register. `production_estimability_v1/estimability_report.json` records the
original estimability gate; the v2 metadata, frozen protocol and evidence
register record the enrichment that followed it. Where an older narrative
conflicts with these frozen artefacts, the release metadata and evidence
register take precedence.

## Final-report extensions

### v3exp: local-backlog extension

The v3exp feature table is built from
`news_collection/e5_local_backlog_v3/canonical_corpus_release_v3exp.json` and
written to `news_features/news_feature_table_v3exp.csv` with its metadata. It
is used by `local_v3_rerun_v1` and as the fitting table for the local arm of
the Woking South blind test. It is an explicitly named extension and does not
replace the v2 confirmatory release.

### v3party: party-level content attribution on corpus v2

The v3party table is not a new corpus release. It rebuilds the canonical v2
corpus with party-level content attribution enabled and writes
`news_features/news_feature_table_v3party.csv` with its metadata. It supports
issue and framing diagnostics, placebo specifications, Reform decomposition,
stance-volume analysis and Stage 1 party-sensitivity analysis. It does not
enter the v1/v2 primary confirmatory prediction.

### Haslemere: isolated exploratory case study

The Haslemere probe has its own corpus manifest,
`news_collection/haslemere_probe/canonical_corpus_haslemere.json`, and its own
feature table,
`news_features/haslemere_probe/news_feature_table_haslemere.csv`. It is a
post-unblinding exploratory case study and does not alter the primary
confirmatory conclusions.

### Woking South: isolated blind-transfer target

The Woking South blind test has its own corpus manifest,
`news_collection/woking_south_blind/canonical_corpus_woking_south.json`, and
target-election feature table,
`news_features/woking_south_blind_v1/news_feature_table_wokingsouth.csv`.
That table supplies news features for the target election; it is not a fitting
table. The combined and national arms are fitted on v2, while the local arm is
fitted on v3exp. This separation preserves the blind-transfer design.

## Historical pilot artifacts — removed from main, kept in commit history

An older 67-article, ward-level pilot chain once lived here:
`article_level_news_features.*`, `context_aggregated_features.*`,
`recency_weighted_features.*`, `missing_news_representation.*`,
`ward_party_election_features_v1/`, `feature_selection_v1/`,
`specification_coverage/` and `residual_feasibility/`, together with their build
and `run_*` code.

None of them were on the final-report reproduction path: the production engine
(`build_feature_table.py`) imported none of them, and no reported result cited
their output. They were **removed from `main`** so the final tree carries only
the reproducible final version; every byte remains recoverable from the git
commit history. Primary confirmatory modelling explicitly names v1 or v2.
Final-report extensions explicitly name v3exp, v3party or an isolated
case-study table; no release is silently substituted for another. Each table's
metadata records the corresponding `canonical_corpus_release_id` and manifest.

## Interpreting the local counts

- **120 local**: includes found in the main eligibility decision table only.
- **188 local**: local articles in the current usable canonical feature corpus.
- The difference comes from terminal include decisions recorded earlier in the
  pilot and validation streams.

These counts describe different funnel stages. The canonical manifest records
both so neither needs to be guessed or relabelled.
