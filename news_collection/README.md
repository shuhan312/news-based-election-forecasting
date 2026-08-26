# news_collection/ — Raw News Collection artefacts

Version-controlled artefacts of the production Raw News Collection
stage. The corpus itself (records, raw HTML, raw API responses,
extracted text) lives in `data/raw/news/` and is deliberately not
committed; everything here exists so the corpus can be audited and
rebuilt.

| File | What it is |
|---|---|
| `query_inventory.csv` | The frozen deterministic plan: 2,470 queries across stages A–H, M and M2. It is regenerated from committed election inputs, the 17-division sample and the committed final geographic crosswalk. |
| `search_log.csv` | Append-only log: one row per executed search, including zero-result and failed searches (protocol §5.3). |
| `query_lineage_v1.csv` | Four superseded `-ward` slug query IDs and their corrected replacements, so every historical search-log row remains joinable. |
| `checkpoints/completed_queries.json` | Resumability: query IDs already executed (local-only, gitignored — it is runtime state, fully derivable from `search_log.csv`); delete a query ID to force re-execution (which appends a new log row). |
| `collection_diagnostics.json` | Corpus statistics + schema re-validation results. Regenerate with `python3 -m src.news_collection.make_collection_report`. |
| `../outputs/leakage_provenance_audit_v1.json` | Machine-readable assertions over query lineage, final article chronology, duplicate control, outcome isolation and Reform/UKIP identity. |

Run collection with:

```
python3 -m src.news_collection.run_collection --stage A|B|C|D|E|F|G|H|M|M2
```

Code: `src/news_collection/` (schema, adapters, runner, CLI, inventory
builder, diagnostics). Design authority: `news_protocol/`.

The inventory includes the complete 19-by-election plan. At the frozen release
cut-off, 704 planned E/G/H queries had not been executed (E 244, G 324, H 136).
They are recorded as unexecuted, not converted into zero-result searches and
not used to claim complete coverage. Rebuild the assertion with
`python3 -m src.audit_leakage_provenance`.

## Cleaning, deduplication and eligibility artefacts

This folder is the shared home for the whole corpus-construction span, not just
collection: the cleaning (Phase 4, `src/normalisation/`), deduplication
(Phase 5, `src/dedup/`) and eligibility-screening stages all write their frozen
decision records and summaries here too. That is why the directory is large — one
committed record per stage decision, so the corpus can be audited without the
article text. The per-article text layers themselves
(`*_articles_v1.jsonl`) are gitignored; the decision records that reference them
are committed.

| File(s) | What it is |
|---|---|
| `character_normalisation_log_v1.csv`, `*_review_queue_v1.csv` | Phase 4 cleaning logs and the human-review queues they raised |
| `article_version_families_v1_provisional.*`, `article_version_relationships/resolutions/temporal_availability_v1_provisional.csv` | Phase 5 version linking: which articles are updates of which, and when each was available |
| `canonical_article_mapping_v1_provisional.csv`, `canonical_resolutions_v1_provisional.csv`, `duplicate_cluster_conflicts/review_queue_v1_provisional.csv` | Phase 5 deduplication: each duplicate mapped to its canonical copy, plus the clusters flagged for review |
| **`canonical_corpus_release_v1.json`, `canonical_corpus_release_v2.json`** | The frozen canonical corpus — the one-per-news-item article universe the feature layer reads (`news_features/ARTIFACT_LINEAGE.md` says which is production) |
| `corpus_eligibility_decisions.csv`, `byelection_eligibility_decisions*.csv`, `byelection_llm_v2.csv`, `*_review*.csv` | Eligibility screening: the keep/drop decision for each article, including the by-election and case-study families |

Naming: `_v1_provisional` marks a stage's provisional freeze; `_review_queue`
files are the rows sent for human review. See `REPO_MAP.md` for how the canonical
corpus flows into the feature and modelling layers.
