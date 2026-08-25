# `src/news_features/` — the feature-construction code

Pipeline layer 4 (news side): turn the labelled article corpus into the
election–party–window **feature tables** the model joins against, with a leakage
audit. This directory is **code only**. The tables and frozen evidence it
produces live at the repository root in
[`news_features/`](../../news_features/README.md); the labelled corpus it reads
is in `news_collection/` and `llm_context/`.

## The Phase 7 pipeline

The feature layer is built in ordered steps, one runner each:

```text
run_alignment            (1) align each article to the entities (party / area) it concerns
run_time_windows         (2) assign each article to a pre-election time window
run_scope_classification (3) classify local vs national scope
run_article_features     (4) build the article-level feature layer
run_context_aggregation  (5) aggregate article-level features to election × party × period
run_recency_weighting    (6) add the recency-weighted feature layer
run_missing_news         (7) build the expected-observation grid and represent missing news explicitly
```

`build_feature_table.py` assembles the extracted article records into the news
feature table the model joins; `build_feature_table_v2.py`,
`build_feature_table_v3exp.py`, `build_feature_table_v3party.py` and
`build_feature_table_v4e5local.py` build the labelled variants (the production
one is named in `news_features/ARTIFACT_LINEAGE.md`).

## Key modules

| Module | Role |
| --- | --- |
| `run_alignment.py`, `run_time_windows.py`, `run_scope_classification.py` | Steps 1–3: alignment, time windows, scope |
| `run_article_features.py`, `article_features.py` | Step 4: the article-level feature layer |
| `run_context_aggregation.py`, `context_aggregation.py` | Step 5: aggregation to election × party × period |
| `run_recency_weighting.py`, `recency_weighting.py` | Step 6: recency weighting |
| `run_missing_news.py`, `missing_news.py` | Step 7: missing-news representation |
| `build_feature_table*.py` | The production feature table and its labelled variants |
| `diagnose_article_area_attribution.py`, `diagnose_feature_grain.py` | Grain and attribution diagnostics |
| `build_haslemere_probe_features.py`, `build_woking_south_blind_features.py` | Case-study feature builds (kept separate for blindness) |
| `build_news_workbook.py` | The research workbook export |

## Running and outputs

The layers are built in order from the frozen LLM output in `llm_context/`; each
runner reads the layer above and writes into the repository-root `news_features/`
directory. From the repository root:

```bash
python3 -m src.news_features.run_alignment
python3 -m src.news_features.run_time_windows
python3 -m src.news_features.run_scope_classification
python3 -m src.news_features.run_article_features
python3 -m src.news_features.run_context_aggregation
python3 -m src.news_features.run_recency_weighting
python3 -m src.news_features.run_missing_news
```

`build_feature_table.py` then assembles the `news_feature_table_*.csv` tables.
Unlike collection, this stage is **deterministic**: it reads frozen files
(`llm_context/`, `news_collection/`), so re-running reproduces the same tables
bit-for-bit. Outputs — the feature tables, the `article_level_*` and
`context_aggregated_*` layers, and their audits and data dictionaries — all land
in the root `news_features/` directory (see its README).

## Discipline

Predictor and outcome columns are kept separate, and missing news is represented
explicitly rather than filled — a party–period with no coverage is recorded as
observed-zero-coverage, not as a missing row. Every feature table ships with a
leakage audit and a data dictionary in `news_features/`. See `REPO_MAP.md` for
how the tables feed Stage 2 modelling.
