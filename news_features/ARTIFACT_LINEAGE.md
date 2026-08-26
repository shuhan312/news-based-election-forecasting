# News artifact lineage

This file prevents two valid but incompatible news pipelines from being treated
as one analysis.

## Final-report releases

The final report preserves two compatible, frozen releases so the effect of
the by-election enrichment remains visible rather than silently replacing the
earlier analysis:

| Release | Canonical corpus | Feature table | Role |
| --- | --- | --- | --- |
| v1 | `news_collection/canonical_corpus_release_v1.json` (`canonical-news-v1-59d113bb9c28`) | `news_feature_table_v1.csv` + metadata | frozen pre-enrichment reference |
| v2 | `news_collection/canonical_corpus_release_v2.json` (`canonical-news-v2-81000bf38785`) | `news_feature_table_v2.csv` + metadata | enriched confirmatory release including 627 by-election articles |

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
commit history. Final-report modelling names either the v1 or v2 table
explicitly and verifies its `canonical_corpus_release_id`.

## Interpreting the local counts

- **120 local**: includes found in the main eligibility decision table only.
- **188 local**: local articles in the current usable canonical feature corpus.
- The difference comes from terminal include decisions recorded earlier in the
  pilot and validation streams.

These counts describe different funnel stages. The canonical manifest records
both so neither needs to be guessed or relabelled.
