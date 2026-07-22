# Legacy news scripts (pre-supervisor-brief)

These four scripts are the exploratory news work written **before** the
supervisor's news-extraction brief was received. They are kept for the
project record but are **superseded** and must not be extended:

| Script | What it did | Superseded by |
|---|---|---|
| `fetch_newsapi.py` | Early NewsAPI pulls (free tier) | `news_protocol/` audit showed the tier reaches none of the election windows; NewsAPI is dormant in the new pipeline |
| `fetch_guardian.py` | Ad-hoc Guardian pulls into `data/processed/guardian_articles.csv` | `src/news_collection/` GuardianAdapter, driven by the versioned query inventory |
| `filter_articles.py` | Early keyword filtering | Article eligibility now belongs to the E1–E10 stage defined in `news_protocol/article_eligibility_rules.md` (not yet run) |
| `build_news_features.py` | Monthly news feature aggregation | Feature engineering is deferred until after date resolution, eligibility, cleaning and deduplication, per the pipeline stages |

The authoritative news pipeline is: `news_protocol/` (design + rules)
→ `src/news_collection/` (production collection) → downstream stages.
Outputs of these legacy scripts (e.g. `data/processed/guardian_articles.csv`,
`news_features_monthly.csv`) are pre-brief artefacts and are not inputs
to the new pipeline.
