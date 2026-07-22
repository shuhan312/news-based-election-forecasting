# news_collection/ — Raw News Collection artefacts

Version-controlled artefacts of the production Raw News Collection
stage. The corpus itself (records, raw HTML, raw API responses,
extracted text) lives in `data/raw/news/` and is deliberately not
committed; everything here exists so the corpus can be audited and
rebuilt.

| File | What it is |
|---|---|
| `query_inventory.csv` | The complete deterministic query inventory (2,495 queries, stages A–M). Regenerate with `python3 -m src.news_collection.build_query_inventory`. |
| `search_log.csv` | Append-only log: one row per executed search, including zero-result and failed searches (protocol §5.3). |
| `checkpoints/completed_queries.json` | Resumability: query IDs already executed; delete a query ID to force re-execution (which appends a new log row). |
| `collection_diagnostics.json` | Corpus statistics + schema re-validation results. Regenerate with `python3 -m src.news_collection.make_collection_report`. |
| `raw_news_collection_report.md` | The stage report: what ran, what it found, unresolved issues, recommendations. |

Run collection with:

```
python3 -m src.news_collection.run_collection --stage A|B|C|D|M
```

Code: `src/news_collection/` (schema, adapters, runner, CLI, inventory
builder, diagnostics). Design authority: `news_protocol/`.
