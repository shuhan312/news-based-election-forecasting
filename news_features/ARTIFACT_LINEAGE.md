# News artifact lineage

This file prevents two valid but incompatible news pipelines from being treated
as one analysis.

## Current production release

The current article universe is
`news_collection/canonical_corpus_release_v1.json`. Its release id is written
into:

- `article_area_attribution_summary.json`;
- `feature_grain_diagnosis.json`; and
- `news_feature_table_v1_metadata.json`.

The production feature table is `news_feature_table_v1.csv`, at
**election × party × period** grain. It uses the supervisor-confirmed six
non-overlapping windows plus six cumulative periods.

## Historical pilot artifacts — do not use for the final model

The following files form one older 67-article pilot chain:

- `article_level_news_features.csv` / `.parquet`;
- `context_aggregated_features.*`;
- `recency_weighted_features.*`;
- `missing_news_representation.*`;
- `ward_party_election_features_v1/`; and
- `feature_selection_v1/`.

They remain in the repository for audit and reproduction. Their ward-level
shape does not make them a full-corpus product: the article feature dictionary
itself records “207 rows / 67 articles / 171 columns at pilot scale”.

The two legacy build commands now require `--allow-legacy-pilot`. This is an
intentional safety gate, not a deletion. The next model-fitting step must read
the production table and verify its `canonical_corpus_release_id`; it must not
select features from `feature_selection_v1`.

## Interpreting the local counts

- **120 local**: includes found in the main eligibility decision table only.
- **188 local**: local articles in the current usable canonical feature corpus.
- The difference comes from terminal include decisions recorded earlier in the
  pilot and validation streams.

These counts describe different funnel stages. The canonical manifest records
both so neither needs to be guessed or relabelled.
