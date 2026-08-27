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

Naming: `_v1_provisional` marks a stage's provisional freeze — the state the
production corpus shipped with; `_review_queue` files are the rows sent for
human review; `*_resolutions` files record the human answers.

## Complete artefact index by pipeline stage

### Collection provenance (Layer 1B)

| File(s) | What it is |
|---|---|
| `query_inventory.csv`, `query_lineage_v1.csv`, `search_log.csv` | the frozen plan, the slug-correction lineage, and the append-only execution log (see above) |
| `sidecar_archive_manifest_20260726.csv` | manifest of the archived sidecar copies retained for collected pages |
| `guardian_geographic_relevance_flags.csv`, `serpapi_domain_relevance_flags.csv` | QA flags from the two collection audits (`src/news_collection/audit_*.py`) |
| `pdf_date_recovery.csv` | date evidence recovered for the records whose stored pages lacked it |

### Date resolution (chronology defence)

| File(s) | What it is |
|---|---|
| `date_resolution_log.csv`, `date_resolution_log_v2.csv` | the per-article date-resolution passes read by `build_effective_dates.py` |
| `date_conflicts_queue.csv` | the human adjudication queue for conflicting date evidence |

### Cleaning (Phase 4, `src/normalisation/`)

| File(s) | What it is |
|---|---|
| `normalisation_input_manifest_v1.csv/.json`, `normalisation_input_records_v1.jsonl`, `normalisation_input_review_queue_v1.csv`, `normalisation_input_summary_v1.md` | step 1: the locked eligible population and text-source selection |
| `html_cleaning_log_v1.csv` + review queue | step 2: HTML cleaning decisions |
| `character_normalisation_log_v1.csv` + review queue | step 3: character normalisation decisions |
| `structure_normalisation_log_v1.csv` + review queue, `structure_review_resolutions_v1.csv` | step 4: structure normalisation and its human resolutions |
| `text_boundary_log_v1.csv` + review queue | step 5: title/body boundary resolution |
| `text_quality_results_v1.csv`, `text_quality_resolutions_v1.csv`, `text_quality_review_queue_v1.csv`, `text_quality_summary_v1.md` | step 6: text-quality verdicts and human resolutions |
| `missing_text_resolutions_v1.csv`, `language_review_resolutions_v1.csv` | human resolutions for missing-body and language-rule cases |
| `normalised_text_audit_v1_provisional.csv`, `normalised_text_manifest_v1_provisional.json`, `normalised_text_quality_report_v1_provisional.md`, `normalised_text_review_queue_v1_provisional.csv` | step 7: the final audited text layer (manifest hashes the git-ignored text files) |

### Deduplication (Phase 5, `src/dedup/`)

One family per step, in step order; each family = clusters/pairs + review
queue + resolutions/summary as applicable.

| Family | What it decides |
|---|---|
| `exact_duplicate_*_v1_provisional` | byte-identical content duplicates |
| `url_groups` / `url_duplicate_mapping` / `url_resolution_*_v1_provisional` | canonical URL resolution |
| `near_duplicate_*_v1_provisional` | near-duplicate detection |
| `syndication_*_v1_provisional` | syndicated-copy identification |
| `article_version_*_v1_provisional` | version linking and temporal availability |
| `duplicate_cluster_*` and `validated_duplicate_*_v1_provisional` | cluster validation |
| `canonical_article_mapping` / `canonical_resolutions` / `canonical_review_queue` / `canonical_selection_report_v1_provisional` | one canonical article per news item |
| `duplicate_mapping_layer/audit/manifest/review_queue_v1_provisional` | the consolidated, provisionally frozen mapping layer the release reads |

### Eligibility screening and the LLM classifier chain

| File(s) | What it is |
|---|---|
| `manual_review_sample.csv`, `manual_review_decisions.csv`, `manual_review_kappa_subset.csv` | the stratified human-review pilot (168 articles), its decisions and the double-coded kappa subset |
| `manual_review_llm_pilot.csv`, `llm_v1_disagreement_audit.csv` | the v1 classifier pilot on the same articles and its row-level disagreement audit |
| `llm_validation_sample.csv`, `manual_review_llm_v2_validation.csv` | the fresh 128-article blind sample and the frozen v2 run on it |
| `manual_review_llm_v2_corpus.csv`, `manual_review_llm_v2_local_extension.csv` | the frozen v2 batch over the remaining corpus and over the local backlog |
| `llm_v2_corpus_batch_state.json`, `llm_v2_byelection_batch_state.json`, `llm_v2_local_extension_batch_state.json`, `llm_v2_local_extension_dry_run.json` | batch ids and state for each frozen v2 run |
| `second_review_queue.csv`, `full_corpus_review.csv`, `corpus_eligibility_decisions.csv` | the escalation queue, the full-corpus review sheet, and the final per-article decisions |
| `e5_hard_disagreement_review_data.json`, `e5_local_manual.csv`, `e5_local_risk_review_plan.json`, `e5_local_risk_review_evaluation.json`, `e5_local_review_queue_round2_summary.json` | the E5 exclusion-rule audit: the 48 hard disagreements, the manual local review, and the blind risk-based review plan and its evaluation |

### Frozen releases and case studies

| File(s) | What it is |
|---|---|
| `canonical_corpus_release_v1.json`, `canonical_corpus_release_v2.json` | the frozen article universes the v1/v2 feature tables read |
| `byelection_review.csv`, `byelection_eligibility_decisions.csv`, `byelection_eligibility_decisions_e5human_v1.csv`, `byelection_llm_v2.csv`, `byelection_second_review_queue.csv` | the by-election eligibility family behind the v2 enrichment |
| `byelection_walkthrough_v1/` | the on-paper walkthrough of the by-election corpus through all six stages, with its findings |
| `haslemere_probe/` (10 files) | the Haslemere replication: its corpus, dates, eligibility, frozen v2 run and second-review resolutions, plus the non-news trail catalogue |
| `woking_south_blind/` (10 files) | the Woking South blind test: same stage families on sealed paths |
| `e5_local_backlog_v3/` (3 files) | the post-unblinding v3exp lineage: the reviewer-admitted decisions and the v3exp corpus release the Woking South local arm reads |

See `REPO_MAP.md` for how the canonical corpus flows into the feature and
modelling layers.
